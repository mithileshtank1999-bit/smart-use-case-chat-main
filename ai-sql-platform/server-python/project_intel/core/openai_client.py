from __future__ import annotations

import os
from openai import OpenAI


def _split_api_keys(raw: str) -> list[str]:
    # Support comma/semicolon/newline separated lists.
    if not raw:
        return []
    cleaned = raw.replace("\r", "\n").replace(";", ",").replace("\n", ",")
    keys = []
    for part in cleaned.split(","):
        key = (part or "").strip().strip('"').strip("'")
        if key:
            keys.append(key)
    return keys


def get_openai_api_keys() -> list[str]:
    """
    Returns a de-duplicated list of API keys to try, in order.

    Supported env vars:
    - OPENAI_API_KEY: primary key
    - OPENAI_API_KEYS: comma/semicolon/newline separated fallback keys
    """
    keys: list[str] = []
    keys.extend(_split_api_keys(os.getenv("OPENAI_API_KEY", "")))
    keys.extend(_split_api_keys(os.getenv("OPENAI_API_KEYS", "")))

    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def get_openai_clients() -> list[OpenAI]:
    return [OpenAI(api_key=key) for key in get_openai_api_keys()]


def get_openai_client() -> OpenAI:
    keys = get_openai_api_keys()
    return OpenAI(api_key=keys[0] if keys else os.getenv("OPENAI_API_KEY"))
