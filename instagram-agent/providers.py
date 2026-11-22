"""Image generation providers. Each returns raw image bytes (PNG/JPEG).

Select with IMAGE_PROVIDER=openai|gemini|replicate|mock.
"""
from __future__ import annotations

import base64
import io
import os
import time

import requests

TIMEOUT = 300


class ProviderError(RuntimeError):
    pass


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise ProviderError(f"Не задана переменная окружения {name}")
    return value


# fmt -> aspect ratio we ask the generator for (final crop happens in compose.py)
ASPECT = {"post": "4:5", "story": "9:16"}


def generate_openai(prompt: str, fmt: str) -> bytes:
    """OpenAI Images API (gpt-image-*)."""
    size = "1024x1536"  # portrait; works for both 4:5 and 9:16 after cropping
    resp = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {_env('OPENAI_API_KEY')}"},
        json={
            "model": os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            "prompt": prompt,
            "size": size,
            "quality": os.getenv("OPENAI_IMAGE_QUALITY", "high"),
            "n": 1,
        },
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise ProviderError(f"OpenAI {resp.status_code}: {resp.text[:500]}")
    item = resp.json()["data"][0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    return requests.get(item["url"], timeout=TIMEOUT).content


def generate_gemini(prompt: str, fmt: str) -> bytes:
    """Google Gemini image generation (generateContent with IMAGE modality)."""
    model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": _env("GEMINI_API_KEY")},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": ASPECT[fmt]},
            },
        },
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise ProviderError(f"Gemini {resp.status_code}: {resp.text[:500]}")
    for cand in resp.json().get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            data = part.get("inlineData") or part.get("inline_data")
            if data and data.get("data"):
                return base64.b64decode(data["data"])
    raise ProviderError(f"Gemini не вернул изображение: {resp.text[:500]}")


def generate_replicate(prompt: str, fmt: str) -> bytes:
    """Replicate (Flux by default)."""
    model = os.getenv("REPLICATE_MODEL", "black-forest-labs/flux-1.1-pro-ultra")
    headers = {"Authorization": f"Bearer {_env('REPLICATE_API_TOKEN')}", "Prefer": "wait"}
    resp = requests.post(
        f"https://api.replicate.com/v1/models/{model}/predictions",
        headers=headers,
        json={"input": {
            "prompt": prompt,
            "aspect_ratio": ASPECT[fmt],
            "output_format": "png",
            "raw": True,  # more natural, less "AI-glossy" skin on flux ultra
            "safety_tolerance": 2,
        }},
        timeout=TIMEOUT,
    )
    if resp.status_code not in (200, 201):
        raise ProviderError(f"Replicate {resp.status_code}: {resp.text[:500]}")
    pred = resp.json()
    deadline = time.time() + TIMEOUT
    while pred.get("status") not in ("succeeded", "failed", "canceled"):
        if time.time() > deadline:
            raise ProviderError("Replicate: истекло время ожидания")
        time.sleep(3)
        pred = requests.get(pred["urls"]["get"], headers=headers, timeout=60).json()
    if pred["status"] != "succeeded":
        raise ProviderError(f"Replicate: {pred.get('error')}")
    out = pred["output"]
    url = out[0] if isinstance(out, list) else out
    return requests.get(url, timeout=TIMEOUT).content


def generate_mock(prompt: str, fmt: str) -> bytes:
    """Offline placeholder for testing the pipeline without paying for images."""
    from PIL import Image, ImageDraw

    w, h = (1024, 1280) if fmt == "post" else (1024, 1820)
    img = Image.new("RGB", (w, h), "#d9cfe8")
    d = ImageDraw.Draw(img)
    for i in range(0, h, 40):
        d.line([(0, i), (w, i + 200)], fill="#cbbfe0", width=12)
    d.ellipse([w * 0.3, h * 0.18, w * 0.7, h * 0.5], fill="#e8cdb8")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


PROVIDERS = {
    "openai": generate_openai,
    "gemini": generate_gemini,
    "replicate": generate_replicate,
    "mock": generate_mock,
}


def generate_image(prompt: str, fmt: str, provider: str | None = None) -> bytes:
    name = (provider or os.getenv("IMAGE_PROVIDER", "openai")).lower()
    if name not in PROVIDERS:
        raise ProviderError(f"Неизвестный IMAGE_PROVIDER={name}; варианты: {', '.join(PROVIDERS)}")
    return PROVIDERS[name](prompt, fmt)
