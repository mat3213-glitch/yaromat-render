#!/usr/bin/env python3
"""
tsx_clip_job.py — GitHub Actions runner: боевой клип через TSX/Remotion-движок.

TSX как МЕДИУМ пула: вместо ffmpeg-композа стиллов клип рендерит Remotion-шаблон
(KineticCard/KineticWords/...) на вайб-арте трека, нужной длины/формата, + микс аудио.

С ЯД (render_jobs/<JOB_ID>/): job.json, track.mp3, <art>.(png|jpg)
Из репо: remotion/ (шаблоны+шрифты — берутся checkout'ом, не с ЯД)

job.json:
  {"composition":"KineticWords", "format":"vertical|square", "out_name":"...mp4",
   "title":"sky is in my hands", "duration":15, "audio_start":30, "seed":7,
   "art_name":"art.png", "brand":"yaromat" (опц), "palette":["#..","#..","#.."] (опц)}

Env: JOB_ID
"""
import json, os, subprocess, sys, shutil
from pathlib import Path

JOB_ID = os.environ.get("JOB_ID", "")
if not JOB_ID:
    sys.exit("JOB_ID not set")

REMOTE  = "ydrive"
JOB_YD  = f"Content factory/render_jobs/{JOB_ID}"
WORK    = Path("/tmp/tsx_clip"); WORK.mkdir(parents=True, exist_ok=True)
REPO    = Path(__file__).resolve().parent
REMOTION = REPO / "remotion"
PUBLIC   = REMOTION / "public"
FPS = 30


def run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd[:8]), "...", flush=True)
    return subprocess.run(cmd, **kw)

def yd_get(remote: str, local: Path) -> bool:
    local.parent.mkdir(parents=True, exist_ok=True)
    return run(["rclone", "copyto", f"{REMOTE}:{remote}", str(local)],
               capture_output=True, text=True).returncode == 0

def yd_put(local: Path, remote: str) -> bool:
    return run(["rclone", "copyto", str(local), f"{REMOTE}:{remote}"],
               capture_output=True, text=True).returncode == 0

def yd_put_text(text: str, remote: str):
    t = WORK / "_s.txt"; t.write_text(text); yd_put(t, remote)


def main():
    print(f"TSX clip job: {JOB_ID}")

    jf = WORK / "job.json"
    if not yd_get(f"{JOB_YD}/job.json", jf):
        sys.exit("no job.json")
    job = json.loads(jf.read_text())

    composition = job["composition"]
    fmt         = job.get("format", "vertical")
    out_name    = job["out_name"]
    title       = job.get("title", "")
    duration    = float(job["duration"])
    audio_start = float(job.get("audio_start", 0))
    seed        = int(job.get("seed", 42))
    art_name    = job.get("art_name", "art.png")
    print(f"  comp={composition} fmt={fmt} dur={duration}s seed={seed} art={art_name}")

    # вход с ЯД: трек + вайб-арт (арт кладём в remotion/public/ для staticFile)
    track = WORK / "track.mp3"
    if not yd_get(f"{JOB_YD}/track.mp3", track):
        sys.exit("no track.mp3")
    PUBLIC.mkdir(parents=True, exist_ok=True)
    art_local = PUBLIC / art_name
    if not yd_get(f"{JOB_YD}/{art_name}", art_local):
        sys.exit(f"no art {art_name}")

    # props для Remotion (durationSec → calculateMetadata растянет композицию на длину трека)
    props = {"artUrl": art_name, "trackTitle": title, "format": fmt,
             "seed": seed, "durationSec": duration}
    if job.get("brand"):   props["brand"] = job["brand"]
    if job.get("palette"): props["palette"] = job["palette"]
    props_file = REMOTION / "props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False))

    # рендер визуала (без звука)
    visual = WORK / "visual.mp4"
    r = run(["npx", "remotion", "render", "src/index.ts", composition, str(visual),
             "--props=./props.json"], cwd=str(REMOTION))
    if r.returncode != 0 or not visual.exists():
        yd_put_text(f"error: remotion render rc={r.returncode}", f"{JOB_YD}/status.txt")
        sys.exit("remotion render fail")
    print(f"  visual.mp4 {visual.stat().st_size//1024}KB")

    # микс аудио (с audio_start, fade in/out), длина = duration
    result = WORK / out_name
    afade_out = max(0.0, duration - 1.5)
    r = run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(visual),
        "-ss", str(audio_start), "-t", str(duration), "-i", str(track),
        "-map", "0:v", "-map", "1:a",
        "-af", f"afade=t=in:st=0:d=0.6,afade=t=out:st={afade_out}:d=1.5",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(result),
    ], capture_output=True, text=True)
    if r.returncode != 0 or not result.exists() or result.stat().st_size < 5000:
        print((r.stderr or "")[-800:])
        yd_put_text(f"error: audio mux rc={r.returncode}", f"{JOB_YD}/status.txt")
        sys.exit("audio mux fail")

    mb = result.stat().st_size / 1024 / 1024
    print(f"  {out_name} {mb:.1f}MB")
    if not yd_put(result, f"{JOB_YD}/{out_name}"):
        yd_put_text("error: upload", f"{JOB_YD}/status.txt"); sys.exit("upload fail")
    yd_put_text("done", f"{JOB_YD}/status.txt")
    print(f"✅ done {out_name} ({mb:.1f}MB)")


if __name__ == "__main__":
    main()
