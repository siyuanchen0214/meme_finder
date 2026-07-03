"""知乎每日速览：抓取 -> 排序 -> LLM 富集 -> 结构化数据 -> 两种渲染。

三大板块，排序信号**互不混淆**：
  一、今日热榜         —— 每个话题按“赞高”给代表性回答
  二、搞笑精选         —— 纯按热度（赞高、评论多）排序
  三、拓展边界         —— 纯按作者含金量（本工具据官方认证文案估算）排序

渲染：
  - render_markdown(data)  -> 存档用的 .md 文档
  - render_html(data)      -> Morning Brew 风格的 HTML 邮件（含内嵌图片）
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .render import md_inline_to_html
from .zhihu import (
    HotItem,
    SearchItem,
    ZhihuClient,
    author_credibility,
    search_fanout,
    top_answers_for_topic,
)

# 搞笑类查询：段子 / 神回复 / 沙雕新闻。排序只看热度。
FUNNY_QUERIES = [
    "有哪些好笑的段子",
    "有什么笑话一听就爆笑不止",
    "有哪些超搞笑的段子",
    "有哪些让人笑不活的神评论",
    "最近有什么好笑的网络热梗",
    "有哪些离谱又好笑的经历",
    "有哪些沙雕新闻",
    "有哪些好笑的神回复",
]

# 拓展边界类查询：偏知识 / 深度。排序只看作者含金量。
KNOWLEDGE_QUERIES = [
    "有哪些反常识的科学知识",
    "有哪些冷门但重要的知识",
    "有哪些改变认知的科普",
    "经济学中有哪些反直觉的现象",
    "神经科学有哪些最新研究",
    "有哪些深刻的历史真相",
    "心理学有哪些实用的研究结论",
    "物理学中有哪些迷人的概念",
    "有哪些值得反复阅读的高质量回答",
]

MEME_DECODE_SYSTEM = """你是一个“梗雷达”。用户会给你一条从知乎搜到的高赞搞笑内容（标题/摘要/赞数）。
无论这条内容里包含多少个段子/条目，你都**只输出一组、共两行**的整体解读，用简体中文，风格机智、略毒舌，但清晰第一，不要瞎编原文没有的内容：
- **笑点解码**：一句话说明它整体为什么好笑（反讽/谐音/荒诞/反转/共鸣等）。
- **可复用一句**：一句我能在聊天里直接甩出来的话。
严格只输出这两行，不要逐条拆解，不要重复标题或链接，不要加多余解释。"""

KNOWLEDGE_BRIEF_SYSTEM = """用户想“拓宽知识边界”，会给你一条来自某位有资历作者（博士/教授/优秀答主等）的知乎高质量内容（标题/作者认证/摘要）。
用简体中文输出两行，客观、精炼、有信息量，不要瞎编原文没有的内容：
- **核心看点**：一句话概括这条内容最值得知道的知识点/观点。
- **为什么值得读**：一句话说明作者视角或这条内容的独到之处（结合作者资历）。
只输出这两行，不要重复链接，不要加多余解释。"""


# ----------------------------- 结构化数据 -----------------------------


@dataclass
class HotEntry:
    item: HotItem
    answers: List[SearchItem] = field(default_factory=list)


@dataclass
class Pick:
    item: SearchItem
    note: Optional[str] = None  # 搞笑=笑点解码；拓展边界=核心看点


@dataclass
class DigestData:
    date_str: str
    generated_at: str
    hot: List[HotEntry] = field(default_factory=list)
    funny: List[Pick] = field(default_factory=list)
    knowledge: List[Pick] = field(default_factory=list)


# ----------------------------- 工具函数 -----------------------------


def _fmt_votes(n: int) -> str:
    if n >= 10000:
        return f"{n/10000:.1f}万赞"
    return f"{n}赞"


def _truncate(text: str, limit: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


# API 的 ContentText 是摘要（段子约 300+ 字、知识类可达 1000+ 字）。
# 完整展示（保留换行），只在极端长度时做安全截断。
_CONTENT_CAP = 4000


def _full_text(text: str) -> str:
    """完整文本（保留换行），供 Markdown 使用。"""
    text = (text or "").strip()
    if len(text) > _CONTENT_CAP:
        text = text[: _CONTENT_CAP - 1] + "…"
    return text


def _content_html(text: str) -> str:
    """完整文本转 HTML：转义 + 换行变 <br>。"""
    return _esc(_full_text(text)).replace("\n", "<br>")


def _limit_per_author(items: List[SearchItem], max_per_author: int) -> List[SearchItem]:
    if max_per_author <= 0:
        return items
    counts: dict = {}
    out: List[SearchItem] = []
    for it in items:
        key = it.author_name or it.author_badge_text or id(it)
        if counts.get(key, 0) >= max_per_author:
            continue
        counts[key] = counts.get(key, 0) + 1
        out.append(it)
    return out


def _llm_enrich(
    items: List[SearchItem],
    *,
    system_prompt: str,
    include_badge: bool,
    api_key: Optional[str],
    model: str,
) -> List[Optional[str]]:
    if not api_key or not items:
        return [None] * len(items)
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return [None] * len(items)

    client = OpenAI(api_key=api_key)
    out: List[Optional[str]] = []
    for it in items:
        user = f"标题：{it.title}\n"
        if include_badge and it.author_badge_text:
            user += f"作者认证：{it.author_badge_text}\n"
        user += f"赞数：{it.vote_up_count}\n摘要：{_truncate(it.content_text, 500)}"
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user},
                ],
                temperature=0.7,
            )
            out.append((resp.choices[0].message.content or "").strip() or None)
        except Exception:
            out.append(None)
    return out


# ----------------------------- 数据收集 -----------------------------


def collect_digest_data(
    client: ZhihuClient,
    *,
    hot_limit: int = 15,
    answers_per_topic: int = 2,
    funny_queries: Optional[List[str]] = None,
    funny_top_n: int = 8,
    funny_min_votes: int = 50,
    knowledge_queries: Optional[List[str]] = None,
    knowledge_top_n: int = 8,
    knowledge_min_credibility: float = 2.0,
    authority_weight: float = 4.0,
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
    date_str: Optional[str] = None,
) -> DigestData:
    date_str = date_str or datetime.now().astimezone().strftime("%Y-%m-%d")
    funny_q = funny_queries or FUNNY_QUERIES
    knowledge_q = knowledge_queries or KNOWLEDGE_QUERIES

    data = DigestData(
        date_str=date_str,
        generated_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
    )

    # 一、热榜 + 每个话题的高赞回答
    for h in client.hot_list(limit=hot_limit):
        answers = top_answers_for_topic(client, h.title, count=10, top_n=answers_per_topic)
        data.hot.append(HotEntry(item=h, answers=answers))

    # 二、搞笑精选（纯热度）
    funny_items = search_fanout(
        client, funny_q, count_per_query=10, min_votes=funny_min_votes, rank_by="engagement"
    )[:funny_top_n]
    funny_notes = _llm_enrich(
        funny_items, system_prompt=MEME_DECODE_SYSTEM, include_badge=False, api_key=api_key, model=model
    )
    data.funny = [Pick(item=it, note=note) for it, note in zip(funny_items, funny_notes)]

    # 三、拓展边界（作者含金量主导，每位作者最多 1 条）
    knowledge_ranked = search_fanout(
        client,
        knowledge_q,
        count_per_query=10,
        min_votes=0,
        min_credibility=knowledge_min_credibility,
        rank_by="authority",
        authority_weight=authority_weight,
    )
    knowledge_items = _limit_per_author(knowledge_ranked, max_per_author=1)[:knowledge_top_n]
    knowledge_notes = _llm_enrich(
        knowledge_items, system_prompt=KNOWLEDGE_BRIEF_SYSTEM, include_badge=True, api_key=api_key, model=model
    )
    data.knowledge = [Pick(item=it, note=note) for it, note in zip(knowledge_items, knowledge_notes)]

    return data


# ----------------------------- Markdown 渲染 -----------------------------


def _author_line_md(it: SearchItem, *, show_credibility: bool = False) -> str:
    bits = [f"**{it.author_name or '匿名'}**"]
    if show_credibility and it.author_badge_text:
        bits.append(f"🎓 {it.author_badge_text}")
        cred = author_credibility(it)
        if cred > 0:
            bits.append(f"含金量估算{cred:.1f}")
    bits.append(f"{_fmt_votes(it.vote_up_count)} · {it.comment_count}评论")
    return " · ".join(bits)


def render_markdown(data: DigestData) -> str:
    lines: List[str] = []
    lines.append(f"# 知乎每日速览 — {data.date_str}")
    lines.append("")
    lines.append(f"> 自动生成于 {data.generated_at} · 数据来源：知乎开放平台 API")
    lines.append(">")
    lines.append("> **口径说明**：知乎官方只返回作者的**认证文案**（如“北京大学 神经科学博士”）和一个当前恒为 1、无区分度的 `AuthorityLevel`，并**不提供**作者评分。")
    lines.append("> 文中的 **“含金量估算”是本工具自己算的启发式分数**（从官方认证文案里按博士/硕士/优秀答主等关键词加权得出），**并非知乎官方分**，仅用于“拓展边界”板块的排序参考。")
    lines.append("")

    lines.append(f"## 一、今日热榜（Top {len(data.hot)}）")
    lines.append("")
    if not data.hot:
        lines.append("_热榜暂无数据。_\n")
    for i, entry in enumerate(data.hot, start=1):
        h = entry.item
        lines.append(f"### {i}. {h.title}")
        if h.summary:
            lines.append(_truncate(h.summary, 160))
        lines.append(f"[🔗 查看话题]({h.url})")
        lines.append("")
        if entry.answers:
            lines.append("**高赞回答：**")
            lines.append("")
            for a in entry.answers:
                lines.append(f"- {_author_line_md(a)}")
                if a.content_text:
                    # 嵌套列表里保持单行，但展示完整摘要。
                    lines.append(f"  - {' '.join(_full_text(a.content_text).split())}")
                lines.append(f"  - [🔗 阅读原文]({a.clean_url})")
            lines.append("")

    lines.append("## 二、搞笑精选（神回复 · 沙雕新闻 · 高赞段子）")
    lines.append("")
    lines.append("_排序：纯按赞数 / 评论热度。_\n")
    if not data.funny:
        lines.append("_今天没搜到达到赞数门槛的搞笑内容。_\n")
    for i, pick in enumerate(data.funny, start=1):
        m = pick.item
        lines.append(f"### {i}. {m.title}")
        lines.append(_author_line_md(m, show_credibility=False))
        lines.append("")
        if m.content_text:
            lines.append(_full_text(m.content_text))
            lines.append("")
        if pick.note:
            lines.append(pick.note)
            lines.append("")
        lines.append(f"[🔗 阅读原文]({m.clean_url})")
        lines.append("")

    lines.append("## 三、拓展边界（高含金量作者）")
    lines.append("")
    lines.append("_排序：纯按“含金量估算”（本工具据官方认证文案自算，非知乎官方分）。哪怕话题冷门、赞数不高，作者够硬就上。_\n")
    if not data.knowledge:
        lines.append("_今天没搜到达到含金量门槛的作者内容。_\n")
    for i, pick in enumerate(data.knowledge, start=1):
        k = pick.item
        lines.append(f"### {i}. {k.title}")
        lines.append(_author_line_md(k, show_credibility=True))
        lines.append("")
        if k.content_text:
            lines.append(_full_text(k.content_text))
            lines.append("")
        if pick.note:
            lines.append(pick.note)
            lines.append("")
        lines.append(f"[🔗 阅读原文]({k.clean_url})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ----------------------------- HTML 渲染 (Morning Brew 风) -----------------------------

_BLUE = "#1a6dff"
_INK = "#1f2328"
_MUTE = "#6b7280"
_LINE = "#eceef1"
_BG = "#f4f5f7"
_FONT = ('-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",'
         '"Hiragino Sans GB","Microsoft YaHei",sans-serif')


def _esc(s: str) -> str:
    return _html.escape(s or "")


def _img(url: str, *, size: int, round_: bool = False, link: str = "") -> str:
    if not url:
        return ""
    radius = "50%" if round_ else "8px"
    tag = (
        f'<img src="{_esc(url)}" width="{size}" height="{size}" '
        f'style="width:{size}px;height:{size}px;object-fit:cover;border-radius:{radius};'
        f'display:block;border:1px solid {_LINE}" alt="">'
    )
    if link:
        return f'<a href="{_esc(link)}" style="text-decoration:none">{tag}</a>'
    return tag


def _section_label(text: str) -> str:
    return (
        f'<div style="color:{_BLUE};font-weight:800;font-size:13px;letter-spacing:1.5px;'
        f'text-transform:uppercase;margin:34px 0 10px">{_esc(text)}</div>'
    )


def _note_box(note: str, *, accent: str) -> str:
    if not note:
        return ""
    inner = md_inline_to_html(note)
    return (
        f'<div style="background:#f7f8fa;border-left:3px solid {accent};'
        f'border-radius:6px;padding:8px 12px;margin:10px 0;font-size:14px;'
        f'line-height:1.7;color:#374151">{inner}</div>'
    )


def _link_button(url: str, text: str) -> str:
    return (
        f'<a href="{_esc(url)}" style="display:inline-block;color:{_BLUE};'
        f'font-size:13px;font-weight:600;text-decoration:none;margin-top:6px">{_esc(text)} →</a>'
    )


def _author_html(it: SearchItem, *, show_credibility: bool) -> str:
    """作者一行：头像 + 名字（+认证/含金量）+ 热度。"""
    avatar = _img(it.author_avatar, size=36, round_=True, link=it.clean_url)
    name = f'<span style="font-weight:700;color:{_INK}">{_esc(it.author_name or "匿名")}</span>'
    meta_bits = []
    if show_credibility and it.author_badge_text:
        meta_bits.append(
            f'<span style="color:{_BLUE};font-weight:600">🎓 {_esc(it.author_badge_text)}</span>'
        )
        cred = author_credibility(it)
        if cred > 0:
            meta_bits.append(f'<span style="color:{_MUTE}">含金量估算{cred:.1f}</span>')
    meta_bits.append(f'<span style="color:{_MUTE}">{_fmt_votes(it.vote_up_count)} · {it.comment_count}评论</span>')
    meta = " · ".join(meta_bits)
    avatar_cell = (
        f'<td width="44" valign="top" style="padding-right:10px">{avatar}</td>' if avatar else ""
    )
    return (
        '<table cellpadding="0" cellspacing="0" style="margin:2px 0 6px"><tr>'
        f"{avatar_cell}"
        f'<td valign="top" style="font-size:13px;line-height:1.6">{name}<br>{meta}</td>'
        "</tr></table>"
    )


def _card_open() -> str:
    return (
        '<div style="border:1px solid ' + _LINE + ';border-radius:10px;padding:16px 18px;margin:14px 0">'
    )


def render_html(data: DigestData) -> str:
    P = []  # parts
    P.append(f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    P.append('<meta name="viewport" content="width=device-width, initial-scale=1"></head>')
    P.append(f'<body style="margin:0;padding:0;background:{_BG}">')
    P.append(f'<div style="max-width:680px;margin:0 auto;padding:20px 14px 48px;font-family:{_FONT}">')

    # 顶部品牌横幅
    P.append(
        f'<div style="background:{_BLUE};border-radius:14px;padding:26px 20px;text-align:center">'
        f'<div style="color:#fff;font-size:24px;font-weight:800;letter-spacing:2px">知乎每日速览</div>'
        f'<div style="color:#d6e4ff;font-size:13px;margin-top:6px">{_esc(data.date_str)} · 每日梗 + 拓展知识边界</div>'
        "</div>"
    )

    # 主体卡片
    P.append(
        '<div style="background:#fff;border-radius:0 0 14px 14px;padding:22px 22px 30px;'
        f'color:{_INK};font-size:15px;line-height:1.75">'
    )

    # 今日速览 TOC
    P.append(
        f'<p style="margin:4px 0 2px"><strong>今日速览。</strong>'
        f'一份不用刷手机的知乎摘要——上面有梗，下面涨知识。</p>'
        f'<p style="margin:6px 0;color:{_MUTE};font-size:14px">今天为你准备了：</p>'
        '<ul style="margin:6px 0 0;padding-left:20px;font-size:14px">'
        f'<li>热榜 <strong>{len(data.hot)}</strong> 条 + 代表性高赞回答</li>'
        f'<li>搞笑精选 <strong>{len(data.funny)}</strong> 条（纯按赞/评论）</li>'
        f'<li>拓展边界 <strong>{len(data.knowledge)}</strong> 位硬核作者（按含金量估算）</li>'
        "</ul>"
    )
    P.append(
        f'<div style="margin:14px 0 0;padding:8px 12px;background:#f7f8fa;border-radius:6px;'
        f'font-size:12px;color:{_MUTE};line-height:1.6">口径说明：知乎官方不提供作者评分；'
        f'“含金量估算”是本工具据官方认证文案（博士/硕士/优秀答主…）自算的启发式分，仅供“拓展边界”排序参考。</div>'
    )

    # ---- 一、今日热榜 ----
    P.append(_section_label(f"今日热榜 · Top {len(data.hot)}"))
    for i, entry in enumerate(data.hot, start=1):
        h = entry.item
        thumb = _img(h.thumbnail_url, size=96, link=h.url) if h.thumbnail_url else ""
        text_col = (
            f'<div style="font-size:16px;font-weight:700;margin-bottom:4px">'
            f'<span style="color:{_BLUE}">{i}.</span> '
            f'<a href="{_esc(h.url)}" style="color:{_INK};text-decoration:none">{_esc(h.title)}</a></div>'
        )
        if h.summary:
            text_col += f'<div style="font-size:13px;color:{_MUTE};line-height:1.6">{_esc(_truncate(h.summary, 300))}</div>'
        if thumb:
            row = (
                '<table cellpadding="0" cellspacing="0" width="100%"><tr>'
                f'<td valign="top">{text_col}</td>'
                f'<td width="106" valign="top" style="padding-left:10px">{thumb}</td>'
                "</tr></table>"
            )
        else:
            row = text_col
        P.append(_card_open())
        P.append(row)
        for a in entry.answers:
            P.append(
                f'<div style="margin-top:10px;padding-top:10px;border-top:1px dashed {_LINE}">'
            )
            P.append(_author_html(a, show_credibility=False))
            if a.content_text:
                P.append(
                    f'<div style="font-size:14px;color:#374151;line-height:1.75">{_content_html(a.content_text)}</div>'
                )
            P.append(_link_button(a.clean_url, "阅读原文"))
            P.append("</div>")
        P.append("</div>")

    # ---- 二、搞笑精选 ----
    P.append(_section_label("搞笑精选 · 神回复 / 沙雕 / 段子"))
    P.append(f'<div style="font-size:12px;color:{_MUTE};margin:-4px 0 4px">排序：纯按赞数 / 评论热度</div>')
    for i, pick in enumerate(data.funny, start=1):
        m = pick.item
        P.append(_card_open())
        P.append(
            f'<div style="font-size:16px;font-weight:700;margin-bottom:2px">'
            f'<span style="color:{_BLUE}">{i}.</span> {_esc(m.title)}</div>'
        )
        P.append(_author_html(m, show_credibility=False))
        if m.content_text:
            P.append(
                f'<div style="font-size:14px;color:#374151;line-height:1.75">{_content_html(m.content_text)}</div>'
            )
        P.append(_note_box(pick.note or "", accent="#e0803a"))
        P.append(_link_button(m.clean_url, "阅读原文"))
        P.append("</div>")

    # ---- 三、拓展边界 ----
    P.append(_section_label("拓展边界 · 高含金量作者"))
    P.append(f'<div style="font-size:12px;color:{_MUTE};margin:-4px 0 4px">排序：纯按“含金量估算”，作者够硬就上（哪怕赞数不高）</div>')
    for i, pick in enumerate(data.knowledge, start=1):
        k = pick.item
        P.append(_card_open())
        P.append(
            f'<div style="font-size:16px;font-weight:700;margin-bottom:2px">'
            f'<span style="color:{_BLUE}">{i}.</span> {_esc(k.title)}</div>'
        )
        P.append(_author_html(k, show_credibility=True))
        if k.content_text:
            P.append(
                f'<div style="font-size:14px;color:#374151;line-height:1.75">{_content_html(k.content_text)}</div>'
            )
        P.append(_note_box(pick.note or "", accent=_BLUE))
        P.append(_link_button(k.clean_url, "阅读原文"))
        P.append("</div>")

    # footer
    P.append(
        f'<div style="margin-top:28px;padding-top:14px;border-top:1px solid {_LINE};'
        f'font-size:12px;color:{_MUTE};text-align:center">'
        f'自动生成于 {_esc(data.generated_at)} · 数据来源：知乎开放平台 API</div>'
    )

    P.append("</div></div></body></html>")
    return "".join(P)


# ----------------------------- 兼容旧接口 -----------------------------


def build_daily_document(client: ZhihuClient, **kwargs) -> str:
    """向后兼容：返回 Markdown 文档字符串。"""
    return render_markdown(collect_digest_data(client, **kwargs))
