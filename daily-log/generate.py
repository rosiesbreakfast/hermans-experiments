#!/usr/bin/env python3
"""
Hermes Daily Log — generates a daily Obsidian note.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def sh(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return ""


def obsidian_path():
    return os.path.join(os.path.expanduser("~/Hermans-Obsidian-Vault"), "daily")


def get_weather():
    r = sh('curl -s "https://wttr.in/Melbourne?format=j1"')
    if not r:
        return None
    try:
        d = json.loads(r)
        c = d["current_condition"][0]
        forecast = d.get("weather", [])[:3]
        days = []
        for day in forecast:
            days.append(
                f"{day['date']}: ↑{day['maxtempC']}° ↓{day['mintempC']}° "
                f"{day['hourly'][0]['weatherDesc'][0]['value']}"
            )
        return {
            "temp": c["temp_C"],
            "desc": c["weatherDesc"][0]["value"],
            "feels": c["FeelsLikeC"],
            "wind": c["windspeedKmph"],
            "humidity": c["humidity"],
            "forecast": days,
        }
    except Exception:
        return None


def get_crypto():
    r = sh(
        'curl -s "https://api.coingecko.com/api/v3/simple/price'
        '?ids=bitcoin,ethereum&vs_currencies=aud&include_24hr_change=true"'
    )
    if not r:
        return None
    try:
        d = json.loads(r)
        return {
            "btc": d["bitcoin"]["aud"],
            "btc_change": d["bitcoin"].get("aud_24h_change", 0),
            "eth": d["ethereum"]["aud"],
            "eth_change": d["ethereum"].get("aud_24h_change", 0),
        }
    except Exception:
        return None


def get_sessions():
    db = os.path.expanduser("~/.hermes/sessions.db")
    if not os.path.exists(db):
        return None
    r = sh(
        f'python3 -c "import sqlite3; '
        f'db = sqlite3.connect(\'{db}\'); '
        f'cutoff = __import__(\'time\').time() - 86400; '
        f'row = db.execute(\'SELECT COUNT(*) FROM sessions WHERE created_at >= ?\', (cutoff,)).fetchone(); '
        f'print(row[0])"'
    )
    return r if r else None


def get_cron_jobs():
    cf = os.path.expanduser("~/.hermes/cron/jobs.json")
    if not os.path.exists(cf):
        return []
    try:
        with open(cf) as f:
            jobs = json.load(f)
        if isinstance(jobs, dict):
            jobs = list(jobs.values())
        active = [
            j for j in jobs
            if j.get("enabled", False) or j.get("disabled") is not True
        ]
        result = []
        for j in active[:10]:
            name = j.get("name") or j.get("id") or "?"
            sched = j.get("schedule") or "?"
            result.append(f"- {name}: {sched}")
        return result
    except Exception:
        return []


def get_news():
    r = sh(
        'curl -s "https://hacker-news.firebaseio.com/v0/topstories.json" | '
        "python3 -c \"import json,urllib.request; "
        "ids=json.loads(__import__('sys').stdin.read())[:5]; "
        "items=[json.loads(urllib.request.urlopen(f'https://hacker-news.firebaseio.com/v0/item/{i}.json', "
        "timeout=5).read()).get('title','') for i in ids]; "
        'print(json.dumps(items))"'
    )
    if not r:
        return []
    try:
        return json.loads(r)
    except Exception:
        return []


def fmt_price(v):
    try:
        return f"${float(v):,.2f}"
    except:
        return f"${v}"


def fmt_change(v):
    try:
        v = float(v)
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.2f}%"
    except:
        return f"{v}%"


def generate():
    today = datetime.now().strftime("%Y-%m-%d")
    weekday = datetime.now().strftime("%A")
    out_dir = obsidian_path()
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{today}.md")

    weather = get_weather()
    crypto = get_crypto()
    news = get_news()
    sessions = get_sessions()
    cron = get_cron_jobs()

    lines = [
        "---",
        f'created: "{today}"',
        "tags:",
        "  - hermes-daily",
        f"date: \"{today}\"",
        "---",
        "",
        f"# {today}",
        "",
        f"_{weekday}_",
        "",
        "## 🌤 Weather",
    ]

    if weather:
        lines.append(f"- **Current:** {weather['temp']}°C, {weather['desc']} "
                      f"(feels like {weather['feels']}°C)")
        lines.append(f"- **Wind:** {weather['wind']} km/h · "
                      f"**Humidity:** {weather['humidity']}%")
        lines.append("- **Forecast:**")
        for day in weather["forecast"]:
            lines.append(f"  - {day}")
    else:
        lines.append("- Weather data unavailable")
    lines.append("")

    lines.append("## ₿ Crypto")
    if crypto:
        lines.append(f"- **Bitcoin:** {fmt_price(crypto['btc'])} AUD "
                      f"({fmt_change(crypto['btc_change'])})")
        lines.append(f"- **Ethereum:** {fmt_price(crypto['eth'])} AUD "
                      f"({fmt_change(crypto['eth_change'])})")
    else:
        lines.append("- Crypto data unavailable")
    lines.append("")

    lines.append("## 🤖 Hermes Status")
    if sessions:
        lines.append(f"- **Sessions (24h):** {sessions}")
    lines.append("- **Active cron jobs:**")
    if cron:
        for job in cron:
            lines.append(f"  {job}")
    else:
        lines.append("  None found")
    lines.append("")

    lines.append("## 📰 Top Stories")
    if news:
        for i, title in enumerate(news, 1):
            lines.append(f"{i}. {title}")
    else:
        lines.append("Could not fetch stories.")
    lines.append("")

    lines.append("---")
    lines.append(f"_Generated by Hermes at {datetime.now().strftime('%H:%M')}_")

    content = "\n".join(lines) + "\n"
    with open(out_path, "w") as f:
        f.write(content)

    print(f"Daily note written: {out_path}")
    if weather:
        print(f"  Weather: {weather['temp']}°C {weather['desc']}")
    if crypto:
        print(f"  BTC: {fmt_price(crypto['btc'])} AUD")


if __name__ == "__main__":
    generate()
