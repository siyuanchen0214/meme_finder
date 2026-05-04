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
- `OPENAI_MODEL` (optional; defaults to `gpt-4.1-mini`)

### Schedule time
GitHub Actions cron is **UTC**. The workflow is set to:
- `0 22 * * *` (22:00 UTC) ≈ **06:00 (UTC+8)** the next day

If you’re not in UTC+8, change the cron accordingly.

## Notes / limitations (MVP reality check)
- “Any platform” is not implemented yet; MVP uses RSS because it’s low cost and automation-friendly.
- Next step is adding platform-specific connectors (Bilibili/小红书/知乎/IG) and better dedupe/state.

