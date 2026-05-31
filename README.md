# Hermans Experiments

Experimental playground for Hermes Agent — tools, prototypes, and things I'm trying out. Built by Hermes, for Ian.

## Projects

### Melbourne Morning Dashboard
A dark-themed personal HTML dashboard combining:
- Melbourne weather (current + 3-day forecast)
- Crypto prices (BTC/ETH in AUD with 24h change)
- Top Hacker News stories

`python3 morning-dashboard/generate.py` → outputs a self-contained HTML page.

### Hermes Daily Log
Generates an Obsidian daily note (`~/Hermans-Obsidian-Vault/daily/YYYY-MM-DD.md`) with:
- Melbourne weather
- Crypto prices (BTC/ETH in AUD)
- Hermes session count (last 24h)
- Active cron job list
- Top HN stories

`python3 daily-log/generate.py`

### Polymarket Vault Sync
Fetches wallet balances (Polygon POL, Base ETH) and trending Polymarket events, writes structured notes to `~/Hermans-Obsidian-Vault/Polymarket Theses/`.

`python3 polymarket-sync/sync.py`

Verifies on-chain positions so vault data doesn't go stale.

## Usage

All scripts are standalone Python 3 with zero dependencies beyond the standard library. Run from anywhere.

## License

What's a license?
