#!/usr/bin/env python3
"""
Posting Dashboard — status overview for LinkedIn + Twitter automations.
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

# Daily posts (9:00 CET) — state-based, started 2026-03-15
DAILY_START = date(2026, 3, 15)
DAILY_FIRST_INDEX = 0  # first post index

# Infographic posts (16:00 CET) — date-based, started 2026-03-15
INFOGRAPHIC_START = date(2026, 3, 15)


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


def get_post_log():
    return load_json(DATA_DIR / "post_log.json") or []


def save_post_log(log):
    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "post_log.json", "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def get_daily_status(today):
    """Calculate daily post schedule status."""
    posts = get_daily_posts()
    total = len(posts)
    if not posts:
        return {"total": 0, "published": 0, "remaining": 0, "schedule": []}

    days_elapsed = (today - DAILY_START).days + 1
    published = min(max(days_elapsed, 0), total)
    remaining = total - published

    schedule = []
    for i, post in enumerate(posts):
        post_date = DAILY_START + timedelta(days=i)
        schedule.append({
            "index": i,
            "date": post_date.isoformat(),
            "image": post["image"],
            "text": post["text"][:100] + "..." if len(post["text"]) > 100 else post["text"],
            "status": "published" if post_date <= today else "scheduled",
            "platform": "daily",
        })

    return {
        "total": total,
        "published": published,
        "remaining": remaining,
        "start_date": DAILY_START.isoformat(),
        "end_date": (DAILY_START + timedelta(days=total - 1)).isoformat(),
        "schedule": schedule,
    }


def get_infographic_status(today):
    """Calculate infographic post schedule status."""
    posts = get_infographic_posts()
    total = len(posts)
    if not posts:
        return {"total": 0, "published": 0, "remaining": 0, "schedule": []}

    days_elapsed = (today - INFOGRAPHIC_START).days + 1
    published = min(max(days_elapsed, 0), total)
    remaining = total - published

    schedule = []
    for i, post in enumerate(posts):
        post_date = INFOGRAPHIC_START + timedelta(days=i)
        schedule.append({
            "index": i,
            "date": post_date.isoformat(),
            "image": post["image"],
            "text": post["text"][:100] + "..." if len(post["text"]) > 100 else post["text"],
            "status": "published" if post_date <= today else "scheduled",
            "platform": "infographic",
        })

    return {
        "total": total,
        "published": published,
        "remaining": remaining,
        "start_date": INFOGRAPHIC_START.isoformat(),
        "end_date": (INFOGRAPHIC_START + timedelta(days=total - 1)).isoformat(),
        "schedule": schedule,
    }


def build_calendar(today, daily_schedule, infographic_schedule, months_ahead=3):
    """Build calendar data for template."""
    # Start from beginning of current month
    cal_start = today.replace(day=1)
    cal_end = today.replace(day=1) + timedelta(days=months_ahead * 31)

    # Index schedules by date
    daily_by_date = {s["date"]: s for s in daily_schedule}
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

        # Find first day of month and pad to Monday
        first_day = current.replace(day=1)
        weekday = first_day.weekday()  # Monday = 0

        week = [None] * weekday
        day = first_day

        while day.month == current.month:
            d = day.isoformat()
            has_daily = d in daily_by_date
            has_infographic = d in infographic_by_date

            daily_status = daily_by_date[d]["status"] if has_daily else None
            infographic_status = infographic_by_date[d]["status"] if has_infographic else None

            week.append({
                "day": day.day,
                "date": d,
                "is_today": day == today,
                "has_daily": has_daily,
                "has_infographic": has_infographic,
                "daily_status": daily_status,
                "infographic_status": infographic_status,
            })

            if len(week) == 7:
                month_data["weeks"].append(week)
                week = []

            day += timedelta(days=1)

        # Pad last week
        if week:
            while len(week) < 7:
                week.append(None)
            month_data["weeks"].append(week)

        months.append(month_data)

        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return months


@app.route("/")
def dashboard():
    today = date.today()

    daily = get_daily_status(today)
    infographic = get_infographic_status(today)
    log = get_post_log()

    calendar = build_calendar(
        today,
        daily.get("schedule", []),
        infographic.get("schedule", []),
        months_ahead=3,
    )

    # Recent errors from log
    errors = [e for e in log if e.get("status") == "error"][-5:]

    return render_template(
        "dashboard.html",
        today=today.isoformat(),
        daily=daily,
        infographic=infographic,
        calendar=calendar,
        log=log[-20:],
        errors=errors,
        total_linkedin=daily["published"] + infographic["published"],
        total_twitter=daily["published"] + infographic["published"],
        total_scheduled=daily["remaining"] + infographic["remaining"],
    )


@app.route("/api/status")
def api_status():
    today = date.today()
    daily = get_daily_status(today)
    infographic = get_infographic_status(today)
    return jsonify({
        "date": today.isoformat(),
        "daily": {k: v for k, v in daily.items() if k != "schedule"},
        "infographic": {k: v for k, v in infographic.items() if k != "schedule"},
        "total_published": daily["published"] + infographic["published"],
        "total_scheduled": daily["remaining"] + infographic["remaining"],
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
