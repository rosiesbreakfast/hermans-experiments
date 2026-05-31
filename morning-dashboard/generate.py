#!/usr/bin/env python3
"""
Generate a Melbourne morning dashboard HTML page.
Combines weather, crypto prices, transport disruptions, and news.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

# Add transport module path
_transport_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _transport_dir not in sys.path:
    sys.path.insert(0, _transport_dir)

try:
    from transport import check_transport
    HAS_TRANSPORT = True
except ImportError:
    HAS_TRANSPORT = False


def fetch(url, timeout=15):
    """Simple HTTP GET with browser-ish UA."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/json,*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except:
        return None


# ─── Weather ───────────────────────────────────────────────────────────────

def get_weather():
    html = fetch("https://wttr.in/Melbourne?format=j1")
    if not html:
        return None
    try:
        d = json.loads(html)
        c = d["current_condition"][0]
        forecast = d.get("weather", [])[:3]
        days = []
        for day in forecast:
            days.append({
                "date": day["date"],
                "high": day["maxtempC"],
                "low": day["mintempC"],
                "desc": day["hourly"][0]["weatherDesc"][0]["value"],
            })
        return {
            "temp": c["temp_C"],
            "desc": c["weatherDesc"][0]["value"],
            "feels": c["FeelsLikeC"],
            "wind": c["windspeedKmph"],
            "humidity": c["humidity"],
            "forecast": days,
        }
    except:
        return None


# ─── Crypto ────────────────────────────────────────────────────────────────

def get_crypto():
    html = fetch(
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum&vs_currencies=aud&include_24hr_change=true"
    )
    if not html:
        return None
    try:
        d = json.loads(html)
        return {
            "btc": {"price": d["bitcoin"]["aud"], "change": d["bitcoin"].get("aud_24h_change", 0)},
            "eth": {"price": d["ethereum"]["aud"], "change": d["ethereum"].get("aud_24h_change", 0)},
        }
    except:
        return None


# ─── Transport (Frankston Line / Cheltenham) ──────────────────────────────

def get_transport():
    """Get Frankston line status from PTV API + Twitter."""
    if HAS_TRANSPORT:
        return check_transport()
    return {
        "status": "unknown",
        "disruptions": [],
        "sources_used": [],
        "note": "Transport module not loaded",
        "timestamp": datetime.now().isoformat(),
        "station": {"name": "Cheltenham", "zone": "2", "line": "Frankston"},
    }


# ─── News ──────────────────────────────────────────────────────────────────

def get_news():
    html = fetch("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10)
    if not html:
        return []
    try:
        ids = json.loads(html)[:8]
        items = []
        for sid in ids:
            item = fetch(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=5)
            if item:
                d = json.loads(item)
                items.append({
                    "title": d.get("title", "?"),
                    "url": d.get("url", ""),
                    "score": d.get("score", 0),
                })
        return items
    except:
        return []


# ─── HTML Generation ──────────────────────────────────────────────────────

def fmt_price(v):
    try:
        return f"${float(v):,.2f}"
    except:
        return f"${v}"


def pct(v):
    try:
        return f"{v:+.2f}%"
    except:
        return f"{v}%"


def transport_html(t):
    """Render transport status to HTML."""
    status = t.get("status", "unknown")
    disruptions = t.get("disruptions", [])
    sources = t.get("sources_used", [])
    note = t.get("note", "")
    station = t.get("station", {})
    sources_str = ", ".join(sources) if sources else "none"

    if status == "normal":
        badge = '<span class="transport-badge" style="background:rgba(100,255,218,0.1);color:var(--green)">✅ Normal</span>'
    elif status == "major_disruption":
        badge = '<span class="transport-badge transport-bad">⚠ Major Disruption</span>'
    elif status == "minor_delays":
        badge = '<span class="transport-badge transport-warn"> Minor Delays</span>'
    elif status == "planned_works":
        badge = '<span class="transport-badge transport-info"> Planned Works</span>'
    else:
        badge = '<span class="transport-badge" style="color:var(--dim)"> Unknown</span>'

    items_html = ""
    if disruptions:
        for d in disruptions[:5]:
            text = d.get("text", d.get("title", ""))
            sev = d.get("severity", "info")
            icon = "⚠️" if sev == "major" else ("" if sev == "minor" else "")
            items_html += f'<div class="transport-issue">{icon} {text[:200]}</div>'

    note_html = f'<div class="transport-note">{note}</div>' if note else ""
    source_html = f'<div class="transport-meta">Sources: {sources_str}</div>' if sources else ""

    station_name = station.get("name", "Cheltenham")
    station_zone = station.get("zone", "2")
    station_line = station.get("line", "Frankston")

    return f"""
      <div style="margin-bottom:8px">
        <span style="font-weight:600">{station_line} Line</span> {badge}
      </div>
      {items_html}
      <div class="transport-detail">{station_name} Station · Zone {station_zone} · {station_line} Line</div>
      {note_html}
      {source_html}
    """


def generate_html():
    weather = get_weather()
    crypto = get_crypto()
    transport = get_transport()
    news = get_news()
    now = datetime.now().strftime("%A, %d %B %Y · %I:%M %p")

    # Weather block
    weather_block = '<div class="weather-detail">Weather data unavailable</div>'
    forecast_block = ""
    if weather:
        weather_block = f"""
          <div class="weather-main">
            <span class="weather-temp">{weather["temp"]}°C</span>
            <span class="weather-desc">{weather["desc"]}</span>
          </div>
          <div class="weather-meta">
            Feels like {weather["feels"]}°C · Wind {weather["wind"]} km/h · Humidity {weather["humidity"]}%
          </div>"""
        for day in weather["forecast"]:
            try:
                date_obj = datetime.strptime(day["date"], "%Y-%m-%d")
                label = date_obj.strftime("%a")
            except:
                label = day["date"]
            forecast_block += f"""
              <div class="forecast-day">
                <div class="forecast-label">{label}</div>
                <div class="forecast-desc">{day["desc"]}</div>
                <div><span class="forecast-high">↑{day["high"]}°</span> <span class="forecast-low">↓{day["low"]}°</span></div>
              </div>"""

    # Crypto block
    crypto_block = '<div class="weather-detail">Crypto data unavailable</div>'
    if crypto:
        crypto_block = f"""
          <div class="crypto-row">
            <span class="crypto-name">₿ Bitcoin</span>
            <div class="crypto-right">
              <div class="crypto-price">{fmt_price(crypto["btc"]["price"])}</div>
              <div class="crypto-change {'green' if crypto['btc']['change'] >= 0 else 'red'}">{pct(crypto['btc']['change'])}</div>
            </div>
          </div>
          <div class="crypto-row">
            <span class="crypto-name">⟠ Ethereum</span>
            <div class="crypto-right">
              <div class="crypto-price">{fmt_price(crypto["eth"]["price"])}</div>
              <div class="crypto-change {'green' if crypto['eth']['change'] >= 0 else 'red'}">{pct(crypto['eth']['change'])}</div>
            </div>
          </div>"""

    # News block
    news_block = '<div class="weather-detail">Could not fetch stories.</div>'
    if news:
        news_block = ""
        for item in news:
            url = item.get("url", "#")
            title = item.get("title", "Untitled")
            score = item.get("score", 0)
            news_block += f"""
              <a href="{url}" class="news-item" target="_blank">
                <span class="news-score">{score}</span>
                <span class="news-title">{title}</span>
              </a>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#1a1a2e">
<title>Melbourne Morning Dashboard</title>
<style>
  :root {{
    --bg: #1a1a2e;
    --card: #16213e;
    --accent: #0f3460;
    --text: #e0e0e0;
    --dim: #8892b0;
    --green: #64ffda;
    --amber: #ffd54f;
    --red: #ff6b6b;
    --orange: #ff9f43;
    --radius: 12px;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 24px;
    max-width: 900px;
    margin: 0 auto;
    line-height: 1.5;
  }}
  h1 {{ font-size: 24px; font-weight: 700; color: #fff; margin-bottom: 4px; }}
  .subtitle {{ color: var(--dim); font-size: 14px; margin-bottom: 32px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
  @media (max-width: 640px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .card {{
    background: var(--card);
    border-radius: var(--radius);
    padding: 20px;
    border: 1px solid rgba(255,255,255,0.06);
  }}
  .card-title {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--dim); margin-bottom: 12px; font-weight: 600; }}
  .full-card {{ grid-column: 1 / -1; }}

  /* Weather */
  .weather-main {{ display: flex; align-items: baseline; gap: 12px; margin-bottom: 6px; }}
  .weather-temp {{ font-size: 40px; font-weight: 300; color: #fff; }}
  .weather-desc {{ font-size: 15px; color: var(--text); }}
  .weather-meta {{ font-size: 13px; color: var(--dim); margin-bottom: 12px; }}
  .forecast {{ display: flex; gap: 10px; }}
  .forecast-day {{ flex:1; text-align:center; padding:8px 4px; background:rgba(255,255,255,0.03); border-radius:8px; }}
  .forecast-label {{ font-size:12px; color:var(--dim); margin-bottom:4px; }}
  .forecast-desc {{ font-size:11px; color:var(--text); margin-bottom:4px; }}
  .forecast-high {{ color:var(--amber); }}
  .forecast-low {{ color:#7ec8e3; }}

  /* Crypto */
  .crypto-row {{ display:flex; justify-content:space-between; align-items:center; padding:10px 0; border-bottom:1px solid rgba(255,255,255,0.05); }}
  .crypto-row:last-child {{ border:none; }}
  .crypto-name {{ font-weight:600; font-size:15px; }}
  .crypto-right {{ text-align:right; }}
  .crypto-price {{ font-size:20px; font-weight:500; color:#fff; }}
  .crypto-change {{ font-size:13px; }}
  .green {{ color:var(--green); }} .red {{ color:var(--red); }} .amber {{ color:var(--amber); }}

  /* Transport */
  .transport-ok {{ color: var(--green); font-size: 14px; }}
  .transport-badge {{ display:inline-block; padding:2px 10px; border-radius:100px; font-size:11px; font-weight:700; letter-spacing:0.3px; }}
  .transport-bad {{ background:rgba(255,107,107,0.15); color:var(--red); }}
  .transport-warn {{ background:rgba(255,213,79,0.15); color:var(--amber); }}
  .transport-info {{ background:rgba(100,255,218,0.1); color:var(--green); }}
  .transport-issue {{ font-size:13px; color:var(--amber); padding:4px 0; }}
  .transport-detail {{ font-size:12px; color:var(--dim); margin-top:8px; }}
  .transport-note {{ font-size:11px; color:var(--slate); margin-top:4px; font-style:italic; }}
  .transport-meta {{ font-size:10px; color:var(--dim); margin-top:6px; opacity:0.6; }}

  /* News */
  .news-item {{ display:flex; align-items:flex-start; gap:10px; padding:10px 0; border-bottom:1px solid rgba(255,255,255,0.05); text-decoration:none; color:var(--text); transition:opacity 0.15s; }}
  .news-item:hover {{ opacity:0.8; }}
  .news-item:last-child {{ border:none; }}
  .news-score {{ flex-shrink:0; font-size:11px; color:var(--dim); min-width:28px; text-align:right; font-weight:600; }}
  .news-title {{ font-size:14px; line-height:1.4; }}

  .footer {{ text-align:center; margin-top:32px; font-size:12px; color:var(--dim); }}
  .inline-warning {{ padding:10px 14px; border-left:3px solid var(--amber); background:rgba(255,213,79,0.06); border-radius:0 8px 8px 0; font-size:13px; color:var(--amber); margin-top:12px; }}
</style>
</head>
<body>
  <h1>🌤 Melbourne Morning</h1>
  <div class="subtitle">{now} · AEDT</div>

  <div class="grid">
    <!-- Weather -->
    <div class="card">
      <div class="card-title">Weather · Melbourne</div>
      {weather_block}
      <div class="forecast">{forecast_block}</div>
    </div>

    <!-- Transport -->
    <div class="card">
      <div class="card-title">🚆 Frankston Line</div>
      {transport_html(transport)}
    </div>

    <!-- Crypto -->
    <div class="card full-card">
      <div class="card-title">₿ Crypto (AUD)</div>
      {crypto_block}
    </div>

    <!-- News -->
    <div class="card full-card">
      <div class="card-title">📰 Top Stories</div>
      {news_block}
    </div>
  </div>

  <div class="inline-warning">
    Generated by Hermes · {datetime.now().strftime("%Y-%m-%d %H:%M")} · Data refreshes on page load
  </div>
</body>
</html>"""


if __name__ == "__main__":
    html = generate_html()
    output_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "dashboard.html"
    )
    with open(output_path, "w") as f:
        f.write(html)
    print(f"Dashboard written to {output_path}")
