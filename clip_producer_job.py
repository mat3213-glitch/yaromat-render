#!/usr/bin/env python3
"""
clip_producer_job.py — GitHub Actions runner for CLIP_PRODUCER pipeline.

Reads cut_plan.json from YaDisk, cuts segments from source videos, concatenates,
mixes audio, uploads result + status.txt.

Environment: JOB_ID (from workflow input)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

JOB_ID  = os.environ.get("JOB_ID", "")
if not JOB_ID:
    sys.exit("JOB_ID not set")

REMOTE  = "ydrive"
JOBS_YD = "Content factory/render_jobs"
JOB_YD  = f"{JOBS_YD}/{JOB_ID}"
WORKDIR = Path("/tmp/clip_job")
WORKDIR.mkdir(parents=True, exist_ok=True)


# ── rclone helpers ─────────────────────────────────────────────────────────────

def yd_get(remote_path: str, local: Path) -> bool:
    local.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["rclone", "copyto", f"{REMOTE}:{remote_path}", str(local)],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def yd_put(local: Path, remote_path: str) -> bool:
    r = subprocess.run(
        ["rclone", "copyto", str(local), f"{REMOTE}:{remote_path}"],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def yd_put_text(text: str, remote_path: str):
    tmp = WORKDIR / "_status.txt"
    tmp.write_text(text)
    yd_put(tmp, remote_path)


# ── ffprobe ────────────────────────────────────────────────────────────────────

def video_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 60.0


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Job ID: {JOB_ID}")

    # 1. Download inputs
    print("\n── Downloading inputs ──")
    plan_file = WORKDIR / "cut_plan.json"
    if not yd_get(f"{JOB_YD}/cut_plan.json", plan_file):
        sys.exit("Failed to download cut_plan.json")

    plan = json.loads(plan_file.read_text())
    segments      = plan["segments"]
    track_dur     = float(plan["track_duration"])
    out_name      = plan["out_name"]
    fmt_filter    = {
        "square":    "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080",
        "vertical":  "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "landscape": "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
    }.get(plan.get("format", "square"), "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080")

    print(f"  segments: {len(segments)}  duration: {track_dur}s  format: {plan.get('format','square')}")

    # Download source videos (only unique sources present in plan)
    needed_sources = {seg["source"] for seg in segments}
    for src in needed_sources:
        dest = WORKDIR / f"{src}.mp4"
        print(f"  downloading {src}.mp4...")
        if not yd_get(f"{JOB_YD}/{src}.mp4", dest):
            sys.exit(f"Failed to download {src}.mp4")
        dur = video_duration(dest)
        print(f"    {dest.stat().st_size//1024}KB  duration={dur:.1f}s")

    # Download track
    track_file = WORKDIR / "track.mp3"
    print("  downloading track.mp3...")
    if not yd_get(f"{JOB_YD}/track.mp3", track_file):
        sys.exit("Failed to download track.mp3")

    # 2. Cut segments
    print(f"\n── Cutting {len(segments)} segments ──")
    seg_files: list[Path] = []

    for i, seg in enumerate(segments):
        src_file = WORKDIR / f"{seg['source']}.mp4"
        out_file = WORKDIR / f"seg_{i:03d}.mp4"

        src_dur = video_duration(src_file)
        src_start = float(seg["src_start"])
        duration  = float(seg["duration"])

        # Safety: clamp src_start to avoid reading past end
        if src_start + duration > src_dur:
            src_start = max(0.0, src_dur - duration - 0.1)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(round(src_start, 3)),
            "-t",  str(round(duration, 3)),
            "-i",  str(src_file),
            "-vf", fmt_filter,
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-an",  # audio added in final mix
            "-fps_mode", "cfr", "-r", "25",
            str(out_file),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not out_file.exists() or out_file.stat().st_size < 1000:
            print(f"  seg_{i:03d} FAIL: {r.stderr[-120:]}")
            continue

        seg_files.append(out_file)
        print(f"  seg_{i:03d}.mp4  {seg['source']:10s}  @{src_start:.1f}s  "
              f"{duration:.2f}s [{seg['energy']}]  {out_file.stat().st_size//1024}KB")

    if not seg_files:
        sys.exit("No segments rendered — aborting")

    print(f"\n  {len(seg_files)}/{len(segments)} segments OK")

    # 3. Concatenate
    print("\n── Concatenating ──")
    concat_list = WORKDIR / "concat.txt"
    concat_list.write_text("\n".join(f"file '{f}'" for f in seg_files))

    concat_mp4 = WORKDIR / "concat.mp4"
    r = subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(concat_mp4),
    ], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Concat failed: {r.stderr[-200:]}")
    print(f"  concat.mp4  {concat_mp4.stat().st_size//1024}KB")

    # 4. Mix audio
    print("\n── Mixing audio ──")
    result = WORKDIR / out_name
    r = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(concat_mp4),
        "-i", str(track_file),
        "-t", str(round(track_dur, 3)),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(result),
    ], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Audio mix failed: {r.stderr[-200:]}")

    mb = result.stat().st_size / 1024 / 1024
    print(f"  {out_name}  {mb:.1f}MB")

    # 5. Upload result
    print(f"\n── Uploading {out_name} ──")
    if not yd_put(result, f"{JOB_YD}/{out_name}"):
        sys.exit("Upload of result.mp4 failed")

    yd_put_text("done", f"{JOB_YD}/status.txt")
    print(f"\n✅ Done: {out_name} ({mb:.1f}MB)")


if __name__ == "__main__":
    main()
