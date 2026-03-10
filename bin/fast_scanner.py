#!/usr/bin/env python3
"""
Fast Scanner — Full small-cap universe, 30-second cycles.
Uses Alpaca bulk snapshots (1000 symbols/call) to scan ~8k stocks in ~5s.
Float cached in SQLite (7-day TTL). Replaces the Finviz-capped 25-stock scanner.
"""
import os, json, sqlite3, time, threading, requests
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Credentials ──────────────────────────────────────────────────────────────
_cred_path = os.path.expanduser("~/.secrets/alpaca-api")
ALPACA_KEY    = "PKTEPYUEFUWUN25AESFYRHGET4"
ALPACA_SECRET = "3HWRsuoEf1jZyuDByL4BK4MUdaVBYkvHLJg9J2bmRGN3"
if os.path.exists(_cred_path):
    for _line in open(_cred_path).read().splitlines():
        if _line.startswith("KEY="):
            ALPACA_KEY = _line.split("=", 1)[1].strip()
        elif _line.startswith("SECRET="):
            ALPACA_SECRET = _line.split("=", 1)[1].strip()

ALPACA_DATA  = "https://data.alpaca.markets"
ALPACA_TRADE = "https://paper-api.alpaca.markets"

EODHD_KEY_PATH = os.path.expanduser("~/.secrets/eodhd-api")
_EODHD_KEY = open(EODHD_KEY_PATH).read().strip() if os.path.exists(EODHD_KEY_PATH) else ""

FLOAT_CACHE_DB   = "/home/pai-server/trading/float-cache.db"
UNIVERSE_FILE    = "/home/pai-server/trading/scanner-universe.json"
FLOAT_CACHE_DAYS = 14   # Refresh float data every 14 days
UNIVERSE_TTL_H   = 12   # Rebuild universe every 12 hours

_headers = {
    "APCA-API-KEY-ID": ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET,
}

# ── Float Cache DB ───────────────────────────────────────────────────────────
def _init_float_db():
    con = sqlite3.connect(FLOAT_CACHE_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS float_cache (
        ticker TEXT PRIMARY KEY,
        float_m REAL,
        avg_vol_30d REAL,
        updated TEXT
    )""")
    con.commit()
    return con

_float_db_lock = threading.Lock()

def _get_float_cached(ticker):
    """Return (float_m, avg_vol) from cache if fresh, else (None, None)."""
    try:
        with _float_db_lock:
            con = _init_float_db()
            row = con.execute(
                "SELECT float_m, avg_vol_30d, updated FROM float_cache WHERE ticker=?",
                (ticker,)
            ).fetchone()
            con.close()
        if row:
            age = (date.today() - date.fromisoformat(row[2])).days
            if age <= FLOAT_CACHE_DAYS:
                return row[0], row[1]
    except:
        pass
    return None, None

def _save_float_cache(ticker, float_m, avg_vol):
    try:
        with _float_db_lock:
            con = _init_float_db()
            con.execute(
                "INSERT OR REPLACE INTO float_cache (ticker, float_m, avg_vol_30d, updated) VALUES (?,?,?,?)",
                (ticker, float_m, avg_vol, str(date.today()))
            )
            con.commit()
            con.close()
    except:
        pass

def _fetch_float_yfinance(ticker):
    """Fetch float + avg volume from yfinance (slow, used for cache misses only)."""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        float_shares = info.get("floatShares") or info.get("sharesFloat")
        avg_vol = info.get("averageVolume") or info.get("averageVolume10days")
        float_m = float_shares / 1_000_000 if float_shares else None
        return float_m, avg_vol
    except:
        return None, None

# ── Universe Builder ─────────────────────────────────────────────────────────
_universe_lock = threading.Lock()
_universe_cache = {"symbols": [], "built_at": 0}

def build_universe(force=False):
    """
    Fetch all tradeable US equity symbols from Alpaca.
    Cached in UNIVERSE_FILE, rebuilt every UNIVERSE_TTL_H hours.
    """
    # Check file cache first
    if not force and os.path.exists(UNIVERSE_FILE):
        try:
            data = json.load(open(UNIVERSE_FILE))
            age_h = (time.time() - data.get("built_at", 0)) / 3600
            if age_h < UNIVERSE_TTL_H:
                return data["symbols"]
        except:
            pass

    print(f"[FastScanner] Building universe from Alpaca...")
    try:
        # Paginate through all assets
        symbols = []
        next_page = None
        while True:
            params = {"status": "active", "asset_class": "us_equity", "limit": 1000}
            if next_page:
                params["page_token"] = next_page
            r = requests.get(f"{ALPACA_TRADE}/v2/assets", headers=_headers,
                           params=params, timeout=30)
            assets = r.json()
            if not isinstance(assets, list) or not assets:
                break
            for a in assets:
                sym = a.get("symbol", "")
                # Include: tradable, active, no dots/slashes (not warrants/units/rights)
                if (a.get("tradable") and a.get("status") == "active"
                        and len(sym) <= 5 and "." not in sym and "/" not in sym):
                    symbols.append(sym)
            # Alpaca assets endpoint returns all in one call (no pagination needed)
            break

        print(f"[FastScanner] Universe: {len(symbols)} symbols")
        data = {"symbols": symbols, "built_at": time.time()}
        with open(UNIVERSE_FILE, "w") as f:
            json.dump(data, f)
        return symbols
    except Exception as e:
        print(f"[FastScanner] Universe build error: {e}")
        # Fallback: return cached if available
        if os.path.exists(UNIVERSE_FILE):
            return json.load(open(UNIVERSE_FILE)).get("symbols", [])
        return []

# ── Alpaca Snapshot Bulk Fetch ────────────────────────────────────────────────
def _get_snapshots_bulk(symbols, feed="iex"):
    """
    Fetch Alpaca snapshots for up to 10k symbols.
    1000 per call, runs sequentially (10 calls ≈ 5s).
    Returns dict: { symbol: snap_dict }
    """
    results = {}
    chunk_size = 1000
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        try:
            r = requests.get(
                f"{ALPACA_DATA}/v2/stocks/snapshots",
                params={"symbols": ",".join(chunk), "feed": feed},
                headers=_headers,
                timeout=15
            )
            if r.status_code == 200:
                data = r.json()
                # Response is either { sym: snap } or { "snapshots": { sym: snap } }
                if "snapshots" in data:
                    data = data["snapshots"]
                results.update(data)
            else:
                print(f"[Snapshot] HTTP {r.status_code} chunk {i}: {r.text[:100]}")
        except Exception as e:
            print(f"[Snapshot] Error chunk {i}-{i+chunk_size}: {e}")
        # Small delay to be polite to Alpaca rate limits
        time.sleep(0.1)
    return results

# ── EODHD News Batch ──────────────────────────────────────────────────────────
def _check_news_eodhd_batch(tickers, max_tickers=10):
    """
    Check for today's news for a batch of tickers via EODHD.
    Returns dict: { ticker: headline_or_empty }
    """
    if not _EODHD_KEY:
        return {t: "" for t in tickers}
    today = datetime.utcnow().strftime("%Y-%m-%d")
    news_map = {}
    for ticker in tickers[:max_tickers]:
        try:
            r = requests.get(
                f"https://eodhd.com/api/news",
                params={"api_token": _EODHD_KEY, "s": f"{ticker}.US",
                        "from": today, "to": today, "limit": 3, "fmt": "json"},
                timeout=6
            )
            articles = r.json() if r.status_code == 200 else []
            if isinstance(articles, list) and articles:
                news_map[ticker] = articles[0].get("title", "")
            else:
                news_map[ticker] = ""
        except:
            news_map[ticker] = ""
    return news_map

# ── Gap Calculation ───────────────────────────────────────────────────────────
def _calc_gap(snap):
    try:
        prev = (snap.get("prevDailyBar") or {}).get("c", 0)
        today_open = (snap.get("dailyBar") or {}).get("o", 0)
        if prev > 0 and today_open > 0:
            return round((today_open - prev) / prev * 100, 1)
    except:
        pass
    return 0.0

def _calc_relvol(snap, cached_avg_vol=None):
    """
    Estimate relative volume.
    Uses cached avg daily volume if available.
    Falls back to Finviz relVol field if present in snap.
    """
    try:
        today_vol = (snap.get("dailyBar") or {}).get("v", 0)
        if cached_avg_vol and cached_avg_vol > 0 and today_vol > 0:
            return round(today_vol / cached_avg_vol, 1)
    except:
        pass
    return None

def _current_price(snap):
    try:
        p = (snap.get("latestTrade") or {}).get("p")
        if p:
            return round(p, 2)
        p = (snap.get("dailyBar") or {}).get("c")
        if p:
            return round(p, 2)
        p = (snap.get("dailyBar") or {}).get("o")
        if p:
            return round(p, 2)
    except:
        pass
    return 0.0

# ── Main Scan Function ────────────────────────────────────────────────────────
def run_fast_scan(config=None):
    """
    Full universe scan. Returns list of candidate dicts.
    config: dict with min_gap_pct, min_price, max_price, max_float_m, min_relvol
    """
    cfg = config or {}
    min_gap   = float(cfg.get("min_gap_pct",  10))
    min_price = float(cfg.get("min_price",    2.0))
    max_price = float(cfg.get("max_price",   20.0))
    max_float = float(cfg.get("max_float_m", 10.0))
    min_rv    = float(cfg.get("min_relvol",   3.0))  # Loose initial filter

    t0 = time.time()

    # 1. Get universe
    symbols = build_universe()
    if not symbols:
        print("[FastScanner] No universe symbols, aborting scan")
        return []

    # 2. Bulk snapshot
    print(f"[FastScanner] Scanning {len(symbols)} symbols via Alpaca snapshots...")
    snaps = _get_snapshots_bulk(symbols)
    t1 = time.time()
    print(f"[FastScanner] Snapshots: {len(snaps)} results in {t1-t0:.1f}s")

    # 3. Pass 1 — price + gap filter (no float check yet)
    pass1 = []
    for sym, snap in snaps.items():
        try:
            price = _current_price(snap)
            gap   = _calc_gap(snap)
            vol   = (snap.get("dailyBar") or {}).get("v", 0)
            if (min_price <= price <= max_price
                    and gap >= min_gap
                    and vol >= 5000):
                pass1.append({
                    "ticker":    sym,
                    "price":     price,
                    "gap_pct":   gap,
                    "volume":    vol,
                    "prev_close": (snap.get("prevDailyBar") or {}).get("c", 0),
                    "open":      (snap.get("dailyBar") or {}).get("o", 0),
                    "_snap":     snap,
                })
        except:
            pass

    t2 = time.time()
    print(f"[FastScanner] Pass 1: {len(pass1)} candidates (gap≥{min_gap}%, price ${min_price}-${max_price}) in {t2-t1:.2f}s")

    if not pass1:
        return []

    # 4. Float check — cache first, parallel yfinance for misses
    def enrich_float(item):
        t = item["ticker"]
        snap = item.pop("_snap")
        float_m, avg_vol = _get_float_cached(t)

        if float_m is None:
            # Cache miss — fetch from yfinance (slow, but only on new tickers)
            float_m, avg_vol = _fetch_float_yfinance(t)
            if float_m is not None:
                _save_float_cache(t, float_m, avg_vol)

        item["float_m"]  = float_m
        item["relvol"]   = _calc_relvol(snap, avg_vol) or 0
        item["avg_vol"]  = avg_vol
        return item

    # Run float enrichment in parallel (up to 10 concurrent for cache misses)
    enriched = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(enrich_float, item): item["ticker"] for item in pass1}
        for fut in as_completed(futs):
            try:
                enriched.append(fut.result())
            except Exception as e:
                print(f"[FastScanner] Float error {futs[fut]}: {e}")

    t3 = time.time()
    print(f"[FastScanner] Float enrichment: {len(enriched)} done in {t3-t2:.1f}s")

    # 5. Pass 2 — float + relVol filter
    pass2 = []
    for item in enriched:
        float_m = item.get("float_m")
        relvol  = item.get("relvol", 0)
        # Accept if float unknown but other criteria strong
        float_ok = float_m is None or float_m <= max_float
        rv_ok    = relvol == 0 or relvol >= min_rv  # 0 = unknown, don't exclude
        if float_ok and rv_ok:
            pass2.append(item)

    print(f"[FastScanner] Pass 2: {len(pass2)} after float/relVol filter")

    # 6. News check for top candidates (sorted by gap %)
    pass2.sort(key=lambda x: x.get("gap_pct", 0), reverse=True)
    top_for_news = [x["ticker"] for x in pass2[:15] if x.get("float_m") and x["float_m"] <= max_float]
    news_map = {}
    if top_for_news and _EODHD_KEY:
        news_map = _check_news_eodhd_batch(top_for_news, max_tickers=15)

    t4 = time.time()

    # 7. Build final candidates with scanner tags
    candidates = []
    for item in pass2:
        ticker   = item["ticker"]
        price    = item["price"]
        gap_pct  = item["gap_pct"]
        float_m  = item.get("float_m")
        relvol   = item.get("relvol", 0)
        headline = news_map.get(ticker, "")
        has_news = bool(headline)

        is_low_float = float_m is not None and float_m <= max_float
        passes_5p = (is_low_float and gap_pct >= min_gap and
                     relvol >= 5 and price >= min_price and has_news)

        tags = []
        if is_low_float and relvol >= 5 and min_price <= price <= max_price and gap_pct >= min_gap:
            tags.append("lf_high_relvol")
        if is_low_float and 3 <= relvol < 5 and min_price <= price <= max_price and gap_pct >= min_gap:
            tags.append("lf_med_relvol")
        if is_low_float and relvol >= 5 and price > max_price and gap_pct >= min_gap:
            tags.append("lf_high_relvol_20")
        if gap_pct > 0:
            tags.append("gainers")
        tags.append("relvol")

        candidates.append({
            "ticker":          ticker,
            "name":            "",
            "price":           price,
            "gap_pct":         gap_pct,
            "relvol":          relvol,
            "float_m":         float_m,
            "volume":          item.get("volume"),
            "avg_vol":         item.get("avg_vol"),
            "prev_close":      item.get("prev_close"),
            "news":            headline,
            "has_news":        has_news,
            "passes_5_pillars": passes_5p,
            "scanner_tags":    tags,
            "source":          "fast_scanner",
            "scan_time_s":     round(t4 - t0, 1),
        })

    total = t4 - t0
    print(f"[FastScanner] ✅ Scan complete: {len(candidates)} candidates from {len(symbols)} symbols in {total:.1f}s")
    return candidates


# ── Universe Stats ────────────────────────────────────────────────────────────
def universe_stats():
    """Return info about current universe for dashboard health display."""
    try:
        data = json.load(open(UNIVERSE_FILE))
        age_h = round((time.time() - data.get("built_at", 0)) / 3600, 1)
        return {"count": len(data["symbols"]), "age_hours": age_h}
    except:
        return {"count": 0, "age_hours": None}


if __name__ == "__main__":
    print("Running fast scanner test...")
    results = run_fast_scan()
    print(f"\nFound {len(results)} candidates:")
    for r in results[:10]:
        print(f"  {r['ticker']:6s}  gap={r['gap_pct']:+.1f}%  price=${r['price']:.2f}"
              f"  float={r['float_m']:.1f}M" if r['float_m'] else
              f"  {r['ticker']:6s}  gap={r['gap_pct']:+.1f}%  price=${r['price']:.2f}  float=?")
