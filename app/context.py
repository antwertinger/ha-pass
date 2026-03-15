"""Shared template context builder.

Extracted from main.py so routers can import it without a circular dependency.
"""
from fastapi import Request

from app.config import settings
from app.theme import brand_bg_dark, brand_css


def base_context(request: Request) -> dict:
    """Common template context: theme, CSP nonce, ingress base path."""
    return {
        "request": request,
        "app_name": settings.app_name,
        "brand_bg": settings.brand_bg,
        "brand_bg_dark": brand_bg_dark,
        "brand_primary": settings.brand_primary,
        "brand_css": brand_css,
        "csp_nonce": request.state.csp_nonce,
        "base_path": request.state.ingress_path,
    }
