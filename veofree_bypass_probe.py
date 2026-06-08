"""
BYPASS PROBE veoaifree — пейволл-модалка («Unlock Premium Access») имеет крестик.
Вопрос: закрыть модалку → сгенерить снова → пустит или нет?
  - если ДА → обход тривиален (гасим апселл, продолжаем на том же IP)
  - если НЕТ → лимит жёсткий по IP → обход = 1 ген на прогон (ротация раннера)

Делает: gen1 → (ожид. ok) → gen2 (ожид. paywall) → перебирает стратегии закрытия модалки,
логирует структуру close-кандидатов → после закрытия пробует gen ещё раз → вывод.
Env: YADISK_LOGIN/PASSWORD, DEST_FOLDER
"""
import os, time, json, requests
from pathlib import Path
from urllib.parse import quote as urlquote
from playwright.sync_api import sync_playwright

YL=os.environ["YADISK_LOGIN"]; YP=os.environ["YADISK_PASSWORD"]
URL="https://veoaifree.com/seedance-2-0-video-generator-free/"
DEST=os.environ.get("DEST_FOLDER","Content factory/_probe_veo_bypass")
WEBDAV="https://webdav.yandex.ru"; AUTH=(YL,YP); TMP=Path("/tmp/veobp"); TMP.mkdir(exist_ok=True)
R=[]
def log(s): print(s,flush=True); R.append(str(s))
def yd_mkcol(p):
    c=""
    for x in p.split("/"):
        c=f"{c}/{x}" if c else x; requests.request("MKCOL",f"{WEBDAV}/{urlquote(c)}",auth=AUTH,timeout=30)
def yd_put(local,remote):
    for _ in range(3):
        try:
            with open(local,"rb") as f:
                if requests.put(f"{WEBDAV}/{urlquote(remote)}",data=f,auth=AUTH,timeout=180).status_code in (200,201,204): return True
        except Exception as e: print("up err",e,flush=True)
        time.sleep(3)
    return False

def paywall_visible(pg):
    for sel in [".pf-btn","#pfEmail",".plan-btn",".btn-month",".btn-life"]:
        try:
            el=pg.query_selector(sel)
            if el and el.is_visible(): return sel
        except: pass
    return None

def cur_src(pg):
    v=pg.query_selector("video"); s=v.get_attribute("src") if v else None
    return s if (s and s.startswith("http")) else None

def try_generate(pg, prompt, prev_src):
    """Успех ТОЛЬКО если появился НОВЫЙ video src (≠ prev_src). Иначе paywall/timeout."""
    ta=pg.query_selector("textarea#fn__include_textarea") or pg.query_selector("textarea")
    if not ta: return "no_input","",prev_src
    try: ta.click(); ta.fill(""); ta.fill(prompt)
    except Exception as e: return "fill_err",str(e),prev_src
    btn=pg.query_selector("#generate_it")
    if not btn: return "no_button","",prev_src
    try: btn.click(timeout=8000)
    except Exception as e: return "click_err",str(e),prev_src
    for _ in range(24):
        pg.wait_for_timeout(5000)
        if paywall_visible(pg): return "paywall","",prev_src
        s=cur_src(pg)
        if s and s!=prev_src: return "ok",s[:90],s   # именно НОВЫЙ url
    return "timeout",f"src без изменений ({(prev_src or '')[-30:]})",prev_src

def dump_close_candidates(pg):
    # ищем потенциальные кнопки закрытия видимой модалки
    js="""() => {
      const out=[];
      const cand=document.querySelectorAll('button, [class*=close], [class*=Close], [aria-label], svg, .modal *');
      for (const el of cand){
        const r=el.getBoundingClientRect();
        if (r.width===0||r.height===0) continue;
        const t=(el.innerText||'').trim().slice(0,20);
        const al=el.getAttribute('aria-label')||'';
        const cl=el.className && el.className.baseVal!==undefined ? el.className.baseVal : (el.className||'');
        if (/close|×|✕|✖|dismiss|skip/i.test(cl+al+t)) out.push({tag:el.tagName,cls:String(cl).slice(0,40),al,t});
      }
      return out.slice(0,15);
    }"""
    try: return pg.evaluate(js)
    except Exception as e: return [{"err":str(e)}]

def try_close(pg):
    # перебор стратегий закрытия
    strategies=[
        ("Escape", lambda: pg.keyboard.press("Escape")),
        ("aria Close", lambda: pg.click("[aria-label='Close']", timeout=2000)),
        (".close-btn", lambda: pg.click(".close-btn", timeout=2000)),
        ("#pfClose", lambda: pg.click("#pfClose", timeout=2000)),
        (".pf-close", lambda: pg.click(".pf-close", timeout=2000)),
        ("[class*=close] visible", lambda: pg.click("[class*='close']:visible", timeout=2000)),
        ("text ×", lambda: pg.get_by_text("×", exact=False).first.click(timeout=2000)),
        ("click outside", lambda: pg.mouse.click(5,5)),
    ]
    for name,fn in strategies:
        try:
            fn(); pg.wait_for_timeout(1500)
            if not paywall_visible(pg):
                return name
        except: pass
    return None

log("=== VEOFREE BYPASS PROBE ===")
try: log(f"runner IP: {requests.get('https://api.ipify.org',timeout=15).text}")
except: pass

with sync_playwright() as pw:
    br=pw.chromium.launch(headless=True,args=["--no-sandbox"])
    ctx=br.new_context(viewport={"width":1280,"height":900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
    pg=ctx.new_page(); pg.goto(URL,wait_until="domcontentloaded",timeout=60000); pg.wait_for_timeout(5000)

    last=None
    st1,d1,last=try_generate(pg,"deep blue ocean light rays",last); log(f"[gen1] {st1} {d1}")
    st2,d2,last=try_generate(pg,"slow drifting clouds dark sky",last); log(f"[gen2] {st2} {d2}")

    if st2=="paywall":
        log("\n-- close candidates --"); [log(f"  {c}") for c in dump_close_candidates(pg)]
        pg.screenshot(path=str(TMP/"modal.png"))
        closed=try_close(pg)
        log(f"\nзакрытие модалки: {'✅ '+closed if closed else '❌ не удалось'}")
        if closed:
            st3,d3,last=try_generate(pg,"calm misty forest at dawn",last)
            log(f"[gen3 после закрытия, тот же IP] {st3} {d3}")
            if st3=="ok":
                log(">>> ВЫВОД: пейволл — СОФТ. Закрыл модалку → НОВОЕ видео сгенерилось на том же IP. Обход тривиален.")
            elif st3=="paywall":
                log(">>> ВЫВОД: модалка возвращается → лимит ЖЁСТКИЙ по IP. Обход = 1 ген/прогон (ротация раннера).")
            elif st3=="timeout":
                log(">>> ВЫВОД: после закрытия НОВОЕ видео НЕ появилось (ген заблокирован, оверлей лишь скрыт) → лимит ЖЁСТКИЙ по IP. Обход = 1 ген/прогон.")
            else:
                log(f">>> ген после закрытия: {st3} {d3} (неясно)")
        else:
            log(">>> модалку закрыть не удалось стандартно — см. modal.png + кандидаты")
    else:
        log(f"\ngen2 не дал пейволл ({st2}) — лимит выше или таймили")
    br.close()

(TMP/"report.txt").write_text("\n".join(R),encoding="utf-8")
yd_mkcol(DEST)
for f in TMP.iterdir(): yd_put(f,f"{DEST}/{f.name}")
log("DONE")
