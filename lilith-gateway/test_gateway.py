import pytest
from fastapi.testclient import TestClient
from gateway_server import app

client = TestClient(app)


def test_health_endpoint():
    """Test that the root endpoint returns HTML"""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_api_status():
    """Test system status endpoint"""
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "timestamp" in data
    assert "gateway_version" in data


def test_api_apps():
    """Test apps listing endpoint"""
    response = client.get("/api/apps")
    assert response.status_code == 200
    data = response.json()
    assert "apps" in data
    assert "count" in data


def test_api_vms():
    """Test VMs listing endpoint"""
    response = client.get("/api/vms")
    assert response.status_code == 200
    data = response.json()
    assert "vms" in data
    assert "count" in data


def test_api_docs():
    """Test API docs endpoint"""
    response = client.get("/api/docs")
    assert response.status_code == 200
    data = response.json()
    assert "endpoints" in data


def test_llm_models_endpoint():
    """Test LLM models listing (may fail if Ollama not running)"""
    response = client.get("/v1/models")
    # Accept 200 or 503 (service unavailable if Ollama down)
    assert response.status_code in [200, 503]


def test_api_categories():
    """Test categories endpoint"""
    response = client.get("/api/categories")
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    assert "total_apps" in data