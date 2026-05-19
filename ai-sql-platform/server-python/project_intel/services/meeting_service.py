from __future__ import annotations

"""
Meeting Intelligence: extract structured insights from a meeting transcript.

Output schema
-------------
{
  "summary":      "2-4 sentence executive overview",
  "action_items": [{"owner", "description", "due_date", "priority"}],
  "decisions":    [{"description", "owner"}],
  "risks":        [{"description", "severity", "mitigation"}],
  "participants": ["Alice", "Bob", ...]
}

Long transcripts (>10 000 chars) are split into overlapping chunks, each
extracted independently, then merged with a second LLM call.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

_MAX_SINGLE = 10_000   # chars — process in one shot below this threshold
_CHUNK_SIZE = 8_000
_CHUNK_OVERLAP = 400

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are a meeting intelligence assistant. "
    "Extract structured information from meeting transcripts. "
    "Always return valid JSON with no markdown fences and no prose."
)

_EXTRACT_TEMPLATE = """\
Extract structured meeting intelligence from the transcript below.

Return ONLY a JSON object using this exact schema (use null for unknown fields):
{{
  "summary": "<2-4 sentence executive summary>",
  "action_items": [
    {{"owner": "<name or team>", "description": "<task>", "due_date": "<YYYY-MM-DD or null>", "priority": "<high|medium|low>"}}
  ],
  "decisions": [
    {{"description": "<decision made>", "owner": "<owner or null>"}}
  ],
  "risks": [
    {{"description": "<risk>", "severity": "<high|medium|low>", "mitigation": "<action or null>"}}
  ],
  "participants": ["<name>"]
}}

{context_line}

Transcript:
{transcript}
"""

_MERGE_TEMPLATE = """\
Merge the following meeting-intelligence JSON results (extracted from consecutive
segments of the same meeting) into one unified JSON using the same schema.

Rules:
- Deduplicate action items and risks that refer to the same topic.
- Combine participant lists (unique names only).
- Write a single unified summary covering all segments.
- Preserve all distinct decisions.
- Return ONLY the merged JSON object.

Segments:
{segments}
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _llm(prompt: str) -> str | None:
    from project_intel.core.config import OPENAI_MODEL
    from project_intel.core.openai_client import get_openai_clients

    clients = get_openai_clients()
    if not clients:
        return None
    for client in clients:
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            if status in (401, 403, 404, 429):
                continue
            raise
    return None


def _parse(raw: str) -> dict:
    text = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip().strip("`").strip()
    return json.loads(text)


def _chunk(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    while start < len(text):
        parts.append(text[start : start + _CHUNK_SIZE])
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return parts


def _extract_one(transcript: str, project_name: str | None = None) -> str | None:
    context_line = f"Project context: {project_name}" if project_name else ""
    prompt = _EXTRACT_TEMPLATE.format(
        transcript=transcript,
        context_line=context_line,
    )
    return _llm(prompt)


def _merge(segment_jsons: list[str]) -> str | None:
    prompt = _MERGE_TEMPLATE.format(segments="\n\n---\n\n".join(segment_jsons))
    return _llm(prompt)


def _normalise(result: dict) -> dict:
    return {
        "summary": result.get("summary") or "",
        "action_items": result.get("action_items") or [],
        "decisions": result.get("decisions") or [],
        "risks": result.get("risks") or [],
        "participants": result.get("participants") or [],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_meeting_intelligence(
    transcript: str,
    *,
    project_name: str | None = None,
) -> dict:
    """
    Extract structured intelligence from a meeting transcript.

    Returns
    -------
    {
        ok: bool,
        summary, action_items, decisions, risks, participants,
        transcript_chars: int,
        segments_processed: int,
        error?: str          # only when ok=False
    }
    """
    transcript = (transcript or "").strip()
    if not transcript:
        return {"ok": False, "error": "empty_transcript"}

    if len(transcript) <= _MAX_SINGLE:
        raw = _extract_one(transcript, project_name)
        if raw is None:
            return {"ok": False, "error": "openai_unavailable"}
        try:
            result = _normalise(_parse(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Meeting extraction JSON parse failed: %s — raw: %.300s", exc, raw)
            return {"ok": False, "error": "json_parse_error", "raw_preview": raw[:400]}
        return {"ok": True, **result, "transcript_chars": len(transcript), "segments_processed": 1}

    # Long transcript — chunk + merge
    chunks = _chunk(transcript)
    segment_raws: list[str] = []
    for chunk in chunks:
        raw = _extract_one(chunk, project_name)
        if raw:
            segment_raws.append(raw)

    if not segment_raws:
        return {"ok": False, "error": "openai_unavailable"}

    if len(segment_raws) == 1:
        try:
            result = _normalise(_parse(segment_raws[0]))
        except Exception:
            return {"ok": False, "error": "json_parse_error"}
    else:
        merged_raw = _merge(segment_raws)
        if not merged_raw:
            return {"ok": False, "error": "merge_failed"}
        try:
            result = _normalise(_parse(merged_raw))
        except Exception:
            return {"ok": False, "error": "json_parse_error"}

    return {
        "ok": True,
        **result,
        "transcript_chars": len(transcript),
        "segments_processed": len(segment_raws),
    }
