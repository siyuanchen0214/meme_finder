# Product Brief — Daily Humor Digest (Meme Finder)

## 1) One-line pitch
A daily, automated digest that summarizes new content from creators I approve—so I stay funny and culturally aware without doomscrolling.

## 2) The core problem (the conflict)
I want to constantly learn and protect my attention, so I avoid spending time on social media.
But I also need up-to-date meme/joke context to socialize well and have things to talk about.

Today, getting that context requires hours of scrolling across multiple apps. I want the context without the scroll.

## 3) Target user & context
- Primary user: me (single-player v1).
- Context: mornings and before social gatherings; I want “conversation ammo” without time sink.
- Input model: a curated whitelist of creators/accounts I personally approve (humor-aligned).
- Platforms (initially flexible): YouTube, Bilibili, 小红书, 知乎, Instagram Reels (and similar).

## 4) Product principles
- Curated > algorithmic: only whitelisted sources by default.
- Passive delivery: I should do nothing except receive the digest.
- Fast to consume: maximize “context per minute.”
- Witty but clear: sarcasm and dark humor are allowed; comprehension comes first.

## 5) MVP: what feels like magic
A machine runs once per day and sends me a single digest (email first) containing:
- many new items (prioritize breadth)
- shallow, fast summaries that give enough context to understand the joke
- links to the originals if I want to go deeper

### Delivery requirements (locked)
- Delivery channel: Email (v1).
- Delivery time: 6:00am (local time) every day.
- Languages: mixed (Chinese + English; keep the original flavor).

## 6) Output spec (what the AI must generate)
The digest is a list of items. Each item should be short by default.

For each content item, output:
- Title / creator / platform
- 1–2 sentence summary (“what happened”)
- “Joke decoded” (1 line): why it’s funny (reference/irony/absurdity/etc.)
- Context (optional, 1–2 bullets): only if needed to understand it
- Reusable line (optional): one-liner I can say in conversation
- Source link

### Tone constraints
- Default voice: sarcastic (witty, slightly dry).
- Allowed: dark humor (deadpan, edgy).
- Must stay readable: never sacrifice clarity for the joke.
- “Punch up” preference: if there’s a target, aim at yourself, systems, or absurd situations—not vulnerable individuals.
- Avoid: harassment, doxxing, dehumanizing language, or inciting violence.
- If a piece of content is already extreme, summarize it neutrally first, then add one optional dark-humor line.

### Safety filters
- None (include everything). Goal is witty, not sanitized.

## 7) Depth preference (v1)
- Prefer more items with shallow summaries.
- Allow “expand” sections for the top N items (optional later), but default is fast scan.

## 8) Success metrics / OKRs (measurable)
### Objective A: deliver a reliable daily digest
- KR1: Digest arrives by 6:00am daily (≥ 95% on-time over 30 days).
- KR2: Digest can be read in ≤ 10 minutes.

### Objective B: keep it automated and low effort
- KR1: Runs once/day with zero manual steps after setup.
- KR2: Handles at least 20 whitelisted sources across ≥ 2 platforms.

### Objective C: make it conversation-ready and actually funny
- KR1: ≥ 70% of items: “I understand the joke and could explain it.”
- KR2: ≥ 40% of items: “This is genuinely funny / witty.”
- KR3: Each item includes a “why it’s funny” line (no missing joke decoding).

## 9) Non-goals (for MVP)
- Building a social feed/community.
- Content creation/editing tools.
- Recommendations beyond the whitelist.
- Deep long-form analysis (opt-in later).

## 10) Open questions (later)
- Should “top items” get deeper summaries automatically?
- Do we want per-platform quotas or just “what’s new”?
- Should the digest be grouped by topic, creator, or platform?

