#!/usr/bin/env python3
"""
Generate a Melbourne morning dashboard HTML page.
Combines weather, crypto prices, events, and news.
"""

import json
import os
import subprocess
import sys
from datetime import datetime


def sh(cmd, timeout=30):
    """Run a shell command and return stdout."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def get_weather():
    """Fetch Melbourne weather via geo-weather-fetch skill."""
    # Try calling the cron skill directly
    result = sh(
        'curl -s "https://wttr.in/Melbourne?format=j1" 2>/dev/null || '
        'python3 -c "import json, urllib.request; '
        "d=json.loads(urllib.request.urlopen('https://wttr.in/Melbourne?format=j1', timeout=10).read()); "
        'c=d[\"current_condition\"][0]; '
        'print(json.dumps(c))" 2>/dev/null'
    )
    try:
        data = json.loads(result)
        return {
            "temp": data.get("temp_C", "?"),
            "feels": data.get("FeelsLikeC", "?"),
            "desc": data.get("weatherDesc", [{}])[0].get("value", "?"),
            "humidity": data.get("humidity", "?"),
            "wind": data.get("windspeedKmph", "?"),
            "icon": data.get("weatherIconUrl", [{}])[0].get("value", ""),
        }
    except:
        return {"temp": "?", "feels": "?", "desc": "?", "humidity": "?", "wind": "?"}


def get_forecast():
    """Get 3-day forecast."""
    result = sh(
        'curl -s "https://wttr.in/Melbourne?format=j1" 2>/dev/null | '
        'python3 -c "import json,sys; '
        "d=json.load(sys.stdin); "
        "days=d.get('weather',[])[:3]; "
        'for day in days: '
        'print(f\'{day[\"date\"]}|{day[\"maxtempC\"]}|{day[\"mintempC\"]}|{day[\"hourly\"][0][\"weatherDesc\"][0][\"value\"]}\')" '
        '2>/dev/null'
    )
    forecast = []
    for line in result.split("\n")[:3]:
        parts = line.split("|")
        if len(parts) >= 4:
            forecast.append({
                "date": parts[0],
                "high": parts[1],
                "low": parts[2],
                "desc": parts[3],
            })
    return forecast


def get_crypto():
    """Fetch BTC and ETH prices in AUD."""
    result = sh(
        'curl -s "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=aud&include_24hr_change=true" 2>/dev/null'
    )
    try:
        data = json.loads(result)
        return {
            "btc": {
                "price": data.get("bitcoin", {}).get("aud", "?"),
                "change": data.get("bitcoin", {}).get("aud_24h_change", 0),
            },
            "eth": {
                "price": data.get("ethereum", {}).get("aud", "?"),
                "change": data.get("ethereum", {}).get("aud_24h_change", 0),
            },
        }
    except:
        return {"btc": {"price": "?", "change": 0}, "eth": {"price": "?", "change": 0}}


def get_news():
    """Get top AI/news headlines from Hacker News."""
    result = sh(
        'curl -s "https://hacker-news.firebaseio.com/v0/topstories.json" 2>/dev/null | '
        'python3 -c "import json,sys,urllib.request; '
        "ids=json.loads(sys.stdin.read())[:10]; "
        "items=[]; "
        "for i in ids: "
        "d=json.loads(urllib.request.urlopen(f'https://hacker-news.firebaseio.com/v0/item/{i}.json', timeout=5).read()); "
        "items.append({'title':d.get('title',''), 'url':d.get('url',''), 'score':d.get('score',0)}); "
        'print(json.dumps(items))" 2>/dev/null'
    )
    try:
        return json.loads(result)
    except:
        return []


def format_price(val):
    """Format a price value."""
    try:
        return f"${float(val):,.2f}"
    except:
        return str(val)


def format_change(val):
    """Format 24h change."""
    try:
        v = float(val)
        icon = "📈" if v >= 0 else "📉"
        return f"{icon} {v:+.2f}%"
    except:
        return str(val)


def generate_html():
    weather = get_weather()
    forecast = get_forecast()
    crypto = get_crypto()
    news = get_news()
    now = datetime.now().strftime("%A, %d %B %Y · %I:%M %p")

    weather_icon = weather.get("icon", "")
    icon_html = f'<img src="{weather_icon}" alt="{weather["desc"]}" style="width:64px;height:64px">' if weather_icon else ""

    news_items = ""
    for i, item in enumerate(news[:8]):
        url = item.get("url", "#")
        title = item.get("title", "Untitled")
        score = item.get("score", 0)
        news_items += f"""
          <a href="{url}" class="news-item" target="_blank">
            <span class="news-score">{score}</span>
            <span class="news-title">{title}</span>
          </a>"""

    forecast_html = ""
    for day in forecast:
        try:
            from datetime import datetime as dt
            date_obj = dt.strptime(day["date"], "%Y-%m-%d")
            label = date_obj.strftime("%a")
        except:
            label = day["date"]
        forecast_html += f"""
          <div class="forecast-day">
            <div class="forecast-label">{label}</div>
            <div class="forecast-desc">{day["desc"]}</div>
            <div class="forecast-temps">
              <span class="forecast-high">↑{day["high"]}°</span>
              <span class="forecast-low">↓{day["low"]}°</span>
            </div>
          </div>"""

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
  .weather-row {{ display: flex; align-items: center; gap: 16px; }}
  .weather-temp {{ font-size: 40px; font-weight: 300; color: #fff; }}
  .weather-detail {{ font-size: 13px; color: var(--dim); }}
  .weather-detail span {{ color: var(--text); }}
  .forecast {{ display: flex; gap: 12px; margin-top: 16px; }}
  .forecast-day {{ flex: 1; text-align: center; padding: 8px; background: rgba(255,255,255,0.03); border-radius: 8px; }}
  .forecast-label {{ font-size: 12px; color: var(--dim); margin-bottom: 4px; }}
  .forecast-desc {{ font-size: 12px; color: var(--text); margin-bottom: 6px; }}
  .forecast-temps {{ font-size: 13px; }}
  .forecast-high {{ color: var(--amber); }}
  .forecast-low {{ color: #7ec8e3; margin-left: 6px; }}
  .crypto-row {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }}
  .crypto-row:last-child {{ border: none; }}
  .crypto-name {{ font-weight: 600; font-size: 15px; }}
  .crypto-price {{ font-size: 20px; font-weight: 500; color: #fff; }}
  .crypto-change {{ font-size: 13px; }}
  .green {{ color: var(--green); }}
  .red {{ color: var(--red); }}
  .amber {{ color: var(--amber); }}
  .news-item {{
    display: flex; align-items: flex-start; gap: 10px;
    padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05);
    text-decoration: none; color: var(--text); transition: opacity 0.15s;
  }}
  .news-item:hover {{ opacity: 0.8; }}
  .news-item:last-child {{ border: none; }}
  .news-score {{ flex-shrink: 0; font-size: 11px; color: var(--dim); min-width: 28px; text-align: right; font-weight: 600; }}
  .news-title {{ font-size: 14px; line-height: 1.4; }}
  .footer {{ text-align: center; margin-top: 32px; font-size: 12px; color: var(--dim); }}
  .full-card {{ grid-column: 1 / -1; }}
  .inline-warning {{
    padding: 10px 14px;
    border-left: 3px solid var(--amber);
    background: rgba(255, 213, 79, 0.06);
    border-radius: 0 8px 8px 0;
    font-size: 13px;
    color: var(--amber);
    margin-top: 12px;
  }}
</style>
</head>
<body>
  <h1>🌤 Melbourne Morning</h1>
  <div class="subtitle">{now} · AEDT</div>

  <div class="grid">
    <!-- Weather -->
    <div class="card">
      <div class="card-title">Weather · Melbourne</div>
      <div class="weather-row">
        {icon_html}
        <div>
          <div class="weather-temp">{weather["temp"]}°C</div>
          <div class="weather-detail">{weather["desc"]} · Feels like {weather["feels"]}°C</div>
          <div class="weather-detail" style="margin-top:4px">💨 Wind: <span>{weather["wind"]} km/h</span> · 💧 Humidity: <span>{weather["humidity"]}%</span></div>
        </div>
      </div>
      <div class="forecast">
        {forecast_html}
      </div>
    </div>

    <!-- Crypto -->
    <div class="card">
      <div class="card-title">Crypto (AUD)</div>
      <div class="crypto-row">
        <span class="crypto-name">₿ Bitcoin</span>
        <div style="text-align:right">
          <div class="crypto-price">{format_price(crypto["btc"]["price"])}</div>
          <div class="crypto-change {'green' if crypto['btc']['change'] >= 0 else 'red'}">{format_change(crypto["btc"]["change"])}</div>
        </div>
      </div>
      <div class="crypto-row">
        <span class="crypto-name">⟠ Ethereum</span>
        <div style="text-align:right">
          <div class="crypto-price">{format_price(crypto["eth"]["price"])}</div>
          <div class="crypto-change {'green' if crypto['eth']['change'] >= 0 else 'red'}">{format_change(crypto["eth"]["change"])}</div>
        </div>
      </div>
    </div>

    <!-- News -->
    <div class="card full-card">
      <div class="card-title">Top Stories · Hacker News</div>
      {news_items if news_items else '<div class="weather-detail" style="padding:8px 0">Could not fetch stories.</div>'}
    </div>
  </div>

  <div class="inline-warning">
    Generated by Hermes · {datetime.now().strftime("%Y-%m-%d %H:%M")} · Data refreshes on page load
  </div>
</body>
</html>"""


if __name__ == "__main__":
    html = generate_html()
    output_path = sys.argv[1] if len(sys.argv) > 1 else "dashboard.html"
    with open(output_path, "w") as f:
        f.write(html)
    print(f"Dashboard written to {output_path}")
