from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List, Optional

from .enrichment import build_llm_document, get_transcript_text, transcript_body_for_model
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

JOKES_SYSTEM_STYLE = """You extract multiple jokes/bits from a comedy transcript.

Hard requirements:
- Write in the transcript's native language (if it's Chinese, respond in Chinese).
- Extract MULTIPLE distinct jokes/bits (not just one).
- Each bit must include enough setup/context to be understandable.
- Keep it short and punchy. Sarcastic/dark humor is allowed, but clarity comes first.

Output format (markdown), repeat for each bit:
- **梗/段子 #N**: <一句话概括>
  - **上下文**: <1-2句铺垫>
  - **笑点**: <为什么好笑/哪里反差>
  - **可复述一句**: <我可以直接拿去社交场合讲的一句>

Do not invent content not present in the transcript chunk. If a chunk is low-signal, output fewer bits.
"""


def _looks_cjk(text: str) -> bool:
    if not text:
        return False
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk >= 50


def _chunk_text(text: str, *, max_chars: int = 8000, overlap: int = 400) -> List[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: List[str] = []
    i = 0
    while i < len(text):
        j = min(len(text), i + max_chars)
        chunks.append(text[i:j])
        if j == len(text):
            break
        i = max(0, j - overlap)
    return chunks


def _dedupe_blocks(blocks: List[str], *, threshold: float = 0.92, keep: int = 20) -> List[str]:
    out: List[str] = []
    for b in blocks:
        b_n = " ".join((b or "").strip().split())
        if not b_n:
            continue
        dup = False
        for existing in out[-50:]:
            ratio = SequenceMatcher(None, b_n, " ".join(existing.strip().split())).ratio()
            if ratio >= threshold:
                dup = True
                break
        if not dup:
            out.append(b.strip())
        if len(out) >= keep:
            break
    return out


def _fallback_one_liner(item: Item) -> str:
    # Deterministic, no-AI fallback. Intentionally simple.
    title = item.title.strip()
    if len(title) > 140:
        title = title[:137] + "..."
    return f"- **{item.source_name}** ({item.platform}): {title}\n  - Link: {item.url}"


def summarize_items(
    items: List[Item],
    api_key: Optional[str],
    model: str,
    *,
    use_transcript: bool = True,
    max_transcript_chars: Optional[int] = 48_000,
    transcription_mode: str = "auto",
    whisper_model: str = "whisper-1",
) -> List[str]:
    """
    Returns markdown blocks per item.
    If api_key is not provided, uses a deterministic fallback summarizer.
    Source text for the LLM comes from `build_llm_document` (transcript when available).
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
        transcript = get_transcript_text(
            it,
            use_transcript=use_transcript,
            max_transcript_chars=max_transcript_chars,
            transcription_mode=transcription_mode,
            openai_api_key=api_key,
            whisper_model=whisper_model,
        )

        body = transcript_body_for_model(transcript)
        # Transcript path: extract multiple bits.
        if body and len(body) > 2000:
            chunks = _chunk_text(body, max_chars=8000, overlap=400)
            chunks = chunks[:16]
            per_chunk: List[str] = []
            for idx, chunk in enumerate(chunks):
                lang_hint = "中文" if _looks_cjk(chunk) else "the transcript's language"
                user = f"""Video metadata:
Title: {it.title}
Source: {it.source_name}
URL: {it.url}

Transcript chunk {idx+1}/{len(chunks)} (language: {lang_hint}):
{chunk}
"""
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": JOKES_SYSTEM_STYLE},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.6,
                )
                txt = (resp.choices[0].message.content or "").strip()
                if txt:
                    per_chunk.append(txt)

            merged = "\n\n".join(per_chunk).strip()
            if merged:
                merged = "\n\n".join(_dedupe_blocks(merged.split("\n\n"), keep=20)).strip()
            else:
                merged = _fallback_one_liner(it)

            if it.url and it.url not in merged:
                merged += f"\n\n- Link: {it.url}"
            blocks.append(merged)
            continue

        content = build_llm_document(
            it,
            use_transcript=use_transcript,
            max_transcript_chars=max_transcript_chars,
            transcription_mode=transcription_mode,
            openai_api_key=api_key,
            whisper_model=whisper_model,
        )
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

