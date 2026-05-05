from __future__ import annotations

from datetime import datetime, timezone
from typing import List


def render_digest(item_blocks: List[str]) -> str:
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    if not item_blocks:
        return f"""# 每日幽默精选 — {today}

过去 24 小时内，你的白名单来源没有新内容。
"""

    joined = "\n\n".join(item_blocks)
    return f"""# 每日幽默精选 — {today}

快速扫一眼。点开之前先想清楚：你真的准备好了吗？

{joined}
"""

