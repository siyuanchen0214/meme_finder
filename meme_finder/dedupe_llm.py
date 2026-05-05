from __future__ import annotations

import json
from typing import List, Optional, Tuple


DEDUPE_SYSTEM = """你是每日幽默精选的“去重裁判”。
目标：避免发送与历史内容“高度相似/几乎一样”的条目。

规则：
- 如果基本是同一件事/同一段子/同一节目切片/重复上传：send=false
- 如果是同系列但新一期/新故事：send=true
- 宁可保守一些：只有在相似度很高时才跳过

只输出 JSON，不要输出任何额外文字：
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
        return True, "未启用 LLM 去重（未提供 API key）。"

    # Keep prompt bounded.
    recent = recent_texts[-80:]
    recent_block = "\n\n".join([f"[{i}] {t}" for i, t in enumerate(recent)])

    user = f"""候选内容：
{candidate_text}

历史已发送内容（越靠后越新）：
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
        return True, "LLM 去重解析失败；为避免漏发，本条照常发送。"

