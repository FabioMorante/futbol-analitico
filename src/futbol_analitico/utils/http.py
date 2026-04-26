from __future__ import annotations

import requests


def build_headers(user_agent: str, referer: str | None = None, origin: str | None = None) -> dict:
    headers = {
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    if origin:
        headers["Origin"] = origin
    return headers


def get_json(url: str, headers: dict, timeout_seconds: int) -> dict:
    response = requests.get(url, headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    return response.json()