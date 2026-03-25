#!/usr/bin/env python3
"""
Social Autopilot Dashboard — status overview for infographic automation.

Automation:
  Infographics (16:00 CET) — image + text → LinkedIn + Twitter + Threads
"""

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, request

try:
    import requests as http_requests
    import tweepy
    SOCIAL_API_AVAILABLE = True
except ImportError:
    SOCIAL_API_AVAILABLE = False

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# --- Social media profile cache (refresh every 30 min) ---
_social_cache = {"data": None, "ts": 0}
_CACHE_TTL = 1800  # 30 minutes


def fetch_social_profiles():
    """Fetch live profile data from Twitter + LinkedIn + Threads APIs."""
    profiles = {}

    # Twitter / X
    tw_api_key = os.environ.get("TWITTER_API_KEY")
    tw_api_secret = os.environ.get("TWITTER_API_SECRET")
    tw_access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
    tw_access_secret = os.environ.get("TWITTER_ACCESS_SECRET")

    if SOCIAL_API_AVAILABLE and tw_api_key and tw_access_token:
        try:
            tw = tweepy.Client(
                consumer_key=tw_api_key, consumer_secret=tw_api_secret,
                access_token=tw_access_token, access_token_secret=tw_access_secret,
            )
            me = tw.get_me(user_fields=["public_metrics", "description", "profile_image_url"])
            if me and me.data:
                pm = me.data.public_metrics or {}
                profiles["twitter"] = {
                    "name": me.data.name,
                    "username": f"@{me.data.username}",
                    "url": f"https://x.com/{me.data.username}",
                    "avatar": (me.data.profile_image_url or "").replace("_normal", "_400x400"),
                    "bio": me.data.description or "",
                    "followers": pm.get("followers_count", 0),
                    "following": pm.get("following_count", 0),
                    "tweets": pm.get("tweet_count", 0),
                    "listed": pm.get("listed_count", 0),
                }
        except Exception as e:
            print(f"Twitter API error: {e}")

    # LinkedIn
    li_token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if SOCIAL_API_AVAILABLE and li_token:
        try:
            r = http_requests.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {li_token}"},
                timeout=10,
            )
            if r.status_code == 200:
                d = r.json()
                profiles["linkedin"] = {
                    "name": d.get("name", ""),
                    "url": "https://www.linkedin.com/in/luk%C3%A1%C5%A1-dlouh%C3%BD-bab026257/",
                    "avatar": d.get("picture", ""),
                    "email": d.get("email", ""),
                }
        except Exception as e:
            print(f"LinkedIn API error: {e}")

    # Threads
    threads_token = os.environ.get("THREADS_ACCESS_TOKEN")
    threads_user_id = os.environ.get("THREADS_USER_ID")
    if SOCIAL_API_AVAILABLE and threads_token and threads_user_id:
        try:
            r = http_requests.get(
                f"https://graph.threads.net/v1.0/{threads_user_id}",
                params={
                    "fields": "id,username,name,threads_profile_picture_url,threads_biography",
                    "access_token": threads_token,
                },
                timeout=10,
            )
            if r.status_code == 200:
                d = r.json()
                threads_data = {
                    "name": d.get("name", ""),
                    "username": f"@{d.get('username', '')}",
                    "url": f"https://www.threads.com/@{d.get('username', '')}",
                    "avatar": d.get("threads_profile_picture_url", ""),
                    "bio": d.get("threads_biography", ""),
                    "user_id": d.get("id", ""),
                }
                # Fetch insights (followers, likes, etc.)
                try:
                    r2 = http_requests.get(
                        f"https://graph.threads.net/v1.0/{threads_user_id}/threads_insights",
                        params={
                            "metric": "followers_count,likes,replies,reposts,quotes",
                            "access_token": threads_token,
                        },
                        timeout=10,
                    )
                    if r2.status_code == 200:
                        for m in r2.json().get("data", []):
                            val = m.get("total_value", {}).get("value", 0)
                            threads_data[m["name"]] = val if val is not None else 0
                except Exception:
                    pass
                profiles["threads"] = threads_data
        except Exception as e:
            print(f"Threads API error: {e}")

    return profiles


def get_social_profiles():
    """Get cached social profiles (refreshes every 30 min)."""
    now = time.time()
    if _social_cache["data"] is None or (now - _social_cache["ts"]) > _CACHE_TTL:
        try:
            _social_cache["data"] = fetch_social_profiles()
            _social_cache["ts"] = now
        except Exception:
            if _social_cache["data"] is None:
                _social_cache["data"] = {}
    return _social_cache["data"]


# --- Schedule config ---
INFOGRAPHIC_START = date(2026, 3, 15)


def load_json(filepath):
    try:
        with open(filepath) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def get_infographic_posts():
    data = load_json(DATA_DIR / "infographic_posts.json")
    return data["posts"] if data else []


def get_post_log():
    return load_json(DATA_DIR / "post_log.json") or []


def save_post_log(log):
    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "post_log.json", "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def get_series_status(posts, start_date, today):
    """Status calculator for infographic series."""
    total = len(posts)
    if not posts:
        return {"total": 0, "published": 0, "remaining": 0, "schedule": []}

    days_elapsed = (today - start_date).days + 1
    published = min(max(days_elapsed, 0), total)
    remaining = total - published

    schedule = []
    for i, post in enumerate(posts):
        post_date = start_date + timedelta(days=i)
        text = post.get("text", "")
        schedule.append({
            "index": i,
            "date": post_date.isoformat(),
            "image": post.get("image", None),
            "text": text[:100] + "..." if len(text) > 100 else text,
            "status": "published" if post_date <= today else "scheduled",
        })

    return {
        "total": total,
        "published": published,
        "remaining": remaining,
        "start_date": start_date.isoformat(),
        "end_date": (start_date + timedelta(days=total - 1)).isoformat() if total > 0 else start_date.isoformat(),
        "schedule": schedule,
    }


def build_calendar(today, infographic_schedule, months_ahead=3):
    """Build calendar data for template."""
    cal_start = today.replace(day=1)
    cal_end = today.replace(day=1) + timedelta(days=months_ahead * 31)

    infographic_by_date = {s["date"]: s for s in infographic_schedule}

    months = []
    current = cal_start
    while current < cal_end:
        month_data = {
            "name": current.strftime("%B %Y"),
            "year": current.year,
            "month": current.month,
            "weeks": [],
        }

        first_day = current.replace(day=1)
        weekday = first_day.weekday()
        week = [None] * weekday
        day = first_day

        while day.month == current.month:
            d = day.isoformat()
            has_infographic = d in infographic_by_date

            week.append({
                "day": day.day,
                "date": d,
                "is_today": day == today,
                "has_infographic": has_infographic,
                "infographic_status": infographic_by_date[d]["status"] if has_infographic else None,
            })

            if len(week) == 7:
                month_data["weeks"].append(week)
                week = []
            day += timedelta(days=1)

        if week:
            while len(week) < 7:
                week.append(None)
            month_data["weeks"].append(week)

        months.append(month_data)

        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return months


@app.route("/")
def dashboard():
    today = date.today()

    infographic = get_series_status(get_infographic_posts(), INFOGRAPHIC_START, today)
    log = get_post_log()

    calendar = build_calendar(
        today,
        infographic.get("schedule", []),
        months_ahead=3,
    )

    errors = [e for e in log if e.get("status") == "error"][-5:]
    social = get_social_profiles()

    return render_template(
        "dashboard.html",
        today=today.isoformat(),
        paused=True,
        infographic=infographic,
        calendar=calendar,
        log=log[-30:],
        errors=errors,
        total_linkedin=infographic["published"],
        total_twitter=infographic["published"],
        total_scheduled=infographic["remaining"],
        total_all=infographic["total"],
        social=social,
    )


@app.route("/api/status")
def api_status():
    today = date.today()
    infographic = get_series_status(get_infographic_posts(), INFOGRAPHIC_START, today)
    return jsonify({
        "date": today.isoformat(),
        "infographic": {
            "total": infographic["total"],
            "published": infographic["published"],
            "remaining": infographic["remaining"],
            "start_date": infographic.get("start_date"),
            "end_date": infographic.get("end_date"),
        },
        "total_published": infographic["published"],
        "total_scheduled": infographic["total"],
    })


@app.route("/api/social")
def api_social():
    return jsonify(get_social_profiles())


@app.route("/api/log", methods=["POST"])
def api_log():
    entry = request.get_json(silent=True)
    if entry:
        log = get_post_log()
        log.append(entry)
        save_post_log(log)
        return jsonify({"ok": True})
    return jsonify({"error": "no data"}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
