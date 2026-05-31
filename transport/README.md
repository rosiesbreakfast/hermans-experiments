# Transport Module — Frankston Line & Cheltenham Station Monitoring

Monitors the Frankston train line for disruptions using two sources:

1. **PTV Timetable API** (primary) — official disruption data
2. **@metrotrains Twitter** (secondary) — real-time updates

## Setup (do this once)

### 1. PTV API Key (free — email request)

Send an email to **APIKeyRequest@ptv.vic.gov.au** with subject:

> PTV Timetable API – request for key

You'll receive a reply with:
- A **DevID** (integer, e.g. `42`)
- An **API Key** (UUID, e.g. `9c132d31-6a30-4cac-8d8b-8a1970834799`)

Save them to `~/.hermes-ptv.yaml`:

```yaml
ptv_devid: 42
ptv_key: "9c132d31-6a30-4cac-8d8b-8a1970834799"
```

Or set as environment variables:

```bash
export PTV_DEVID=42
export PTV_KEY="9c132d31-6a30-4cac-8d8b-8a1970834799"
```

No paid tier — it's genuinely free for developers.

### 2. X/Twitter API (via xurl CLI)

The Twitter monitor checks @metrotrains for disruption tweets.

**Prerequisites:**
- An X Developer account (https://developer.x.com)
- An X app with OAuth 2.0 enabled
- The `xurl` CLI (already installed)

**One-time setup (run these commands directly, NOT via agent):**

```bash
# 1. Create an X app at https://developer.x.com/en/portal/dashboard
#    Get your Client ID and Client Secret

# 2. Register the app locally
xurl auth apps add metrotrains --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET

# 3. Authenticate (opens a browser for OAuth)
xurl auth oauth2 --app metrotrains

# 4. Set as default
xurl auth default metrotrains

# 5. Verify it works
xurl auth status
xurl search "from:metrotrains" -n 3
```

## Usage

### Dashboard

Run the dashboard as usual — it automatically uses the transport module:

```bash
cd ~/hermans-experiments
python3 morning-dashboard/generate.py
```

### Standalone Twitter Monitor

```bash
# Text summary
python3 transport/twitter_monitor.py

# JSON output (for cron jobs/programmatic use)
python3 transport/twitter_monitor.py --json

# Watch mode (poll every 5 min)
python3 transport/twitter_monitor.py --watch

# Adjust watch interval
python3 transport/twitter_monitor.py --watch --interval 600
```

### Cron Job

To check @metrotrains every 15 minutes and deliver to Discord:

```bash
hermes cron create \
  --name "metro-trains-check" \
  --schedule "*/15 * * * *" \
  --prompt "Run python3 ~/hermans-experiments/transport/twitter_monitor.py --json. If there are Frankston line disruptions (status != normal), format a brief alert. If normal status, stay silent." \
  --deliver discord:#bot-home
```

## Architecture

```
transport/
├── __init__.py           # Main module — check_transport() function
├── twitter_monitor.py    # Standalone Twitter script + watch mode
└── README.md             # Setup instructions

morning-dashboard/
└── generate.py           # Uses transport.check_transport()
```

**Data flow:**
1. `generate.py` calls `transport.check_transport()`
2. Tries PTV API first (via HMAC-signed request to `timetableapi.ptv.vic.gov.au`)
3. Falls back to `@metrotrains` tweets via `xurl`
4. Combines both sources, deduplicates, picks the worst severity
5. Returns structured data to the dashboard

**Route IDs (used internally):**
- Frankston: 6
- Cranbourne: 4
- Pakenham: 11
- Sandringham: 12
- Glen Waverley: 7
