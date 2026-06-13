#!/usr/bin/env python3
"""
tsx_scout_merge.py — мердж одобренных TSX-кандидатов из tsx_proposals.json в tsx_templates.json.
Зеркало style_scout_merge.py. Гейт РУЧНОЙ: запускать ПОСЛЕ ОК yaromat по превью в TG.

ВАЖНО: мердж только РЕГИСТРИРУЕТ шаблон (имя+composition+мета). Сам .tsx-файл шаблона
должен быть уже в remotion/src/templates/ и добавлен в реестр TEMPLATES (Root.tsx),
провалидирован sandbox-рендером. Этот скрипт — финальная отмашка «в боевой пул».

  python3 tsx_scout_merge.py --list
  python3 tsx_scout_merge.py --names ParallaxDepth ParticleDrift
  python3 tsx_scout_merge.py --all
"""
import json, argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "tsx_templates.json"
PROPOSALS = HERE / "tsx_proposals.json"
KEEP = ("name", "note", "composition", "source", "format")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if not PROPOSALS.exists():
        print("нет tsx_proposals.json — агенту ещё нечего предлагать"); return
    prop = json.loads(PROPOSALS.read_text(encoding="utf-8"))["candidates"]

    if args.list:
        for c in prop:
            print(f"  {c['name']:24} comp={c.get('composition')} source={c.get('source')} "
                  f"preview={c.get('preview','—')}")
        return

    pick = prop if args.all else [c for c in prop if c["name"] in args.names]
    if not pick:
        print("нечего мерджить (укажи --names или --all)"); return

    doc = json.loads(TEMPLATES.read_text(encoding="utf-8"))
    existing = {t["name"] for t in doc["templates"]}
    added = []
    for c in pick:
        if c["name"] in existing:
            print(f"  пропуск (уже есть): {c['name']}"); continue
        doc["templates"].append({k: c[k] for k in KEEP if k in c})
        added.append(c["name"])
    doc["_version"] = doc.get("_version", 1) + (1 if added else 0)
    TEMPLATES.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"добавлено {len(added)}: {added} | всего шаблонов: {len(doc['templates'])}")
    print("не забудь: убедись что .tsx есть в remotion/src/templates/ и в Root.tsx TEMPLATES,")
    print("           затем git add tsx_templates.json remotion/ && commit && push в render-репо")


if __name__ == "__main__":
    main()
