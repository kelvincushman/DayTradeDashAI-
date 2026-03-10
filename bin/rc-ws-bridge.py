#!/usr/bin/env python3
"""WebSocket bridge — reads from SQLite and broadcasts to dashboard clients."""

import asyncio, json, logging, os, sys

sys.path.insert(0, "/home/pai-server/bin")
import rc_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ws-bridge")

try:
    import websockets
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "--break-system-packages", "-q"])
    import websockets

CLIENTS = set()
last_hash = ""

_squeeze_cache = {}  # ticker -> (sq5, sq10, timestamp)
SQUEEZE_CACHE_TTL = 60  # seconds
import time as _time

def calc_squeeze(ticker):
    """Calculate % move in last 5 and 10 minutes using EODHD intraday data."""
    try:
        import urllib.request
        key = open(os.path.expanduser('~/.secrets/eodhd-api')).read().strip()
        url = f'https://eodhd.com/api/intraday/{ticker}.US?interval=1m&api_token={key}&fmt=json'
        with urllib.request.urlopen(url, timeout=5) as r:
            bars = json.loads(r.read())
        if not bars or len(bars) < 6:
            return 0, 0
        c_now = float(bars[-1]['close'])
        c_5m = float(bars[-6]['close']) if len(bars) >= 6 else c_now
        c_10m = float(bars[-11]['close']) if len(bars) >= 11 else c_now
        sq5 = round(((c_now - c_5m) / c_5m) * 100, 2) if c_5m else 0
        sq10 = round(((c_now - c_10m) / c_10m) * 100, 2) if c_10m else 0
        return sq5, sq10
    except:
        return 0, 0

def get_squeeze(ticker):
    now = _time.time()
    if ticker in _squeeze_cache:
        sq5, sq10, ts = _squeeze_cache[ticker]
        if now - ts < SQUEEZE_CACHE_TTL:
            return sq5, sq10
    sq5, sq10 = calc_squeeze(ticker)
    _squeeze_cache[ticker] = (sq5, sq10, now)
    return sq5, sq10

def build_payload():
    candidates = rc_db.get_all_active()
    out = {}
    for c in candidates:
        key = f"{c['ticker']}_{c['scan_date']}"
        sq5, sq10 = get_squeeze(c["ticker"])
        out[key] = {
            "ticker": c["ticker"], "name": c["name"], "price": c["price"],
            "gap_pct": c["gap_pct"], "relvol": c["relvol"], "float_m": c["float_m"],
            "news": c["news"], "timestamp": c["first_seen"], "status": c["status"],
            "scout_status": c["scout_status"], "scan_date": c["scan_date"],
            "former_momo": c.get("former_momo", 0),
            "squeeze_5m": sq5, "squeeze_10m": sq10,
        }
    return json.dumps(out)

async def handler(ws):
    CLIENTS.add(ws)
    log.info(f"Client connected ({len(CLIENTS)} total)")
    try:
        await ws.send(build_payload())
        async for msg in ws:
            for c in CLIENTS:
                if c != ws:
                    try: await c.send(msg)
                    except: pass
    finally:
        CLIENTS.discard(ws)
        log.info(f"Client disconnected ({len(CLIENTS)} total)")

async def broadcast_loop():
    global last_hash
    while True:
        await asyncio.sleep(5)
        data = build_payload()
        h = hash(data)
        if h != last_hash:
            last_hash = h
            for c in list(CLIENTS):
                try: await c.send(data)
                except: CLIENTS.discard(c)

async def main():
    rc_db.init_db()
    log.info("WS bridge starting on 0.0.0.0:8765")
    async with websockets.serve(handler, "0.0.0.0", 8765):
        await broadcast_loop()

if __name__ == "__main__":
    asyncio.run(main())
