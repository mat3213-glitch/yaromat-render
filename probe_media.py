"""
PROBE: проверка, обходит ли раннер GitHub Actions (US-IP) блоки источников,
которые мрут с RU-IP / CF-Worker. Качает Pexels-файл (CF-защищён) и yt-dlp Pinterest-пин,
пишет результат и льёт на ЯД для чтения с локальной машины.

Env (GitHub Secrets):
  YADISK_LOGIN / YADISK_PASSWORD — WebDAV
  PEXELS_URL  — прямой videos.pexels.com mp4 (есть дефолт)
  PIN_URL     — pinterest пин/доска (есть дефолт)
"""
import os, subprocess, requests
from pathlib import Path
from urllib.parse import quote as urlquote

YADISK_LOGIN = os.environ["YADISK_LOGIN"]
YADISK_PASS  = os.environ["YADISK_PASSWORD"]
PEXELS_URL = os.environ.get("PEXELS_URL",
    "https://videos.pexels.com/video-files/12336960/12336960-sd_426_228_30fps.mp4")
PIN_URL = os.environ.get("PIN_URL", "https://pin.it/6yweXbZ0O")
WEBDAV_BASE = "https://webdav.yandex.ru"
AUTH_YD = (YADISK_LOGIN, YADISK_PASS)

lines = []
def log(s):
    print(s, flush=True); lines.append(s)

log("=== PROBE media from GitHub Actions runner (US-IP) ===")

# IP / гео раннера
try:
    ip = requests.get("https://api.ipify.org", timeout=15).text
    geo = requests.get(f"https://ipinfo.io/{ip}/json", timeout=15).json()
    log(f"runner IP: {ip}  geo: {geo.get('country')}/{geo.get('region')}  org: {geo.get('org')}")
except Exception as e:
    log(f"ip lookup err: {e}")

# 1) PEXELS — прямой download CF-защищённого файла
log("\n--- PEXELS ---")
log(f"url: {PEXELS_URL}")
try:
    r = requests.get(PEXELS_URL, timeout=40, stream=True, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
        "Referer": "https://www.pexels.com/", "Range": "bytes=0-1048575"})
    body = r.raw.read(1_100_000) if r.status_code in (200, 206) else b""
    log(f"status: {r.status_code}  server: {r.headers.get('server')}  bytes_read: {len(body)}")
    log("PEXELS: ✅ PASS" if r.status_code in (200, 206) and len(body) > 10000 else "PEXELS: ❌ BLOCKED")
except Exception as e:
    log(f"PEXELS: ❌ ERR {type(e).__name__}: {e}")

# 2) PINTEREST — yt-dlp пин/доску (HLS)
log("\n--- PINTEREST (yt-dlp) ---")
log(f"url: {PIN_URL}")
try:
    # сначала список форматов (быстро, без полной закачки)
    p = subprocess.run(["yt-dlp", "--no-warnings", "--socket-timeout", "20",
                        "-F", PIN_URL], capture_output=True, text=True, timeout=120)
    log(f"yt-dlp -F rc={p.returncode}")
    out = (p.stdout or "")[-800:] + (("\nERR:" + p.stderr[-400:]) if p.returncode else "")
    log(out.strip())
    if p.returncode == 0:
        # пробуем реально скачать в самом мелком качестве
        d = subprocess.run(["yt-dlp", "--no-warnings", "-f", "worst", "-o", "/tmp/pin.%(ext)s",
                            PIN_URL], capture_output=True, text=True, timeout=180)
        got = list(Path("/tmp").glob("pin.*"))
        sz = got[0].stat().st_size if got else 0
        log(f"download rc={d.returncode}  file={got[0].name if got else '-'}  size={sz//1024}KB")
        log("PINTEREST: ✅ PASS" if sz > 10000 else "PINTEREST: ❌ download empty")
    else:
        log("PINTEREST: ❌ extract failed")
except subprocess.TimeoutExpired:
    log("PINTEREST: ❌ TIMEOUT")
except Exception as e:
    log(f"PINTEREST: ❌ ERR {type(e).__name__}: {e}")

# результат → ЯД
res = "\n".join(lines) + "\n"
Path("/tmp/probe_result.txt").write_text(res, encoding="utf-8")
remote = "Content factory/_probe/probe_result.txt"
requests.request("MKCOL", f"{WEBDAV_BASE}/{urlquote('Content factory/_probe')}", auth=AUTH_YD, timeout=30)
u = requests.put(f"{WEBDAV_BASE}/{urlquote(remote)}", data=res.encode("utf-8"), auth=AUTH_YD, timeout=60)
log(f"\nupload result → {remote}: {u.status_code}")
