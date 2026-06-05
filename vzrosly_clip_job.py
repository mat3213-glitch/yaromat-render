#!/usr/bin/env python3
"""
vzrosly_clip_job.py — GitHub Actions runner: биполярный коллаж-тизер по clip_style_guide.

Техника из гайда «примеры-клипов»: held↔строб ритм, читаемый scratch-слой («видна рука»),
рукописный хук, тёплый детский контраст в аутро. Палитра/смысл — из брифа трека «взрослый».

С ЯД (render_jobs/<JOB_ID>/): job.json, track.mp3, anchor.png, cold_01..04.png, child.png
Из репо (assets/): Caveat.ttf (рукописный кириллический), scratch_overlay.mp4

job.json:
  {"format":"square|vertical", "out_name":"...mp4", "audio_start":8, "duration":28,
   "word":"ВЗРОСЛЫЙ",
   "hook":"Никто не спасёт тебя.\\nВзрослый тут ты.",
   "outro":"yaromat — взрослый\\nскоро · включи звук"}

Env: JOB_ID
"""
import json, os, subprocess, sys, math
from pathlib import Path

JOB_ID = os.environ.get("JOB_ID", "")
if not JOB_ID:
    sys.exit("JOB_ID not set")

REMOTE  = "ydrive"
JOBS_YD = "Content factory/render_jobs"
JOB_YD  = f"{JOBS_YD}/{JOB_ID}"
WORK    = Path("/tmp/vzrosly_job"); WORK.mkdir(parents=True, exist_ok=True)
REPO    = Path(__file__).resolve().parent
FONT    = str(REPO / "assets" / "Caveat.ttf")
SCRATCH = str(REPO / "assets" / "scratch_overlay.mp4")

FMT = {"square": (1080, 1080), "vertical": (1080, 1920)}
FPS = 25
BEAT = 60.0 / 87.0  # 0.6897s


def yd_get(remote: str, local: Path) -> bool:
    local.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(["rclone", "copyto", f"{REMOTE}:{remote}", str(local)],
                          capture_output=True, text=True).returncode == 0

def yd_put(local: Path, remote: str) -> bool:
    return subprocess.run(["rclone", "copyto", str(local), f"{REMOTE}:{remote}"],
                          capture_output=True, text=True).returncode == 0

def yd_put_text(text: str, remote: str):
    t = WORK / "_s.txt"; t.write_text(text); yd_put(t, remote)

def run(cmd) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def make_cover(src: Path, dst: Path, W: int, H: int, zoom: float = 1.0, flip: bool = False):
    """Cover-crop картинки к WxH (+опц. зум-кроп для 'punch', +опц. флип)."""
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H}")
    if zoom > 1.0:
        cw, ch = int(W / zoom), int(H / zoom)
        vf += f",crop={cw}:{ch},scale={W}:{H}"
    if flip:
        vf += ",hflip"
    vf += ",format=yuv420p"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", vf,
         "-frames:v", "1", str(dst)])


def build_timeline():
    """Список (image_key, dur) по ритм-карте. Сумма = duration."""
    b = BEAT
    seq = []
    # 0:00–0:04 held intro — anchor
    seq.append(("anchor", 6 * b))                 # 4.14
    # groove — cut/1 доля, чередование cold+anchor-вспышки
    groove = ["c1", "anchor", "c2", "c3", "anchor", "c4",
              "c1f", "anchor", "c2f", "c3", "anchor", "c4f"]   # 12 × 1b = 8.28
    seq += [(k, b) for k in groove]
    # strobe — cut/½ доли, плотная очередь (20 × 0.5b = 6.90)
    strobe_pool = ["c1", "c2", "c3", "c4", "anchor", "c1f", "c2f", "c4f"]
    for i in range(20):
        seq.append((strobe_pool[i % len(strobe_pool)], 0.5 * b))
    # 0:20–0:24 held breath — anchor punch (ближе)
    seq.append(("anchorp", 6 * b))                # 4.14
    # outro — тёплый детский рисунок
    seq.append(("child", 4.54))
    total = sum(d for _, d in seq)
    return seq, total


def main():
    print(f"Job: {JOB_ID}")
    jf = WORK / "job.json"
    if not yd_get(f"{JOB_YD}/job.json", jf):
        sys.exit("no job.json")
    job = json.loads(jf.read_text())
    fmt = job.get("format", "square")
    W, H = FMT.get(fmt, FMT["square"])
    out_name = job["out_name"]
    audio_start = float(job.get("audio_start", 8))
    word  = job.get("word", "")
    hook  = job.get("hook", "")
    outro = job.get("outro", "")

    # downloads
    for name in ["track.mp3", "anchor.png", "cold_01.png", "cold_02.png",
                 "cold_03.png", "cold_04.png", "child.png"]:
        if not yd_get(f"{JOB_YD}/{name}", WORK / name):
            sys.exit(f"missing {name}")
    print(f"  format={fmt} {W}x{H} audio_start={audio_start}")

    # covers
    cov = WORK / "cov"; cov.mkdir(exist_ok=True)
    base = {
        "anchor":  ("anchor.png", 1.0,  False),
        "anchorp": ("anchor.png", 1.28, False),   # punch-in для выдоха
        "child":   ("child.png",  1.0,  False),
        "c1":  ("cold_01.png", 1.0, False), "c1f": ("cold_01.png", 1.06, True),
        "c2":  ("cold_02.png", 1.0, False), "c2f": ("cold_02.png", 1.06, True),
        "c3":  ("cold_03.png", 1.0, False),
        "c4":  ("cold_04.png", 1.0, False), "c4f": ("cold_04.png", 1.06, True),
    }
    cover_path = {}
    for key, (src, zoom, flip) in base.items():
        p = cov / f"{key}.png"
        make_cover(WORK / src, p, W, H, zoom, flip)
        cover_path[key] = p

    # timeline → каждый сегмент в короткий mp4, затем concat encoded (кросс-версийно надёжно)
    seq, total = build_timeline()
    duration = round(total, 3)
    print(f"  segments={len(seq)} duration={duration}s")
    segdir = WORK / "seg"; segdir.mkdir(exist_ok=True)
    seg_files = []
    for i, (key, dur) in enumerate(seq):
        sp = segdir / f"seg_{i:03d}.mp4"
        r = run(["ffmpeg", "-y", "-loglevel", "error",
                 "-loop", "1", "-t", f"{dur:.4f}", "-i", str(cover_path[key]),
                 "-r", str(FPS), "-vf", "format=yuv420p",
                 "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
                 "-video_track_timescale", "12800", str(sp)])
        if r.returncode != 0 or not sp.exists():
            print(r.stderr[-500:]); yd_put_text(f"error: seg {i}", f"{JOB_YD}/status.txt"); sys.exit("seg fail")
        seg_files.append(sp)
    concat = WORK / "concat.txt"
    concat.write_text("\n".join(f"file '{p}'" for p in seg_files))

    body = WORK / "body.mp4"
    r = run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(concat), "-c", "copy", str(body)])
    if r.returncode != 0 or not body.exists():
        print(r.stderr[-800:]); yd_put_text("error: body", f"{JOB_YD}/status.txt"); sys.exit("body fail")

    # текст-слои (рукописный Caveat). enable по тайм-карте.
    fs_word  = int(W * 0.13)
    fs_hook  = int(W * 0.058)
    fs_outro = int(W * 0.05)
    hook_file  = WORK / "hook.txt";  hook_file.write_text(hook,  encoding="utf-8")
    outro_file = WORK / "outro.txt"; outro_file.write_text(outro, encoding="utf-8")

    draw = []
    if word:
        draw.append(
            f"drawtext=fontfile={FONT}:text='{word}':fontcolor=white:fontsize={fs_word}:"
            f"x=(w-text_w)/2:y=h*0.42:alpha='if(lt(t,0.4),0,if(lt(t,1.2),(t-0.4)/0.8,if(lt(t,3.6),1,if(lt(t,4.0),(4.0-t)/0.4,0))))'")
    if hook:
        draw.append(
            f"drawtext=fontfile={FONT}:textfile={hook_file}:fontcolor=white:fontsize={fs_hook}:"
            f"line_spacing=10:box=1:boxcolor=black@0.35:boxborderw=26:"
            f"x=(w-text_w)/2:y=h*0.60:enable='between(t,20.0,24.2)':"
            f"alpha='if(lt(t,20.0),0,if(lt(t,20.8),(t-20.0)/0.8,1))'")
    if outro:
        # тёмный текст на тёплом светлом детском рисунке
        draw.append(
            f"drawtext=fontfile={FONT}:textfile={outro_file}:fontcolor=0x3a2a18:fontsize={fs_outro}:"
            f"line_spacing=8:x=(w-text_w)/2:y=h*0.78:enable='between(t,24.2,{duration})':"
            f"alpha='if(lt(t,24.4),(t-24.2)/0.2,1)'")
    draw_chain = ("," + ",".join(draw)) if draw else ""

    # scratch screen-blend + текст + аудио
    result = WORK / out_name
    afade_out = max(0.0, duration - 1.5)
    fc = (
        f"[0:v]fps={FPS},format=gbrp,setpts=PTS-STARTPTS[v];"
        f"[1:v]scale={W}:{H},fps={FPS},format=gray,format=gbrp,setpts=PTS-STARTPTS[s];"
        f"[v][s]blend=all_mode=screen:all_opacity=0.55[bl];"
        f"[bl]format=yuv420p,trim=duration={duration},setpts=PTS-STARTPTS{draw_chain}[vout]"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(body),
        "-stream_loop", "-1", "-i", SCRATCH,
        "-ss", str(audio_start), "-t", str(duration), "-i", str(WORK / "track.mp3"),
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "2:a",
        "-af", f"afade=t=in:st=0:d=0.6,afade=t=out:st={afade_out}:d=1.5",
        "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-shortest",
        str(result),
    ]
    r = run(cmd)
    if r.returncode != 0 or not result.exists() or result.stat().st_size < 5000:
        print(r.stderr[-1200:]); yd_put_text(f"error: render rc={r.returncode}", f"{JOB_YD}/status.txt"); sys.exit("render fail")

    mb = result.stat().st_size / 1024 / 1024
    print(f"  {out_name} {mb:.1f}MB")
    if not yd_put(result, f"{JOB_YD}/{out_name}"):
        yd_put_text("error: upload", f"{JOB_YD}/status.txt"); sys.exit("upload fail")
    yd_put_text("done", f"{JOB_YD}/status.txt")
    print(f"✅ done {out_name} ({mb:.1f}MB)")


if __name__ == "__main__":
    main()
