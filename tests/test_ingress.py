"""Tests for ingress detection and ingress-based auth bypass.

These cover the new ingress feature: header spoofing prevention,
admin auth bypass for HA sidebar, login disabled in add-on mode,
and logout sentinel safety.
"""
from unittest.mock import patch

import app.ingress
from app import database as db


# ---------------------------------------------------------------------------
# Security: header spoofing prevention
# ---------------------------------------------------------------------------

def test_ingress_header_ignored_without_supervisor_token():
    """Without SUPERVISOR_TOKEN, X-Ingress-Path is untrusted — blocks spoofing."""
    from unittest.mock import MagicMock
    req = MagicMock()
    req.headers = {"X-Ingress-Path": "/api/hassio_ingress/spoofed"}
    with patch.object(app.ingress, "_SUPERVISOR_TOKEN", None):
        assert app.ingress.get_ingress_path(req) == ""


# ---------------------------------------------------------------------------
# Integration: ingress auth bypass
# ---------------------------------------------------------------------------

async def test_ingress_bypass_grants_admin_access(client, mock_ha_client, test_db):
    """Ingress requests skip session auth — admin endpoints accessible without cookie."""
    with patch("app.auth.is_ingress_request", return_value=True):
        resp = await client.get("/admin/tokens")
    assert resp.status_code == 200


async def test_login_returns_403_when_no_password(client, mock_ha_client, test_db):
    """In add-on mode (empty password), login endpoint returns 403."""
    from app.config import settings
    with patch.object(settings, "admin_password", ""):
        resp = await client.post(
            "/admin/login",
            json={"username": "testadmin", "password": "anything"},
        )
    assert resp.status_code == 403
    assert "Login disabled" in resp.json()["detail"]


async def test_ingress_logout_does_not_delete_real_sessions(client, mock_ha_client, test_db):
    """Ingress logout returns ok without accidentally wiping a real session."""
    session_id = await db.create_admin_session(ttl_seconds=86400)
    with patch("app.auth.is_ingress_request", return_value=True):
        resp = await client.post("/admin/logout")
    assert resp.status_code == 200
    row = await db.get_admin_session(session_id)
    assert row is not None
