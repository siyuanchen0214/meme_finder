"""把 Markdown 文档渲染成适合邮件客户端阅读的 HTML。

邮件客户端（尤其 Gmail）对 CSS 支持有限，因此这里用一个 `<style>` 块 +
克制的排版，保证标题层级、加粗、链接、间距都清晰可读。
"""

from __future__ import annotations

try:
    import markdown as _markdown  # type: ignore
except Exception:  # pragma: no cover - markdown 未安装时优雅降级
    _markdown = None


_EMAIL_CSS = """
  body { margin: 0; padding: 0; background: #f4f5f7; }
  .wrap { max-width: 720px; margin: 0 auto; padding: 24px 16px 48px; }
  .card {
    background: #ffffff; border-radius: 12px; padding: 28px 28px 32px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
      "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    color: #1f2328; line-height: 1.75; font-size: 15px;
  }
  .card h1 { font-size: 24px; margin: 0 0 4px; color: #0f1419; }
  .card h2 {
    font-size: 19px; margin: 34px 0 12px; padding-bottom: 8px;
    border-bottom: 2px solid #eef0f2; color: #0f1419;
  }
  .card h3 { font-size: 16px; margin: 22px 0 6px; color: #1a1a1a; }
  .card p { margin: 8px 0; }
  .card a { color: #175199; text-decoration: none; }
  .card a:hover { text-decoration: underline; }
  .card ul { margin: 8px 0; padding-left: 22px; }
  .card li { margin: 6px 0; }
  .card blockquote {
    margin: 12px 0; padding: 10px 14px; background: #f7f8fa;
    border-left: 3px solid #c9ced6; color: #57606a; font-size: 13px; border-radius: 4px;
  }
  .card blockquote p { margin: 4px 0; }
  .card hr { border: none; border-top: 1px solid #eef0f2; margin: 24px 0; }
  .meta { color: #8b949e; font-size: 12px; }
  .card strong { color: #0f1419; }
  /* 作者/摘要行的语义标签，靠自定义 class 上色（见下方替换逻辑）。 */
  .decode { color: #b2532a; }
"""


def md_inline_to_html(text: str) -> str:
    """把一小段 Markdown（如“- **标签**：内容”）转成 HTML 片段。"""
    text = (text or "").strip()
    if not text:
        return ""
    if _markdown is None:
        import html

        return html.escape(text).replace("\n", "<br>")
    return _markdown.markdown(text, extensions=["extra", "nl2br"])


def _fallback_html(md_text: str) -> str:
    """markdown 库不可用时的极简转义降级：至少保证换行可读。"""
    import html

    escaped = html.escape(md_text)
    return f"<pre style='white-space:pre-wrap;font-family:sans-serif'>{escaped}</pre>"


def markdown_to_email_html(md_text: str, *, title: str = "知乎每日速览") -> str:
    """Markdown -> 带内嵌样式的完整 HTML 文档。"""
    if _markdown is None:
        body = _fallback_html(md_text)
    else:
        body = _markdown.markdown(
            md_text,
            extensions=["extra", "sane_lists", "nl2br"],
        )
    return (
        "<!DOCTYPE html>"
        '<html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{_EMAIL_CSS}</style></head>"
        '<body><div class="wrap"><div class="card">'
        f"{body}"
        "</div></div></body></html>"
    )
