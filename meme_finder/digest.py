from __future__ import annotations

from datetime import datetime, timezone
from typing import List


def render_digest(item_blocks: List[str]) -> str:
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    if not item_blocks:
        return f"""# Daily Humor Digest — {today}

Nothing new from your approved feeds in the last day.
"""

    joined = "\n\n".join(item_blocks)
    return f"""# Daily Humor Digest — {today}

Quick scan. Click only if it’s worth losing your innocence.

{joined}
"""

