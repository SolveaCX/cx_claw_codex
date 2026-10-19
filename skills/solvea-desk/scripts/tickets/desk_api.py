#!/usr/bin/env python3
"""Shared authenticated HTTP adapter for Shulex Desk / Tars APIs."""

import os
import sys
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import SOLVEA_ENV  # noqa: E402

from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_APPS_STAGING_URL = "https://apps-staging.voc.ai"
DEFAULT_APPS_PROD_URL = "https://apps.voc.ai"


@dataclass(frozen=True)
class DeskApiConfig:
    base_url: str
    token: str
    cookie_name: str


def resolve_desk_api_config() -> DeskApiConfig:
    """Resolve the authenticated Desk proxy for the current runtime environment."""
    env = os.environ.get("SOLVEA_ENV", SOLVEA_ENV) or "prod"
    if env == "prod":
        return DeskApiConfig(
            base_url=os.environ.get("SOLVEA_PROD_URL", DEFAULT_APPS_PROD_URL).rstrip("/"),
            token=os.environ.get("SOLVEA_PROD_TOKEN", "") or os.environ.get("SOLVEA_TOKEN", ""),
            cookie_name="_token",
        )
    return DeskApiConfig(
        base_url=os.environ.get("SOLVEA_BASE_URL", DEFAULT_APPS_STAGING_URL).rstrip("/"),
        token=os.environ.get("SOLVEA_TOKEN", ""),
        cookie_name="_token_staging",
    )


def request_json(
    client: httpx.Client,
    config: DeskApiConfig,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send one Desk request and validate its transport and business envelope."""
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": config.base_url,
        "Referer": f"{config.base_url}/botdesk",
    }
    if config.token:
        headers["Cookie"] = f"{config.cookie_name}={config.token}"

    response = client.request(
        method,
        f"{config.base_url}{path}",
        params=params,
        json=json_body,
        headers=headers,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Desk API must return a JSON object")
    if payload.get("code") is not None and str(payload["code"]) != "200":
        raise RuntimeError(str(payload.get("message") or "Desk API request failed"))
    return payload
