#!/usr/bin/env python3
"""Instagram content agent for Laser Electro Epilace Praha.

Pipeline per run:
  1. Claude (creative director) plans posts + stories: concept, a fictional
     model persona, a photo prompt, on-image text, caption, hashtags.
  2. An image provider (OpenAI / Gemini / Replicate) generates the photo.
  3. Claude reviews the photo (anatomy, artifacts, brand fit) and asks for a
     regeneration with a corrected prompt if needed.
  4. Branded text overlay is added and the image is cropped to IG size.
  5. Image is uploaded and scheduled for auto-publishing via Metricool.

Usage:
  python agent.py run                 # plan, generate, publish
  python agent.py run --no-publish    # generate only, save to output/
  python agent.py run --brief "Летняя акция на ноги -20%" --posts 1 --stories 2
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import yaml

from compose import compose
from providers import ProviderError, generate_image
from publish import PublishError, schedule_instagram, upload_public

ROOT = Path(__file__).parent
OUTPUT = ROOT / "output"
HISTORY = ROOT / "history.jsonl"
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
MAX_REGENERATIONS = int(os.getenv("MAX_REGENERATIONS", "2"))

client = anthropic.Anthropic()

SYSTEM = """You are the in-house creative director and Instagram copywriter for a laser and
electro-epilation studio in Prague. You plan Instagram feed posts and stories and write the
photo prompts for an AI image generator that creates FICTIONAL models for the ads.

Rules for the people in the photos:
- Every person is fictional and an adult (roughly 22-50). Never describe or resemble a real
  person, celebrity or influencer. Vary age, body type, skin tone, hair and gender across a plan
  so the feed looks like a real diverse Prague clientele, not one repeated face.
- Tasteful and non-sexual: hair-removal context (legs, underarms, arms, face, back, a bikini line
  shown only through swimwear or clothing at a beach, pool or spa). No nudity, no lingerie shoots.
- Realistic skin with natural texture, natural light, believable anatomy (hands, fingers).

Photo prompt rules (prompts are in English, 60-120 words):
- Describe subject, pose, wardrobe, setting, light, camera (e.g. 85mm, shallow depth of field),
  colour palette matching the brand, and mood. Photorealistic editorial beauty photography.
- The photo must contain NO text, letters, logos or watermarks: text is added later.
- Leave calm negative space where on-image text will go (top or bottom, as you specify).
- Stories are vertical 9:16, feed posts are 4:5.

Copy rules:
- On-image headline: max ~6 words; subline: max ~14 words; CTA: 1-3 words.
- Caption in the brand language, then the extra languages (separated by a blank line and a flag
  emoji), 2-5 short paragraphs, emojis sparingly, end with a clear call to book via DM.
- 8-15 relevant hashtags (Czech + Prague local + niche). Only use prices from the price list.
- Honest advertising: no fake testimonials or reviews, no invented before/after results, no
  medical guarantees ("navždy", "100 %", "bez bolesti"). Say results are individual when relevant.
- Never repeat a concept from the recent history you are given.
"""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["post", "story"]},
                    "pillar": {"type": "string"},
                    "concept": {"type": "string", "description": "One-sentence idea, in Russian, for the owner"},
                    "persona": {"type": "string", "description": "Fictional model: age, look, vibe"},
                    "image_prompt": {"type": "string"},
                    "text_position": {"type": "string", "enum": ["top", "bottom"]},
                    "headline": {"type": "string"},
                    "subline": {"type": "string"},
                    "cta": {"type": "string"},
                    "caption": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "alt_text": {"type": "string"},
                },
                "required": ["format", "pillar", "concept", "persona", "image_prompt", "text_position",
                             "headline", "subline", "cta", "caption", "hashtags", "alt_text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "revised_prompt": {"type": "string", "description": "Improved prompt if not approved, else empty"},
    },
    "required": ["approved", "issues", "revised_prompt"],
    "additionalProperties": False,
}


def ask_claude(content, schema: dict, effort: str = "high") -> dict:
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=32000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": content}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude отклонил запрос; измените бриф.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Ответ Claude обрезан (max_tokens); уменьшите число публикаций за запуск.")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def load_history(limit: int = 40) -> list[dict]:
    if not HISTORY.exists():
        return []
    lines = HISTORY.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(line) for line in lines if line.strip()]


def plan(brand: dict, n_posts: int, n_stories: int, brief: str | None) -> list[dict]:
    history = [{"date": h["date"], "format": h["format"], "concept": h["concept"], "persona": h["persona"]}
               for h in load_history()]
    prompt = (
        f"Brand profile (YAML):\n{yaml.safe_dump(brand, allow_unicode=True)}\n\n"
        f"Recent history (do not repeat concepts or personas):\n{json.dumps(history, ensure_ascii=False)}\n\n"
        f"Today is {dt.date.today().isoformat()}; take the season and upcoming Czech holidays into account.\n"
        f"Plan exactly {n_posts} feed posts and {n_stories} stories. Stories may form a small sequence "
        f"(teaser → info → CTA), feed posts should cover different pillars.\n"
    )
    if brief:
        prompt += f"\nOwner's brief for this run (top priority): {brief}\n"
    return ask_claude(prompt, PLAN_SCHEMA)["items"]


def review(image_bytes: bytes, item: dict) -> dict:
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": _mime(image_bytes),
                                      "data": base64.standard_b64encode(image_bytes).decode()}},
        {"type": "text", "text": (
            "Review this generated ad photo before it is published.\n"
            f"Intended persona: {item['persona']}\nPrompt used: {item['image_prompt']}\n"
            f"Text will be overlaid at the {item['text_position']}.\n\n"
            "Reject it if any of these hold: distorted anatomy (hands, fingers, limbs, eyes, teeth), "
            "plastic or waxy skin, visible text/letters/logos/watermarks, the person looks underage, "
            "nudity or sexualised framing, the image looks obviously AI-made, it clashes with the brand look, "
            "or there is no calm area for the text. If rejected, write a revised prompt that fixes it."
        )},
    ]
    return ask_claude(content, REVIEW_SCHEMA, effort="medium")


def _mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def slot_times(brand: dict, fmt: str, count: int) -> list[str]:
    sched = brand["schedule"]
    tz = ZoneInfo(brand["timezone"])
    day = dt.datetime.now(tz).date() + dt.timedelta(days=sched.get("days_ahead", 1))
    hours = sched["post_hours" if fmt == "post" else "story_hours"]
    times = []
    for i in range(count):
        h, m = map(int, hours[i % len(hours)].split(":"))
        d = day + dt.timedelta(days=i // len(hours))
        times.append(dt.datetime(d.year, d.month, d.day, h, m).strftime("%Y-%m-%dT%H:%M:%S"))
    return times


def run(args) -> int:
    brand = yaml.safe_load((ROOT / "brand.yaml").read_text(encoding="utf-8"))
    sched = brand["schedule"]
    n_posts = sched["posts_per_run"] if args.posts is None else args.posts
    n_stories = sched["stories_per_run"] if args.stories is None else args.stories

    print(f"→ Claude планирует {n_posts} пост(а) и {n_stories} сторис…")
    items = plan(brand, n_posts, n_stories, args.brief)

    times = {f: iter(slot_times(brand, f, sum(i["format"] == f for i in items))) for f in ("post", "story")}
    run_dir = OUTPUT / dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    failures = 0

    for idx, item in enumerate(items, 1):
        fmt = item["format"]
        print(f"\n[{idx}/{len(items)}] {fmt}: {item['concept']}")
        prompt = item["image_prompt"]
        raw = None
        for attempt in range(MAX_REGENERATIONS + 1):
            try:
                raw = generate_image(prompt, fmt, args.provider)
            except ProviderError as e:
                print(f"   ✗ генерация: {e}")
                raw = None
                break
            if args.skip_review:
                break
            verdict = review(raw, {**item, "image_prompt": prompt})
            if verdict["approved"]:
                print(f"   ✓ проверка пройдена (попытка {attempt + 1})")
                break
            print(f"   ↻ отклонено: {'; '.join(verdict['issues'])}")
            prompt = verdict["revised_prompt"] or prompt
            if attempt == MAX_REGENERATIONS:
                raw = None
        if raw is None:
            print("   ✗ пропущено: не удалось получить качественное изображение")
            failures += 1
            continue

        final = compose(raw, fmt, item["headline"], item["subline"], item["cta"], brand, item["text_position"])
        name = f"{idx:02d}_{fmt}"
        (run_dir / f"{name}_raw.png").write_bytes(raw)
        (run_dir / f"{name}.jpg").write_bytes(final)
        caption = item["caption"].strip() + "\n\n" + " ".join(
            t if t.startswith("#") else f"#{t}" for t in item["hashtags"])
        (run_dir / f"{name}.txt").write_text(caption, encoding="utf-8")
        item.update(final_prompt=prompt, file=str(run_dir / f"{name}.jpg"))

        when = next(times[fmt])
        if args.no_publish:
            print(f"   💾 сохранено: {run_dir / (name + '.jpg')}")
        else:
            try:
                url = upload_public(final, f"{run_dir.name}/{name}.jpg")
                res = schedule_instagram(url, fmt, caption, item["alt_text"], when, brand["timezone"])
                item.update(image_url=url, scheduled_for=when, metricool=res)
                print(f"   📅 запланировано в Metricool на {when}")
            except PublishError as e:
                print(f"   ✗ публикация: {e}")
                failures += 1

        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"date": dt.date.today().isoformat(), **item}, ensure_ascii=False) + "\n")

    (run_dir / "plan.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nГотово. Файлы: {run_dir}")
    return 1 if failures else 0


def main() -> int:
    p = argparse.ArgumentParser(description="AI-агент контента для Instagram")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="спланировать, сгенерировать и опубликовать")
    r.add_argument("--brief", help="задание на этот запуск (акция, тема, праздник)")
    r.add_argument("--posts", type=int, help="число постов в ленту")
    r.add_argument("--stories", type=int, help="число сторис")
    r.add_argument("--provider", help="openai | gemini | replicate | mock")
    r.add_argument("--no-publish", action="store_true", help="только сохранить файлы")
    r.add_argument("--skip-review", action="store_true", help="не проверять картинки через Claude")
    args = p.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
