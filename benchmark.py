#!/usr/bin/env python3
"""
Performance Benchmark Script for VM AI Gateway & Dashboards

Measures response times, throughput, and resource usage for:
- Lilith Gateway (port 8080)
- Windows Port Console (port 8081)

Usage:
  python3 benchmark.py --gateway http://localhost:8080 --console http://localhost:8081
  python3 benchmark.py --all --iterations 100 --concurrent 10
  python3 benchmark.py --report benchmark_results.json
"""

import asyncio
import json
import time
import statistics
import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

try:
    import aiohttp
except ImportError:
    print("Installing aiohttp...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "aiohttp"], check=True)
    import aiohttp

try:
    import psutil
except ImportError:
    psutil = None


@dataclass
class BenchmarkResult:
    endpoint: str
    method: str
    iterations: int
    successful: int
    failed: int
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    std_dev_ms: float
    throughput_rps: float
    errors: List[str]


class BenchmarkRunner:
    def __init__(self, gateway_url: str = "http://localhost:8080", 
                 console_url: str = "http://localhost:8081"):
        self.gateway_url = gateway_url.rstrip('/')
        self.console_url = console_url.rstrip('/')
        self.results: List[BenchmarkResult] = []
        
    async def _make_request(self, session: aiohttp.ClientSession, 
                           url: str, method: str = "GET", 
                           data: Optional[Dict] = None) -> tuple:
        """Make a single request and return (success, latency_ms, error)"""
        start = time.perf_counter()
        try:
            async with session.request(method, url, json=data) as resp:
                await resp.read()
                latency = (time.perf_counter() - start) * 1000
                return (resp.status < 400, latency, None)
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return (False, latency, str(e))
    
    async def benchmark_endpoint(self, session: aiohttp.ClientSession,
                                 url: str, method: str = "GET",
                                 data: Dict = None,
                                 iterations: int = 100,
                                 concurrent: int = 10) -> BenchmarkResult:
        """Benchmark a single endpoint"""
        print(f"  Benchmarking {method} {url} ({iterations} requests, {concurrent} concurrent)...")
        
        semaphore = asyncio.Semaphore(concurrent)
        latencies = []
        successful = 0
        failed = 0
        errors = []
        
        async def bounded_request():
            nonlocal successful, failed
            async with semaphore:
                success, latency, error = await self._make_request(session, url, method, data)
                latencies.append(latency)
                if success:
                    successful += 1
                else:
                    failed += 1
                    if error:
                        errors.append(error)
        
        # Run all requests
        tasks = [bounded_request() for _ in range(iterations)]
        start_time = time.perf_counter()
        await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time
        
        # Calculate statistics
        if latencies:
            latencies.sort()
            min_ms = min(latencies)
            max_ms = max(latencies)
            mean_ms = statistics.mean(latencies)
            median_ms = statistics.median(latencies)
            p50_ms = latencies[len(latencies) // 2]
            p95_idx = int(len(latencies) * 0.95)
            p99_idx = int(len(latencies) * 0.99)
            p95_ms = latencies[min(p95_idx, len(latencies) - 1)]
            p99_ms = latencies[min(p99_idx, len(latencies) - 1)]
            std_dev_ms = statistics.stdev(latencies) if len(latencies) > 1 else 0
        else:
            min_ms = max_ms = mean_ms = median_ms = p50_ms = p95_ms = p99_ms = std_dev_ms = 0
        
        throughput = iterations / total_time if total_time > 0 else 0
        
        return BenchmarkResult(
            endpoint=url,
            method=method,
            iterations=iterations,
            successful=successful,
            failed=failed,
            min_ms=round(min_ms, 2),
            max_ms=round(max_ms, 2),
            mean_ms=round(mean_ms, 2),
            median_ms=round(median_ms, 2),
            p50_ms=round(p50_ms, 2),
            p95_ms=round(p95_ms, 2),
            p99_ms=round(p99_ms, 2),
            std_dev_ms=round(std_dev_ms, 2),
            throughput_rps=round(throughput, 2),
            errors=list(set(errors))[:5]  # Unique errors, max 5
        )
    
    async def run_gateway_benchmarks(self, session: aiohttp.ClientSession,
                                     iterations: int = 100, concurrent: int = 10) -> List[BenchmarkResult]:
        """Run all gateway benchmarks"""
        print(f"\n=== Lilith Gateway ({self.gateway_url}) ===")
        
        endpoints = [
            ("/health", "GET"),
            ("/health/ready", "GET"),
            ("/health/live", "GET"),
            ("/api/status", "GET"),
            ("/api/apps", "GET"),
            ("/api/vms", "GET"),
            ("/api/categories", "GET"),
            ("/v1/models", "GET"),
            ("/api/docs", "GET"),
        ]
        
        results = []
        for endpoint, method in endpoints:
            url = f"{self.gateway_url}{endpoint}"
            result = await self.benchmark_endpoint(session, url, method, 
                                                   iterations=iterations, 
                                                   concurrent=concurrent)
            results.append(result)
            self._print_result(result)
        
        # Test POST endpoints
        post_endpoints = [
            ("/api/cache/invalidate", "POST", {"cache_type": "all"}),
            ("/v1/chat/completions", "POST", {
                "model": "test", 
                "messages": [{"role": "user", "content": "test"}]
            }),
        ]
        
        for endpoint, method, data in post_endpoints:
            url = f"{self.gateway_url}{endpoint}"
            result = await self.benchmark_endpoint(session, url, method, data,
                                                   iterations=min(iterations, 20),
                                                   concurrent=min(concurrent, 5))
            results.append(result)
            self._print_result(result)
        
        return results
    
    async def run_console_benchmarks(self, session: aiohttp.ClientSession,
                                     iterations: int = 100, concurrent: int = 10) -> List[BenchmarkResult]:
        """Run all console benchmarks"""
        print(f"\n=== Windows Port Console ({self.console_url}) ===")
        
        endpoints = [
            ("/health", "GET"),
            ("/health/ready", "GET"),
            ("/health/live", "GET"),
            ("/api/vm/status", "GET"),
            ("/api/vm/iso", "GET"),
            ("/api/files/list", "GET"),
            ("/api/winrm/setup-guide", "GET"),
        ]
        
        results = []
        for endpoint, method in endpoints:
            url = f"{self.console_url}{endpoint}"
            result = await self.benchmark_endpoint(session, url, method,
                                                   iterations=iterations,
                                                   concurrent=concurrent)
            results.append(result)
            self._print_result(result)
        
        # Test POST endpoints
        post_endpoints = [
            ("/api/ai/port", "POST", {
                "code": "#include <windows.h>\nint main() { return 0; }",
                "source_lang": "c",
                "target_lang": "c"
            }),
            ("/api/files/write", "POST", {
                "path": "benchmark_test.txt",
                "content": "Benchmark test content"
            }),
        ]
        
        for endpoint, method, data in post_endpoints:
            url = f"{self.console_url}{endpoint}"
            result = await self.benchmark_endpoint(session, url, method, data,
                                                   iterations=min(iterations, 20),
                                                   concurrent=min(concurrent, 5))
            results.append(result)
            self._print_result(result)
        
        return results
    
    async def run_websocket_benchmark(self, session: aiohttp.ClientSession,
                                      gateway_ws: str = None, console_ws: str = None,
                                      duration: int = 30) -> Dict:
        """Benchmark WebSocket connections"""
        print(f"\n=== WebSocket Benchmark ({duration}s) ===")
        
        results = {}
        
        # Test Gateway WebSocket
        if gateway_ws:
            try:
                async with session.ws_connect(gateway_ws) as ws:
                    start = time.perf_counter()
                    messages_sent = 0
                    messages_received = 0
                    latencies = []
                    
                    async def sender():
                        nonlocal messages_sent
                        while time.perf_counter() - start < duration:
                            send_start = time.perf_counter()
                            await ws.send_str("ping")
                            messages_sent += 1
                            await asyncio.sleep(0.1)
                    
                    async def receiver():
                        nonlocal messages_received
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                latencies.append((time.perf_counter() - send_start) * 1000)
                                messages_received += 1
                            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                                break
                    
                    await asyncio.gather(sender(), receiver())
                    
                    if latencies:
                        results["gateway_ws"] = {
                            "messages_sent": messages_sent,
                            "messages_received": messages_received,
                            "mean_latency_ms": round(statistics.mean(latencies), 2),
                            "p99_latency_ms": round(sorted(latencies)[int(len(latencies)*0.99)], 2)
                        }
            except Exception as e:
                results["gateway_ws"] = {"error": str(e)}
        
        return results
    
    def _print_result(self, result: BenchmarkResult):
        status = "✓" if result.failed == 0 else "✗"
        print(f"  {status} {result.method} {result.endpoint}")
        print(f"      Success: {result.successful}/{result.iterations} | "
              f"Mean: {result.mean_ms}ms | P95: {result.p95_ms}ms | "
              f"P99: {result.p99_ms}ms | Throughput: {result.throughput_rps} req/s")
        if result.errors:
            print(f"      Errors: {', '.join(result.errors[:3])}")
    
    def get_system_metrics(self) -> Dict:
        """Get current system metrics"""
        metrics = {}
        if psutil:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            metrics = {
                "cpu_percent": cpu,
                "memory_percent": mem.percent,
                "memory_available_mb": round(mem.available / (1024*1024), 1),
                "disk_percent": disk.percent,
                "disk_free_gb": round(disk.free / (1024**3), 2)
            }
        return metrics
    
    def generate_report(self, output_path: str = None) -> Dict:
        """Generate comprehensive benchmark report"""
        report = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "gateway_url": self.gateway_url,
            "console_url": self.console_url,
            "system_metrics": self.get_system_metrics(),
            "results": [asdict(r) for r in self.results],
            "summary": self._generate_summary()
        }
        
        if output_path:
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"\nReport saved to {output_path}")
        
        return report
    
    def _generate_summary(self) -> Dict:
        if not self.results:
            return {}
        
        gateway_results = [r for r in self.results if r.endpoint.startswith(self.gateway_url)]
        console_results = [r for r in self.results if r.endpoint.startswith(self.console_url)]
        
        def calc_avg(results, field):
            vals = [getattr(r, field) for r in results if getattr(r, field) > 0]
            return round(statistics.mean(vals), 2) if vals else 0
        
        return {
            "gateway": {
                "total_endpoints": len(gateway_results),
                "total_requests": sum(r.iterations for r in gateway_results),
                "total_successful": sum(r.successful for r in gateway_results),
                "total_failed": sum(r.failed for r in gateway_results),
                "avg_mean_latency_ms": calc_avg(gateway_results, "mean_ms"),
                "avg_p95_latency_ms": calc_avg(gateway_results, "p95_ms"),
                "avg_throughput_rps": calc_avg(gateway_results, "throughput_rps"),
            },
            "console": {
                "total_endpoints": len(console_results),
                "total_requests": sum(r.iterations for r in console_results),
                "total_successful": sum(r.successful for r in console_results),
                "total_failed": sum(r.failed for r in console_results),
                "avg_mean_latency_ms": calc_avg(console_results, "mean_ms"),
                "avg_p95_latency_ms": calc_avg(console_results, "p95_ms"),
                "avg_throughput_rps": calc_avg(console_results, "throughput_rps"),
            }
        }


async def main():
    parser = argparse.ArgumentParser(description="Benchmark VM AI Gateway & Dashboards")
    parser.add_argument("--gateway", default="http://localhost:8080", help="Gateway URL")
    parser.add_argument("--console", default="http://localhost:8081", help="Console URL")
    parser.add_argument("--iterations", type=int, default=100, help="Requests per endpoint")
    parser.add_argument("--concurrent", type=int, default=10, help="Concurrent requests")
    parser.add_argument("--ws-duration", type=int, default=30, help="WebSocket test duration (s)")
    parser.add_argument("--output", help="Output JSON report path")
    parser.add_argument("--gateway-only", action="store_true", help="Only benchmark gateway")
    parser.add_argument("--console-only", action="store_true", help="Only benchmark console")
    
    args = parser.parse_args()
    
    runner = BenchmarkRunner(args.gateway, args.console)
    
    print(f"=== VM AI Gateway Benchmark ===")
    print(f"Gateway: {args.gateway}")
    print(f"Console: {args.console}")
    print(f"Iterations: {args.iterations} | Concurrent: {args.concurrent}")
    print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
    
    async with aiohttp.ClientSession() as session:
        # Check if services are up
        try:
            async with session.get(f"{args.gateway}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    print(f"\n✓ Gateway reachable")
                else:
                    print(f"\n⚠ Gateway returned {resp.status}")
        except:
            print(f"\n✗ Gateway unreachable at {args.gateway}")
        
        try:
            async with session.get(f"{args.console}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    print(f"✓ Console reachable")
                else:
                    print(f"⚠ Console returned {resp.status}")
        except:
            print(f"✗ Console unreachable at {args.console}")
        
        # Run benchmarks
        if not args.console_only:
            gateway_results = await runner.run_gateway_benchmarks(session, args.iterations, args.concurrent)
            runner.results.extend(gateway_results)
        
        if not args.gateway_only:
            console_results = await runner.run_console_benchmarks(session, args.iterations, args.concurrent)
            runner.results.extend(console_results)
        
        # WebSocket benchmarks
        ws_results = await runner.run_websocket_benchmark(
            session,
            gateway_ws=f"{args.gateway.replace('http', 'ws')}/ws",
            console_ws=f"{args.console.replace('http', 'ws')}/ws/terminal",
            duration=args.ws_duration
        )
        
        # Generate report
        output_path = args.output or f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report = runner.generate_report(output_path)
        
        # Print summary
        print("\n" + "="*60)
        print("BENCHMARK SUMMARY")
        print("="*60)
        
        summary = report["summary"]
        for service in ["gateway", "console"]:
            if service in summary:
                s = summary[service]
                print(f"\n{service.upper()}:")
                print(f"  Endpoints tested: {s['total_endpoints']}")
                print(f"  Total requests:   {s['total_requests']}")
                print(f"  Successful:       {s['total_successful']}")
                print(f"  Failed:           {s['total_failed']}")
                print(f"  Avg latency:      {s['avg_mean_latency_ms']}ms")
                print(f"  Avg P95:          {s['avg_p95_latency_ms']}ms")
                print(f"  Avg throughput:   {s['avg_throughput_rps']} req/s")
        
        if ws_results:
            print("\nWEBSOCKET:")
            for k, v in ws_results.items():
                if "error" in v:
                    print(f"  {k}: ERROR - {v['error']}")
                else:
                    print(f"  {k}: {v['messages_sent']} sent, {v['messages_received']} recv, "
                          f"{v['mean_latency_ms']}ms avg latency")
        
        # Overall success
        total_failed = sum(r.failed for r in runner.results)
        if total_failed > 0:
            print(f"\n⚠ {total_failed} requests failed overall")
            sys.exit(1)
        else:
            print("\n✓ All benchmarks passed")
            sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())