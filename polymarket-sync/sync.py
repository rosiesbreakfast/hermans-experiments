#!/usr/bin/env python3
"""
Polymarket Vault Sync — fetches wallet positions and active Polymarket
markets, then writes a structured markdown note to the Obsidian vault.

Usage:
    python3 polymarket-sync.py [wallet_address]
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path


# ─── Config ────────────────────────────────────────────────────────────────

VAULT_BASE = os.path.expanduser("~/Hermans-Obsidian-Vault")
POLY_DIR = os.path.join(VAULT_BASE, "Polymarket Theses")

DEFAULT_WALLETS = {
    "polygon": "0x31eb6b3f1a6c9d5f66a1b18b9708cf86a9343a87",
    "base": "0xaf41a551adcbf9d91d104a4abab1b7eb9d39ffac",
}

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
POLYGON_RPC = "https://polygon-bor-rpc.publicnode.com"


# ─── Helpers ───────────────────────────────────────────────────────────────

def sh(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except:
        return ""


def api_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except:
        return None


def fmt_addr(addr):
    """Shorten address for display."""
    return f"{addr[:6]}...{addr[-4:]}"


# ─── On-chain checks ──────────────────────────────────────────────────────

def check_balances(wallets):
    """Check MATIC/POL and ETH balances via RPC."""
    results = {}
    for chain, addr in wallets.items():
        if chain == "polygon":
            # Use Polygon RPC for POL balance
            payload = json.dumps({
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [addr, "latest"],
                "id": 1,
            }).encode()
            req = urllib.request.Request(
                POLYGON_RPC,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    d = json.loads(resp.read().decode())
                    hex_bal = d.get("result", "0x0")
                    bal = int(hex_bal, 16) / 1e18
                    results[chain] = {
                        "address": addr,
                        "balance": bal,
                        "symbol": "POL",
                    }
            except:
                results[chain] = {"address": addr, "balance": None, "symbol": "POL"}
        elif chain == "base":
            # Try Basescan API
            r = sh(f'curl -s "https://api.basescan.org/api?module=account&action=balance&address={addr}&tag=latest&apikey="')
            try:
                d = json.loads(r)
                if d.get("status") == "1":
                    bal = int(d["result"]) / 1e18
                    results[chain] = {"address": addr, "balance": bal, "symbol": "ETH"}
                else:
                    results[chain] = {"address": addr, "balance": None, "symbol": "ETH"}
            except:
                results[chain] = {"address": addr, "balance": None, "symbol": "ETH"}
    return results


# ─── Polymarket data ──────────────────────────────────────────────────────

def get_trending():
    """Get top active events by volume."""
    url = f"{GAMMA}/events?closed=false&limit=10&order=volume24hr&ascending=false"
    data = api_get(url)
    if not data or not isinstance(data, list):
        return []
    results = []
    for event in data[:10]:
        title = event.get("title", "Untitled")
        vol = event.get("volume24hr", 0)
        markets = event.get("markets", [])
        mkt_info = []
        for m in markets[:2]:
            prices = m.get("outcomePrices", "[]")
            if isinstance(prices, str):
                try:
                    prices = json.loads(prices)
                except:
                    prices = []
            mkt_info.append({
                "question": m.get("question", "?"),
                "prices": [f"{float(p)*100:.1f}%" for p in prices],
                "volume": m.get("volume", 0),
            })
        results.append({
            "title": title,
            "volume": vol,
            "markets": mkt_info,
        })
    return results


def get_wallet_positions(addr):
    """Check if wallet holds any Polymarket CLOB positions."""
    # Try to find USDC balance as proxy for active positions
    usdc_polygon = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{
            "to": usdc_polygon,
            "data": "0x70a08231" + "0" * 24 + addr[2:].lower()
        }, "latest"],
        "id": 1,
    }).encode()
    req = urllib.request.Request(
        POLYGON_RPC,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode())
            bal = int(d.get("result", "0x0"), 16) / 1e6
            return bal
    except:
        return None


# ─── Markdown generation ──────────────────────────────────────────────────

def generate():
    wallets = DEFAULT_WALLETS
    if len(sys.argv) > 1:
        wallets["custom"] = sys.argv[1]

    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(POLY_DIR, exist_ok=True)

    print("🔍 Checking wallet balances...")
    balances = check_balances(wallets)

    print("📊 Fetching trending Polymarket events...")
    trending = get_trending()

    print("💳 Checking USDC positions...")
    polygon_usdc = get_wallet_positions(wallets["polygon"])

    # Build markdown
    lines = [
        "---",
        f'updated: "{today}"',
        "tags:",
        "  - polymarket",
        "  - positions",
        "---",
        "",
        f"# Polymarket Positions — {today}",
        "",
        "## Wallet Balances",
        "",
    ]

    total_usd = 0
    for chain, info in balances.items():
        bal = info["balance"]
        symbol = info["symbol"]
        addr = fmt_addr(info["address"])
        if bal is not None:
            lines.append(f"- **{chain.title()}** ({addr}): {bal:.4f} {symbol}")
            if symbol == "ETH":
                total_usd += bal * 3500  # rough estimate
            elif symbol == "POL":
                total_usd += bal * 0.5
        else:
            lines.append(f"- **{chain.title()}** ({addr}): unavailable")
    lines.append("")

    if polygon_usdc is not None:
        total_usd += polygon_usdc
        lines.append(f"- **USDC (Polygon):** ${polygon_usdc:.2f}")
    lines.append("")
    lines.append(f"**Estimated total:** ~${total_usd:.2f}")
    lines.append("")

    lines.append("---")
    lines.append("")

    # Active markets
    lines.append("## 🔥 Active Markets (by 24h volume)")
    lines.append("")
    if trending:
        for event in trending[:5]:
            lines.append(f"### {event['title']}")
            lines.append(f"*24h volume: ${float(event['volume']):,.0f}*")
            lines.append("")
            for m in event["markets"]:
                prices_str = " / ".join(m["prices"])
                lines.append(f"- **{m['question']}** → {prices_str}")
            lines.append("")
    else:
        lines.append("Could not fetch trending markets.")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 📝 Notes")
    lines.append("")
    lines.append("- Data fetched via Polygon RPC and Polymarket API")
    lines.append("- Prices are indicative — verify before trading")
    lines.append("- Australia is geo-blocked from Polymarket trading")
    lines.append("")
    lines.append(f"_Synced by Hermes at {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    lines.append("")

    content = "\n".join(lines)

    # Write
    out_path = os.path.join(POLY_DIR, f"positions-{today}.md")
    with open(out_path, "w") as f:
        f.write(content)

    # Also update a "latest.md" link
    latest_path = os.path.join(POLY_DIR, "latest.md")
    with open(latest_path, "w") as f:
        f.write(f"# Latest Positions\n\nSee [[positions-{today}]]\n")

    print(f"\n✅ Written: {out_path}")
    if polygon_usdc is not None:
        print(f"   USDC (Polygon): ${polygon_usdc:.2f}")
    for chain, info in balances.items():
        if info["balance"] is not None:
            print(f"   {chain.title()}: {info['balance']:.4f} {info['symbol']}")


if __name__ == "__main__":
    generate()
