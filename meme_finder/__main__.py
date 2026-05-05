from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from .config import load_app_env, load_config, load_email_from_env, load_openai_from_env
from .enrichment import fetch_youtube_oembed_title, get_youtube_video_id
from .dedupe_llm import llm_should_send
from .digest import render_digest
from .emailer import send_email
from .fetch_rss import fetch_all
from .state import MemoryStore, filter_new_items
from .summarize import summarize_items
from .types import Item


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="meme_finder", description="Daily humor digest from whitelisted sources.")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Fetch, summarize, and deliver the daily digest.")
    run.add_argument("--sources", default="sources.yaml", help="Path to sources YAML.")
    run.add_argument("--lookback-hours", type=int, default=24, help="How far back to fetch items.")
    run.add_argument("--dry-run", action="store_true", help="Print digest to stdout instead of emailing.")
    run.add_argument("--state-path", default=".state/memory.json", help="Path to persistent memory store.")
    run.add_argument("--min-items", type=int, default=10, help="Minimum items to send (may backfill older content).")
    run.add_argument("--max-items", type=int, default=20, help="Maximum items to send.")
    run.add_argument(
        "--no-transcript",
        action="store_true",
        help="Do not pull YouTube captions; use RSS title/snippet only.",
    )
    run.add_argument(
        "--transcript-chars",
        type=int,
        default=48_000,
        help="Max transcript characters per video before humor extraction (truncated beyond this).",
    )
    run.add_argument(
        "--transcription-mode",
        choices=["auto", "captions", "openai_audio"],
        default="auto",
        help="How to obtain transcript text: captions, full-audio OpenAI STT, or auto (captions then STT).",
    )

    rv = sub.add_parser(
        "run-video",
        help="Summarize a single YouTube URL (transcript when available) and email the digest.",
    )
    rv.add_argument("--url", required=True, help="YouTube watch URL.")
    rv.add_argument(
        "--label",
        default="YouTube (single-video test)",
        help="Display name for the source in the digest.",
    )
    rv.add_argument("--no-transcript", action="store_true")
    rv.add_argument(
        "--transcript-chars",
        type=int,
        default=0,
        help="Max transcript chars before humor extraction; use 0 for no truncation (recommended for STT).",
    )
    rv.add_argument(
        "--transcription-mode",
        choices=["auto", "captions", "openai_audio"],
        default="openai_audio",
        help="Default uses OpenAI speech-to-text on the full video audio (requires ffmpeg + yt-dlp).",
    )
    rv.add_argument(
        "--whisper-model",
        default=None,
        help="Override OPENAI_WHISPER_MODEL (default whisper-1).",
    )
    rv.add_argument(
        "--model",
        default=None,
        help="OpenAI model override (default: OPENAI_MODEL from .env).",
    )
    rv.add_argument("--dry-run", action="store_true")

    test = sub.add_parser("test-email", help="Send a one-line email to verify SMTP settings in .env.")
    test.add_argument(
        "--message",
        default="meme_finder SMTP test: if you see this, email delivery works.",
        help="Plain text body for the test message.",
    )

    return p


def cmd_run(args: argparse.Namespace) -> int:
    load_app_env()
    cfg = load_config(args.sources, require_email=not args.dry_run)
    use_transcript = not args.no_transcript

    store = MemoryStore.load(args.state_path)

    # Backfill strategy: widen the lookback window until we have enough novel items.
    lookbacks = [args.lookback_hours, 72, 168, 720, 8760]  # 1d, 3d, 7d, 30d, ~1y
    candidates = []
    seen_urls = set()
    for hrs in lookbacks:
        fetched = fetch_all(cfg.sources, lookback_hours=hrs)
        for it in fetched:
            if it.url and it.url in seen_urls:
                continue
            if it.url:
                seen_urls.add(it.url)
            candidates.append(it)

        # Layer 1 dedupe (exact title + URL + per-source title similarity)
        candidates = filter_new_items(candidates, store)

        # Stop widening once we have enough candidates to choose from.
        if len(candidates) >= max(args.min_items * 3, args.max_items):
            break

    # Summarize a larger pool, then LLM-dedupe down.
    candidates = candidates[: max(args.min_items * 4, args.max_items * 3, 60)]
    cap = None if int(args.transcript_chars) == 0 else int(args.transcript_chars)
    blocks = summarize_items(
        candidates,
        api_key=cfg.openai.api_key,
        model=cfg.openai.model,
        use_transcript=use_transcript,
        max_transcript_chars=cap,
        transcription_mode=args.transcription_mode,
        whisper_model=cfg.openai.whisper_model,
    )

    selected_items = []
    selected_blocks = []
    recent_texts = store.recent_sent_texts(limit=80)

    for it, block in zip(candidates, blocks):
        # Layer 2 dedupe (LLM "very similar" judge) — only meaningful if we have prior texts.
        send, _reason = llm_should_send(
            api_key=cfg.openai.api_key,
            model=cfg.openai.model,
            candidate_text=block,
            recent_texts=recent_texts,
        )
        if not send:
            continue

        selected_items.append(it)
        selected_blocks.append(block)
        recent_texts.append(block)

        if len(selected_items) >= args.max_items:
            break

    # If LLM dedupe was too strict and we still don't hit min, fail open and send more.
    if len(selected_items) < args.min_items:
        for it, block in zip(candidates, blocks):
            if it in selected_items:
                continue
            selected_items.append(it)
            selected_blocks.append(block)
            if len(selected_items) >= min(args.max_items, args.min_items):
                break

    digest = render_digest(selected_blocks)

    if args.dry_run:
        print(digest)
        for it, block in zip(selected_items, selected_blocks):
            store.mark_sent(it, sent_text=block)
        store.save()
        return 0

    subject = f"Daily Humor Digest — {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d')}"
    if not cfg.email:
        raise RuntimeError("Email config is missing.")
    send_email(cfg.email, subject=subject, body_markdown=digest)
    for it, block in zip(selected_items, selected_blocks):
        store.mark_sent(it, sent_text=block)
    store.save()
    return 0


def cmd_run_video(args: argparse.Namespace) -> int:
    load_app_env()
    if not get_youtube_video_id(args.url):
        raise SystemExit("Not a recognized YouTube watch URL.")

    openai_cfg = load_openai_from_env()
    if not openai_cfg.api_key:
        raise SystemExit("OPENAI_API_KEY is required for run-video (transcript summarization).")

    title = fetch_youtube_oembed_title(args.url) or "(YouTube video)"
    item = Item(
        source_name=args.label,
        platform="YouTube",
        title=title,
        url=args.url,
        published_at=None,
        summary=None,
    )
    model = args.model or openai_cfg.model
    whisper = args.whisper_model or openai_cfg.whisper_model
    cap = None if int(args.transcript_chars) == 0 else int(args.transcript_chars)
    blocks = summarize_items(
        [item],
        api_key=openai_cfg.api_key,
        model=model,
        use_transcript=not args.no_transcript,
        max_transcript_chars=cap,
        transcription_mode=args.transcription_mode,
        whisper_model=whisper,
    )
    digest = render_digest(blocks)

    if args.dry_run:
        print("Dry-run: digest is printed below; no email is sent. Omit --dry-run to mail.", file=sys.stderr)
        print(digest)
        return 0

    email_cfg = load_email_from_env()
    subject = f"YouTube digest (test) — {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d')}"
    send_email(email_cfg, subject=subject, body_markdown=digest)
    print("Email sent.")
    return 0


def cmd_test_email(args: argparse.Namespace) -> int:
    load_app_env()
    email_cfg = load_email_from_env()
    subject = f"meme_finder SMTP test — {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')}"
    send_email(email_cfg, subject=subject, body_markdown=args.message + "\n")
    print("Test email sent.")
    return 0


def main() -> int:
    p = build_parser()
    args = p.parse_args()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "run-video":
        return cmd_run_video(args)
    if args.cmd == "test-email":
        return cmd_test_email(args)
    raise RuntimeError("Unknown command")


if __name__ == "__main__":
    raise SystemExit(main())

