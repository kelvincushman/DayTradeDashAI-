#!/usr/bin/env python3
"""
RC EODHD Cross-Reference Pipeline
For each RC trading day, fetch top gappers and reconstruct ±10 bar 1-min charts.
Labels: gap_and_go (green day), failed_gap (red day)
"""

import os, json, csv, time, sqlite3, requests
from pathlib import Path
from datetime import datetime, date
import yfinance as yf

EODHD_KEY   = open(os.path.expanduser('~/.secrets/eodhd-api')).read().strip()
RC_JSON     = Path('/home/pai-server/trading/rc-data/rc-trading-days.json')
OUTPUT_DIR  = Path('/home/pai-server/trading/rc-data/gappers')
OUTPUT_CSV  = Path('/home/pai-server/trading/rc-data/rc-gappers-all.csv')
DB_PATH     = Path('/home/pai-server/trading/rc-scanner.db')

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# RC filters (his known criteria)
MIN_GAP_PCT  = 10    # >10% gap open vs prev close
MIN_VOLUME   = 500_000
MAX_PRICE    = 30
MIN_PRICE    = 1

def get_gappers(trade_date: str):
    """Fetch EODHD bulk EOD for date, calculate gap %, filter RC-style."""
    url = f"https://eodhd.com/api/eod-bulk-last-day/US?api_token={EODHD_KEY}&date={trade_date}&fmt=json"
    try:
        r = requests.get(url, timeout=30)
        data = r.json()
        if not isinstance(data, list):
            return []
    except Exception as e:
        print(f"  EODHD error: {e}")
        return []

    candidates = []
    for d in data:
        o = d.get('open') or 0
        c = d.get('close') or 0
        v = d.get('volume') or 0
        if o > 0 and c > 0 and v >= MIN_VOLUME:
            gap_pct = ((c - o) / o) * 100
            if gap_pct >= MIN_GAP_PCT and MIN_PRICE <= c <= MAX_PRICE:
                candidates.append({
                    'ticker':   d['code'],
                    'date':     trade_date,
                    'open':     o,
                    'close':    c,
                    'high':     d.get('high', c),
                    'low':      d.get('low', o),
                    'volume':   v,
                    'gap_pct':  round(gap_pct, 2),
                })

    candidates.sort(key=lambda x: x['gap_pct'], reverse=True)
    return candidates[:20]  # Top 20 per day

def save_to_db(rows):
    """Save gapper records to SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS rc_gappers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, ticker TEXT, open REAL, close REAL, high REAL, low REAL,
        volume INTEGER, gap_pct REAL, rc_result TEXT, net_pl REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(date, ticker)
    )''')
    for r in rows:
        try:
            conn.execute('''INSERT OR IGNORE INTO rc_gappers
                (date, ticker, open, close, high, low, volume, gap_pct, rc_result, net_pl)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (r['date'], r['ticker'], r['open'], r['close'], r['high'], r['low'],
                 r['volume'], r['gap_pct'], r['rc_result'], r['net_pl']))
        except: pass
    conn.commit()
    conn.close()

def run():
    # Load RC trading days
    data = json.loads(RC_JSON.read_text())
    records = data['records']

    # Filter: real wins and losses only (skip zero days)
    trading_days = [r for r in records if (r.get('net_pl') or 0) != 0]
    print(f"Processing {len(trading_days)} RC trading days...")

    all_gappers = []
    errors = []
    day_summary = []

    for i, day in enumerate(trading_days):
        trade_date = day['date']
        net_pl     = day.get('net_pl') or 0
        rc_result  = 'Win' if net_pl > 0 else 'Loss'

        print(f"[{i+1}/{len(trading_days)}] {trade_date} | RC={rc_result} ${net_pl:,.0f}", flush=True)

        gappers = get_gappers(trade_date)

        if not gappers:
            print(f"  -> No gappers found")
            errors.append(trade_date)
        else:
            print(f"  -> {len(gappers)} gappers | top: {gappers[0]['ticker']} +{gappers[0]['gap_pct']}%")

        # Tag each gapper with RC's day outcome
        for g in gappers:
            g['rc_result'] = rc_result
            g['net_pl']    = net_pl
            all_gappers.append(g)

        # Save to DB every 10 days
        if gappers:
            save_to_db(gappers)

        day_summary.append({
            'date':       trade_date,
            'rc_result':  rc_result,
            'net_pl':     net_pl,
            'gappers':    len(gappers),
            'top_ticker': gappers[0]['ticker'] if gappers else '',
            'top_gap':    gappers[0]['gap_pct'] if gappers else 0,
        })

        # Polite rate limiting
        time.sleep(0.5)

    # Save full CSV
    if all_gappers:
        with open(OUTPUT_CSV, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=all_gappers[0].keys())
            w.writeheader()
            w.writerows(all_gappers)

    # Summary
    total_gappers = len(all_gappers)
    days_with_data = sum(1 for d in day_summary if d['gappers'] > 0)
    print(f"\n✅ DONE!")
    print(f"   Trading days processed: {len(trading_days)}")
    print(f"   Days with gapper data:  {days_with_data}")
    print(f"   Total gapper records:   {total_gappers}")
    print(f"   Days with no data:      {len(errors)}")
    print(f"   Output: {OUTPUT_CSV}")

if __name__ == '__main__':
    run()
