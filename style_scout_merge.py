#!/usr/bin/env python3
"""
style_scout_merge.py — мердж одобренных кандидатов из style_proposals.json в styles.json.
Гейт ручной: запускать ПОСЛЕ ОК yaromat по контакт-листу.

  python3 style_scout_merge.py --names scout_cool_night_muted scout_warm_mid_soft
  python3 style_scout_merge.py --all          # влить всех кандидатов
  python3 style_scout_merge.py --list         # показать кандидатов, не менять
"""
import json, argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
STYLES = HERE / "styles.json"
PROPOSALS = HERE / "style_proposals.json"
KEEP = ("name", "note", "eq", "balance", "grain", "vignette")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    prop = json.loads(PROPOSALS.read_text(encoding="utf-8"))["candidates"]
    if args.list:
        for c in prop:
            print(f"  {c['name']:28} eq={c['eq']} balance={c.get('balance')}")
        return

    pick = prop if args.all else [c for c in prop if c["name"] in args.names]
    if not pick:
        print("нечего мерджить (укажи --names или --all)"); return

    doc = json.loads(STYLES.read_text(encoding="utf-8"))
    existing = {s["name"] for s in doc["styles"]}
    added = []
    for c in pick:
        if c["name"] in existing:
            print(f"  пропуск (уже есть): {c['name']}"); continue
        doc["styles"].append({k: c[k] for k in KEEP if k in c})
        added.append(c["name"])
    doc["_version"] = doc.get("_version", 1) + (1 if added else 0)
    STYLES.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"добавлено {len(added)}: {added} | всего стилей: {len(doc['styles'])}")
    print("не забудь: git add styles.json && commit && push в render-репо")


if __name__ == "__main__":
    main()
