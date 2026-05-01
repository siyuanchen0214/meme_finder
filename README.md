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

2) Configure sources

```bash
cp sources.yaml.example sources.yaml
```

Edit `sources.yaml` to include your approved creators.

3) Configure email + (optional) AI

```bash
cp .env.example .env
```

Fill in `.env`.

4) Run (dry-run prints to stdout)

```bash
python -m meme_finder run --sources sources.yaml --dry-run
```

Send email:

```bash
python -m meme_finder run --sources sources.yaml
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

