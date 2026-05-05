from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List, Optional

from .enrichment import build_llm_document, get_transcript_text, transcript_body_for_model
from .types import Item


SYSTEM_STYLE = """你在写一份每日幽默精选。
默认口吻：刻薄一点但不恶毒（机智、干、略阴阳）。允许黑色幽默（面无表情、边缘、冷）。
必须好读：宁可少一点“梗”，也不要牺牲清晰度。
优先“向上吐槽”：吐槽自己、系统、荒诞处境，不要攻击脆弱个体。
避免骚扰、开盒、去人化表达、煽动暴力等内容。
语言：**只用中文输出**（专有名词/人名/英文标题允许保留原样，但整体叙述必须是中文）。

每条内容输出（markdown）：
- 1 句中性总结（发生了什么）
- 1 句吐槽/冷幽默（可选）
- 1 行：**为什么好笑**：...
保持短小精悍。
"""

JOKES_SYSTEM_STYLE = """你从喜剧/综艺/相声/脱口秀的字幕或转写稿中提取多个“梗/段子/笑点片段”。

Hard requirements:
- **只用中文输出**（专有名词/人名/英文标题允许保留原样，但整体叙述必须是中文）。
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


def _force_chinese_output(text: str) -> str:
    """
    Best-effort post-processing to keep the final digest Chinese-only.
    We do *not* translate proper nouns/titles; we mainly remove/rename common English labels.
    """
    t = (text or "").strip()
    if not t:
        return t

    # Normalize common section labels.
    repl = {
        "What happened:": "发生了什么：",
        "What happened": "发生了什么：",
        "Sarcastic line:": "吐槽一句：",
        "Sarcastic/dark line:": "吐槽一句：",
        "Why it's funny:": "为什么好笑：",
        "Why it’s funny:": "为什么好笑：",
        "Why it's funny": "为什么好笑：",
        "Link:": "链接：",
        "- Link:": "- 链接：",
    }
    for a, b in repl.items():
        t = t.replace(a, b)

    # If the model emits numbered English template lines, strip the pure-English ones.
    lines = []
    for line in t.splitlines():
        s = line.strip()
        if not s:
            lines.append(line)
            continue
        # Drop lines that look like the English template bullets and contain no CJK at all.
        has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in s)
        if not has_cjk and (
            s.lower().startswith("what happened")
            or s.lower().startswith("sarcastic")
            or s.lower().startswith("why it's funny")
            or s.lower().startswith("why it’s funny")
        ):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


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
    # Keep the digest Chinese-only even without OpenAI.
    return f"- **{item.source_name}**（{item.platform}）：{title}\n  - 链接：{item.url}"


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
                merged += f"\n\n- 链接：{it.url}"
            blocks.append(_force_chinese_output(merged))
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
            text = text + f"\n- 链接：{it.url}"

        blocks.append(_force_chinese_output(text))

    return blocks

