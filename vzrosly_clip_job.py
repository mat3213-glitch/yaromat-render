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
               out: Path, W: int, H: int, crf: str = "22", preset: str = "veryfast") -> bool:
    """Сегмент-видео: 2 копии арта дрейфуют + blend (двойная экспозиция → виден бленд
    + движение). mode: pan (встречный дрейф) | inward (схождение к центру) | single.
    Амплитуда и скорость движения снижены (фидбэк yaromat: -50% и то и то)."""
    enc = ["-r", str(FPS), "-c:v", "libx264", "-crf", crf, "-preset", preset,
           "-video_track_timescale", "12800", str(out)]
    SPEED = 0.5                       # плотность/скорость движения ×0.5
    BW, BH = int(W * 1.15), int(H * 1.15)   # амплитуда (margin) ×0.5 (было 1.30)
    pre = f"scale={BW}:{BH}:force_original_aspect_ratio=increase,crop={BW}:{BH}"
    mx, my = BW - W, BH - H
    cx, cy = mx / 2, my / 2
    ax, ay = mx / 2 * math.cos(theta) * SPEED, my / 2 * math.sin(theta) * SPEED
    # фаза: pan — дрейф через центр (-1..1); inward — схождение к центру (1..0)
    ph_pan = f"((t/{dur:.4f})*2-1)"
    ph_in  = f"(1-(t/{dur:.4f}))"
    def drift(c, a, sign, ph): return f"{c:.1f}+({sign}({a:.2f}))*{ph}"

    if mode == "single":   # один слой, нежный дрейф (для outro/рисунка)
        fc = (f"[0]{pre},crop={W}:{H}:"
              f"x='{drift(cx, ax, '+', ph_pan)}':y='{drift(cy, ay, '+', ph_pan)}',"
              f"format=yuv420p[v]")
    else:
        ph = ph_in if mode == "inward" else ph_pan
        # format=gbrp на входах blend → бленд в RGB (иначе screen/lighten сдвигают цвет в фиолет)
        fc = (f"[0]{pre},split[a][b];"
              f"[a]crop={W}:{H}:x='{drift(cx, ax, '+', ph)}':y='{drift(cy, ay, '+', ph)}',setsar=1,format=gbrp[ca];"
              f"[b]crop={W}:{H}:x='{drift(cx, ax, '-', ph)}':y='{drift(cy, ay, '-', ph)}',setsar=1,format=gbrp[cb];"
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


def mean_luma(p: Path) -> float:
    """Средняя яркость кадра 0..255 (ffmpeg signalstats YAVG). Для выбора контраста текста."""
    import re
    r = run(["ffmpeg", "-i", str(p), "-vf", "signalstats,metadata=print:file=-",
             "-frames:v", "1", "-f", "null", "-"])
    m = re.search(r"YAVG[:=]([0-9.]+)", r.stdout + r.stderr)
    return float(m.group(1)) if m else 128.0


def contrast_text(luma: float):
    """По яркости фона → (fontcolor, bordercolor) для читаемости на любом кадре."""
    return ("white", "black") if luma < 120 else ("0x222018", "white")


def xfade_chain(segs, durs, trans, tdurs, out: Path,
                crf: str = "20", preset: str = "veryfast") -> bool:
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
             "-r", str(FPS), "-c:v", "libx264", "-crf", crf, "-preset", preset,
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


def build_timeline(variant="full", bpm=87.0):
    """Список сегментов: dict(key,dur,mode,theta,blend,tin,tdur,region).
    variant: 'full' (~28с) | 'short' (~14с, для X) — та же биполярная структура, сжата.
    bpm: темп трека — задаёт долю (held↔строб ритм матчит бит). Дефолт 87 (трек «взрослый»)."""
    random.seed(42)  # детерминизм: square и vertical монтируются одинаково
    b = 60.0 / bpm
    raw = []
    if variant == "short":
        raw.append(("anchor", 3 * b, "intro"))             # 0: held intro
        groove = ["c1", "anchor", "clock", "c2", "anchor", "crowd"]
        raw += [(k, b, "groove") for k in groove]          # 1..6
        strobe_pool = ["clock", "c1", "crowd", "a4", "c2", "a2", "anchor", "c3",
                       "a1", "c4"]
        for i in range(10):
            raw.append((strobe_pool[i % len(strobe_pool)], 0.5 * b, "strobe"))  # 7..16
        raw.append(("anchorp", 3 * b, "breath"))           # 17: held breath
        raw.append(("child", 2.3, "outro"))                # 18: warm outro
    else:
        raw.append(("anchor", 6 * b, "intro"))             # 0: held intro
        groove = ["c1", "anchor", "clock", "c2", "anchor", "crowd",
                  "c3", "anchor", "c4", "a1", "anchor", "a2"]
        raw += [(k, b, "groove") for k in groove]          # 1..12
        strobe_pool = ["clock", "c1", "crowd", "a4", "c2", "a2", "anchor", "c3",
                       "a1", "c4", "crowd", "c1f", "a2f", "c2f", "clock", "c4f"]
        for i in range(20):
            raw.append((strobe_pool[i % len(strobe_pool)], 0.5 * b, "strobe"))  # 13..32
        raw.append(("anchorp", 6 * b, "breath"))           # 33: held breath
        raw.append(("child", 4.54, "outro"))               # 34: warm outro

    seq = []
    for i, (key, dur, region) in enumerate(raw):
        # движение: held — мягкий дрейф; грув/строб — полный + случайный zoom; outro — нежный single
        if region in ("intro", "breath"):
            mode, blend = "pan", "average"
        elif region == "outro":
            mode, blend = "single", "none"
        else:
            # рандомно встречный дрейф или схождение «внутрь» (фидбэк yaromat)
            mode = random.choice(["pan", "inward", "inward"])
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
                        blend=blend, tin=tin, tdur=tdur, region=region))
    total = sum(s["dur"] for s in seq)
    return seq, total


# источники-ассеты (имена файлов) и спецификация cover-кадров: ключ → (src, zoom, flip).
# Общий источник правды для рендера и для локального сториборда (preview tier 1).
SRC_ASSETS = ["anchor.png", "cold_01.png", "cold_02.png", "cold_03.png", "cold_04.png",
              "child.png", "crowd.png", "clock.png", "art1.png", "art2.png", "art4.png"]
COVER_SPEC = {
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
    variant = job.get("variant", "full")
    bpm = float(job.get("bpm", 87.0))
    preview = bool(job.get("preview", False))
    word  = job.get("word", "")
    hook  = job.get("hook", "")
    outro = job.get("outro", "")
    track_credit = job.get("track_credit", "")   # старт: «Артист — Трек» (режим reference)
    watermark    = job.get("watermark", "")       # весь клип: кредит yaromat (привязка охватов)

    # preview tier 2: половинное разрешение + ultrafast → дешёвый proxy для ревью движения/плотности/ритма
    if preview:
        W, H = (W // 2) // 2 * 2, (H // 2) // 2 * 2   # half, чётное
    seg_crf, seg_preset = ("30", "ultrafast") if preview else ("22", "veryfast")
    body_crf, body_preset = ("30", "ultrafast") if preview else ("20", "veryfast")

    # downloads
    for name in ["track.mp3"] + SRC_ASSETS:
        if not yd_get(f"{JOB_YD}/{name}", WORK / name):
            sys.exit(f"missing {name}")
    print(f"  format={fmt} {W}x{H} audio_start={audio_start} preview={preview}")

    # covers
    cov = WORK / "cov"; cov.mkdir(exist_ok=True)
    cover_path = {}
    for key, (src, zoom, flip) in COVER_SPEC.items():
        p = cov / f"{key}.png"
        make_cover(WORK / src, p, W, H, zoom, flip)
        cover_path[key] = p

    # timeline → motion-сегменты (двойная экспозиция с движением) → xfade-цепь
    seq, total = build_timeline(variant, bpm)
    print(f"  variant={variant} bpm={bpm}")
    nominal = round(total, 3)
    print(f"  segments={len(seq)} nominal={nominal}s")
    segdir = WORK / "seg"; segdir.mkdir(exist_ok=True)
    seg_files, durs, trans, tdurs = [], [], [], []
    for i, s in enumerate(seq):
        sp = segdir / f"seg_{i:03d}.mp4"
        # длиннее на величину входящего перехода — xfade «съест» этот overlap, нетто=план
        enc_dur = s["dur"] + s["tdur"]
        if not motion_seg(cover_path[s["key"]], enc_dur, s["mode"], s["theta"],
                          s["blend"], sp, W, H, crf=seg_crf, preset=seg_preset):
            yd_put_text(f"error: seg {i}", f"{JOB_YD}/status.txt"); sys.exit("seg fail")
        seg_files.append(sp)
        durs.append(probe_dur(sp))
        trans.append(s["tin"] or "fade")
        tdurs.append(s["tdur"])

    body = WORK / "body.mp4"
    if not xfade_chain(seg_files, durs, trans, tdurs, body, crf=body_crf, preset=body_preset):
        yd_put_text("error: body", f"{JOB_YD}/status.txt"); sys.exit("body fail")
    duration = round(probe_dur(body), 3)
    print(f"  body duration={duration}s")

    # onset каждого сегмента в финальном xfade-таймлайне (та же математика, что в xfade_chain)
    onsets, running = [0.0], durs[0]
    for i in range(1, len(seq)):
        onsets.append(max(0.0, running - tdurs[i]))
        running = running + durs[i] - tdurs[i]
    i_groove = next((i for i, s in enumerate(seq) if s["region"] == "groove"), 1)
    i_breath = next((i for i, s in enumerate(seq) if s["region"] == "breath"), len(seq) - 2)
    i_outro  = next((i for i, s in enumerate(seq) if s["region"] == "outro"),  len(seq) - 1)
    # тайм-карта текста из реального таймлайна (работает для full и short)
    w0, w1 = 0.4, 1.2
    w2 = max(w1 + 0.4, onsets[i_groove] - 0.2); w3 = w2 + 0.4   # слово-хук на held-интро
    hk0 = onsets[i_breath] + 0.4; hk1 = onsets[i_breath] + seq[i_breath]["dur"]  # хук на выдохе
    ot0 = onsets[i_outro] + 0.3                                 # аутро-подпись на тёплом кадре
    print(f"  text: word[{w0:.1f}-{w3:.1f}] hook[{hk0:.1f}-{hk1:.1f}] outro[{ot0:.1f}-{duration}]")

    # текст-слои (рукописный Caveat). enable по тайм-карте.
    fs_word  = int(W * 0.13)
    fs_hook  = int(W * 0.058)
    fs_outro = int(W * 0.05)
    fs_cred  = int(W * 0.046)   # старт-кредит «Артист — Трек»
    fs_wm    = int(W * 0.030)   # вотермарк yaromat
    hook_file  = WORK / "hook.txt";  hook_file.write_text(hook,  encoding="utf-8")
    outro_file = WORK / "outro.txt"; outro_file.write_text(outro, encoding="utf-8")

    # адаптивный контраст: яркость кадров под интро-текстом и под аутро
    luma_intro = mean_luma(cover_path["anchor"])
    luma_outro = mean_luma(cover_path.get("child", cover_path["anchor"]))
    fc_intro, bc_intro = contrast_text(luma_intro)
    fc_outro, bc_outro = contrast_text(luma_outro)
    bw_word  = max(2, int(fs_word * 0.04))
    bw_small = max(2, int(fs_outro * 0.07))
    print(f"  luma intro={luma_intro:.0f}({fc_intro}) outro={luma_outro:.0f}({fc_outro})")

    draw = []
    if word:
        draw.append(
            f"drawtext=fontfile={FONT}:text='{word}':fontcolor={fc_intro}:fontsize={fs_word}:"
            f"borderw={bw_word}:bordercolor={bc_intro}@0.6:"
            f"x=(w-text_w)/2:y=h*0.42:"
            f"alpha='if(lt(t,{w0}),0,if(lt(t,{w1}),(t-{w0})/{w1-w0:.3f},if(lt(t,{w2:.3f}),1,if(lt(t,{w3:.3f}),({w3:.3f}-t)/{w3-w2:.3f},0))))'")
    if track_credit:
        # старт: «Артист — Трек» (reference-режим), адаптивный контраст, под словом
        cred_file = WORK / "cred.txt"; cred_file.write_text(track_credit, encoding="utf-8")
        draw.append(
            f"drawtext=fontfile={FONT}:textfile={cred_file}:fontcolor={fc_intro}:fontsize={fs_cred}:"
            f"borderw={bw_small}:bordercolor={bc_intro}@0.6:"
            f"x=(w-text_w)/2:y=h*0.60:"
            f"alpha='if(lt(t,{w0}),0,if(lt(t,{w1}),(t-{w0})/{w1-w0:.3f},if(lt(t,{w2+1.2:.3f}),1,if(lt(t,{w3+1.2:.3f}),({w3+1.2:.3f}-t)/{w3-w2:.3f},0))))'")
    if hook:
        draw.append(
            f"drawtext=fontfile={FONT}:textfile={hook_file}:fontcolor=white:fontsize={fs_hook}:"
            f"line_spacing=10:box=1:boxcolor=black@0.35:boxborderw=26:"
            f"x=(w-text_w)/2:y=h*0.60:enable='between(t,{hk0:.3f},{hk1:.3f})':"
            f"alpha='if(lt(t,{hk0:.3f}),0,if(lt(t,{hk0+0.6:.3f}),(t-{hk0:.3f})/0.6,1))'")
    if outro:
        # адаптивный контраст под кадр аутро (фикс: на тёмном фоне тёмный текст пропадал)
        draw.append(
            f"drawtext=fontfile={FONT}:textfile={outro_file}:fontcolor={fc_outro}:fontsize={fs_outro}:"
            f"borderw={bw_small}:bordercolor={bc_outro}@0.6:line_spacing=8:"
            f"x=(w-text_w)/2:y=h*0.78:enable='between(t,{ot0:.3f},{duration})':"
            f"alpha='if(lt(t,{ot0+0.3:.3f}),(t-{ot0:.3f})/0.3,1)'")
    if watermark:
        # весь клип: кредит yaromat в нижнем углу (scroll-proof привязка охватов).
        # читаемость на любом фоне — белый текст + тёмная обводка, лёгкая прозрачность.
        wm_file = WORK / "wm.txt"; wm_file.write_text(watermark, encoding="utf-8")
        draw.append(
            f"drawtext=fontfile={FONT}:textfile={wm_file}:fontcolor=white@0.85:fontsize={fs_wm}:"
            f"borderw={bw_small}:bordercolor=black@0.7:"
            f"x=w-text_w-{int(W*0.04)}:y=h-text_h-{int(H*0.035)}")
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
        "-c:v", "libx264",
        *(["-crf", "30", "-preset", "ultrafast"] if preview
          else ["-crf", "23", "-preset", "fast", "-maxrate", "9M", "-bufsize", "18M"]),
        "-r", str(FPS),
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
