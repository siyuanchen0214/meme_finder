"""知乎开放平台 (developer.zhihu.com) API 客户端。

封装两个数据接口：
- hot_list:      GET /api/v1/content/hot_list       当前知乎热榜
- zhihu_search:  GET /api/v1/content/zhihu_search    站内内容搜索（问题/回答/文章）

鉴权：请求头 Authorization: Bearer <access_secret> + X-Request-Timestamp（秒级）。

搜索接口没有“按赞排序”的参数（默认按相关度返回、每次最多 10 条），
因此“找高赞”的策略在本模块里用客户端侧的多查询扇出 + 去重 + 加权重排实现。
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

BASE_URL = "https://developer.zhihu.com"
HOT_LIST_PATH = "/api/v1/content/hot_list"
SEARCH_PATH = "/api/v1/content/zhihu_search"

DEFAULT_TIMEOUT = 20


class ZhihuAPIError(RuntimeError):
    """知乎接口返回非 0 Code 或 HTTP 错误时抛出。"""


@dataclass(frozen=True)
class HotItem:
    title: str
    url: str
    thumbnail_url: str = ""
    summary: str = ""


@dataclass(frozen=True)
class SearchItem:
    title: str
    content_type: str
    content_id: str
    content_text: str
    url: str
    comment_count: int
    vote_up_count: int
    author_name: str
    author_avatar: str
    author_badge_text: str
    edit_time: int
    authority_level: str
    ranking_score: float
    comments: List[str] = field(default_factory=list)

    @property
    def clean_url(self) -> str:
        """去掉溯源 utm 参数，便于展示与去重。"""
        if not self.url:
            return self.url
        parsed = urllib.parse.urlsplit(self.url)
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _parse_search_item(raw: dict) -> SearchItem:
    comments = []
    for c in raw.get("CommentInfoList") or []:
        content = (c or {}).get("Content")
        if content:
            comments.append(str(content))
    return SearchItem(
        title=str(raw.get("Title") or "").strip(),
        content_type=str(raw.get("ContentType") or ""),
        content_id=str(raw.get("ContentID") or ""),
        content_text=str(raw.get("ContentText") or "").strip(),
        url=str(raw.get("Url") or ""),
        comment_count=int(raw.get("CommentCount") or 0),
        vote_up_count=int(raw.get("VoteUpCount") or 0),
        author_name=str(raw.get("AuthorName") or "").strip(),
        author_avatar=str(raw.get("AuthorAvatar") or "").strip(),
        author_badge_text=str(raw.get("AuthorBadgeText") or "").strip(),
        edit_time=int(raw.get("EditTime") or 0),
        authority_level=str(raw.get("AuthorityLevel") or ""),
        ranking_score=float(raw.get("RankingScore") or 0.0),
        comments=comments,
    )


class ZhihuClient:
    def __init__(self, access_secret: str, *, base_url: str = BASE_URL, timeout: int = DEFAULT_TIMEOUT):
        if not access_secret:
            raise ValueError("ZHIHU_ACCESS_SECRET is required to call the Zhihu API.")
        self._secret = access_secret
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _get(self, path: str, params: dict) -> dict:
        url = self._base_url + path + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._secret}",
                "X-Request-Timestamp": str(int(time.time())),
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            raise ZhihuAPIError(f"HTTP {e.code} calling {path}: {body}") from e
        except urllib.error.URLError as e:
            raise ZhihuAPIError(f"Network error calling {path}: {e}") from e

        code = payload.get("Code")
        if code != 0:
            raise ZhihuAPIError(
                f"Zhihu API returned Code={code} Message={payload.get('Message')!r} for {path}"
            )
        return payload.get("Data") or {}

    def hot_list(self, limit: int = 30) -> List[HotItem]:
        """获取当前知乎热榜（默认 30，最大 30）。"""
        data = self._get(HOT_LIST_PATH, {"Limit": max(1, min(int(limit), 30))})
        items = []
        for raw in data.get("Items") or []:
            items.append(
                HotItem(
                    title=str(raw.get("Title") or "").strip(),
                    url=str(raw.get("Url") or ""),
                    thumbnail_url=str(raw.get("ThumbnailUrl") or ""),
                    summary=str(raw.get("Summary") or "").strip(),
                )
            )
        return items

    def search(self, query: str, count: int = 10) -> List[SearchItem]:
        """站内搜索（默认 10，最大 10）。返回按接口相关度排序的结果。"""
        query = (query or "").strip()
        if not query:
            return []
        data = self._get(SEARCH_PATH, {"Query": query, "Count": max(1, min(int(count), 10))})
        return [_parse_search_item(raw) for raw in (data.get("Items") or [])]


# 默认让“作者含金量”成为主导信号：拓宽知识边界优先于纯热度。
DEFAULT_AUTHORITY_WEIGHT = 4.0

# 从 AuthorBadgeText（作者认证文案）里解析作者含金量。
# 说明：知乎开放平台邀测阶段 AuthorityLevel 恒为 "1"，无区分度，
# 因此真正的“作者有多厉害”信号来自认证文案里的头衔/资质关键词。
# 取命中关键词的最高分（避免长文案叠加虚高），再叠加名校 / 荣誉加分。
_CREDENTIAL_WEIGHTS = [
    (("院士",), 6.0),
    (("教授", "博导", "首席科学家", "主任医师", "研究员"), 5.0),
    (("博士", "phd", "ph.d", "博士后"), 4.0),
    (("硕士", "master"), 3.0),
    (("优秀答主", "优秀回答者", "十佳答主", "年度答主"), 3.0),
    (("答主", "知势榜", "成长力榜"), 2.0),
    (("作者", "译者", "主编"), 2.0),
    (("认证", "官方", "机构", "蓝V", "蓝v"), 2.0),
    (("创始人", "ceo", "cto", "法定代表人", "总监", "总裁", "合伙人", "工程师", "分析师", "律师", "医生"), 2.0),
]

# 名校 / 顶尖机构额外加分（作者更“硬”）。
_PRESTIGE_KEYWORDS = (
    "中科院", "中国科学院", "清华", "北京大学", "北大", "复旦", "浙江大学",
    "上海交通大学", "中国科学技术大学", "南京大学", "985", "双一流", "常春藤",
    "mit", "stanford", "斯坦福", "harvard", "哈佛", "剑桥", "牛津", "berkeley",
)


def parse_authority_level(raw: str) -> float:
    """把 AuthorityLevel 字符串解析成数值；无法解析时返回 0。"""
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def author_credibility(item: SearchItem) -> float:
    """从认证文案 + AuthorityLevel 估算“作者含金量”（0 起步，越高越厉害）。"""
    badge = (item.author_badge_text or "").lower()
    score = 0.0
    if badge:
        # 有认证文案本身就说明是被平台标注的答主，给一个基线分。
        score += 1.0
        best = 0.0
        for keywords, weight in _CREDENTIAL_WEIGHTS:
            if any(k in badge for k in keywords):
                best = max(best, weight)
        score += best
        if any(k in badge for k in _PRESTIGE_KEYWORDS):
            score += 2.0
    # AuthorityLevel 目前恒为 1、无区分度，但保留少量权重以便平台启用后自动生效。
    score += parse_authority_level(item.authority_level) * 0.5
    return score


def hotness_score(
    item: SearchItem,
    *,
    now: Optional[float] = None,
    authority_weight: float = DEFAULT_AUTHORITY_WEIGHT,
) -> float:
    """综合分：**作者含金量为主导**，赞数/评论/新鲜度为辅。

    含金量项用线性权重放大，而赞数/评论取 log 压缩，
    这样一个高含金量作者（博士/教授/优秀答主…）即使话题冷门、赞数中等，
    也能排到高热但低含金量内容前面。`authority_weight` 越大越偏向“作者厉害”。
    """
    now = now if now is not None else time.time()
    # 主导项：作者含金量（线性、可调权重）。
    score = author_credibility(item) * authority_weight
    # 辅助项：热度（log 压缩，避免超高赞碾压含金量信号）。
    score += math.log1p(max(0, item.vote_up_count)) * 1.0
    score += math.log1p(max(0, item.comment_count)) * 0.3
    if item.edit_time:
        age_days = max(0.0, (now - item.edit_time) / 86400.0)
        # 近 30 天内有正向加分，越新越高；30 天后基本归零。
        score += max(0.0, 0.5 * (1.0 - age_days / 30.0))
    return score


def dedupe_items(items: List[SearchItem]) -> List[SearchItem]:
    """按 ContentID（优先）或去 utm 的 URL 去重，保留首次出现（赞数更高的先放）。"""
    seen = set()
    out: List[SearchItem] = []
    for it in items:
        key = it.content_id or it.clean_url or it.title
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def engagement_score(item: SearchItem) -> float:
    """纯热度分：以赞数为主、评论为辅（不考虑作者）。用于“搞笑类”排序。"""
    return math.log1p(max(0, item.vote_up_count)) * 1.0 + math.log1p(max(0, item.comment_count)) * 0.6


def search_fanout(
    client: ZhihuClient,
    queries: List[str],
    *,
    count_per_query: int = 10,
    min_votes: int = 0,
    min_credibility: float = 0.0,
    rank_by: str = "authority",
    authority_weight: float = DEFAULT_AUTHORITY_WEIGHT,
) -> List[SearchItem]:
    """对多个查询词扇出搜索，合并去重后重排。

    rank_by:
      - "engagement"：纯热度（赞/评论），用于搞笑类。
      - "authority" ：作者含金量主导，用于拓展边界类。
    min_credibility：只保留作者含金量 >= 该值的条目（拓展边界类用来确保“作者够硬”）。
    """
    collected: List[SearchItem] = []
    for q in queries:
        try:
            collected.extend(client.search(q, count=count_per_query))
        except ZhihuAPIError:
            # 单个查询失败不应中断整体流程。
            continue
    if min_votes > 0:
        collected = [it for it in collected if it.vote_up_count >= min_votes]
    if min_credibility > 0:
        collected = [it for it in collected if author_credibility(it) >= min_credibility]
    # 先按赞数降序，保证去重时保留高赞版本。
    collected.sort(key=lambda it: it.vote_up_count, reverse=True)
    deduped = dedupe_items(collected)
    if rank_by == "engagement":
        deduped.sort(key=engagement_score, reverse=True)
    else:
        deduped.sort(key=lambda it: hotness_score(it, authority_weight=authority_weight), reverse=True)
    return deduped


def top_answers_for_topic(
    client: ZhihuClient,
    topic_title: str,
    *,
    count: int = 10,
    top_n: int = 3,
    min_votes: int = 0,
) -> List[SearchItem]:
    """针对某个热榜话题，搜索并返回其下的**高赞**回答（热榜看热度，不看作者）。"""
    try:
        items = client.search(topic_title, count=count)
    except ZhihuAPIError:
        return []
    if min_votes > 0:
        items = [it for it in items if it.vote_up_count >= min_votes]
    items = dedupe_items(items)
    items.sort(key=engagement_score, reverse=True)
    return items[:top_n]
