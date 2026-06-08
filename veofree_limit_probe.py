"""
LIMIT PROBE veoaifree (Seedance 2.0) — нащупать предел бесплатных генераций и проверить обход.
Аккуратно (паузы, ограниченное число) чтобы не словить IP-блок.

Делает в ОДНОЙ сессии до MAX_GENS генераций подряд, после каждой логирует:
  - успех (появился video src) или пейволл/ошибка
  - снимок localStorage + cookies (ищем счётчик лимита)
Когда ловит пейволл → пробует ОБХОД: чистит cookies+localStorage (+ new context) и повторяет.
Вывод (report.txt + ключевые скрины) → ЯД.

Env: YADISK_LOGIN/PASSWORD, MAX_GENS (деф 8), DELAY_S (деф 12), DEST_FOLDER
"""
import os, time, json, requests
from pathlib import Path
from urllib.parse import quote as urlquote
from playwright.sync_api import sync_playwright

YL=os.environ["YADISK_LOGIN"]; YP=os.environ["YADISK_PASSWORD"]
MAX_GENS=int(os.environ.get("MAX_GENS","8")); DELAY=int(os.environ.get("DELAY_S","12"))
URL="https://veoaifree.com/seedance-2-0-video-generator-free/"
DEST=os.environ.get("DEST_FOLDER","Content factory/_probe_veo_limit")
WEBDAV="https://webdav.yandex.ru"; AUTH=(YL,YP); TMP=Path("/tmp/veolim"); TMP.mkdir(exist_ok=True)
R=[]
def log(s): print(s,flush=True); R.append(str(s))
def yd_mkcol(p):
    c=""
    for x in p.split("/"):
        c=f"{c}/{x}" if c else x
        requests.request("MKCOL",f"{WEBDAV}/{urlquote(c)}",auth=AUTH,timeout=30)
def yd_put(local,remote):
    for _ in range(3):
        try:
            with open(local,"rb") as f:
                r=requests.put(f"{WEBDAV}/{urlquote(remote)}",data=f,auth=AUTH,timeout=180)
            if r.status_code in (200,201,204): return True
        except Exception as e: print("up err",e,flush=True)
        time.sleep(3)
    return False

PROMPTS=["deep blue ocean water with light rays","slow drifting clouds over dark mountains",
         "ink dispersing in clear water","foggy forest at dawn","calm sea surface from below",
         "northern lights over still lake","rain on a window at night","smoke swirling in dark room",
         "underwater sun rays in the deep","slow waves on a misty shore"]

def dismiss_modals(pg):
    # закрыть рекламные/согласие/пейволл-модалки если мешают
    for sel in ["#pfClose",".pf-close","#closeBtn",".close-btn","#ab-allow",".ab-primary",
                "button:has-text('Accept')","button:has-text('Got it')","button:has-text('Close')"]:
        try:
            el=pg.query_selector(sel)
            if el and el.is_visible(): el.click(timeout=2000); pg.wait_for_timeout(500)
        except: pass

def paywall_visible(pg):
    # признаки пейволла: видимая форма оплаты / план-кнопки / текст про лимит/покупку
    for sel in [".pf-btn","#pfEmail",".plan-btn",".btn-month",".btn-life"]:
        try:
            el=pg.query_selector(sel)
            if el and el.is_visible(): return f"paywall el {sel}"
        except: pass
    try:
        body=(pg.inner_text("body") or "").lower()
        for kw in ["upgrade to continue","purchase a plan","limit reached","daily limit",
                   "buy a package","you have reached","please subscribe","out of credits"]:
            if kw in body: return f"paywall text '{kw}'"
    except: pass
    return None

def one_gen(pg, prompt):
    """Одна генерация. Возвращает (status, detail)."""
    dismiss_modals(pg)
    ta=pg.query_selector("textarea#fn__include_textarea") or pg.query_selector("textarea")
    if not ta: return "no_input","нет textarea"
    try: ta.click(); ta.fill(""); ta.fill(prompt)
    except Exception as e: return "fill_err",str(e)
    btn=pg.query_selector("#generate_it") or None
    if not btn:
        try: btn=pg.get_by_role("button",name="GENERATE",exact=False).first.element_handle()
        except: pass
    if not btn: return "no_button","нет кнопки"
    pre_pw = paywall_visible(pg)
    try: btn.click(timeout=8000)
    except Exception as e: return "click_err",str(e)
    # ждём video src ИЛИ пейволл, до ~120с
    for _ in range(24):
        pg.wait_for_timeout(5000)
        pw=paywall_visible(pg)
        if pw: return "paywall",pw
        v=pg.query_selector("video")
        src=v.get_attribute("src") if v else None
        if src and src.startswith("http"): return "ok",src[:90]
    return "timeout","нет видео за 120с"

def snap(pg):
    try: ck=[c["name"] for c in pg.context.cookies()]
    except: ck=[]
    try: ls=pg.evaluate("Object.keys(localStorage)")
    except: ls=[]
    # значения ключей, где может быть счётчик
    vals={}
    try:
        for k in ls:
            if any(t in k.lower() for t in ["gen","count","limit","free","use","credit","quota","trial"]):
                vals[k]=pg.evaluate(f"localStorage.getItem({json.dumps(k)})")
    except: pass
    return ck, ls, vals

log(f"=== VEOFREE LIMIT PROBE === MAX_GENS={MAX_GENS} DELAY={DELAY}s")
try: log(f"runner IP: {requests.get('https://api.ipify.org',timeout=15).text}")
except: pass

with sync_playwright() as pw:
    br=pw.chromium.launch(headless=True,args=["--no-sandbox"])
    ctx=br.new_context(viewport={"width":1280,"height":900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
    pg=ctx.new_page()
    pg.goto(URL,wait_until="domcontentloaded",timeout=60000); pg.wait_for_timeout(5000)
    dismiss_modals(pg)
    hit_paywall_at=None
    for i in range(1,MAX_GENS+1):
        st,detail=one_gen(pg,PROMPTS[(i-1)%len(PROMPTS)])
        ck,ls,vals=snap(pg)
        log(f"\n[gen {i}] {st} | {detail}")
        log(f"   cookies={ck}")
        log(f"   ls_keys={ls}")
        if vals: log(f"   counters={vals}")
        if st=="paywall":
            hit_paywall_at=i
            pg.screenshot(path=str(TMP/f"paywall_at_{i}.png"))
            log(f"   >>> ПЕЙВОЛЛ на генерации #{i}")
            break
        time.sleep(DELAY)

    # ОБХОД: чистим хранилище + new context, пробуем ещё раз
    if hit_paywall_at:
        log("\n=== ПРОБА ОБХОДА: clear cookies+localStorage + new context ===")
        try:
            ctx.clear_cookies()
            pg.evaluate("localStorage.clear(); sessionStorage.clear();")
        except Exception as e: log(f"clear err {e}")
        ctx2=br.new_context(viewport={"width":1280,"height":900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36")
        pg2=ctx2.new_page(); pg2.goto(URL,wait_until="domcontentloaded",timeout=60000); pg2.wait_for_timeout(5000)
        dismiss_modals(pg2)
        st,detail=one_gen(pg2,"calm deep water light rays")
        log(f"[bypass via new context] {st} | {detail}")
        log("   ВЫВОД: лимит КЛИЕНТСКИЙ (обходится чистой сессией)" if st=="ok"
            else "   ВЫВОД: лимит держится и в чистой сессии → вероятно ПО IP (спасёт ротация раннера)")
    else:
        log(f"\n=== за {MAX_GENS} генераций пейволл НЕ словлен — лимит выше {MAX_GENS} ===")
    br.close()

(TMP/"report.txt").write_text("\n".join(R),encoding="utf-8")
yd_mkcol(DEST)
for f in TMP.iterdir():
    yd_put(f,f"{DEST}/{f.name}")
log("DONE")
