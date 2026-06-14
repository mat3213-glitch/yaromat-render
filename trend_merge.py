#!/usr/bin/env python3
"""
trend_merge.py — S3.2: применяет ОДОБРЕННЫЕ тренд-параметры (от mimo-анализа сигналов).
Грейды → styles.json (Style Scout), запросы → extra_queries.json (подмешиваются в QUERIES Скаута).

Входы через env (передаёт trend_merge.yml из dispatch-inputs облачного бота):
  CANDIDATES_JSON — JSON-массив грейдов [{name,eq,balance,note,...}]
  QUERIES_JSON    — JSON-массив строк-запросов
Дедуп по имени/строке. Только yaromat апрувит (через /trend_apply в боте).
"""
import json, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
STYLES = HERE / "styles.json"
EXTRA_Q = HERE / "extra_queries.json"
KEEP = ("name", "note", "eq", "balance", "grain", "vignette")


def main():
    cands = json.loads(os.environ.get("CANDIDATES_JSON", "[]") or "[]")
    queries = json.loads(os.environ.get("QUERIES_JSON", "[]") or "[]")

    doc = json.loads(STYLES.read_text(encoding="utf-8")) if STYLES.exists() else {"_version": 1, "styles": []}
    existing = {s["name"] for s in doc["styles"]}
    added = []
    for c in cands:
        if not isinstance(c, dict) or not c.get("name") or c["name"] in existing:
            continue
        c.setdefault("grain", [12, 17])
        c.setdefault("vignette", "angle=PI/4.5")
        doc["styles"].append({k: c[k] for k in KEEP if k in c})
        existing.add(c["name"]); added.append(c["name"])
    if added:
        doc["_version"] = doc.get("_version", 1) + 1
        STYLES.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    q = json.loads(EXTRA_Q.read_text(encoding="utf-8")) if EXTRA_Q.exists() else []
    qset = set(q)
    newq = [x for x in queries if isinstance(x, str) and x and x not in qset]
    if newq:
        (EXTRA_Q).write_text(json.dumps(q + newq, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"added styles: {added} | new queries: {len(newq)} | total styles: {len(doc['styles'])}")


if __name__ == "__main__":
    main()
