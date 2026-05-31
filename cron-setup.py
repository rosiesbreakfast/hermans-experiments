#!/usr/bin/env python3
"""
Cron helper — run these from your terminal to set up Hermes cron jobs.

## Daily Log (every morning at 8am AEDT)
python3 -c "
import subprocess, json
subprocess.run([
    'hermes', 'cron', 'create',
    '--name', 'daily-log',
    '--schedule', '0 8 * * *',
    '--prompt', 'Run the daily log generator',
    '--deliver', 'discord:#cron_jobs',
])
"

## Polymarket Sync (every 6 hours)
python3 -c "
import subprocess, json
subprocess.run([
    'hermes', 'cron', 'create',
    '--name', 'polymarket-sync',
    '--schedule', '0 */6 * * *',
    '--prompt', 'Run polymarket vault sync',
])
"

## Morning Dashboard (every hour)
python3 -c "
import subprocess, json
subprocess.run([
    'hermes', 'cron', 'create',
    '--name', 'morning-dashboard',
    '--schedule', '0 * * * *',
    '--prompt', 'Regenerate the morning dashboard HTML',
])
"
"""

if __name__ == "__main__":
    print(__doc__)
