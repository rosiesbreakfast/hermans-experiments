"""
Transport data for Melbourne Morning Dashboard.

Combines official PTV API data with @metrotrains Twitter monitoring.
Degrades gracefully when sources are unavailable.

PTV API setup:
  1. Email APIKeyRequest@ptv.vic.gov.au with subject
     "PTV Timetable API - request for key"
  2. You'll receive a devid (integer) and an API key (UUID string).
  3. Save them to ~/.hermes/config.yaml or ~/.hermes-ptv.yaml

Twitter (xurl) setup:
  1. Create an app at https://developer.x.com/en/portal/dashboard
  2. Register it: xurl auth apps add metrotrains --client-id ... --client-secret ...
  3. Auth: xurl auth oauth2 --app metrotrains
  4. Set default: xurl auth default metrotrains
"""

import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.error
import urllib.parse
import hmac
import hashlib
from datetime import datetime

# ─── Config ──────────────────────────────────────────────────────────────────

def _load_ptv_config():
    """Load PTV credentials from file or env vars."""
    # Try config files first
    for path in [
        os.path.expanduser("~/.hermes-ptv.yaml"),
        os.path.expanduser("~/.hermes/config.yaml"),
    ]:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    text = f.read()
                import re as _re
                m = _re.search(r"ptv_devid\s*[=:]\s*['\"]?(\d+)", text)
                k = _re.search(r"ptv_key\s*[=:]\s*['\"]?([\w-]+)", text)
                if m and k:
                    return {"devid": int(m.group(1)), "key": k.group(1)}
            except Exception:
                pass

    # Try env vars
    devid = os.environ.get("PTV_DEVID")
    key = os.environ.get("PTV_KEY")
    if devid and key:
        return {"devid": int(devid), "key": key}

    return None


# ─── PTV API Client ─────────────────────────────────────────────────────────

PTV_BASE = "http://timetableapi.ptv.vic.gov.au"

# Known metropolitan train route IDs (from PTV GTFS)
# Route type 0 = Train
ROUTE_IDS = {
    "frankston": 6,
    "cranbourne": 4,
    "pakenham": 11,
    "sandringham": 12,
    "glen_waverley": 7,
    "belgrave": 2,
    "lilydale": 9,
    "alamein": 1,
    "craigieburn": 3,
    "upfield": 15,
    "werribee": 16,
    "williamstown": 17,
    "hurstbridge": 8,
    "mernda": 10,
    "sunbury": 14,
    "flemington": 5,
    "stony_point": 13,
}


def ptv_sign(path, params, key):
    """Create HMAC-SHA1 signature for PTV API request.

    The signing string is: /v2/{path}?{sorted_query_string}
    where query_string includes devid.
    """
    # Build query string (params sorted alphabetically by key)
    query_parts = []
    for k in sorted(params.keys()):
        v = params[k]
        query_parts.append(f"{k}={urllib.parse.quote(str(v), safe='')}")
    query_string = "&".join(query_parts)

    sign_string = f"/v2/{path}?{query_string}"
    dig = hmac.new(key.encode("ascii"), sign_string.encode("ascii"), hashlib.sha1).hexdigest().upper()
    return dig


def ptv_request(path, params=None, timeout=15):
    """Make a signed request to the PTV Timetable API (v2/v3).

    Returns parsed JSON, or None on failure.
    """
    config = _load_ptv_config()
    if not config:
        return None

    params = dict(params or {})
    params["devid"] = config["devid"]

    signature = ptv_sign(path, params, config["key"])
    params["signature"] = signature

    query = urllib.parse.urlencode(params)
    url = f"{PTV_BASE}/v2/{path}?{query}"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Hermes-Morning-Dashboard/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
        return json.loads(body)
    except Exception as e:
        return None


# ─── Disruptions (v3 API endpoint) ──────────────────────────────────────────

def get_disruptions(route_id=None, route_name=None):
    """Fetch current disruptions from PTV.

    Tries v3 disruptions endpoint first, falls back to v2 route search.

    Args:
        route_id: PTV route ID (int). If omitted, uses Frankston (6).
        route_name: Display name for the route.

    Returns:
        Dict with disruption info, or None.
    """
    if route_id is None:
        route_id = ROUTE_IDS.get("frankston", 6)

    config = _load_ptv_config()
    if not config:
        return None

    display_name = route_name or f"Route {route_id}"

    # Try v3 disruptions endpoint (note: v3 uses same base + signing)
    params = {"devid": config["devid"]}

    # v3 endpoint for route disruptions
    v3_path = f"disruptions/route/{route_id}"
    v3_params = {"devid": config["devid"]}
    v3_sig = ptv_sign(v3_path, v3_params, config["key"])
    v3_params["signature"] = v3_sig
    v3_query = urllib.parse.urlencode(v3_params)
    v3_url = f"{PTV_BASE}/v3/{v3_path}?{v3_query}"

    try:
        req = urllib.request.Request(v3_url, headers={
            "User-Agent": "Hermes-Morning-Dashboard/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", errors="replace")
        data = json.loads(body)
    except Exception:
        data = None

    if data and isinstance(data, dict):
        disruptions = data.get("disruptions", [])
        if disruptions:
            return _format_disruptions(disruptions, display_name)

    # Fallback: try v2 route search
    return _ptv_route_check(route_id, display_name)


def _format_disruptions(disruptions, route_name):
    """Format PTV disruptions into display structure."""
    now = datetime.now()
    items = []
    statuses = set()

    for d in disruptions:
        title = d.get("title", "") or d.get("description", "")
        d_type = d.get("disruption_type", d.get("type", ""))
        status = d.get("disruption_status", d.get("status", "")).lower()
        color = d.get("color", "")

        # Classify severity
        severity = "info"
        if any(w in (title + " " + status + " " + d_type).lower()
               for w in ["suspend", "major", "emergency", "closure"]):
            severity = "major"
            statuses.add("major_disruption")
        elif any(w in (title + " " + status).lower()
                 for w in ["delay", "minor", "slow"]):
            severity = "minor"
            statuses.add("minor_delays")
        elif "planned" in (title + " " + status + " " + d_type).lower():
            severity = "planned"
            statuses.add("planned_works")

        items.append({
            "title": title,
            "type": d_type,
            "severity": severity,
            "status": status,
        })

    if not statuses:
        statuses.add("normal")

    return {
        "route": route_name,
        "status": _pick_status(statuses),
        "disruptions": items,
        "source": "ptv_api",
        "timestamp": datetime.now().isoformat(),
    }


def _pick_status(statuses):
    """Pick the worst status from a set."""
    priority = ["major_disruption", "minor_delays", "planned_works", "normal"]
    for s in priority:
        if s in statuses:
            return s
    return "unknown"


def _ptv_route_check(route_id, route_name):
    """Fallback: check if route exists and has any issues via v2."""
    data = ptv_request(f"mode/0/line/{route_id}/stops-for-line")
    if data is not None:
        return {
            "route": route_name,
            "status": "normal",
            "disruptions": [],
            "source": "ptv_api",
            "note": "PTV API reachable · No current disruptions reported",
            "timestamp": datetime.now().isoformat(),
        }
    return None


# ─── Metro Trains Twitter Monitor ──────────────────────────────────────────

METRO_TRAINS_HANDLE = "metrotrainsmelb"


def get_twitter_disruptions():
    """Check @metrotrains for recent disruption tweets.

    Uses xurl CLI if available (requires user to set up X API auth).
    Falls back to nothing gracefully.
    """
    try:
        # Test if xurl is available and authenticated
        result = subprocess.run(
            ["xurl", "auth", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        # Get latest tweets from @metrotrains
        tweets = subprocess.run(
            ["xurl", "search", f"from:{METRO_TRAINS_HANDLE}", "-n", "10"],
            capture_output=True, text=True, timeout=15,
        )
        if tweets.returncode != 0:
            return None

        data = json.loads(tweets.stdout)
        tweet_texts = []
        if "data" in data:
            for t in data["data"]:
                tweet_texts.append(t.get("text", ""))
        elif "statuses" in data:
            for t in data["statuses"]:
                tweet_texts.append(t.get("text", ""))

        if not tweet_texts:
            return None

        return _parse_metro_tweets(tweet_texts)

    except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return None


def _parse_metro_tweets(tweets):
    """Parse disruption info from @melbournemetro (note: handle may vary) tweets."""
    now = datetime.now()
    disruptions = []
    statuses = set()

    for text in tweets:
        lower = text.lower()
        # Check if this tweet is about Frankston line
        is_frankston = any(w in lower for w in ["frankston", "cheltenham"])
        is_relevant = is_frankston or " " not in text  # General metro tweet

        # Look for disruption keywords
        if any(w in lower for w in ["delays", "delayed", "suspend", "cancelled", "bus replacement"]):
            severity = "minor" if "minor" in lower else "major"
            if is_frankston or "line" in lower:
                disruptions.append({
                    "text": text.strip()[:200],
                    "severity": severity,
                    "source": "twitter",
                })
                if severity == "major":
                    statuses.add("major_disruption")
                else:
                    statuses.add("minor_delays")

        if "planned" in lower and ("works" in lower or "maintenance" in lower):
            if is_frankston or "line" in lower:
                statuses.add("planned_works")
                disruptions.append({
                    "text": text.strip()[:200],
                    "severity": "info",
                    "source": "twitter",
                })

    if not statuses:
        # No disruption tweets found in recent tweets
        return None

    return {
        "route": "Frankston Line",
        "status": _pick_status(statuses),
        "disruptions": disruptions,
        "source": "twitter",
        "timestamp": now.isoformat(),
    }


# ─── Combined Check ─────────────────────────────────────────────────────────

def check_transport(route_id=None, route_name="Frankston Line"):
    """Combined transport check: PTV API primary, Twitter backup.

    Returns a unified structure:
    {
        "status": "normal" | "minor_delays" | "major_disruption" | "planned_works" | "unknown",
        "disruptions": [...],
        "sources_used": [...],
        "note": "...",
        "timestamp": "...",
    }
    """
    result = {
        "status": "unknown",
        "disruptions": [],
        "sources_used": [],
        "note": "",
        "timestamp": datetime.now().isoformat(),
        "station": {
            "name": "Cheltenham",
            "zone": "2",
            "line": "Frankston",
        },
    }

    # Source 1: PTV API
    ptv_data = get_disruptions(route_id=route_id, route_name=route_name)
    if ptv_data:
        result["status"] = ptv_data["status"]
        result["disruptions"].extend(ptv_data.get("disruptions", []))
        result["sources_used"].append("ptv_api")
        if "note" in ptv_data:
            result["note"] = ptv_data["note"]

    # Source 2: Twitter
    tw_data = get_twitter_disruptions()
    if tw_data:
        result["sources_used"].append("twitter")
        # If Twitter has worse status, upgrade
        tw_priority = ["major_disruption", "minor_delays", "planned_works"]
        cur_priority = ["major_disruption", "minor_delays", "planned_works", "normal", "unknown"]

        tw_idx = tw_priority.index(tw_data["status"]) if tw_data["status"] in tw_priority else 99
        cur_idx = cur_priority.index(result["status"]) if result["status"] in cur_priority else 99

        if tw_idx < cur_idx:
            result["status"] = tw_data["status"]

        # De-duplicate by combining
        existing_titles = {d.get("title", "") for d in result["disruptions"]}
        for d in tw_data.get("disruptions", []):
            key = d.get("text", "")[:50]
            if key not in existing_titles:
                result["disruptions"].append(d)
                existing_titles.add(key)

    # Weekend note
    now = datetime.now()
    if now.weekday() >= 5:
        result["note"] = "Weekend — check for planned works and bus replacements"

    # Status summary
    if not result["sources_used"]:
        result["status"] = "unknown"
        result["note"] = "No transport data sources configured. See transport/README.md for setup."

    return result
