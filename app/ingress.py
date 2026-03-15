"""Ingress detection helpers.

Only trust X-Ingress-Path when SUPERVISOR_TOKEN exists (add-on mode).
This prevents header spoofing in standalone Docker deployments.
"""
import os

from fastapi import Request

_SUPERVISOR_TOKEN: str | None = os.environ.get("SUPERVISOR_TOKEN")


def get_ingress_path(request: Request) -> str:
    if not _SUPERVISOR_TOKEN:
        return ""
    return request.headers.get("X-Ingress-Path", "")


def is_ingress_request(request: Request) -> bool:
    return bool(get_ingress_path(request))
