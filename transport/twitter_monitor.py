#!/usr/bin/env python3
"""
Standalone Metro Trains Twitter monitor.

Checks @metrotrains for recent disruption tweets, especially
for the Frankston line, and outputs a clean summary.

Can be run standalone or used as a cron job data source.

Requires xurl CLI to be authenticated (see transport/README.md).

Usage:
    python3 twitter_monitor.py              # Print summary
    python3 twitter_monitor.py --json       # JSON output
    python3 twitter_monitor.py --watch      # Continual mode (poll every 5 min)
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime

METRO_HANDLE = "metrotrains"
LINE_KEYWORDS = ["frankston", "cheltenham"]
DISRUPTION_KEYWORDS = [
    "delay", "delayed", "delays",
    "suspend", "suspended", "suspension",
    "cancel", "cancelled", "cancellation",
    "bus", "replacement", "coach",
    "planned", "works", "maintenance",
    "disrupt", "disruption", "disruptions",
    "resume", "resumed",
    "altered", "change", "changed",
    "emergency", "incident",
    "closure", "closed",
    "good service", "normal", "cleared",
]


def fetch_tweets(handle, count=10):
    """Fetch recent tweets from a handle using xurl."""
    try:
        result = subprocess.run(
            ["xurl", "search", f"from:{handle}", "-n", str(count)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        return None


def parse_tweets(data):
    """Parse xurl response into tweet text list."""
    if not data:
        return []
    tweets = []
    if "data" in data:
        for t in data["data"]:
            tweets.append({
                "id": t.get("id", ""),
                "text": t.get("text", ""),
                "time": "",  # xurl might not return created_at in search results
            })
    elif "statuses" in data:
        for t in data["statuses"]:
            tweets.append({
                "id": t.get("id_str", ""),
                "text": t.get("full_text", t.get("text", "")),
                "time": t.get("created_at", ""),
            })
    return tweets


def classify_tweet(text):
    """Classify a tweet's relevance to Frankston line disruptions.

    Returns: (is_relevant, severity, category)
    """
    lower = text.lower()

    # Check if Frankston/Cheltenham specific
    is_line_specific = any(kw in lower for kw in LINE_KEYWORDS)

    # Count disruption keywords found
    found = []
    for kw in DISRUPTION_KEYWORDS:
        if kw in lower:
            found.append(kw)

    if not found:
        return (False, None, "none")

    # Determine severity
    severity = "info"
    if any(w in lower for w in ["suspend", "emergency", "incident", "closure", "cancelled"]):
        severity = "major"
    elif any(w in lower for w in ["delay", "delayed", "delays", "altered"]):
        severity = "minor"

    # Determine relevance
    is_relevant = is_line_specific or severity != "info"

    return (is_relevant, severity, found)


def generate_report(tweets):
    """Generate a clean report from tweet data."""
    now = datetime.now()
    report = {
        "timestamp": now.isoformat(),
        "handle": METRO_HANDLE,
        "tweets_checked": len(tweets),
        "frankston_tweets": [],
        "all_disruptions": [],
        "summary": {
            "frankston_line": "normal",
            "has_frankston_issues": False,
            "has_general_disruptions": False,
        },
    }

    for t in tweets:
        is_relevant, severity, keywords = classify_tweet(t["text"])

        if not is_relevant:
            continue

        entry = {
            "id": t["id"],
            "text": t["text"][:300],
            "severity": severity,
            "keywords": keywords,
        }

        is_line = any(kw in t["text"].lower() for kw in LINE_KEYWORDS)
        if is_line:
            report["frankston_tweets"].append(entry)
        else:
            report["all_disruptions"].append(entry)

    # Determine summary status
    severities = [t["severity"] for t in report["frankston_tweets"]]
    if "major" in severities:
        report["summary"]["frankston_line"] = "major_disruption"
        report["summary"]["has_frankston_issues"] = True
    elif "minor" in severities:
        report["summary"]["frankston_line"] = "minor_delays"
        report["summary"]["has_frankston_issues"] = True
    elif report["frankston_tweets"]:
        report["summary"]["frankston_line"] = "planned_works"
        report["summary"]["has_frankston_issues"] = True

    if report["all_disruptions"]:
        report["summary"]["has_general_disruptions"] = True

    return report


def print_report(report):
    """Print a human-readable summary."""
    status = report["summary"]["frankston_line"]
    status_icons = {
        "normal": "✅",
        "minor_delays": "",
        "major_disruption": "⚠️",
        "planned_works": "",
    }
    icon = status_icons.get(status, "❓")

    print(f"�� Metro Trains (@{METRO_HANDLE})")
    print(f"   Last checked: {report['timestamp'][:19]}")
    print(f"   Tweets scanned: {report['tweets_checked']}")
    print()

    # Frankston line status
    if status == "normal":
        print(f"   {icon} Frankston Line — No issues detected")
    else:
        label = status.replace("_", " ").title()
        print(f"   {icon} Frankston Line — {label}")
        print()

    if report["frankston_tweets"]:
        print(f"   Relevant tweets ({len(report['frankston_tweets'])}):")
        for t in report["frankston_tweets"][:5]:
            sev_icon = "⚠️" if t["severity"] == "major" else ""
            print(f"   {sev_icon} {t['text'][:120]}...")
        print()

    if report["all_disruptions"]:
        print(f"   Other line disruptions ({len(report['all_disruptions'])}):")
        for t in report["all_disruptions"][:3]:
            print(f"     · {t['text'][:100]}...")
        print()

    if status == "normal" and not report["all_disruptions"]:
        print("   No active disruptions found.")
        print()


def watch_mode(interval=300):
    """Run in watch mode, polling every N seconds."""
    print(f"Watching @{METRO_HANDLE} every {interval}s...")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            data = fetch_tweets(METRO_HANDLE)
            tweets = parse_tweets(data)
            report = generate_report(tweets)
            print_report(report)
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}")
            time.sleep(interval)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        interval = 300
        for i, arg in enumerate(sys.argv):
            if arg == "--interval" and i + 1 < len(sys.argv):
                interval = int(sys.argv[i + 1])
        watch_mode(interval)
        sys.exit(0)

    data = fetch_tweets(METRO_HANDLE)
    tweets = parse_tweets(data)

    if not tweets:
        if "--json" in sys.argv:
            print(json.dumps({"error": "xurl not authenticated", "handle": METRO_HANDLE, "frankston_line": "unknown"}))
        else:
            print("No tweets fetched. Is xurl authenticated?")
            print("Run: xurl auth status")
        sys.exit(1)

    report = generate_report(tweets)

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
