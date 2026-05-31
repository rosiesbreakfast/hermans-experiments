#!/usr/bin/env python3
"""
Defuse Weekly — rumination pattern analyzer.

Reads a Defuse export JSON file, analyzes patterns across entries,
cross-references against Obsidian vault notes for counter-evidence,
and writes a Weekly Pattern Report to the vault.

Usage:
    python3 defuse-weekly.py <defuse_export.json> [--vault ~/Hermans-Obsidian-Vault]
    python3 defuse-weekly.py --demo  (uses built-in sample data)
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

# ─── Config ────────────────────────────────────────────────────────────────

VAULT = os.path.expanduser("~/Hermans-Obsidian-Vault")
WEEKLY_DIR = os.path.join(VAULT, "wikis", "hermes", "weekly")
MAX_RECENT = 50  # max entries to analyze per run

TRIGGER_LABELS = {
    "dismissed": "Dismissed / ignored",
    "talked_over": "Talked over / interrupted",
    "status_challenge": "Status challenged",
    "excluded": "Excluded / left out",
    "criticised": "Criticised / judged",
    "micromanaged": "Micro-managed",
    "misrepresented": "Misrepresented",
    "tone": "Tone / delivery",
    "boundary": "Boundary crossed",
    "ghosted": "Ghosted / no reply",
    "credit": "Credit taken",
    "blamed": "Blamed unfairly",
    "uncertainty": "Uncertainty / ambiguity",
    "other": "Other",
}


# ─── Parsing ───────────────────────────────────────────────────────────────

def load_defuse_data(path):
    """Load and validate a Defuse export JSON file."""
    if path == "--demo":
        return generate_demo_data()

    with open(path) as f:
        raw = f.read()
    # Support both raw JSON array and the console export format:
    # JSON.parse(localStorage.getItem('defuse_events'))
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "defuse_events" in data:
        return data["defuse_events"]
    if isinstance(data, str):
        return json.loads(data)
    return data


def generate_demo_data():
    """Generate realistic sample data for demo mode."""
    now = datetime.now(timezone.utc)
    entries = []
    base_triggers = ["dismissed", "talked_over", "criticised", "uncertainty"]
    for i in range(30):
        day_offset = i * 1.2
        dt = now - timedelta(hours=day_offset * 24 * (i / 30 + 0.5))
        triggers = [base_triggers[i % 4], base_triggers[(i + 1) % 4]]
        sev = 4 + (i % 7)
        who = ["colleague", "manager", "friend", "partner", "stranger"][i % 5]
        entries.append({
            "id": f"demo-{i}",
            "createdAt": dt.isoformat(),
            "mode": "quick" if i % 3 != 0 else "full",
            "facts": f"Sample entry #{i}: something happened with {who}",
            "meaning": f"I worried this meant something bad about me",
            "severity": sev,
            "triggerCategories": triggers,
            "who": who,
            "intent": ["unclear", "no", "yes"][i % 3],
            "intentEvidence": ["low", "medium", "high"][i % 3],
            "alternativeExplanations": i % 2 == 0,
            "jobImpact": i % 3 == 0,
            "isClosed": True,
            "closedAt": (dt + timedelta(minutes=15)).isoformat(),
            "interruptDecision": "close" if i % 3 != 0 else ["park", "act"][i % 2],
            "actionDecision": "none" if i % 3 != 0 else ["follow_up", "defer"][i % 2],
            "statusAssessment": ["stable", "unclear", "impact_possible"][i % 3],
            "reopenedCount": i // 10,
        })
    return entries


# ─── Analysis engine ───────────────────────────────────────────────────────

def analyze(events):
    """Run analysis on Defuse events and return structured results."""
    now = datetime.now(timezone.utc)
    cutoff_week = now - timedelta(days=7)
    cutoff_month = now - timedelta(days=30)

    weekly = [e for e in events if parse_ts(e.get("createdAt", "")) >= cutoff_week]
    monthly = [e for e in events if parse_ts(e.get("createdAt", "")) >= cutoff_month]

    # Severity
    weekly_sev = [e.get("severity", 0) for e in weekly if e.get("severity")]
    monthly_sev = [e.get("severity", 0) for e in monthly if e.get("severity")]

    # Trigger frequency
    all_triggers = []
    for e in monthly:
        for t in e.get("triggerCategories", []):
            all_triggers.append(t)
    trigger_counts = Counter(all_triggers)

    # Who appears most
    who_counts = Counter(e.get("who") for e in monthly if e.get("who"))

    # Time of day distribution
    hour_counts = Counter()
    for e in monthly:
        ts = parse_ts(e.get("createdAt", ""))
        if ts:
            hour_counts[ts.hour] += 1

    # Intentionality breakdown
    intent_counts = Counter(e.get("intent") for e in monthly if e.get("intent"))

    # Status assessment breakdown
    status_counts = Counter(e.get("statusAssessment") for e in monthly if e.get("statusAssessment"))

    # Action decisions
    action_counts = Counter(e.get("actionDecision") for e in monthly if e.get("actionDecision"))

    # Recurring topics (by trigger combination patterns)
    trigger_pairs = Counter()
    for e in monthly:
        triggers = tuple(sorted(e.get("triggerCategories", [])))
        if len(triggers) >= 2:
            trigger_pairs[triggers] += 1

    # Weekly trend: severity over last 7 days
    daily_sev = defaultdict(list)
    for e in weekly:
        ts = parse_ts(e.get("createdAt", ""))
        if ts:
            day_key = ts.strftime("%Y-%m-%d")
            daily_sev[day_key].append(e.get("severity", 0))

    return {
        "total": len(events),
        "weekly_count": len(weekly),
        "monthly_count": len(monthly),
        "weekly_avg_sev": round(sum(weekly_sev) / len(weekly_sev), 1) if weekly_sev else 0,
        "monthly_avg_sev": round(sum(monthly_sev) / len(monthly_sev), 1) if monthly_sev else 0,
        "weekly_max_sev": max(weekly_sev) if weekly_sev else 0,
        "trigger_counts": trigger_counts.most_common(10),
        "who_counts": who_counts.most_common(5),
        "hour_distribution": sorted(hour_counts.items()),
        "intent_counts": dict(intent_counts),
        "status_counts": dict(status_counts),
        "action_counts": dict(action_counts),
        "top_trigger_pairs": trigger_pairs.most_common(5),
        "daily_severity": dict(sorted(daily_sev.items())),
        "trigger_labels": TRIGGER_LABELS,
    }


def parse_ts(ts_str):
    """Parse an ISO timestamp string, with fallback."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str)
    except:
        try:
            return datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        except:
            return None


# ─── Vault cross-reference ─────────────────────────────────────────────────

def search_vault_for_topic(topic, vault_path):
    """Search vault notes for mentions of a topic (simple keyword match)."""
    topic_lower = topic.lower()
    matches = []
    notes_dir = os.path.join(vault_path, "wikis")
    if not os.path.isdir(notes_dir):
        return []
    for root, dirs, files in os.walk(notes_dir):
        for f in files:
            if not f.endswith(".md"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    content = fh.read()
                if topic_lower in content.lower():
                    # Extract relevant snippet
                    idx = content.lower().find(topic_lower)
                    start = max(0, idx - 60)
                    end = min(len(content), idx + 120)
                    snippet = content[start:end].strip()
                    # Clean up snippet
                    rel_path = os.path.relpath(path, vault_path)
                    matches.append({
                        "file": rel_path,
                        "snippet": snippet[:150],
                    })
            except:
                continue
        break  # only top-level wiki dirs
    return matches


# ─── Mood/trigger correlation ──────────────────────────────────────────────

def compute_recurring_patterns(analysis, events):
    """Identify recurring patterns — same triggers appearing multiple times."""
    monthly = [
        e for e in events
        if parse_ts(e.get("createdAt", "")) >= datetime.now(timezone.utc) - timedelta(days=30)
    ]

    # Group triggers by person
    person_trigger = defaultdict(list)
    for e in monthly:
        who = e.get("who", "unknown")
        for t in e.get("triggerCategories", []):
            person_trigger[who].append(t)

    patterns = []
    for person, triggers in person_trigger.items():
        counts = Counter(triggers)
        if len(monthly) >= 2:
            pattern = {
                "person": person,
                "top_triggers": [f"{TRIGGER_LABELS.get(t, t)} ({c}×)" for t, c in counts.most_common(3)],
                "count": len(triggers),
            }
            patterns.append(pattern)

    return sorted(patterns, key=lambda p: -p["count"])[:5]


# ─── Report generation ─────────────────────────────────────────────────────

def generate_report(analysis, patterns, vault_matches, header=""):
    """Generate the weekly report markdown."""
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=7)).strftime("%b %d")
    week_end = now.strftime("%b %d, %Y")

    lines = [
        "---",
        f'generated: "{now.strftime("%Y-%m-%d %H:%M")}"',
        "tags:",
        "  - hermes",
        "  - defuse",
        "  - weekly-report",
        "  - rumination",
        "---",
        "",
        f"# Weekly Pattern Report — {week_start} – {week_end}",
        "",
    ]

    if header:
        lines.append(header)
        lines.append("")

    # ── Overview ──
    lines.append("## 📊 Overview")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| This week | {analysis['weekly_count']} events |")
    lines.append(f"| Last 30 days | {analysis['monthly_count']} events |")
    lines.append(f"| Avg severity (week) | {analysis['weekly_avg_sev']}/10 |")
    lines.append(f"| Avg severity (month) | {analysis['monthly_avg_sev']}/10 |")
    lines.append(f"| Max severity (week) | {analysis['weekly_max_sev']}/10 |")
    lines.append(f"| All time | {analysis['total']} events |")
    lines.append("")

    # ── Trigger breakdown ──
    lines.append("## 🔥 Most Common Triggers (30 days)")
    lines.append("")
    for trigger, count in analysis["trigger_counts"][:8]:
        label = analysis["trigger_labels"].get(trigger, trigger)
        bar = "█" * min(count, 20)
        lines.append(f"- **{label}**: {count}× {bar}")
    lines.append("")

    # ── Trigger pairs (recurring patterns) ──
    if analysis["top_trigger_pairs"]:
        lines.append("## 🔗 Recurring Trigger Combinations")
        lines.append("")
        lines.append("These trigger pairs appear together repeatedly — they may be the same rumination loop surfacing in different contexts:")
        lines.append("")
        for pair, count in analysis["top_trigger_pairs"][:5]:
            labels = [analysis["trigger_labels"].get(t, t) for t in pair]
            lines.append(f"- **{labels[0]}** + **{labels[1]}** — {count}×")
        lines.append("")

    # ── Who appears ──
    if analysis["who_counts"]:
        lines.append("## 👤 People in Events (30 days)")
        lines.append("")
        for who, count in analysis["who_counts"][:5]:
            if who and who != "unknown":
                lines.append(f"- **{who.title()}**: {count} events")
        lines.append("")

    # ── Recurring person patterns ──
    if patterns:
        lines.append("## 🔄 Recurring Patterns by Person")
        lines.append("")
        lines.append("When the same person appears multiple times, look for the pattern:")
        lines.append("")
        for p in patterns[:4]:
            triggers_str = ", ".join(p["top_triggers"])
            lines.append(f"- **{p['person'].title()}**: {triggers_str}")
        lines.append("")

    # ── Severity trend ──
    if analysis["daily_severity"]:
        lines.append("## 📈 Severity Trend (This Week)")
        lines.append("")
        for day, sevs in analysis["daily_severity"].items():
            avg = round(sum(sevs) / len(sevs), 1)
            bar_len = max(1, int(avg * 2))
            bar = "█" * bar_len
            pretty_day = datetime.strptime(day, "%Y-%m-%d").strftime("%a %d")
            lines.append(f"- {pretty_day}: {avg}/10 {bar}")
        lines.append("")

    # ── Decision breakdown ──
    if analysis["action_counts"]:
        lines.append("## 🎯 How Events Were Resolved")
        lines.append("")
        for decision, count in sorted(analysis["action_counts"].items(), key=lambda x: -x[1]):
            label = decision.replace("_", " ").title()
            lines.append(f"- **{label}**: {count} events")
        lines.append("")

    # ── Vault cross-reference ──
    if vault_matches:
        lines.append("## 📚 Related Vault Notes")
        lines.append("")
        lines.append("_Notes that may contain useful reframes or counter-evidence:_")
        lines.append("")
        for trigger, matches in vault_matches.items():
            label = analysis["trigger_labels"].get(trigger, trigger)
            if matches:
                lines.append(f"### {label}")
                for m in matches[:2]:
                    lines.append(f"- `{m['file']}`: _{m['snippet']}_")
                lines.append("")

    # ── Weekly insight ──
    lines.append("## 💡 Insight")
    lines.append("")
    if analysis["weekly_count"] == 0:
        insight = "No rumination events logged this week. That's worth noting — either it was a calm week or logging slipped."
    elif analysis["weekly_avg_sev"] < 4:
        insight = "Low average severity this week. Most events were minor blips handled quickly."
    elif analysis["weekly_avg_sev"] < 7:
        insight = f"Moderate severity week (avg {analysis['weekly_avg_sev']}/10). The top triggers were manageable. Check if any specific person or situation is driving the pattern."
    else:
        insight = f"High severity week (avg {analysis['weekly_avg_sev']}/10). Consider whether these events share a root cause that needs addressing beyond closure."
    lines.append(f"> {insight}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"_Generated by Hermes · Defuse Weekly_")

    return "\n".join(lines)


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Defuse Weekly — rumination pattern analyzer")
    parser.add_argument("input", nargs="?", default=None,
                        help="Path to Defuse export JSON file. Omit for demo mode.")
    parser.add_argument("--vault", default=VAULT,
                        help=f"Obsidian vault path (default: {VAULT})")
    parser.add_argument("--out", "-o", default=None,
                        help="Output path (default: vault wikis/hermes/weekly/)")
    parser.add_argument("--all", action="store_true",
                        help="Analyze all events, not just last 50")
    args = parser.parse_args()

    if not args.input:
        print("📥 Using demo data...")
        events = generate_demo_data()
    else:
        print("📥 Loading Defuse data...")
        events = load_defuse_data(args.input)
    if not args.all:
        events = sorted(events, key=lambda e: e.get("createdAt", ""), reverse=True)[:MAX_RECENT]
        events = sorted(events, key=lambda e: e.get("createdAt", ""))
    print(f"   Loaded {len(events)} events")

    print("🔍 Analyzing patterns...")
    analysis = analyze(events)
    patterns = compute_recurring_patterns(analysis, events)

    print("📖 Cross-referencing vault...")
    vault_matches = {}
    for trigger, _ in analysis["trigger_counts"][:5]:
        label = analysis["trigger_labels"].get(trigger, trigger)
        matches = search_vault_for_topic(label, args.vault)
        search_terms = [trigger.replace("_", " ")]
        for term in search_terms:
            matches.extend(search_vault_for_topic(term, args.vault))
        if matches:
            vault_matches[trigger] = matches

    # Check direction of change
    header_lines = []
    if analysis["weekly_count"] > 0 and analysis["monthly_count"] > 0:
        weekly_pct = analysis["weekly_count"] / max(1, (analysis["monthly_count"] / 4))
        if weekly_pct < 0.7:
            header_lines.append("📉 Events are down this week compared to the monthly average.")
        elif weekly_pct > 1.3:
            header_lines.append("⚠️ Events are up this week compared to the monthly average.")
        else:
            header_lines.append("📊 Event frequency is stable compared to the monthly average.")
    header = " ".join(header_lines)

    print("📝 Generating report...")
    report = generate_report(analysis, patterns, vault_matches, header)

    if args.out:
        out_path = args.out
    else:
        week_label = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(WEEKLY_DIR, exist_ok=True)
        out_path = os.path.join(WEEKLY_DIR, f"defuse-weekly-{week_label}.md")

    with open(out_path, "w") as f:
        f.write(report)

    print(f"\n✅ Report written: {out_path}")
    print(f"   This week: {analysis['weekly_count']} events  (avg {analysis['weekly_avg_sev']}/10)")
    print(f"   Top trigger: {analysis['trigger_counts'][0][0] if analysis['trigger_counts'] else 'N/A'}")
    print(f"   Vault cross-refs found: {sum(len(m) for m in vault_matches.values())}")


if __name__ == "__main__":
    main()
