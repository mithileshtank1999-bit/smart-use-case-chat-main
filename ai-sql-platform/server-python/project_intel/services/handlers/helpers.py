from __future__ import annotations

import re


def extract_after(text: str, needle: str) -> str | None:
    """Extract the value appearing after 'needle' in text. Returns None if placeholder or missing."""
    pattern = re.compile(r"\b" + re.escape(needle) + r"\b\s+(.+)$", flags=re.IGNORECASE)
    m = pattern.search(text or "")
    if not m:
        return None
    value = (m.group(1) or "").strip()
    if not value or "{" in value or "}" in value:
        return None
    return value


def detect_stage(text: str) -> str | None:
    """Detect DEV / SIT / UAT stage prefix in text."""
    t = (text or "").strip().lower()
    if "dev " in t or t.startswith("dev "):
        return "DEV"
    if "sit " in t or t.startswith("sit "):
        return "SIT"
    if "uat " in t or t.startswith("uat "):
        return "UAT"
    return None
