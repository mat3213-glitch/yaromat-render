#!/usr/bin/env python3
"""
vinyl_viral_job.py — GH Actions runner: viral vinyl snippet (3 bg modes).

bg_type: "art" | "blend" | "photo"
  art:   bg_art.png from ЯД → blurred ken-burns background
  blend: clip_urls in job.json → Pexels clips downloaded, double-exposure blend
  photo: photo_url in job.json → single Pexels photo, blurred ken-burns

Vinyl improvements over v4:
  - Sheen/specular highlight is STATIC (fixed light source, doesn't rotate)
  - Realistic rim highlight with angle-based brightness
  - Animated text: fade-in + slide-up over first 1.5s
  - Film grain via ffmpeg noise filter
  - Vignette as separate PIL compositing step

job.json: {bg_type, duration, format, out_name, audio_start, title, track_name,
           clip_urls?, photo_url?}
"""

import json, math, os, subprocess, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

JOB_ID = os.environ.get("JOB_ID", "")
if not JOB_ID:
    sys.exit("JOB_ID not set")

REMOTE  = "ydrive"
JOBS_YD = "Content factory/render_jobs"
JOB_YD  = f"{JOBS_YD}/{JOB_ID}"
WORKDIR = Path("/tmp/vinyl_viral")
WORKDIR.mkdir(parents=True, exist_ok=True)

FMT_DIMS = {"square": (1080, 1080), "vertical": (1080, 1920)}
FONT_B   = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R   = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
RPM      = 33.333
RPS      = RPM / 60.0
FPS      = 25


# ─── ЯД helpers ───────────────────────────────────────────────────────────────

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


# ─── Download helpers ─────────────────────────────────────────────────────────

def download_url(url: str, out_path: Path) -> Path:
    import requests
    out_path.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, stream=True, timeout=90,
                     headers={"User-Agent": "Mozilla/5.0 (compatible)"})
    r.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    kb = out_path.stat().st_size // 1024
    print(f"  ↓ {out_path.name} ({kb}KB)", flush=True)
    return out_path


def ffrun(cmd: list, desc: str = ""):
    if desc:
        print(f"  → {desc}", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  STDERR: {r.stderr[-400:]}")
        sys.exit(f"ffmpeg failed: {desc}")


# ─── Background preparation ───────────────────────────────────────────────────

def load_image_bg(path: Path, W: int, H: int, blur: int = 20) -> Image.Image:
    """Scale image to cover (W + 10%) × (H + 10%) then blur for ken-burns."""
    img = Image.open(path).convert("RGB")
    extra_x = int(W * 0.10) + 2
    extra_y = int(H * 0.10) + 2
    s = max((W + extra_x) / img.width, (H + extra_y) / img.height)
    nw, nh = int(img.width * s) + 2, int(img.height * s) + 2
    img = img.resize((nw, nh), Image.LANCZOS)
    if blur > 0:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return img  # larger than W×H; get_art_frame() crops into it


def get_art_frame(art: Image.Image, W: int, H: int,
                  frame_idx: int, total: int, pan_dir: int = 0) -> Image.Image:
    """Slow ken-burns: zoom-in + pan. pan_dir=0 left→right, 1 right→left."""
    t = frame_idx / max(total - 1, 1)
    # Crop shrinks slightly → content zooms in
    zoom = 1.0 - 0.05 * t   # 1.0 → 0.95 crop factor
    cw = max(W, int(W * zoom + 0.5))
    ch = max(H, int(H * zoom + 0.5))
    cw = min(cw, art.width)
    ch = min(ch, art.height)
    max_x = art.width  - cw
    max_y = art.height - ch
    if pan_dir == 0:
        x = int(max_x * t * 0.6)
    else:
        x = int(max_x * (1 - t * 0.6))
    y = int(max_y * 0.3)
    cropped = art.crop((x, y, x + cw, y + ch))
    if cw != W or ch != H:
        return cropped.resize((W, H), Image.BILINEAR)
    return cropped


def prepare_blend_bg(clip_paths: list, W: int, H: int, duration: float, tmp: Path) -> Path:
    """Normalize clips → blend pairs → concat → tinted bg video."""
    SEG = 7
    norm_dir = tmp / "norm"; norm_dir.mkdir(exist_ok=True)
    norm = []
    for i, src in enumerate(clip_paths):
        dst = norm_dir / f"n{i:02d}.mp4"
        ffrun([
            "ffmpeg", "-y", "-stream_loop", "-1", "-t", str(SEG), "-i", str(src),
            "-vf", (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},setsar=1,"
                    f"eq=brightness=0.02:contrast=1.04:saturation=0.68,fps={FPS}"),
            "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-an", str(dst),
        ], f"norm {i+1}/{len(clip_paths)}")
        norm.append(dst)

    blend_dir = tmp / "blend"; blend_dir.mkdir(exist_ok=True)
    blended = []
    for i in range(len(norm) - 1):
        dst = blend_dir / f"b{i:02d}.mp4"
        ffrun([
            "ffmpeg", "-y", "-i", str(norm[i]), "-i", str(norm[(i + 1) % len(norm)]),
            "-filter_complex",
            "[0:v]unsharp=5:5:1.8[base];[1:v]eq=brightness=-0.12:contrast=0.85[top];"
            "[base][top]blend=all_mode=normal:all_opacity=0.42[v]",
            "-map", "[v]", "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-an", str(dst),
        ], f"blend {i+1}/{len(norm)-1}")
        blended.append(dst)

    if not blended:
        blended = norm

    needed = duration + 3
    repeat  = math.ceil(needed / (SEG * len(blended))) + 1
    entries = blended * repeat
    concat_f = tmp / "concat.txt"
    concat_f.write_text("\n".join(f"file '{f}'" for f in entries))

    bg_path = tmp / "blend_bg.mp4"
    ffrun([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_f),
        "-t", str(needed + 1),
        "-vf", "colorchannelmixer=rr=0.84:gg=0.90:bb=1.10",  # cold cinematic tint
        "-c:v", "libx264", "-crf", "26", "-preset", "fast",
        "-pix_fmt", "yuv420p", "-an", str(bg_path),
    ], "concat → blend_bg")
    return bg_path


def iter_video_frames(path: Path, W: int, H: int):
    """Infinite looping generator of RGB PIL frames from video."""
    while True:
        cmd = [
            "ffmpeg", "-v", "quiet", "-i", str(path),
            "-vf", (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},fps={FPS}"),
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        frame_size = W * H * 3
        got = False
        while True:
            data = proc.stdout.read(frame_size)
            if len(data) < frame_size:
                break
            got = True
            yield Image.frombytes("RGB", (W, H), data)
        proc.stdout.close()
        proc.wait()
        if not got:
            break


# ─── Vinyl assets ─────────────────────────────────────────────────────────────

def make_vinyl_base(size: int, label_art_path) -> Image.Image:
    """Vinyl disc RGBA (no sheen — applied as separate static overlay)."""
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size // 2
    r  = size // 2 - 5

    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(10, 10, 16, 255))

    # Grooves — fine rings with subtle brightness variation
    lr   = int(r * 0.28)
    gstart = int(lr * 1.06)
    step = max(2, size // 280)
    for i, gr in enumerate(range(gstart, int(r * 0.97), step)):
        luma = 44 + (i % 4) * 5
        draw.ellipse([cx - gr, cy - gr, cx + gr, cy + gr],
                     outline=(luma, luma, luma + 10, 200), width=1)

    # Center label
    if label_art_path and Path(label_art_path).exists():
        art = Image.open(label_art_path).convert("RGBA").resize((lr * 2, lr * 2), Image.LANCZOS)
        mask = Image.new("L", (lr * 2, lr * 2), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, lr * 2 - 1, lr * 2 - 1], fill=255)
        art.putalpha(mask)
        img.paste(art, (cx - lr, cy - lr), art)
        draw.ellipse([cx - lr - 1, cy - lr - 1, cx + lr + 1, cy + lr + 1],
                     outline=(55, 55, 70, 190), width=1)
    else:
        for i in range(lr, 0, -1):
            t = 1 - i / lr
            draw.ellipse([cx - i, cy - i, cx + i, cy + i],
                         fill=(int(10 + 28 * t), int(10 + 18 * t), int(28 + 48 * t), 255))

    hr = max(4, size // 115)
    draw.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=(4, 4, 7, 255))
    return img


def make_vinyl_sheen(size: int) -> Image.Image:
    """Static RGBA overlay: specular rim highlight + soft reflection blob.
    Does NOT rotate — simulates a fixed light source from upper-left."""
    cx = cy = size // 2
    r  = size // 2 - 5

    Y, X = np.ogrid[:size, :size]
    dist  = np.sqrt(((X - cx) ** 2 + (Y - cy) ** 2).astype(np.float32))
    angle = np.arctan2((Y - cy).astype(np.float32), (X - cx).astype(np.float32))

    in_disc = dist <= r

    # Rim highlight: thin ring at outer edge, brightest at ~225° (upper-left)
    rim = (dist >= r - 2.5) & (dist <= r + 0.5) & in_disc
    af  = (np.cos(angle - math.radians(225)) + 1) / 2  # 0→1, peaks upper-left
    rim_a = (af * 180 + 20).astype(np.uint8)
    rim_c = (af * 90 + 130).astype(np.uint8)

    # Specular blob: soft ellipse offset to upper-left
    bx = cx - int(r * 0.18)
    by = cy - int(r * 0.28)
    bd = np.sqrt(((X - bx) ** 2 + (Y - by) ** 2).astype(np.float32))
    br = r * 0.60
    blob_a = np.clip((1 - bd / br) ** 2.5 * 52, 0, 52).astype(np.float32) * in_disc

    rgba = np.zeros((size, size, 4), dtype=np.uint8)

    # Blob (cool white)
    m = blob_a > 2
    rgba[m, 0] = np.clip(175 + blob_a[m] * 0.5, 0, 220).astype(np.uint8)
    rgba[m, 1] = np.clip(185 + blob_a[m] * 0.5, 0, 228).astype(np.uint8)
    rgba[m, 2] = np.clip(205 + blob_a[m] * 0.5, 0, 235).astype(np.uint8)
    rgba[m, 3] = blob_a[m].astype(np.uint8)

    # Rim (on top)
    rgba[rim, 0] = rim_c[rim]
    rgba[rim, 1] = np.clip(rim_c[rim].astype(int) + 10, 0, 255).astype(np.uint8)
    rgba[rim, 2] = np.clip(rim_c[rim].astype(int) + 22, 0, 255).astype(np.uint8)
    rgba[rim, 3] = rim_a[rim]

    return Image.fromarray(rgba, "RGBA")


# ─── Text & vignette ──────────────────────────────────────────────────────────

def make_text_base(W: int, H: int, title: str, track_name: str,
                   vinyl_size: int) -> Image.Image:
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fs_t = max(14, W // 22)
    fs_r = max(12, W // 32)
    try:
        fb = ImageFont.truetype(FONT_B, fs_t)
        fr = ImageFont.truetype(FONT_R, fs_r)
    except Exception:
        fb = fr = ImageFont.load_default()

    text_y = H // 2 + vinyl_size // 2 + max(14, H // 55)
    for fnt, text, dy in [(fb, title, 0), (fr, track_name, fs_t + 8)]:
        if not text:
            continue
        bb = draw.textbbox((0, 0), text, font=fnt)
        tw = bb[2] - bb[0]
        x  = (W - tw) // 2
        y  = text_y + dy
        if y + max(fs_t, fs_r) < H - 8:
            draw.text((x + 2, y + 2), text, font=fnt, fill=(0, 0, 0, 130))
            draw.text((x, y),         text, font=fnt, fill=(210, 215, 228, 235))
    return img


def get_text_frame(text_base: Image.Image, frame_idx: int,
                   anim_frames: int = 38) -> Image.Image:
    """Fade-in + upward slide over anim_frames frames."""
    t = min(frame_idx / anim_frames, 1.0)
    t = 1 - (1 - t) ** 2  # ease-out
    if t >= 1.0:
        return text_base
    y_shift = int(18 * (1 - t))
    alpha_mult = t
    layer = Image.new("RGBA", text_base.size, (0, 0, 0, 0))
    if alpha_mult > 0.02:
        tc = text_base.copy()
        tc.putalpha(tc.getchannel("A").point(lambda p: int(p * alpha_mult)))
        layer.paste(tc, (0, y_shift), tc)
    return layer


def make_vignette(W: int, H: int) -> Image.Image:
    Y, X = np.ogrid[:H, :W]
    dx = (X - W / 2) / (W / 2)
    dy = (Y - H / 2) / (H / 2)
    d  = np.sqrt(dx ** 2 + dy ** 2)
    a  = np.clip((d - 0.55) / 0.55, 0, 1) ** 1.7 * 0.72 * 255
    rgba = np.zeros((H, W, 4), dtype=np.uint8)
    rgba[:, :, 3] = a.astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


# ─── Render loop ──────────────────────────────────────────────────────────────

def render(bg_source, bg_type: str, pan_dir: int,
           vinyl: Image.Image, sheen: Image.Image,
           text_base: Image.Image, vignette: Image.Image,
           W: int, H: int, vinyl_size: int,
           duration: float, track_path: Path, audio_start: float,
           out_path: Path) -> int:

    total      = int(duration * FPS)
    angle_step = 360.0 * RPS / FPS
    vx = (W - vinyl_size) // 2
    vy = (H - vinyl_size) // 2

    FADE_IN  = int(0.5 * FPS)
    FADE_OUT = int(1.5 * FPS)
    BLACK    = Image.new("RGB", (W, H), 0)

    if bg_type == "blend":
        bg_gen = iter_video_frames(bg_source, W, H)
        def get_bg(i):
            return next(bg_gen)
    else:
        def get_bg(i):
            return get_art_frame(bg_source, W, H, i, total, pan_dir)

    afade_out = max(0.0, duration - 1.5)
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(FPS), "-i", "pipe:0",
        "-ss", str(audio_start), "-t", str(duration), "-i", str(track_path),
        "-map", "0:v", "-map", "1:a",
        "-af", f"afade=t=in:st=0:d=0.5,afade=t=out:st={afade_out}:d=1.5",
        "-vf", "noise=alls=9:allf=u",
        "-c:v", "libx264", "-crf", "22", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-t", str(duration), str(out_path),
    ]

    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as proc:
        for i in range(total):
            frame = get_bg(i).convert("RGBA")

            # Rotating vinyl
            angle   = angle_step * i
            rotated = vinyl.rotate(-angle, resample=Image.BICUBIC, expand=False)
            frame.paste(rotated, (vx, vy), rotated)

            # Static sheen (fixed light source)
            frame.paste(sheen, (vx, vy), sheen)

            # Vignette
            frame = Image.alpha_composite(frame, vignette)

            # Text (animated)
            frame = Image.alpha_composite(frame, get_text_frame(text_base, i))

            # Fade in/out
            rgb = frame.convert("RGB")
            if i < FADE_IN:
                rgb = Image.blend(BLACK, rgb, i / FADE_IN)
            elif i >= total - FADE_OUT:
                f = (total - i) / FADE_OUT
                rgb = Image.blend(BLACK, rgb, max(0.0, f))

            proc.stdin.write(rgb.tobytes())

            if i % 100 == 0:
                print(f"  frame {i}/{total} ({i * 100 // total}%)", flush=True)

        proc.stdin.close()
        return proc.wait()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"Job: {JOB_ID}", flush=True)

    job_file = WORKDIR / "job.json"
    if not yd_get(f"{JOB_YD}/job.json", job_file):
        sys.exit("Failed: job.json")
    job = json.loads(job_file.read_text())

    duration    = float(job["duration"])
    fmt         = job.get("format", "square")
    out_name    = job["out_name"]
    audio_start = float(job.get("audio_start", 0))
    title       = job.get("title", "yaromat")
    track_name  = job.get("track_name", "")
    bg_type     = job.get("bg_type", "art")
    pan_dir     = int(job.get("pan_dir", 0))
    W, H = FMT_DIMS.get(fmt, FMT_DIMS["square"])

    print(f"  {W}×{H}  {duration}s  bg={bg_type}  audio_start={audio_start}s")

    track_file = WORKDIR / "track.mp3"
    if not yd_get(f"{JOB_YD}/track.mp3", track_file):
        sys.exit("Failed: track.mp3")

    # pip install (idempotent on Actions since cache is warm for apt but not pip)
    subprocess.run(["pip", "install", "-q", "Pillow", "numpy", "requests"],
                   capture_output=True)

    # ── Prepare background ──────────────────────────────────────────────────
    label_art_file = WORKDIR / "label_art.png"
    yd_get(f"{JOB_YD}/label_art.png", label_art_file)
    label_art = label_art_file if label_art_file.exists() else None

    if bg_type == "art":
        bg_art = WORKDIR / "bg_art.png"
        if not yd_get(f"{JOB_YD}/bg_art.png", bg_art):
            sys.exit("Failed: bg_art.png")
        print("  Loading art background...")
        bg_source = load_image_bg(bg_art, W, H, blur=18)

    elif bg_type == "blend":
        clip_urls = job.get("clip_urls", [])
        if not clip_urls:
            sys.exit("bg_type=blend but clip_urls missing in job.json")
        clips_dir = WORKDIR / "clips"; clips_dir.mkdir(exist_ok=True)
        print(f"  Downloading {len(clip_urls)} clips...")
        clip_paths = []
        for idx, url in enumerate(clip_urls):
            try:
                clip_paths.append(download_url(url, clips_dir / f"clip_{idx:02d}.mp4"))
            except Exception as e:
                print(f"  ! clip {idx} skip: {e}")
        if not clip_paths:
            sys.exit("No clips downloaded")
        blend_tmp = WORKDIR / "blend_tmp"; blend_tmp.mkdir(exist_ok=True)
        print(f"  Building blend bg ({len(clip_paths)} clips)...")
        bg_source = prepare_blend_bg(clip_paths, W, H, duration, blend_tmp)

    elif bg_type == "photo":
        photo_url = job.get("photo_url", "")
        if not photo_url:
            sys.exit("bg_type=photo but photo_url missing in job.json")
        photo_file = WORKDIR / "bg_photo.jpg"
        print("  Downloading photo background...")
        download_url(photo_url, photo_file)
        bg_source = load_image_bg(photo_file, W, H, blur=22)

    else:
        sys.exit(f"Unknown bg_type: {bg_type}")

    # ── Vinyl assets ────────────────────────────────────────────────────────
    print("\n── Vinyl assets ──")
    vinyl_size = int(min(W, H) * 0.72)
    vinyl      = make_vinyl_base(vinyl_size, label_art)
    sheen      = make_vinyl_sheen(vinyl_size)
    text_base  = make_text_base(W, H, title, track_name, vinyl_size)
    vignette   = make_vignette(W, H)
    print(f"  vinyl={vinyl_size}px  sheen ready  vignette ready")

    # ── Render ──────────────────────────────────────────────────────────────
    result = WORKDIR / out_name
    print(f"\n── Rendering {int(duration * FPS)} frames → ffmpeg ──")
    ret = render(bg_source, bg_type, pan_dir, vinyl, sheen, text_base, vignette,
                 W, H, vinyl_size, duration, track_file, audio_start, result)

    if ret != 0 or not result.exists() or result.stat().st_size < 10_000:
        yd_put_text(f"error: ffmpeg rc={ret}", f"{JOB_YD}/status.txt")
        sys.exit(f"ffmpeg failed rc={ret}")

    mb = result.stat().st_size / 1_048_576
    print(f"  {out_name}  {mb:.1f}MB")

    # ── Upload ──────────────────────────────────────────────────────────────
    print("\n── Uploading ──")
    if not yd_put(result, f"{JOB_YD}/{out_name}"):
        yd_put_text("error: upload failed", f"{JOB_YD}/status.txt")
        sys.exit("upload failed")

    yd_put_text("done", f"{JOB_YD}/status.txt")
    print(f"\n✅ Done: {out_name}  ({mb:.1f}MB)")


if __name__ == "__main__":
    main()
