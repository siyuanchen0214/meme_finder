from __future__ import annotations

import json
from typing import List, Optional, Tuple


DEDUPE_SYSTEM = """You are a deduplication judge for a daily humor digest.
Goal: avoid sending content that is "very very similar" to previously sent items.

Rules:
- If it is basically the same story/premise/re-upload/clip of the same bit: send=false.
- If it is a new episode/new story even in the same series/theme: send=true.
- Prefer being conservative about skipping: only skip when similarity is high.
- Languages: mixed Chinese/English is fine.

Output JSON only, no extra text:
{"send": true/false, "reason": "...", "similar_to_index": <number or null>}
"""


def _load_openai(api_key: str):
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "OPENAI_API_KEY is set but the 'openai' package is not installed. "
            "Install it or unset OPENAI_API_KEY to disable LLM dedupe."
        ) from e
    return OpenAI(api_key=api_key)


def llm_should_send(
    *,
    api_key: Optional[str],
    model: str,
    candidate_text: str,
    recent_texts: List[str],
) -> Tuple[bool, str]:
    """
    Returns (send, reason).
    If api_key is None, defaults to send=True.
    """
    if not api_key:
        return True, "LLM dedupe disabled (no API key)."

    # Keep prompt bounded.
    recent = recent_texts[-80:]
    recent_block = "\n\n".join([f"[{i}] {t}" for i, t in enumerate(recent)])

    user = f"""Candidate:
{candidate_text}

Previously sent items (most recent last):
{recent_block}
"""

    client = _load_openai(api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": DEDUPE_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    raw = (resp.choices[0].message.content or "").strip()
    try:
        obj = json.loads(raw)
        send = bool(obj.get("send"))
        reason = str(obj.get("reason") or "")
        return send, reason or ("send" if send else "skip")
    except Exception:
        # Fail open: better to send than to silently drop.
        return True, "LLM dedupe parse failed; sending."

