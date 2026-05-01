from __future__ import annotations

from dataclasses import replace
from typing import List, Optional

from .types import Item


SYSTEM_STYLE = """You write a daily humor digest.
Default voice: sarcastic (witty, slightly dry). Allowed: dark humor (deadpan, edgy).
Must stay readable: never sacrifice clarity for the joke.
"Punch up" preference: aim at yourself, systems, or absurd situations—not vulnerable individuals.
Avoid harassment, doxxing, dehumanizing language, or inciting violence.
Languages: mixed Chinese + English; preserve the original flavor of names/slang.
Output per item:
- 1 neutral sentence summary ("what happened")
- 1 sarcastic/dark line (optional)
- 1 line: "Why it's funny:" ...
Keep it short.
"""


def _fallback_one_liner(item: Item) -> str:
    # Deterministic, no-AI fallback. Intentionally simple.
    title = item.title.strip()
    if len(title) > 140:
        title = title[:137] + "..."
    return f"- **{item.source_name}** ({item.platform}): {title}\n  - Link: {item.url}"


def summarize_items(items: List[Item], api_key: Optional[str], model: str) -> List[str]:
    """
    Returns markdown blocks per item.
    If api_key is not provided, uses a deterministic fallback summarizer.
    """
    if not api_key:
        return [_fallback_one_liner(i) for i in items]

    # Optional OpenAI summarization; only imported when configured.
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "OPENAI_API_KEY is set but the 'openai' package is not installed. "
            "Install it or unset OPENAI_API_KEY to use the fallback summarizer."
        ) from e

    client = OpenAI(api_key=api_key)
    blocks: List[str] = []
    for it in items:
        content = f"""Title: {it.title}
Source: {it.source_name}
Platform: {it.platform}
URL: {it.url}
Snippet: {it.summary or ""}
"""
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_STYLE},
                {"role": "user", "content": content},
            ],
            temperature=0.7,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            text = _fallback_one_liner(it)

        # Ensure link is included even if model forgets.
        if it.url and it.url not in text:
            text = text + f"\n- Link: {it.url}"

        blocks.append(text)

    return blocks

