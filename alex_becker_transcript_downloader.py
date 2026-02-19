#!/usr/bin/env python3
"""
alex_becker_transcript_downloader.py
-------------------------------------
Download all available transcripts from Alex Becker's YouTube channel
using yt-dlp (no API key required), then save each transcript as an
individual text file and also combine them into one master file.

Requirements
------------
pip install yt-dlp

Usage
-----
Run:  python alex_becker_transcript_downloader.py
  - Individual transcripts go into ./alex_becker_transcripts/<video_id>.txt
  - A combined file is written to ./alex_becker_all_transcripts.txt
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CHANNEL_URL: str = "https://www.youtube.com/@alexbeckerbusiness/videos"
OUTPUT_DIR: str = "alex_becker_transcripts"
COMBINED_FILE: str = "alex_becker_all_transcripts.txt"
SUBTITLE_LANG: str = "en"
# ---------------------------------------------------------------------------


def get_all_videos(channel_url: str) -> List[Tuple[str, str]]:
    """
    Fetch all video IDs and titles from a YouTube channel using yt-dlp
    flat-playlist mode (fast, no per-video page load).

    Returns
    -------
    List of (video_id, title) tuples.
    """
    cmd = [
        "yt-dlp",
        "--no-check-certificates",
        "--flat-playlist",
        "--print", "%(id)s\t%(title)s",
        channel_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        print(f"[ERROR] Failed to list channel videos:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    videos = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            video_id, title = parts
            videos.append((video_id.strip(), title.strip()))

    return videos


def clean_vtt(vtt_text: str) -> str:
    """
    Convert raw VTT subtitle text into clean, readable plaintext.

    Removes timestamps, positioning metadata, duplicate lines from
    the rolling-caption format, and inline timing tags.
    """
    lines = vtt_text.split("\n")
    cleaned = []
    seen = set()

    for line in lines:
        # Skip VTT header, blank lines, and timestamp/position lines
        if line.startswith("WEBVTT"):
            continue
        if line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->", line):
            continue
        if not line.strip():
            continue

        # Remove inline timing tags like <00:00:01.234><c> </c>
        text = re.sub(r"<\d{2}:\d{2}:\d{2}\.\d{3}>", "", line)
        text = re.sub(r"</?c>", "", text)
        # Remove alignment/position metadata
        text = re.sub(r"align:\S+", "", text)
        text = re.sub(r"position:\S+", "", text)
        text = text.strip()

        if not text:
            continue

        # Deduplicate rolling captions (VTT repeats lines as they scroll)
        if text not in seen:
            seen.add(text)
            cleaned.append(text)

    return " ".join(cleaned)


def download_subtitle(video_id: str, temp_dir: str) -> Optional[str]:
    """
    Download the English subtitle for a single video using yt-dlp.

    Returns the cleaned transcript text, or None if unavailable.
    """
    output_template = os.path.join(temp_dir, f"{video_id}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-check-certificates",
        "--remote-components", "ejs:github",
        "--skip-download",
        "--write-auto-sub",
        "--write-sub",
        "--sub-lang", f"{SUBTITLE_LANG}*",
        "--sub-format", "vtt",
        "-o", output_template,
        f"https://www.youtube.com/watch?v={video_id}",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] Subtitle download timed out for {video_id}")
        return None

    # Look for the downloaded VTT file (could be .en.vtt or .en-orig.vtt)
    vtt_path = None
    for suffix in [f".{SUBTITLE_LANG}.vtt", f".{SUBTITLE_LANG}-orig.vtt"]:
        candidate = os.path.join(temp_dir, f"{video_id}{suffix}")
        if os.path.exists(candidate):
            vtt_path = candidate
            break

    if not vtt_path:
        # Check for any .vtt file matching this video
        for f in os.listdir(temp_dir):
            if f.startswith(video_id) and f.endswith(".vtt"):
                vtt_path = os.path.join(temp_dir, f)
                break

    if not vtt_path:
        return None

    with open(vtt_path, "r", encoding="utf-8") as f:
        vtt_content = f.read()

    # Clean up temp files
    for f in os.listdir(temp_dir):
        if f.startswith(video_id):
            os.remove(os.path.join(temp_dir, f))

    return clean_vtt(vtt_content)


def sanitize_filename(title: str) -> str:
    """Create a filesystem-safe filename from a video title."""
    safe = re.sub(r'[<>:"/\\|?*]', '', title)
    safe = safe.strip(". ")
    return safe[:200] if safe else "untitled"


def main() -> None:
    """Orchestrate the full channel transcript download."""
    print(f"Fetching video list from: {CHANNEL_URL}")
    print("This may take a moment for large channels...\n")

    videos = get_all_videos(CHANNEL_URL)
    total = len(videos)
    print(f"Found {total} videos. Starting transcript downloads...\n")

    # Create output directories
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    temp_dir = os.path.join(OUTPUT_DIR, ".tmp")
    os.makedirs(temp_dir, exist_ok=True)

    # Track progress
    success_count = 0
    fail_count = 0
    failed_videos = []

    # Open combined output file
    with open(COMBINED_FILE, "w", encoding="utf-8") as combined:
        combined.write(f"# Alex Becker - Complete YouTube Channel Transcripts\n")
        combined.write(f"# Total videos found: {total}\n")
        combined.write(f"# Downloaded: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        combined.write(f"# Source: {CHANNEL_URL}\n\n")

        for idx, (video_id, title) in enumerate(videos, 1):
            progress = f"[{idx}/{total}]"
            print(f"{progress} Processing: {title}")

            transcript = download_subtitle(video_id, temp_dir)

            if transcript:
                # Save individual file
                safe_title = sanitize_filename(title)
                individual_path = os.path.join(
                    OUTPUT_DIR, f"{safe_title} [{video_id}].txt"
                )
                with open(individual_path, "w", encoding="utf-8") as f:
                    f.write(f"Title: {title}\n")
                    f.write(f"Video ID: {video_id}\n")
                    f.write(f"URL: https://www.youtube.com/watch?v={video_id}\n")
                    f.write(f"{'=' * 80}\n\n")
                    f.write(transcript)

                # Append to combined file
                combined.write(f"\n\n{'=' * 80}\n")
                combined.write(f"TITLE: {title}\n")
                combined.write(f"VIDEO ID: {video_id}\n")
                combined.write(f"URL: https://www.youtube.com/watch?v={video_id}\n")
                combined.write(f"{'=' * 80}\n\n")
                combined.write(transcript)

                success_count += 1
                print(f"  -> Saved transcript ({len(transcript):,} chars)")
            else:
                fail_count += 1
                failed_videos.append((video_id, title))
                print(f"  -> No transcript available")

            # Brief pause to avoid rate limiting
            if idx % 10 == 0:
                time.sleep(2)

    # Clean up temp directory
    try:
        os.rmdir(temp_dir)
    except OSError:
        pass

    # Write manifest of all videos
    manifest_path = os.path.join(OUTPUT_DIR, "_manifest.json")
    manifest = {
        "channel_url": CHANNEL_URL,
        "download_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_videos": total,
        "transcripts_downloaded": success_count,
        "transcripts_failed": fail_count,
        "videos": [
            {"id": vid, "title": title, "has_transcript": (vid, title) not in failed_videos}
            for vid, title in videos
        ],
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"DOWNLOAD COMPLETE")
    print(f"{'=' * 60}")
    print(f"Total videos:          {total}")
    print(f"Transcripts saved:     {success_count}")
    print(f"No transcript:         {fail_count}")
    print(f"Individual files:      ./{OUTPUT_DIR}/")
    print(f"Combined file:         ./{COMBINED_FILE}")
    print(f"Manifest:              ./{manifest_path}")

    if failed_videos:
        print(f"\nVideos without transcripts:")
        for vid, title in failed_videos:
            print(f"  - {title} ({vid})")


if __name__ == "__main__":
    main()
