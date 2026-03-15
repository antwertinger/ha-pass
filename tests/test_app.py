"""Tests for top-level app routes in main.py."""


async def test_root_redirects_to_admin_dashboard(client, mock_ha_client):
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code in (301, 302, 307)
    assert "/admin/dashboard" in resp.headers["location"]


async def test_health_check_returns_503_when_ws_unhealthy(client, mock_ha_client):
    """Degraded WS returns 503 so monitoring can alert."""
    mock_ha_client["is_ws_healthy"].return_value = False
    resp = await client.get("/health")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["ws"] == "disconnected"
