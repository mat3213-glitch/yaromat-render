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
GRIT    = str(REPO / "assets" / "grit_overlay.mp4")

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


def motion_seg(cover: Path, dur: float, mode: str, theta: float, blend: str,
               out: Path, W: int, H: int) -> bool:
    """Сегмент-видео: 2 копии арта дрейфуют в противоположные стороны + blend
    (двойная экспозиция → виден бленд + движение). mode: pan|zoom|single."""
    enc = ["-r", str(FPS), "-c:v", "libx264", "-crf", "22", "-preset", "veryfast",
           "-video_track_timescale", "12800", str(out)]
    BW, BH = int(W * 1.30), int(H * 1.30)
    pre = f"scale={BW}:{BH}:force_original_aspect_ratio=increase,crop={BW}:{BH}"
    mx, my = BW - W, BH - H          # margins
    cx, cy = mx / 2, my / 2
    ax, ay = mx / 2 * math.cos(theta), my / 2 * math.sin(theta)
    # нормированное время 0..1: s = (t/dur). дрейф через центр: (s*2-1)
    def panx(sign): return f"{cx:.1f}+({sign}({ax:.2f}))*((t/{dur:.4f})*2-1)"
    def pany(sign): return f"{cy:.1f}+({sign}({ay:.2f}))*((t/{dur:.4f})*2-1)"

    if mode == "single":   # один слой, нежный дрейф (для outro/рисунка)
        fc = (f"[0]{pre},crop={W}:{H}:x='{panx('+')}':y='{pany('+')}',"
              f"format=yuv420p[v]")
    elif mode == "zoom":   # слой A — наезд, слой B — отъезд, blend
        zin  = f"'{W}*(1-0.16*(t/{dur:.4f}))'"
        zinh = f"'{H}*(1-0.16*(t/{dur:.4f}))'"
        zout = f"'{W}*(0.84+0.16*(t/{dur:.4f}))'"
        zouth= f"'{H}*(0.84+0.16*(t/{dur:.4f}))'"
        fc = (f"[0]{pre},split[a][b];"
              f"[a]crop=w={zin}:h={zinh}:x='(iw-ow)/2':y='(ih-oh)/2',scale={W}:{H},setsar=1[ca];"
              f"[b]crop=w={zout}:h={zouth}:x='(iw-ow)/2':y='(ih-oh)/2',scale={W}:{H},setsar=1[cb];"
              f"[ca][cb]blend=all_mode={blend}:all_opacity=0.5,format=yuv420p[v]")
    else:                  # pan — слои дрейфуют в противоположные стороны
        fc = (f"[0]{pre},split[a][b];"
              f"[a]crop={W}:{H}:x='{panx('+')}':y='{pany('+')}',setsar=1[ca];"
              f"[b]crop={W}:{H}:x='{panx('-')}':y='{pany('-')}',setsar=1[cb];"
              f"[ca][cb]blend=all_mode={blend}:all_opacity=0.5,format=yuv420p[v]")
    r = run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", f"{dur:.4f}",
             "-i", str(cover), "-filter_complex", fc, "-map", "[v]"] + enc)
    if r.returncode != 0:
        print("motion_seg:", r.stderr[-400:])
    return r.returncode == 0 and out.exists()


def probe_dur(p: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(p)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def xfade_chain(segs, durs, trans, tdurs, out: Path) -> bool:
    """Склейка сегментов через xfade с разными переходами. Возвращает успех.
    segs[i] — путь, durs[i] — реальная длительность, trans[i]/tdurs[i] — переход
    ВХОДА в сегмент i (i>=1)."""
    inputs = []
    for s in segs:
        inputs += ["-i", str(s)]
    parts = []
    prev = "0:v"
    running = durs[0]
    for i in range(1, len(segs)):
        d = tdurs[i]
        off = max(0.0, running - d)
        lbl = f"x{i}"
        parts.append(f"[{prev}][{i}:v]xfade=transition={trans[i]}:"
                     f"duration={d:.3f}:offset={off:.3f}[{lbl}]")
        prev = lbl
        running = running + durs[i] - d
    fc = ";".join(parts)
    r = run(["ffmpeg", "-y", "-loglevel", "error"] + inputs +
            ["-filter_complex", fc, "-map", f"[{prev}]",
             "-r", str(FPS), "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
             "-pix_fmt", "yuv420p", str(out)])
    if r.returncode != 0:
        print("xfade_chain:", r.stderr[-600:])
    return r.returncode == 0 and out.exists()


import random

# 8 направлений дрейфа (радианы) для двойной экспозиции
DIRS = [i * math.pi / 4 for i in range(8)]
# палитра переходов xfade для грува/выдоха (разнообразие «смены кадров»)
GROOVE_TR = ["dissolve", "wipeleft", "wiperight", "slideup", "slidedown",
             "smoothright", "smoothleft", "circleopen", "fadegrays"]
STROBE_TR = ["fade", "fade", "fade", "fadewhite", "slideleft", "fade",
             "fadeblack", "slideup", "fade", "fadewhite"]


def build_timeline():
    """Список сегментов: dict(key,dur,mode,theta,blend,tin,tdur). Сумма dur = 28."""
    random.seed(42)  # детерминизм: square и vertical монтируются одинаково
    b = BEAT
    raw = []
    raw.append(("anchor", 6 * b, "intro"))                 # 0: held intro
    groove = ["c1", "anchor", "clock", "c2", "anchor", "crowd",
              "c3", "anchor", "c4", "a1", "anchor", "a2"]
    raw += [(k, b, "groove") for k in groove]              # 1..12
    strobe_pool = ["clock", "c1", "crowd", "a4", "c2", "a2", "anchor", "c3",
                   "a1", "c4", "crowd", "c1f", "a2f", "c2f", "clock", "c4f"]
    for i in range(20):
        raw.append((strobe_pool[i % len(strobe_pool)], 0.5 * b, "strobe"))  # 13..32
    raw.append(("anchorp", 6 * b, "breath"))               # 33: held breath
    raw.append(("child", 4.54, "outro"))                   # 34: warm outro

    seq = []
    for i, (key, dur, region) in enumerate(raw):
        # движение: held — мягкий дрейф; грув/строб — полный + случайный zoom; outro — нежный single
        if region in ("intro", "breath"):
            mode, blend = "pan", "average"
        elif region == "outro":
            mode, blend = "single", "none"
        else:
            mode = "pan"   # направление дрейфа задаёт theta (8 вариантов) → разнообразие движения
            blend = random.choice(["average", "average", "screen", "lighten"])
        theta = random.choice(DIRS)
        # переход ВХОД в сегмент i (граница i-1 → i)
        if i == 0:
            tin, tdur = None, 0.0
        elif region == "groove":
            tin, tdur = random.choice(GROOVE_TR), 0.15
        elif region == "strobe":
            tin, tdur = random.choice(STROBE_TR), (0.05 if raw[i][1] < 0.4 else 0.1)
        elif region == "breath":
            tin, tdur = random.choice(["fadeblack", "dissolve"]), 0.30
        elif region == "outro":
            tin, tdur = "fadewhite", 0.40    # вспышка в белый → тёплый переворот
        else:
            tin, tdur = "fade", 0.05
        seq.append(dict(key=key, dur=dur, mode=mode, theta=theta,
                        blend=blend, tin=tin, tdur=tdur))
    total = sum(s["dur"] for s in seq)
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
                 "cold_03.png", "cold_04.png", "child.png",
                 "crowd.png", "clock.png", "art1.png", "art2.png", "art4.png"]:
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
        "crowd": ("crowd.png", 1.0, False),
        "clock": ("clock.png", 1.0, False),
        "a1": ("art1.png", 1.0, False),
        "a2": ("art2.png", 1.0, False), "a2f": ("art2.png", 1.06, True),
        "a4": ("art4.png", 1.0, False),
    }
    cover_path = {}
    for key, (src, zoom, flip) in base.items():
        p = cov / f"{key}.png"
        make_cover(WORK / src, p, W, H, zoom, flip)
        cover_path[key] = p

    # timeline → motion-сегменты (двойная экспозиция с движением) → xfade-цепь
    seq, total = build_timeline()
    nominal = round(total, 3)
    print(f"  segments={len(seq)} nominal={nominal}s")
    segdir = WORK / "seg"; segdir.mkdir(exist_ok=True)
    seg_files, durs, trans, tdurs = [], [], [], []
    for i, s in enumerate(seq):
        sp = segdir / f"seg_{i:03d}.mp4"
        # длиннее на величину входящего перехода — xfade «съест» этот overlap, нетто=план
        enc_dur = s["dur"] + s["tdur"]
        if not motion_seg(cover_path[s["key"]], enc_dur, s["mode"], s["theta"],
                          s["blend"], sp, W, H):
            yd_put_text(f"error: seg {i}", f"{JOB_YD}/status.txt"); sys.exit("seg fail")
        seg_files.append(sp)
        durs.append(probe_dur(sp))
        trans.append(s["tin"] or "fade")
        tdurs.append(s["tdur"])

    body = WORK / "body.mp4"
    if not xfade_chain(seg_files, durs, trans, tdurs, body):
        yd_put_text("error: body", f"{JOB_YD}/status.txt"); sys.exit("body fail")
    duration = round(probe_dur(body), 3)
    print(f"  body duration={duration}s")

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
            f"x=(w-text_w)/2:y=h*0.60:enable='between(t,19.6,23.3)':"
            f"alpha='if(lt(t,19.6),0,if(lt(t,20.2),(t-19.6)/0.6,1))'")
    if outro:
        # тёмный текст на тёплом светлом детском рисунке
        draw.append(
            f"drawtext=fontfile={FONT}:textfile={outro_file}:fontcolor=0x3a2a18:fontsize={fs_outro}:"
            f"line_spacing=8:x=(w-text_w)/2:y=h*0.78:enable='between(t,23.6,{duration})':"
            f"alpha='if(lt(t,23.9),(t-23.6)/0.3,1)'")
    draw_chain = ("," + ",".join(draw)) if draw else ""

    # плотность: контраст/деసатурация → scratch + grit (screen) → зерно + виньетка → текст → аудио
    result = WORK / out_name
    afade_out = max(0.0, duration - 1.5)
    fc = (
        f"[0:v]fps={FPS},eq=contrast=1.14:saturation=0.9:brightness=-0.02:gamma=0.96,"
        f"format=gbrp,setpts=PTS-STARTPTS[v];"
        f"[1:v]scale={W}:{H},fps={FPS},format=gray,format=gbrp,setpts=PTS-STARTPTS[scr];"
        f"[2:v]scale={W}:{H},fps={FPS},format=gray,format=gbrp,setpts=PTS-STARTPTS[grt];"
        f"[v][scr]blend=all_mode=screen:all_opacity=0.6[b1];"
        f"[b1][grt]blend=all_mode=screen:all_opacity=0.5[b2];"
        f"[b2]format=yuv420p,noise=alls=12:allf=t+u,"
        f"vignette=angle=PI/4.5,"
        f"trim=duration={duration},setpts=PTS-STARTPTS{draw_chain}[vout]"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(body),
        "-stream_loop", "-1", "-i", SCRATCH,
        "-stream_loop", "-1", "-i", GRIT,
        "-ss", str(audio_start), "-t", str(duration), "-i", str(WORK / "track.mp3"),
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "3:a",
        "-af", f"afade=t=in:st=0:d=0.6,afade=t=out:st={afade_out}:d=1.5",
        "-c:v", "libx264", "-crf", "23", "-preset", "fast", "-r", str(FPS),
        "-maxrate", "9M", "-bufsize", "18M",
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
