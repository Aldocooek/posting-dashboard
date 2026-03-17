#!/usr/bin/env python3
"""
Social Autopilot Dashboard — status overview for all 3 automations.

Automations:
  1. Daily Posts (09:00 CET) — image + text → LinkedIn + Twitter
  2. Infographics (16:00 CET) — image + text → LinkedIn + Twitter
  3. Evening Posts (20:00 CET) — text only → LinkedIn + Twitter
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# --- Schedule configs ---
DAILY_START = date(2026, 3, 15)
INFOGRAPHIC_START = date(2026, 3, 15)
EVENING_START = date(2026, 3, 17)  # Day 3 series started today


def load_json(filepath):
    try:
        with open(filepath) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def get_daily_posts():
    data = load_json(DATA_DIR / "daily_posts.json")
    return data["posts"] if data else []


def get_infographic_posts():
    data = load_json(DATA_DIR / "infographic_posts.json")
    return data["posts"] if data else []


def get_evening_posts():
    data = load_json(DATA_DIR / "evening_posts.json")
    if data:
        return data["posts"] if "posts" in data else data
    return []


def get_post_log():
    return load_json(DATA_DIR / "post_log.json") or []


def save_post_log(log):
    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "post_log.json", "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def get_series_status(posts, start_date, today, platform_name):
    """Generic status calculator for any post series."""
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
            "platform": platform_name,
        })

    return {
        "total": total,
        "published": published,
        "remaining": remaining,
        "start_date": start_date.isoformat(),
        "end_date": (start_date + timedelta(days=total - 1)).isoformat() if total > 0 else start_date.isoformat(),
        "schedule": schedule,
    }


def build_calendar(today, daily_schedule, infographic_schedule, evening_schedule, months_ahead=3):
    """Build calendar data for template — now includes evening posts."""
    cal_start = today.replace(day=1)
    cal_end = today.replace(day=1) + timedelta(days=months_ahead * 31)

    daily_by_date = {s["date"]: s for s in daily_schedule}
    infographic_by_date = {s["date"]: s for s in infographic_schedule}
    evening_by_date = {s["date"]: s for s in evening_schedule}

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
            has_daily = d in daily_by_date
            has_infographic = d in infographic_by_date
            has_evening = d in evening_by_date

            week.append({
                "day": day.day,
                "date": d,
                "is_today": day == today,
                "has_daily": has_daily,
                "has_infographic": has_infographic,
                "has_evening": has_evening,
                "daily_status": daily_by_date[d]["status"] if has_daily else None,
                "infographic_status": infographic_by_date[d]["status"] if has_infographic else None,
                "evening_status": evening_by_date[d]["status"] if has_evening else None,
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

    daily = get_series_status(get_daily_posts(), DAILY_START, today, "daily")
    infographic = get_series_status(get_infographic_posts(), INFOGRAPHIC_START, today, "infographic")
    evening = get_series_status(get_evening_posts(), EVENING_START, today, "evening")
    log = get_post_log()

    calendar = build_calendar(
        today,
        daily.get("schedule", []),
        infographic.get("schedule", []),
        evening.get("schedule", []),
        months_ahead=3,
    )

    errors = [e for e in log if e.get("status") == "error"][-5:]

    total_pub = daily["published"] + infographic["published"] + evening["published"]
    total_sched = daily["remaining"] + infographic["remaining"] + evening["remaining"]
    total_all = daily["total"] + infographic["total"] + evening["total"]

    return render_template(
        "dashboard.html",
        today=today.isoformat(),
        daily=daily,
        infographic=infographic,
        evening=evening,
        calendar=calendar,
        log=log[-30:],
        errors=errors,
        total_linkedin=total_pub,
        total_twitter=total_pub,
        total_scheduled=total_sched,
        total_all=total_all,
    )


@app.route("/api/status")
def api_status():
    today = date.today()
    daily = get_series_status(get_daily_posts(), DAILY_START, today, "daily")
    infographic = get_series_status(get_infographic_posts(), INFOGRAPHIC_START, today, "infographic")
    evening = get_series_status(get_evening_posts(), EVENING_START, today, "evening")
    return jsonify({
        "date": today.isoformat(),
        "daily": {k: v for k, v in daily.items() if k != "schedule"},
        "infographic": {k: v for k, v in infographic.items() if k != "schedule"},
        "evening": {k: v for k, v in evening.items() if k != "schedule"},
        "total_published": daily["published"] + infographic["published"] + evening["published"],
        "total_scheduled": daily["remaining"] + infographic["remaining"] + evening["remaining"],
    })


@app.route("/api/log", methods=["POST"])
def api_log():
    """Endpoint for automations to report post status."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    log = get_post_log()
    log.append(data)
    save_post_log(log)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
