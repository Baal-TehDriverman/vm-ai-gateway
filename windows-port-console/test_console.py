import pytest
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


def test_root_endpoint():
    """Test that the root endpoint returns HTML"""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_vm_status_endpoint():
    """Test VM status endpoint"""
    response = client.get("/api/vm/status")
    assert response.status_code == 200
    data = response.json()
    # Should have at least VM name and state
    assert "name" in data or "state" in data


def test_vm_iso_endpoint():
    """Test ISO info endpoint"""
    response = client.get("/api/vm/iso")
    assert response.status_code == 200
    data = response.json()
    assert "exists" in data or "path" in data


def test_files_list_endpoint():
    """Test file listing endpoint"""
    response = client.get("/api/files/list")
    assert response.status_code == 200
    data = response.json()
    assert "files" in data


def test_ai_port_endpoint():
    """Test AI porting analysis endpoint"""
    response = client.post("/api/ai/port", json={
        "code": "#include <windows.h>\nint main() { return 0; }",
        "source_lang": "c",
        "target_lang": "c"
    })
    assert response.status_code == 200
    data = response.json()
    assert "portability_score" in data
    assert "windows_patterns_found" in data


def test_winrm_setup_guide():
    """Test WinRM setup guide endpoint"""
    response = client.get("/api/winrm/setup-guide")
    assert response.status_code == 200
    data = response.json()
    assert "guide" in data
    assert len(data["guide"]) > 0


def test_static_files():
    """Test static file serving"""
    response = client.get("/app.js")
    assert response.status_code == 200
    assert "javascript" in response.headers.get("content-type", "")

    response = client.get("/style.css")
    assert response.status_code == 200
    assert "css" in response.headers.get("content-type", "")