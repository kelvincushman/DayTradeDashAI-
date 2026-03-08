#!/usr/bin/env python3
"""Ross Cameron Pre-Market Gap Scanner — SQLite-backed."""

import argparse, json, logging, os, sys, time, datetime, requests
import yfinance as yf
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, "/home/pai-server/bin")
import rc_db

EODHD_KEY = open("/home/pai-server/.secrets/eodhd-api").read().strip()
AV_KEY = open("/home/pai-server/.secrets/alphavantage-api").read().strip()
import os as _os
BOT_TOKEN = _os.path.expanduser and open(_os.path.expanduser("~/.secrets/telegram-signals-bot")).read().strip()
TG_CHAT = "1486798034"
LOG_PATH = Path("/home/pai-server/trading/scanner.log")
ET = ZoneInfo("America/New_York")
POLL_INTERVAL = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("gap-scanner")

def send_telegram(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": msg}, timeout=10)
    except Exception as e:
        log.error(f"Telegram failed: {e}")

def get_float(ticker):
    try:
        f = yf.Ticker(ticker).info.get("floatShares")
        return f if f else None
    except Exception as e:
        log.warning(f"Float lookup failed {ticker}: {e}")
        return None

def get_news(ticker):
    try:
        r = requests.get("https://www.alphavantage.co/query",
            params={"function": "NEWS_SENTIMENT", "tickers": ticker, "limit": "1", "apikey": AV_KEY}, timeout=10)
        feed = r.json().get("feed", [])
        return feed[0].get("title", "No headline") if feed else "No news found"
    except:
        return "News unavailable"

def is_market_hours(now_et):
    if now_et.weekday() >= 5: return False
    return 4 <= now_et.hour < 13

def spawn_stock_scout(ticker, float_m, gap_pct, news):
    trigger = {
        "ticker": ticker, "float_m": float_m, "gap_pct": gap_pct,
        "news": news, "timestamp": datetime.datetime.now(ET).isoformat(),
        "action": "spawn_stock_scout"
    }
    trigger_path = Path(f"/home/pai-server/trading/stock-research/{ticker}")
    trigger_path.mkdir(parents=True, exist_ok=True)
    with open(trigger_path / "trigger.json", "w") as f:
        json.dump(trigger, f, indent=2)
    log.info(f"Stock Scout trigger written for {ticker}")

def check_former_momo(ticker):
    """Check if stock had a 50%+ gap day in the last 180 days."""
    try:
        import urllib.request
        from datetime import datetime, timedelta
        key = open(os.path.expanduser('~/.secrets/eodhd-api')).read().strip()
        start = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
        url = f'https://eodhd.com/api/eod/{ticker}.US?api_token={key}&fmt=json&from={start}'
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        for i in range(1, len(data)):
            prev_close = float(data[i-1]['close'])
            open_price = float(data[i]['open'])
            if prev_close > 0:
                gap = ((open_price - prev_close) / prev_close) * 100
                if gap >= 50:
                    return True
        return False
    except:
        return False

def scan_cycle():
    log.info("Starting scan cycle...")
    try:
        r = requests.get("https://eodhd.com/api/screener",
            params={"api_token": EODHD_KEY, "limit": "50",
                "filters": json.dumps([["exchange", "=", "us"], ["refund_1d_p", ">", 10]]),
                "fmt": "json"}, timeout=15)
        data = r.json()
    except Exception as e:
        log.error(f"Screener failed: {e}")
        rc_db.log_scan(0, 0, f"Screener API error: {e}")
        return

    stocks = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(stocks, list):
        log.warning(f"Unexpected response: {str(data)[:200]}")
        rc_db.log_scan(0, 0, "Unexpected API response format")
        return

    log.info(f"Screener returned {len(stocks)} candidates")
    now_et = datetime.datetime.now(ET)
    today = now_et.strftime("%Y-%m-%d")
    checked = len(stocks)
    passed = 0

    # Get existing candidates for today to skip duplicates
    existing = {c["ticker"] for c in rc_db.get_candidates(today)}

    for s in stocks:
        ticker = s.get("code", "")
        if not ticker or ticker in existing:
            continue

        gap_pct = s.get("refund_1d_p", 0) or 0
        price = s.get("adjusted_close", 0) or s.get("close", 0) or 0

        if price < 2 or price > 20:
            log.info(f"SKIP {ticker}: price ${price:.2f} outside $2-$20")
            continue

        avgvol_1d = s.get("avgvol_1d", 0) or 0
        avgvol_200d = s.get("avgvol_200d", 0) or 1
        relvol = avgvol_1d / avgvol_200d if avgvol_200d > 0 else 0
        if relvol < 5:
            log.info(f"SKIP {ticker}: RelVol {relvol:.1f}x < 5x")
            continue

        float_shares = get_float(ticker)
        if float_shares is None:
            log.info(f"SKIP {ticker}: no float data")
            continue
        float_m = float_shares / 1_000_000
        if float_m >= 10:
            log.info(f"SKIP {ticker}: float {float_m:.1f}M >= 10M")
            continue

        news = get_news(ticker)
        log.info(f"🚨 ALERT {ticker}: gap {gap_pct:.1f}%, RelVol {relvol:.1f}x, float {float_m:.1f}M")
        spawn_stock_scout(ticker, float_m, gap_pct, news)

        # FIX6: Cache former_momo — skip EODHD if already in DB
        existing = rc_db._conn().execute(
            "SELECT former_momo FROM candidates WHERE ticker=? AND former_momo IS NOT NULL LIMIT 1",
            (ticker,)
        ).fetchone()
        if existing is not None:
            is_former_momo = bool(existing[0])
        else:
            is_former_momo = check_former_momo(ticker)
        rc_db.upsert_candidate({
            "ticker": ticker, "name": s.get("name", ""),
            "price": round(price, 2), "gap_pct": round(gap_pct, 1),
            "relvol": round(relvol, 1), "float_m": round(float_m, 2),
            "news": news, "scan_date": today, "status": "new", "scout_status": "pending",
            "former_momo": 1 if is_former_momo else 0,
        })
        passed += 1

        send_telegram(
            f"🚨 GAP SCANNER ALERT\n${ticker} — up {gap_pct:.1f}% pre-market\n"
            f"Price: ${price:.2f} | Float: {float_m:.1f}M | RelVol: {relvol:.0f}x\n"
            f"News: {news}\nTime: {now_et.strftime('%H:%M')} ET")

    rc_db.log_scan(checked, passed, f"Cycle at {now_et.strftime('%H:%M')} ET")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    rc_db.init_db()
    log.info("Gap scanner started (SQLite-backed)")
    if args.test:
        scan_cycle()
        log.info("Test cycle complete")
        return
    while True:
        now_et = datetime.datetime.now(ET)
        if is_market_hours(now_et):
            scan_cycle()
        else:
            log.info(f"Outside market hours ({now_et.strftime('%H:%M')} ET)")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
