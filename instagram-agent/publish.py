"""Upload finished images to public storage and schedule them in Metricool."""
from __future__ import annotations

import os

import requests

METRICOOL_API = "https://app.metricool.com/api"


class PublishError(RuntimeError):
    pass


def _env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise PublishError(f"Не задана переменная окружения {name}")
    return value


def upload_public(image_bytes: bytes, path: str) -> str:
    """Upload to a public Supabase Storage bucket and return its public URL.

    Metricool / Instagram need a publicly reachable image URL.
    """
    base = _env("SUPABASE_URL").rstrip("/")
    bucket = os.getenv("SUPABASE_BUCKET", "instagram")
    resp = requests.post(
        f"{base}/storage/v1/object/{bucket}/{path}",
        headers={
            "Authorization": f"Bearer {_env('SUPABASE_SERVICE_KEY')}",
            "Content-Type": "image/jpeg",
            "x-upsert": "true",
        },
        data=image_bytes,
        timeout=120,
    )
    if resp.status_code not in (200, 201):
        raise PublishError(f"Supabase upload {resp.status_code}: {resp.text[:300]}")
    return f"{base}/storage/v1/object/public/{bucket}/{path}"


def schedule_instagram(image_url: str, fmt: str, caption: str, alt_text: str,
                       date_time: str, timezone: str, first_comment: str = "") -> dict:
    """Schedule an Instagram post or story via the Metricool REST API.

    date_time: "YYYY-MM-DDTHH:MM:SS" local time in `timezone`.
    """
    params = {"userId": _env("METRICOOL_USER_ID"), "blogId": _env("METRICOOL_BLOG_ID")}
    headers = {"X-Mc-Auth": _env("METRICOOL_USER_TOKEN"), "Content-Type": "application/json"}

    is_story = fmt == "story"
    body = {
        "publicationDate": {"dateTime": date_time, "timezone": timezone},
        # Stories have no caption; sending text for a story-only post is rejected.
        "text": "" if is_story else caption,
        "firstCommentText": "" if is_story else first_comment,
        "providers": [{"network": "instagram"}],
        "media": [image_url],
        "mediaAltText": [] if is_story else [alt_text],
        "autoPublish": True,
        "draft": False,
        "shortener": False,
        "descendants": [],
        "smartLinkData": {"ids": []},
        "instagramData": {
            "type": "STORY" if is_story else "POST",
            # Instagram requires labeling AI-generated content; all people here are synthetic.
            "isAiGenerated": True,
        },
    }
    resp = requests.post(f"{METRICOOL_API}/v2/scheduler/posts", params=params,
                         headers=headers, json=body, timeout=60)
    if resp.status_code not in (200, 201):
        raise PublishError(f"Metricool {resp.status_code}: {resp.text[:500]}")
    return resp.json() if resp.content else {}
