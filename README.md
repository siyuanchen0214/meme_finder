# meme_finder

Daily humor digest from whitelisted creators—so you can stay funny without doomscrolling.

See `PRODUCT_BRIEF.md` for the product framing.

## MVP (what exists right now)
- Fetches new posts from whitelisted **RSS/Atom feeds** (including YouTube channel RSS).
- Generates a short **sarcastic** digest (AI if `OPENAI_API_KEY` is set; deterministic fallback otherwise).
- Delivers the digest by **email (SMTP)**.
- Can run locally or on a **daily GitHub Actions schedule** (6:00am UTC+8 by default).
- Keeps a small persistent **memory** to avoid sending duplicates/near-duplicates.

## Quick start (local)
1) Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Tests (optional)

```bash
pip install -r requirements-dev.txt
pytest
```

2) Configure sources

```bash
cp sources.yaml.example sources.yaml
```

Edit `sources.yaml` to include your approved creators.

3) Configure email + (optional) AI

Create `.env` in the repo root (it is gitignored), for example:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=your_gmail_app_password
EMAIL_FROM=you@gmail.com
EMAIL_TO=you@gmail.com
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_WHISPER_MODEL=whisper-1
```

4) Run (dry-run prints to stdout)

```bash
python -m meme_finder run --sources sources.yaml --dry-run
```

Send email:

```bash
python -m meme_finder run --sources sources.yaml
```

### One YouTube video → email (full audio → OpenAI STT → humor extraction)

`run-video` defaults to **`--transcription-mode openai_audio`**: download audio with **yt-dlp**, transcribe with **OpenAI** (`OPENAI_WHISPER_MODEL`, usually `whisper-1`), then extract multiple joke “bits” with your chat model (`OPENAI_MODEL`).

**System requirements:** install **ffmpeg** (e.g. `brew install ffmpeg`) — needed for audio extract/compression and for splitting very large uploads.

```bash
python -m meme_finder run-video --url "https://www.youtube.com/watch?v=VIDEO_ID" --model gpt-4o-mini
```

- Preview without email: `--dry-run`
- Use YouTube captions only (no download): `--transcription-mode captions`
- Cheap default for daily `run`: `--transcription-mode auto` (captions first, then STT if missing)
- No truncation before joke extraction: `--transcript-chars 0` (default for `run-video`)

### Full daily digest transcription modes

```bash
python -m meme_finder run --sources sources.yaml --transcription-mode auto
```

### 知乎每日速览 (`zhihu-daily`)

Pulls three sections from the official Zhihu Open Platform API (`developer.zhihu.com`) and writes a Markdown document (optionally emails it):

1. **今日热榜** — top hot-list topics, each with its top-voted answer(s).
2. **搞笑精选** — 神回复 / 沙雕新闻 / 高赞段子, ranked **purely by votes/comments** (author ignored).
3. **拓展边界** — knowledge-oriented picks ranked **purely by author credibility** (博士/教授/优秀答主…), so an impressive author surfaces even on a niche topic with modest votes.

The two discovery sections use **separate, non-mixed ranking signals** by design.

Requires `ZHIHU_ACCESS_SECRET` in `.env` (申请自 developer.zhihu.com 个人中心).

```bash
python -m meme_finder zhihu-daily
```

The document is written to `digests/zhihu-YYYY-MM-DD.md` and printed to stdout.

Useful flags:
- `--hot-limit N` how many hot-list topics (default 15, max 30)
- `--answers-per-topic N` top-voted answers per hot topic (default 2)
- `--funny-top N` how many funny picks (default 8) · `--funny-min-votes N` (default 50)
- `--knowledge-top N` how many knowledge picks (default 8)
- `--knowledge-min-cred F` minimum author credibility for knowledge picks (default 2.0 — must have a real credential)
- `--authority-weight F` how author-dominant the knowledge section is (default 4.0)
- `--no-llm` skip LLM enrichment (笑点解码 for funny / 核心看点 for knowledge)
- `--email` also send the document to `EMAIL_TO`
- `--no-open` don't echo the document to stdout

**Credibility signal:** the Zhihu API's `AuthorityLevel` field is currently constant (`"1"`) during the invite-only beta, so author "含金量" is derived from the `AuthorBadgeText` credential text (院士/教授 > 博士 > 硕士 > 优秀答主 > 普通认证, plus a bonus for top schools/institutions). Each author appears at most once in the knowledge section for variety.

### Memory / dedupe
By default the app stores what it has sent in `.state/memory.json` and skips:
- exact repeats (same URL already sent)
- near repeats (same creator + very similar title already sent)

It also does an optional **LLM similarity check** (when `OPENAI_API_KEY` is set) to skip items that are “very very similar” to previously sent summaries.

### Minimum daily amount
The runner will backfill older content if needed to hit a minimum, default **10 items** (cap **20**):

```bash
python -m meme_finder run --sources sources.yaml --min-items 10 --max-items 20
```

## Automation (GitHub Actions)
There is a scheduled workflow at `.github/workflows/daily-digest.yml`.

### Add repo secrets
In GitHub repo settings → Secrets and variables → Actions, add:
- `SOURCES_YAML` (the full contents of your `sources.yaml`)
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO`
- `OPENAI_API_KEY` (optional; leave unset to use fallback)
- `OPENAI_MODEL` (optional; defaults to `gpt-4o-mini`)

### Schedule time
GitHub Actions cron is **UTC**. The workflow is set to:
- `0 22 * * *` (22:00 UTC) ≈ **06:00 (UTC+8)** the next day

If you’re not in UTC+8, change the cron accordingly.

## Notes / limitations (MVP reality check)
- “Any platform” is not implemented yet; MVP uses RSS because it’s low cost and automation-friendly.
- Next step is adding platform-specific connectors (Bilibili/小红书/知乎/IG) and better dedupe/state.

