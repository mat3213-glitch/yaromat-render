#!/usr/bin/env python3
"""
gen_cf_image.py — генерация картинки через CF Worker yaromat-img (Workers AI).

Гоняется на GH Actions (стабильный линк к Cloudflare), НЕ на локальном буке:
RU↔CF линк рвёт длинные /gen-запросы. Модель крутится на GPU Cloudflare.

ENV:
  IMG_WORKER_URL     — базовый URL воркера (по умолч. yaromat-img.mat3213.workers.dev)
  IMG_WORKER_SECRET  — значение WORKER_SECRET воркера (из GH secret)

Запуск:
  python gen_cf_image.py --model flux --out flux.jpg --prompt "..."
  python gen_cf_image.py --model sdxl --out sdxl.png --width 1280 --height 720 \
      --steps 20 --negative "..." --prompt "..."
"""
import argparse
import os
import sys

import requests

URL = os.environ.get("IMG_WORKER_URL", "https://yaromat-img.mat3213.workers.dev").rstrip("/")
SECRET = os.environ.get("IMG_WORKER_SECRET", "")

MODELS = {
    "flux": "@cf/black-forest-labs/flux-1-schnell",
    "sdxl": "@cf/stabilityai/stable-diffusion-xl-base-1.0",
    "sdxl-lightning": "@cf/bytedance/stable-diffusion-xl-lightning",
}


def generate(prompt, model_key, out, negative=None, width=None, height=None, steps=None):
    body = {"prompt": prompt, "model": MODELS.get(model_key, model_key)}
    if negative:
        body["negative_prompt"] = negative
    if width:
        body["width"] = width
    if height:
        body["height"] = height
    if steps:
        body["steps"] = steps

    r = requests.post(f"{URL}/gen", headers={"X-Worker-Secret": SECRET}, json=body, timeout=(15, 180))
    ct = r.headers.get("content-type", "")
    if r.status_code != 200 or not ct.startswith("image"):
        print(f"[gen_cf] FAIL HTTP {r.status_code} | {ct} | {r.text[:200]}")
        sys.exit(1)
    with open(out, "wb") as f:
        f.write(r.content)
    print(f"[gen_cf] ✅ {out} | {len(r.content)} bytes | {ct} | model={model_key}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--model", default="flux", help="flux | sdxl | sdxl-lightning | полный @cf/...")
    ap.add_argument("--out", required=True)
    ap.add_argument("--negative", default=None)
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--steps", type=int, default=None)
    args = ap.parse_args()

    if not SECRET:
        print("[gen_cf] ERROR: IMG_WORKER_SECRET не задан")
        sys.exit(2)

    generate(args.prompt, args.model, args.out, args.negative, args.width, args.height, args.steps)


if __name__ == "__main__":
    main()
