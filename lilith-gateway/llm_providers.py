#!/usr/bin/env python3
"""
🜏 Lilith LLM Provider Router — Unified multi-LLM abstraction layer.

Routes requests to any provider: NVIDIA NIM, OpenAI, Anthropic, Google Gemini,
Groq, OpenRouter, Together AI, and local Ollama — all through a single
OpenAI-compatible interface.

Usage:
  from llm_providers import get_provider, list_providers, chat, models

  # List all configured providers
  for p in list_providers():
      print(p.name, p.status())

  # Chat with any model
  response = chat("nvidia", "deepseek-ai/deepseek-v4-flash",
                  [{"role": "user", "content": "Hello!"}])

  # List available models from a provider
  for m in models("nvidia"):
      print(m["id"])

  # Provider auto-detection — no model name needed
  response = chat(auto=True, messages=[{"role": "user", "content": "Hi"}])
"""
from __future__ import annotations

import json
import os
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Generator
from urllib.error import URLError
from urllib.request import Request, urlopen

# ── Types ──

Message = dict[str, Any]  # {"role": str, "content": str}
ChatResponse = dict[str, Any]
StreamChunk = dict[str, Any]

# ── Constants ──

LILITH_DIR = Path.home() / ".lilith"
PROVIDER_CONFIG_PATH = LILITH_DIR / "providers.json"
CACHE_DIR = LILITH_DIR / "model-cache"

DEFAULT_PROVIDER_ORDER = [
    "nvidia",
    "openai",
    "anthropic",
    "google",
    "groq",
    "openrouter",
    "together",
    "ollama",
]

# ── Config Management ──


def load_provider_config() -> dict:
    """Load provider config (API keys, preferences)."""
    if PROVIDER_CONFIG_PATH.exists():
        try:
            return json.loads(PROVIDER_CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"providers": {}, "default_provider": None, "provider_order": DEFAULT_PROVIDER_ORDER}


def save_provider_config(cfg: dict):
    """Save provider config."""
    LILITH_DIR.mkdir(parents=True, exist_ok=True)
    PROVIDER_CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def get_api_key(provider_name: str) -> str | None:
    """Get API key for a provider — checks env vars first, then config file."""
    # Env var mapping
    env_map = {
        "nvidia": "NVIDIA_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "together": "TOGETHER_API_KEY",
        "ollama": None,  # no key needed
    }
    env_key = env_map.get(provider_name)
    if env_key and os.environ.get(env_key):
        return os.environ[env_key]

    # Check config file
    cfg = load_provider_config()
    provider_cfg = cfg.get("providers", {}).get(provider_name, {})
    key = provider_cfg.get("api_key")
    if key:
        return key

    return None


def set_api_key(provider_name: str, key: str):
    """Save API key to config file and set env var."""
    cfg = load_provider_config()
    if provider_name not in cfg["providers"]:
        cfg["providers"][provider_name] = {}
    cfg["providers"][provider_name]["api_key"] = key
    save_provider_config(cfg)

    # Also set env var for current session
    env_map = {
        "nvidia": "NVIDIA_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "together": "TOGETHER_API_KEY",
    }
    if provider_name in env_map:
        os.environ[env_map[provider_name]] = key

    print(f"  ✅ API key set for {provider_name}")


# ── Provider Base ──


@dataclass
class ProviderInfo:
    """Static info about a provider."""
    name: str
    display_name: str
    base_url: str
    env_key_name: str | None
    default_model: str
    requires_key: bool
    free_tier: bool
    rpm_limit: int | None
    description: str
    models_url: str | None = None
    headers: dict = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base for an LLM provider."""

    def __init__(self, info: ProviderInfo):
        self.info = info
        self._api_key: str | None = None

    @property
    def api_key(self) -> str | None:
        if self._api_key:
            return self._api_key
        self._api_key = get_api_key(self.info.name)
        return self._api_key

    def status(self) -> dict:
        """Return connection status."""
        key = self.api_key
        if self.info.requires_key and not key:
            return {"configured": False, "healthy": False, "error": "No API key configured"}
        # Try a lightweight check
        try:
            self._request("GET", "/models", timeout=5)
            return {"configured": True, "healthy": True}
        except Exception as e:
            return {"configured": True, "healthy": False, "error": str(e)[:80]}

    def _request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        timeout: int = 30,
        headers: dict | None = None,
    ) -> tuple[int, str]:
        """Make an HTTP request to the provider."""
        url = self.info.base_url.rstrip("/") + path
        req_headers = {"Content-Type": "application/json"}
        req_headers.update(self.info.headers)

        if self.api_key:
            req_headers["Authorization"] = f"Bearer {self.api_key}"

        if headers:
            req_headers.update(headers)

        body = json.dumps(data).encode() if data else None
        req = Request(url, data=body, headers=req_headers, method=method)

        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8")
        except URLError as e:
            if hasattr(e, "code") and e.code:
                body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
                return e.code, body
            return 0, str(e.reason)
        except Exception as e:
            return 0, str(e)

    def _stream_request(
        self,
        path: str,
        data: dict,
        timeout: int = 60,
    ) -> Generator[StreamChunk, None, None]:
        """Stream a chat completion response (SSE)."""
        import http.client
        from urllib.parse import urlparse as _urlparse

        parsed = _urlparse(self.info.base_url)
        host = parsed.hostname
        port = parsed.port
        use_ssl = parsed.scheme == "https"
        full_path = (parsed.path.rstrip("/") + path) if parsed.path else path

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body = json.dumps(data).encode()

        if use_ssl:
            conn = http.client.HTTPSConnection(host, port or 443, timeout=timeout)
        else:
            conn = http.client.HTTPConnection(host, port or 80, timeout=timeout)

        try:
            conn.request("POST", full_path, body=body, headers=headers)
            resp = conn.getresponse()

            if resp.status != 200:
                error_body = resp.read().decode("utf-8", errors="replace")
                yield {"error": True, "status": resp.status, "body": error_body[:500]}
                return

            buffer = b""
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buffer += chunk
                # Process complete SSE events
                while b"\n\n" in buffer:
                    event_end = buffer.index(b"\n\n") + 2
                    event_data = buffer[:event_end]
                    buffer = buffer[event_end:]

                    for line in event_data.decode("utf-8", errors="replace").split("\n"):
                        line = line.strip()
                        if line.startswith("data: "):
                            payload = line[6:]
                            if payload.strip() == "[DONE]":
                                yield {"done": True}
                                return
                            try:
                                parsed = json.loads(payload)
                                yield parsed
                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            yield {"error": True, "message": str(e)}
        finally:
            conn.close()

    # ── Public API ──

    def list_models(self) -> list[dict]:
        """List available models from this provider."""
        cache_key = f"{self.info.name}_models"
        cache_file = CACHE_DIR / cache_key
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Use cache if < 1 hour old
        if cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < 3600:
                try:
                    return json.loads(cache_file.read_text())
                except Exception:
                    pass

        models = self._fetch_models()
        try:
            cache_file.write_text(json.dumps(models, indent=2))
        except Exception:
            pass
        return models

    @abstractmethod
    def _fetch_models(self) -> list[dict]:
        """Fetch models from the provider API — implement in subclass."""
        ...

    @abstractmethod
    def chat(
        self,
        model: str,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        **kwargs,
    ) -> ChatResponse | Generator[StreamChunk, None, None]:
        """Send a chat completion request."""
        ...

    def _build_chat_payload(
        self,
        model: str,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        **kwargs,
    ) -> dict:
        """Build the standard OpenAI-format payload."""
        msgs = list(messages)
        if system:
            msgs.insert(0, {"role": "system", "content": system})

        payload = {
            "model": model,
            "messages": msgs,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)
        return payload

    def _parse_chat_response(self, body: str) -> ChatResponse:
        """Parse a standard OpenAI-format response."""
        data = json.loads(body)
        if "choices" in data:
            return data
        # Anthropic-style or other format
        return data


# ── Concrete Providers ──


class NvidiaProvider(LLMProvider):
    """NVIDIA NIM API — https://build.nvidia.com"""

    def __init__(self):
        super().__init__(ProviderInfo(
            name="nvidia",
            display_name="NVIDIA NIM",
            base_url="https://integrate.api.nvidia.com/v1",
            env_key_name="NVIDIA_API_KEY",
            default_model="meta/llama-3.3-70b-instruct",
            requires_key=True,
            free_tier=True,
            rpm_limit=40,
            description="NVIDIA hosted open models (Llama, DeepSeek, Nemotron, Qwen) — free tier with 40 RPM",
        ))

    def _fetch_models(self) -> list[dict]:
        code, body = self._request("GET", "/models")
        if code == 200:
            try:
                data = json.loads(body)
                return [{"id": m["id"], "provider": "nvidia"} for m in data.get("data", [])]
            except (json.JSONDecodeError, KeyError):
                pass
        # Fallback: return known featured models
        return [
            {"id": "deepseek-ai/deepseek-v4-flash", "provider": "nvidia"},
            {"id": "deepseek-ai/deepseek-v4-pro", "provider": "nvidia"},
            {"id": "nvidia/nemotron-3-ultra-550b-a55b", "provider": "nvidia"},
            {"id": "nvidia/llama-3.1-nemotron-70b-instruct", "provider": "nvidia"},
            {"id": "meta/llama-3.3-70b-instruct", "provider": "nvidia"},
            {"id": "meta/llama-4-scout-17b-16e-instruct", "provider": "nvidia"},
            {"id": "mistralai/mistral-large-3", "provider": "nvidia"},
            {"id": "moonshotai/kimi-k2.6", "provider": "nvidia"},
            {"id": "google/gemma-2-2b-it", "provider": "nvidia"},
            {"id": "qwen/qwen2.5-72b-instruct", "provider": "nvidia"},
        ]

    def chat(
        self,
        model: str,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        **kwargs,
    ):
        payload = self._build_chat_payload(model, messages, system, temperature, max_tokens, stream, **kwargs)

        if stream:
            return self._stream_request("/chat/completions", payload)

        code, body = self._request("POST", "/chat/completions", payload)
        if code == 200:
            return json.loads(body)
        # Try to extract meaningful error
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", body[:200])
        except (json.JSONDecodeError, TypeError):
            msg = body[:200]
        return {"error": True, "status": code, "message": msg}


class OpenAIProvider(LLMProvider):
    """OpenAI API"""

    def __init__(self):
        super().__init__(ProviderInfo(
            name="openai",
            display_name="OpenAI",
            base_url="https://api.openai.com/v1",
            env_key_name="OPENAI_API_KEY",
            default_model="gpt-4.1",
            requires_key=True,
            free_tier=False,
            rpm_limit=None,
            description="OpenAI GPT-4.1, GPT-5.x series, o-series reasoning models",
        ))

    def _fetch_models(self) -> list[dict]:
        code, body = self._request("GET", "/models")
        if code == 200:
            try:
                data = json.loads(body)
                return [{"id": m["id"], "provider": "openai"} for m in data.get("data", [])]
            except Exception:
                pass
        return [{"id": "gpt-4.1", "provider": "openai"}, {"id": "gpt-4.1-mini", "provider": "openai"}]

    def chat(self, model, messages, system=None, temperature=0.7, max_tokens=None, stream=False, **kwargs):
        payload = self._build_chat_payload(model, messages, system, temperature, max_tokens, stream, **kwargs)
        if stream:
            return self._stream_request("/chat/completions", payload)
        code, body = self._request("POST", "/chat/completions", payload)
        if code == 200:
            return json.loads(body)
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", body[:200])
        except Exception:
            msg = body[:200]
        return {"error": True, "status": code, "message": msg}


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API — different format from OpenAI."""

    def __init__(self):
        super().__init__(ProviderInfo(
            name="anthropic",
            display_name="Anthropic Claude",
            base_url="https://api.anthropic.com/v1",
            env_key_name="ANTHROPIC_API_KEY",
            default_model="claude-sonnet-4-6",
            requires_key=True,
            free_tier=False,
            rpm_limit=None,
            description="Anthropic Claude Opus 4.7, Sonnet 4.6, Haiku 4.5",
            headers={"anthropic-version": "2023-06-01"},
        ))

    def _fetch_models(self) -> list[dict]:
        return [
            {"id": "claude-opus-4-7", "provider": "anthropic"},
            {"id": "claude-sonnet-4-6", "provider": "anthropic"},
            {"id": "claude-haiku-4-5", "provider": "anthropic"},
        ]

    def chat(self, model, messages, system=None, temperature=0.7, max_tokens=None, stream=False, **kwargs):
        # Anthropic format: system is top-level, messages are user/assistant only
        anthropic_messages = []
        anthropic_system = system

        for msg in messages:
            role = msg["role"]
            if role == "system":
                if anthropic_system is None:
                    anthropic_system = msg["content"]
                continue
            content = msg["content"]
            if role == "tool":
                content = [{"type": "tool_result", "tool_use_id": msg.get("tool_call_id", ""), "content": content}]
                role = "user"
            anthropic_messages.append({"role": role, "content": content})

        payload = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
        }
        if anthropic_system:
            payload["system"] = anthropic_system

        # Anthropic uses x-api-key header, not Bearer
        code, body = self._request("POST", "/messages", payload, headers={"x-api-key": self.api_key or ""})
        if code == 200:
            data = json.loads(body)
            return self._anthropic_to_openai(data, model)
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", body[:200])
        except Exception:
            msg = body[:200]
        return {"error": True, "status": code, "message": msg}

    def _anthropic_to_openai(self, data: dict, model: str) -> dict:
        """Convert Anthropic response to OpenAI-compatible format."""
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        return {
            "id": data.get("id", ""),
            "object": "chat.completion",
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": data.get("stop_reason", "stop"),
            }],
            "usage": {
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
                "total_tokens": (
                    data.get("usage", {}).get("input_tokens", 0)
                    + data.get("usage", {}).get("output_tokens", 0)
                ),
            },
        }


class GoogleProvider(LLMProvider):
    """Google Gemini API via OpenAI-compatible endpoint."""

    def __init__(self):
        super().__init__(ProviderInfo(
            name="google",
            display_name="Google Gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            env_key_name="GOOGLE_API_KEY",
            default_model="gemini-2.5-pro",
            requires_key=True,
            free_tier=True,
            rpm_limit=None,
            description="Google Gemini 2.5 Pro, 3.5 Flash — free tier available",
        ))

    def _fetch_models(self) -> list[dict]:
        return [
            {"id": "gemini-2.5-pro", "provider": "google"},
            {"id": "gemini-2.5-flash", "provider": "google"},
            {"id": "gemini-3-flash", "provider": "google"},
            {"id": "gemma-3-27b-it", "provider": "google"},
        ]

    def chat(self, model, messages, system=None, temperature=0.7, max_tokens=None, stream=False, **kwargs):
        payload = self._build_chat_payload(model, messages, system, temperature, max_tokens, stream, **kwargs)
        if stream:
            return self._stream_request("/chat/completions", payload)
        code, body = self._request("POST", "/chat/completions", payload)
        if code == 200:
            return json.loads(body)
        return {"error": True, "status": code, "message": body[:200]}


class GroqProvider(LLMProvider):
    """Groq API — fastest inference, free tier."""

    def __init__(self):
        super().__init__(ProviderInfo(
            name="groq",
            display_name="Groq",
            base_url="https://api.groq.com/openai/v1",
            env_key_name="GROQ_API_KEY",
            default_model="llama-3.3-70b-versatile",
            requires_key=True,
            free_tier=True,
            rpm_limit=30,
            description="Groq LPU — fastest inference (500-2600 tok/s), free 30 RPM",
        ))

    def _fetch_models(self) -> list[dict]:
        code, body = self._request("GET", "/models")
        if code == 200:
            try:
                data = json.loads(body)
                return [{"id": m["id"], "provider": "groq"} for m in data.get("data", [])]
            except Exception:
                pass
        return [
            {"id": "llama-3.3-70b-versatile", "provider": "groq"},
            {"id": "llama-3.1-8b-instant", "provider": "groq"},
            {"id": "llama-4-maverick-17b", "provider": "groq"},
            {"id": "deepseek-r1-distill-70b", "provider": "groq"},
            {"id": "qwen3-32b", "provider": "groq"},
            {"id": "groq/compound", "provider": "groq"},
        ]

    def chat(self, model, messages, system=None, temperature=0.7, max_tokens=None, stream=False, **kwargs):
        payload = self._build_chat_payload(model, messages, system, temperature, max_tokens, stream, **kwargs)
        if stream:
            return self._stream_request("/chat/completions", payload)
        code, body = self._request("POST", "/chat/completions", payload)
        if code == 200:
            return json.loads(body)
        return {"error": True, "status": code, "message": body[:200]}


class OpenRouterProvider(LLMProvider):
    """OpenRouter — routes to 200+ models from 60+ providers."""

    def __init__(self):
        super().__init__(ProviderInfo(
            name="openrouter",
            display_name="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            env_key_name="OPENROUTER_API_KEY",
            default_model="openai/gpt-4.1",
            requires_key=True,
            free_tier=True,
            rpm_limit=20,
            description="OpenRouter — 200+ models from 60+ providers with fallback chains",
        ))

    def _fetch_models(self) -> list[dict]:
        code, body = self._request("GET", "/models")
        if code == 200:
            try:
                data = json.loads(body)
                return [{"id": m["id"], "provider": "openrouter"} for m in data.get("data", [])]
            except Exception:
                pass
        return [
            {"id": "openai/gpt-4.1", "provider": "openrouter"},
            {"id": "anthropic/claude-sonnet-4-6", "provider": "openrouter"},
            {"id": "google/gemini-2.5-pro", "provider": "openrouter"},
            {"id": "meta-llama/llama-3.3-70b-instruct", "provider": "openrouter"},
            {"id": "nvidia/nemotron-3-ultra-550b-a55b", "provider": "openrouter"},
        ]

    def chat(self, model, messages, system=None, temperature=0.7, max_tokens=None, stream=False, **kwargs):
        payload = self._build_chat_payload(model, messages, system, temperature, max_tokens, stream, **kwargs)
        # OpenRouter gets provider preferences in extra body
        payload.setdefault("extra_body", {})
        if stream:
            return self._stream_request("/chat/completions", payload)
        code, body = self._request("POST", "/chat/completions", payload)
        if code == 200:
            return json.loads(body)
        return {"error": True, "status": code, "message": body[:200]}


class TogetherProvider(LLMProvider):
    """Together AI — 200+ open-source models."""

    def __init__(self):
        super().__init__(ProviderInfo(
            name="together",
            display_name="Together AI",
            base_url="https://api.together.ai/v1",
            env_key_name="TOGETHER_API_KEY",
            default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            requires_key=True,
            free_tier=False,
            rpm_limit=None,
            description="Together AI — 200+ open-source models (DeepSeek, Llama, Qwen)",
        ))

    def _fetch_models(self) -> list[dict]:
        code, body = self._request("GET", "/models")
        if code == 200:
            try:
                data = json.loads(body)
                return [{"id": m["id"], "provider": "together"} for m in data]
            except Exception:
                pass
        return [
            {"id": "deepseek-ai/DeepSeek-V4-Pro", "provider": "together"},
            {"id": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "provider": "together"},
            {"id": "Qwen/Qwen3-235B-A22B", "provider": "together"},
        ]

    def chat(self, model, messages, system=None, temperature=0.7, max_tokens=None, stream=False, **kwargs):
        payload = self._build_chat_payload(model, messages, system, temperature, max_tokens, stream, **kwargs)
        if stream:
            return self._stream_request("/chat/completions", payload)
        code, body = self._request("POST", "/chat/completions", payload)
        if code == 200:
            return json.loads(body)
        return {"error": True, "status": code, "message": body[:200]}


class OllamaProvider(LLMProvider):
    """Local Ollama — no key needed."""

    def __init__(self):
        super().__init__(ProviderInfo(
            name="ollama",
            display_name="Ollama (Local)",
            base_url="http://localhost:11434/v1",
            env_key_name=None,
            default_model="llama3.1:8b",
            requires_key=False,
            free_tier=True,
            rpm_limit=None,
            description="Local Ollama — 14 models including Llama 3.1, Qwen, Nemotron, custom MSN variants",
        ))

    def _fetch_models(self) -> list[dict]:
        # Use OpenAI-compatible models endpoint first
        code, body = self._request("GET", "/models")
        if code == 200:
            try:
                data = json.loads(body)
                return [{"id": m["id"], "provider": "ollama"} for m in data.get("data", [])]
            except Exception:
                pass
        # Fallback: hit native Ollama API directly
        try:
            from urllib.request import urlopen
            resp = urlopen("http://localhost:11434/api/tags", timeout=5)
            data = json.loads(resp.read().decode())
            models = []
            for m in data.get("models", []):
                name = m.get("name", "")
                size = m.get("size", 0)
                models.append({
                    "id": name,
                    "provider": "ollama",
                    "size_bytes": size,
                    "size_gb": round(size / 1e9, 1) if size else None,
                })
            return models
        except Exception:
            pass
        return [
            {"id": "llama3.1:8b", "provider": "ollama"},
            {"id": "qwen2.5-coder:7b", "provider": "ollama"},
            {"id": "deepseek-coder-v2:lite", "provider": "ollama"},
            {"id": "nemotron-mini:latest", "provider": "ollama"},
        ]

    def chat(self, model, messages, system=None, temperature=0.7, max_tokens=None, stream=False, **kwargs):
        payload = self._build_chat_payload(model, messages, system, temperature, max_tokens, stream, **kwargs)
        payload["stream"] = stream

        if stream:
            # Ollama SSE stream is compatible with our handler
            return self._stream_request("/chat/completions", payload)

        code, body = self._request("POST", "/chat/completions", payload)
        if code == 200:
            return json.loads(body)
        return {"error": True, "status": code, "message": body[:200]}


# ── Provider Registry ──

_PROVIDER_INSTANCES: dict[str, LLMProvider] = {}
_PROVIDER_CLASSES: list[type[LLMProvider]] = [
    NvidiaProvider,
    OpenAIProvider,
    AnthropicProvider,
    GoogleProvider,
    GroqProvider,
    OpenRouterProvider,
    TogetherProvider,
    OllamaProvider,
]


def _get_instance(cls: type[LLMProvider]) -> LLMProvider:
    """Get or create a singleton instance of a provider class."""
    name = cls().info.name
    if name not in _PROVIDER_INSTANCES:
        _PROVIDER_INSTANCES[name] = cls()
    return _PROVIDER_INSTANCES[name]


def get_provider(name: str) -> LLMProvider | None:
    """Get a provider by name."""
    for cls in _PROVIDER_CLASSES:
        if cls().info.name == name:
            return _get_instance(cls)
    return None


def list_providers() -> list[LLMProvider]:
    """List all registered providers."""
    return [_get_instance(cls) for cls in _PROVIDER_CLASSES]


def active_providers() -> list[LLMProvider]:
    """List providers that have API keys configured."""
    return [p for p in list_providers() if p.status().get("configured")]


def get_default_provider() -> LLMProvider | None:
    """Get the default provider from config, or first active one, or Ollama."""
    cfg = load_provider_config()
    default_name = cfg.get("default_provider")

    if default_name:
        p = get_provider(default_name)
        if p and p.status().get("configured"):
            return p

    # First active provider
    active = active_providers()
    if active:
        return active[0]

    # Fallback to Ollama (always available)
    return get_provider("ollama")


def get_default_model(provider_name: str | None = None) -> str:
    """Get the default model for a provider, or the global default."""
    if provider_name:
        p = get_provider(provider_name)
        if p:
            cfg = load_provider_config()
            return cfg.get("providers", {}).get(provider_name, {}).get("default_model", p.info.default_model)
    # Global default
    cfg = load_provider_config()
    global_model = cfg.get("default_model")
    if global_model:
        return global_model
    p = get_default_provider()
    return p.info.default_model if p else "llama3.1:8b"


def set_default_provider(name: str):
    """Set the default provider."""
    p = get_provider(name)
    if not p:
        raise ValueError(f"Unknown provider: {name}")
    cfg = load_provider_config()
    cfg["default_provider"] = name
    save_provider_config(cfg)
    print(f"  ✅ Default provider set to: {p.info.display_name}")


def chat(
    provider_name: str | None = None,
    model: str | None = None,
    messages: list[Message] | None = None,
    prompt: str | None = None,
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    stream: bool = False,
    **kwargs,
) -> ChatResponse | Generator[StreamChunk, None, None]:
    """High-level chat function — auto-selects provider if not specified.

    Args:
        provider_name: Provider name, or None for auto-select
        model: Model ID, or None for provider's default
        messages: Full message list
        prompt: Shortcut — single user message
        system: Optional system prompt
        ...
    """
    if messages is None and prompt:
        messages = [{"role": "user", "content": prompt}]

    if not messages:
        raise ValueError("Either messages or prompt is required")

    # Auto-select provider
    if not provider_name:
        prov = get_default_provider()
    else:
        prov = get_provider(provider_name)

    if not prov:
        available = ", ".join(p.info.name for p in list_providers())
        raise ValueError(f"No provider found. Available: {available}")

    # Auto-select model
    if not model:
        model = get_default_model(prov.info.name)

    return prov.chat(model, messages, system, temperature, max_tokens, stream, **kwargs)


def models(provider_name: str | None = None) -> list[dict]:
    """List models from one or all providers."""
    if provider_name:
        prov = get_provider(provider_name)
        if not prov:
            return []
        return prov.list_models()

    result = []
    for prov in list_providers():
        result.extend(prov.list_models())
    return result


def check_all_providers() -> dict[str, dict]:
    """Check status of all providers."""
    result = {}
    for prov in list_providers():
        result[prov.info.name] = prov.status()
        result[prov.info.name]["display_name"] = prov.info.display_name
        result[prov.info.name]["default_model"] = get_default_model(prov.info.name)
    return result


def extract_content(response: ChatResponse) -> str:
    """Extract the text content from a chat response (works across providers)."""
    if response.get("error"):
        return f"[Error {response.get('status', '?')}] {response.get('message', 'Unknown error')}"

    # OpenAI format
    choices = response.get("choices", [])
    if choices:
        msg = choices[0].get("message", {})
        content = msg.get("content")
        if content:
            return content

    # Anthropic format (already converted)
    # Fallback: return raw
    return json.dumps(response, indent=2)[:2000]


def extract_usage(response: ChatResponse) -> dict:
    """Extract token usage from a response."""
    usage = response.get("usage", {})
    if isinstance(usage, dict) and usage:
        return usage
    return {}


# ── CLI Integration Helpers ──


def format_model_list(models_list: list[dict]) -> str:
    """Pretty-print a list of models grouped by provider."""
    by_provider: dict[str, list[dict]] = {}
    for m in models_list:
        pid = m.get("provider", "unknown")
        by_provider.setdefault(pid, []).append(m)

    output = []
    for pid, mods in sorted(by_provider.items()):
        prov = get_provider(pid)
        label = prov.info.display_name if prov else pid
        output.append(f"\n  🜏 {label} — {len(mods)} models")
        output.append(f"  {'─' * 50}")
        for m in sorted(mods, key=lambda x: x["id"]):
            size = ""
            if m.get("size_gb"):
                size = f" ({m['size_gb']} GB)"
            output.append(f"  {m['id']}{size}")
    return "\n".join(output)


def format_status(checks: dict[str, dict]) -> str:
    """Pretty-print provider status."""
    output = ["\n  🜏 LLM Provider Status", "  ───────────────────────"]
    cfg = load_provider_config()
    default = cfg.get("default_provider")

    for name, info in sorted(checks.items()):
        icon = "✅" if info.get("healthy") else "⬜" if info.get("configured") else "🔑"
        default_marker = " ★" if name == default else ""
        key_status = "key set" if info.get("configured") else "no key" if info.get("configured") is False else "?"
        output.append(f"  {icon} {info['display_name']:<22} {key_status:<12} {info.get('default_model', '?'):<30}{default_marker}")

    output.append("")
    output.append("  ★ = default provider")
    output.append("  Set keys: export <ENV_VAR>=<key>  or  lilith provider key <name> <key>")
    output.append("  Set default: lilith provider set <name>")
    output.append("")

    return "\n".join(output)


# ── Standalone CLI Test ──

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LLM Provider Router — test all providers")
    parser.add_argument("action", nargs="?", default="status", choices=["status", "models", "chat", "keys"])
    parser.add_argument("--provider", "-p", help="Provider name")
    parser.add_argument("--model", "-m", help="Model ID")
    parser.add_argument("--prompt", help="Prompt message")
    parser.add_argument("--system", "-s", help="System prompt")
    args = parser.parse_args()

    if args.action == "status":
        s = check_all_providers()
        print(format_status(s))

    elif args.action == "models":
        m = models(args.provider)
        print(format_model_list(m))

    elif args.action == "chat":
        if not args.prompt:
            # Interactive mode
            print("🜏 Lilith LLM Chat (Ctrl+D to exit)")
            prov = get_default_provider()
            print(f"  Default: {prov.info.display_name} / {get_default_model()}")
            history = []
            while True:
                try:
                    user_input = input("\n  You: ")
                    if not user_input.strip():
                        continue
                    history.append({"role": "user", "content": user_input})
                    print("  LLM: ", end="", flush=True)
                    resp = chat(provider_name=args.provider, model=args.model, messages=history, stream=True)
                    full = ""
                    for chunk in resp:
                        if chunk.get("error"):
                            print(f"[Error: {chunk.get('message', '?')}]")
                            break
                        delta = (chunk.get("choices", [{}])[0]
                                  .get("delta", {})
                                  .get("content", ""))
                        if delta:
                            full += delta
                            print(delta, end="", flush=True)
                    print()
                    if full:
                        history.append({"role": "assistant", "content": full})
                except (EOFError, KeyboardInterrupt):
                    print("\n  Bye!")
                    break
        else:
            resp = chat(provider_name=args.provider, model=args.model, prompt=args.prompt, system=args.system)
            print(extract_content(resp))
            usage = extract_usage(resp)
            if usage:
                print(f"\n  [tokens: {usage.get('total_tokens', '?')} "
                      f"(prompt: {usage.get('prompt_tokens', '?')}, "
                      f"completion: {usage.get('completion_tokens', '?')})]")

    elif args.action == "keys":
        for prov in list_providers():
            key = get_api_key(prov.info.name)
            masked = key[:8] + "..." if key and len(key) > 8 else "(not set)" if not key else "(set)"
            print(f"  {prov.info.display_name:<22} {masked}")
