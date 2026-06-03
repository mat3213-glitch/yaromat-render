#!/usr/bin/env python3
"""
vinyl_job.py — GitHub Actions runner: spinning vinyl record teaser.

Steps:
  1. Download job.json + track.mp3 + (optional) label_art.png from ЯД
  2. Generate vinyl PNG with PIL (black record + grooves + center label)
  3. Generate dark atmospheric background
  4. ffmpeg: spin vinyl (33.3 RPM) over background + mix track segment + fade
  5. Upload result.mp4 + status.txt to ЯД

job.json:
  {"duration": 30, "format": "square|vertical", "out_name": "name.mp4",
   "audio_start": 0, "title": "YAROMAT", "track_name": "взрослый",
   "bg_color": "0x0a0a12"}   ← опционально

Environment: JOB_ID
"""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

JOB_ID = os.environ.get("JOB_ID", "")
if not JOB_ID:
    sys.exit("JOB_ID not set")

REMOTE  = "ydrive"
JOBS_YD = "Content factory/render_jobs"
JOB_YD  = f"{JOBS_YD}/{JOB_ID}"
WORKDIR = Path("/tmp/vinyl_job")
WORKDIR.mkdir(parents=True, exist_ok=True)

FMT_DIMS = {
    "square":   (1080, 1080),
    "vertical": (1080, 1920),
}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
RPM = 33.333
RPS = RPM / 60.0  # rotations per second


def yd_get(remote_path: str, local: Path) -> bool:
    local.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["rclone", "copyto", f"{REMOTE}:{remote_path}", str(local)],
                       capture_output=True, text=True)
    return r.returncode == 0

def yd_put(local: Path, remote_path: str) -> bool:
    r = subprocess.run(["rclone", "copyto", str(local), f"{REMOTE}:{remote_path}"],
                       capture_output=True, text=True)
    return r.returncode == 0

def yd_put_text(text: str, remote_path: str):
    tmp = WORKDIR / "_status.txt"
    tmp.write_text(text)
    yd_put(tmp, remote_path)


def hex_to_rgb(h: str):
    h = h.lstrip("0x").lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def generate_vinyl(
    out: Path,
    size: int,
    label_art: Path | None,
    title: str,
    track_name: str,
    bg_color_hex: str = "0x0a0a12",
):
    """Рисует vinyl record PNG: квадратный, фон прозрачный, запись чёрная."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    bg_rgb = hex_to_rgb(bg_color_hex)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = size // 2 - 4  # радиус пластинки

    # ── Тело пластинки (чёрный круг)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(12, 12, 18, 255))

    # ── Дорожки (тонкие концентрические кольца, чуть светлее)
    groove_start = int(r * 0.30)
    groove_end   = int(r * 0.96)
    step = max(3, size // 200)
    for gr in range(groove_start, groove_end, step):
        lw = 1
        col = (32, 32, 40, 160)
        draw.ellipse([cx - gr, cy - gr, cx + gr, cy + gr], outline=col, width=lw)

    # ── Центральная метка
    label_r = int(r * 0.28)
    if label_art and label_art.exists():
        art = Image.open(label_art).convert("RGBA")
        art = art.resize((label_r * 2, label_r * 2), Image.LANCZOS)
        # круговая маска
        mask = Image.new("L", (label_r * 2, label_r * 2), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, label_r * 2 - 1, label_r * 2 - 1], fill=255)
        art.putalpha(mask)
        img.paste(art, (cx - label_r, cy - label_r), art)
    else:
        # градиентная метка: тёмно-синяя
        for i in range(label_r, 0, -1):
            t = 1 - i / label_r
            c = (int(10 + 30 * t), int(10 + 20 * t), int(30 + 50 * t), 255)
            draw.ellipse([cx - i, cy - i, cx + i, cy + i], fill=c)

        # Текст на метке
        fontsize_title = max(12, label_r // 4)
        fontsize_track = max(10, label_r // 6)
        try:
            fnt_bold = ImageFont.truetype(FONT, fontsize_title)
            fnt_reg  = ImageFont.truetype(FONT_REG, fontsize_track)
        except Exception:
            fnt_bold = fnt_reg = ImageFont.load_default()

        # Название артиста
        bbox = draw.textbbox((0, 0), title, font=fnt_bold)
        tw = bbox[2] - bbox[0]
        draw.text((cx - tw // 2, cy - fontsize_title - 4), title,
                  font=fnt_bold, fill=(220, 220, 230, 255))
        # Название трека
        bbox2 = draw.textbbox((0, 0), track_name, font=fnt_reg)
        tw2 = bbox2[2] - bbox2[0]
        draw.text((cx - tw2 // 2, cy + 4), track_name,
                  font=fnt_reg, fill=(160, 165, 180, 255))

    # ── Центральное отверстие (шпиндель)
    hole_r = max(4, size // 120)
    draw.ellipse([cx - hole_r, cy - hole_r, cx + hole_r, cy + hole_r],
                 fill=(0, 0, 0, 255))

    # ── Блик (тонкий полукруг вверху)
    hiw = int(r * 0.7)
    hih = int(r * 0.12)
    draw.arc([cx - hiw, cy - r + 8, cx + hiw, cy - r + 8 + hih],
             start=200, end=340, fill=(80, 85, 100, 60), width=max(2, size // 180))

    img.save(out, "PNG")
    print(f"  vinyl.png: {out.stat().st_size // 1024}KB")


def generate_bg(out: Path, W: int, H: int, bg_color_hex: str):
    """Тёмный атмосферный фон через PIL — градиент + лёгкий шум."""
    from PIL import Image, ImageFilter
    import random as _rnd

    bg_rgb = hex_to_rgb(bg_color_hex)
    img = Image.new("RGB", (W, H), bg_rgb)
    # виньетка: затемнение по краям
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    steps = 60
    for i in range(steps):
        t = i / steps
        alpha = int(120 * (1 - t) ** 2)
        r = int(W * 0.5 * (1 - t * 0.5))
        g = int(H * 0.5 * (1 - t * 0.5))
        c = tuple(max(0, v - int(40 * (1 - t))) for v in bg_rgb)
        # рисуем от краёв
        draw.rectangle([i * W // (steps * 2), i * H // (steps * 2),
                        W - i * W // (steps * 2), H - i * H // (steps * 2)],
                       outline=(*c, alpha))
    img = img.filter(ImageFilter.GaussianBlur(radius=8))
    img.save(out, "PNG")
    print(f"  bg.png: {out.stat().st_size // 1024}KB")


def main():
    print(f"Job ID: {JOB_ID}")

    job_file = WORKDIR / "job.json"
    if not yd_get(f"{JOB_YD}/job.json", job_file):
        sys.exit("Failed to download job.json")
    job = json.loads(job_file.read_text())

    duration    = float(job["duration"])
    fmt         = job.get("format", "square")
    out_name    = job["out_name"]
    audio_start = float(job.get("audio_start", 0))
    title       = job.get("title", "YAROMAT")
    track_name  = job.get("track_name", "")
    bg_color    = job.get("bg_color", "0x0a0a12")
    W, H = FMT_DIMS.get(fmt, FMT_DIMS["square"])
    print(f"  {W}x{H}  dur={duration}s  audio_start={audio_start}s  rpm={RPM}")

    track_file = WORKDIR / "track.mp3"
    if not yd_get(f"{JOB_YD}/track.mp3", track_file):
        sys.exit("Failed to download track.mp3")

    label_art = WORKDIR / "label_art.png"
    if not yd_get(f"{JOB_YD}/label_art.png", label_art):
        label_art = None
        print("  no label_art.png — drawing text label")

    print("\n── Generating vinyl & background (PIL) ──")
    subprocess.run(["pip", "install", "-q", "Pillow"], capture_output=True)
    from importlib import import_module  # re-import after install

    vinyl_size = int(min(W, H) * 0.82)
    vinyl_png  = WORKDIR / "vinyl.png"
    bg_png     = WORKDIR / "bg.png"

    generate_vinyl(vinyl_png, vinyl_size, label_art, title, track_name, bg_color)
    generate_bg(bg_png, W, H, bg_color)

    # Позиция центра винила на кадре
    vx = (W - vinyl_size) // 2
    vy = (H - vinyl_size) // 2

    result    = WORKDIR / out_name
    afade_out = max(0.0, duration - 1.5)
    # 33.3 RPM = 2π * 0.556 rad/s
    angle_expr = f"2*PI*{RPS:.4f}*t"

    # Фильтр:
    # 1. bg — статичный фон
    # 2. vinyl — rotate(33RPM) с чёрным fillcolor, crop к vinyl_size×vinyl_size
    # 3. overlay vinyl поверх bg по центру
    vf = (
        f"[0:v]scale={W}:{H}[bg];"
        f"[1:v]rotate='{angle_expr}':fillcolor=0x0a0a12@0:oh={vinyl_size}:ow={vinyl_size}[vr];"
        f"[bg][vr]overlay={vx}:{vy}[out]"
    )

    print("\n── ffmpeg render ──")
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(duration + 1), "-i", str(bg_png),
        "-loop", "1", "-t", str(duration + 1), "-i", str(vinyl_png),
        "-ss", str(audio_start), "-t", str(duration), "-i", str(track_file),
        "-filter_complex", vf, "-map", "[out]", "-map", "2:a",
        "-af", f"afade=t=in:st=0:d=1,afade=t=out:st={afade_out}:d=1.5",
        "-t", str(duration),
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-r", "25",
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        str(result),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not result.exists() or result.stat().st_size < 5000:
        print(r.stderr[-800:])
        yd_put_text(f"error: ffmpeg rc={r.returncode}", f"{JOB_YD}/status.txt")
        sys.exit("ffmpeg failed")

    mb = result.stat().st_size / 1024 / 1024
    print(f"  {out_name}  {mb:.1f}MB")

    print(f"\n── Uploading ──")
    if not yd_put(result, f"{JOB_YD}/{out_name}"):
        yd_put_text("error: upload failed", f"{JOB_YD}/status.txt")
        sys.exit("Upload failed")

    yd_put_text("done", f"{JOB_YD}/status.txt")
    print(f"\n✅ Done: {out_name} ({mb:.1f}MB)")


if __name__ == "__main__":
    main()
