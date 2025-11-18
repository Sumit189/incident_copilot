from __future__ import annotations

import json
import logging
from typing import Any, Iterable, Optional

from google.adk.sessions.session import Session


logger = logging.getLogger("incident_copilot.state")

_DECODER = json.JSONDecoder()


def _strip_code_fence_block(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    body = text[3:]
    fence_end = body.rfind("```")
    if fence_end != -1:
        body = body[:fence_end]
    if body.startswith("json"):
        body = body[4:]
    return body.strip()


def _extract_code_blocks(text: str) -> Iterable[str]:
    start = 0
    while True:
        fence_start = text.find("```", start)
        if fence_start == -1:
            break
        fence_end = text.find("```", fence_start + 3)
        if fence_end == -1:
            break
        block = text[fence_start + 3 : fence_end]
        if block.startswith("json"):
            block = block[4:]
        block = block.strip()
        if block:
            yield block
        start = fence_end + 3


def _parse_json_from_text(raw: str) -> Any | None:
    if not raw:
        return None

    stripped = raw.strip()
    if not stripped:
        return None

    candidates = [stripped]
    if stripped.startswith("```"):
        candidates.append(_strip_code_fence_block(stripped))
    candidates.extend(_extract_code_blocks(stripped))

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except Exception:
            continue

    for idx, char in enumerate(stripped):
        if char not in "{[":
            continue
        try:
            obj, _ = _DECODER.raw_decode(stripped, idx)
        except json.JSONDecodeError:
            continue
        return obj

    return None


def _coerce_entry(entry: Any) -> Any | None:
    if entry is None:
        return None
    if isinstance(entry, (dict, list)):
        return entry
    text = str(entry).strip()
    if not text:
        return None
    return _parse_json_from_text(text)


def _iter_event_payloads(session: Session, agent_name: str) -> Iterable[Any]:
    events = getattr(session, "events", None) or []
    for event in reversed(events):
        if getattr(event, "author", None) != agent_name:
            continue
        actions = getattr(event, "actions", None)
        if actions:
            agent_state = getattr(actions, "agent_state", None)
            if isinstance(agent_state, (dict, list)):
                yield agent_state
                continue
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if not parts:
            continue
        texts = [getattr(part, "text", None) for part in parts]
        normalized = "\n".join(t.strip() for t in texts if isinstance(t, str) and t.strip())
        if normalized:
            parsed = _parse_json_from_text(normalized)
            if parsed is not None:
                yield parsed


def get_agent_snapshot(session: Session, agent_name: str) -> Optional[Any]:
    """Fetch the latest structured response stored for the given agent."""
    snapshots = session.state.setdefault("agent_snapshots", {})
    snapshot = snapshots.get(agent_name)
    if snapshot is not None:
        return snapshot

    responses = session.state.get("agent_responses", {}).get(agent_name) or []
    logger.debug(
        "[state] No snapshot for %s; attempting to parse %d responses",
        agent_name,
        len(responses),
    )

    for entry in reversed(responses):
        parsed = _coerce_entry(entry)
        if parsed is not None:
            snapshots[agent_name] = parsed
            return parsed

    for parsed in _iter_event_payloads(session, agent_name):
        snapshots[agent_name] = parsed
        return parsed

    logger.debug("[state] No responses to parse for %s", agent_name)
    return None

