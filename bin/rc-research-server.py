#!/usr/bin/env python3
"""Serves Stock Scout research + news + trades + Alpaca + settings + native RC scanner for the dashboard."""
import http.server, socketserver, os, json, sqlite3, sys, urllib.request, urllib.error
import threading, time, requests
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rc_alpaca

RESEARCH_DIR = "/home/pai-server/trading/stock-research"
DB_PATH = "/home/pai-server/trading/rc-scanner.db"

_backtest_running = False
_backtest_progress = {"total": 0, "done": 0, "trades": 0}

SCANNER_CONFIG_PATH = "/home/pai-server/trading/scanner-config.json"
PORT = 8767

DEFAULTS = {
    "starting_balance": "600",
    "max_risk_pct": "2",
    "max_position_pct": "20",
    "max_positions_open": "3",
    "min_gap_pct": "10",
    "max_gap_pct": "500",
    "min_relvol": "5",
    "max_float_m": "10",
    "min_price": "2.00",
    "max_price": "20.00",
    "scan_interval": "60",
    "active_hours_start": "04:00",
    "active_hours_end": "12:00",
    "telegram_alerts": "on",
    "alert_new_candidate": "on",
    "alert_scout_done": "on",
    "alert_trade_executed": "on",
    "min_gap_alert": "20",
}

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def _now():
    return datetime.now(timezone.utc).isoformat()

def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def init_tables():
    c = db()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, side TEXT NOT NULL, qty INTEGER NOT NULL,
            entry_price REAL NOT NULL, exit_price REAL, entry_time TEXT, exit_time TEXT,
            status TEXT DEFAULT 'open', pnl REAL, pnl_pct REAL, notes TEXT,
            source TEXT DEFAULT 'manual', alpaca_order_id TEXT
        );
        CREATE TABLE IF NOT EXISTS daily_pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT UNIQUE,
            gross_pnl REAL DEFAULT 0, num_trades INTEGER DEFAULT 0,
            num_wins INTEGER DEFAULT 0, num_losses INTEGER DEFAULT 0,
            best_trade REAL DEFAULT 0, worst_trade REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            name TEXT, price REAL, gap_pct REAL, relvol REAL,
            float_m REAL, news TEXT, scan_date TEXT, first_seen TEXT,
            last_updated TEXT, status TEXT DEFAULT 'new',
            scout_status TEXT DEFAULT 'pending',
            former_momo INTEGER DEFAULT 0,
            squeeze_5m REAL DEFAULT 0,
            squeeze_10m REAL DEFAULT 0,
            avgvol_1d REAL,
            avgvol_200d REAL,
            volume REAL
        );
    """)
    # Migrate: add columns if missing
    for col, typedef in [
        ('squeeze_5m', 'REAL DEFAULT 0'),
        ('squeeze_10m', 'REAL DEFAULT 0'),
        ('avgvol_1d', 'REAL'),
        ('avgvol_200d', 'REAL'),
        ('volume', 'REAL'),
    ]:
        try:
            c.execute(f'ALTER TABLE candidates ADD COLUMN {col} {typedef}')
        except Exception:
            pass
    for k, v in DEFAULTS.items():
        row = c.execute("SELECT 1 FROM settings WHERE key=?", (k,)).fetchone()
        if not row:
            c.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (k, v))
    c.commit(); c.close()
    write_scanner_config()

def get_setting(key, default=None):
    try:
        c = db(); row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone(); c.close()
        return row['value'] if row else (default or DEFAULTS.get(key))
    except:
        return default or DEFAULTS.get(key)

def get_all_settings():
    try:
        c = db(); rows = c.execute("SELECT key, value FROM settings").fetchall(); c.close()
        d = dict(DEFAULTS)
        d.update({r['key']: r['value'] for r in rows})
        return d
    except:
        return dict(DEFAULTS)

def save_settings(data):
    c = db()
    for k, v in data.items():
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
    c.commit(); c.close()
    write_scanner_config()

def write_scanner_config():
    s = get_all_settings()
    cfg = {
        "min_gap_pct": float(s.get("min_gap_pct", 10)),
        "max_gap_pct": float(s.get("max_gap_pct", 500)),
        "min_relvol": float(s.get("min_relvol", 5)),
        "max_float_m": float(s.get("max_float_m", 10)),
        "min_price": float(s.get("min_price", 2)),
        "max_price": float(s.get("max_price", 20)),
        "scan_interval": int(s.get("scan_interval", 60)),
        "active_hours_start": s.get("active_hours_start", "04:00"),
        "active_hours_end": s.get("active_hours_end", "12:00"),
        "telegram_alerts": s.get("telegram_alerts", "on") == "on",
        "alert_new_candidate": s.get("alert_new_candidate", "on") == "on",
        "alert_scout_done": s.get("alert_scout_done", "on") == "on",
        "alert_trade_executed": s.get("alert_trade_executed", "on") == "on",
        "min_gap_alert": float(s.get("min_gap_alert", 20)),
    }
    try:
        with open(SCANNER_CONFIG_PATH, 'w') as f:
            json.dump(cfg, f, indent=2)
    except: pass

def test_api(name):
    """Test an API connection and return status."""
    try:
        if name == 'eodhd':
            key_path = os.path.expanduser("~/.secrets/eodhd-api")
            if not os.path.exists(key_path): return {"status": "not_configured"}
            key = open(key_path).read().strip()
            req = urllib.request.Request(f"https://eodhd.com/api/exchange-symbol-list/US?api_token={key}&fmt=json&type=common_stock")
            with urllib.request.urlopen(req, timeout=8) as r:
                return {"status": "connected", "info": "EODHD API active"}
        elif name == 'alpaca_paper':
            old_mode = rc_alpaca.get_mode()
            rc_alpaca.set_mode("paper")
            acct = rc_alpaca.get_account()
            rc_alpaca.set_mode(old_mode)
            if "error" in acct: return {"status": "error", "info": str(acct["error"])}
            return {"status": "connected", "equity": acct.get("equity", "?"), "info": f"${float(acct.get('equity',0)):,.2f} equity"}
        elif name == 'alpaca_live':
            live_creds_path = os.path.expanduser("~/.secrets/alpaca-live-api")
            if not os.path.exists(live_creds_path):
                return {"status": "not_configured", "info": "No live credentials found"}
            live_creds = {}
            with open(live_creds_path) as f:
                for line in f:
                    if '=' in line:
                        k, v = line.strip().split('=', 1)
                        live_creds[k.strip()] = v.strip()
            req = urllib.request.Request("https://api.alpaca.markets/v2/account")
            req.add_header("APCA-API-KEY-ID", live_creds.get("KEY",""))
            req.add_header("APCA-API-SECRET-KEY", live_creds.get("SECRET",""))
            with urllib.request.urlopen(req, timeout=10) as r:
                acct = json.loads(r.read())
            equity = float(acct.get("equity", 0))
            bp = float(acct.get("buying_power", 0))
            return {"status": "connected", "equity": str(equity), "info": f"${equity:,.2f} equity · ${bp:,.2f} buying power"}
        elif name == 'alphavantage':
            key_path = os.path.expanduser("~/.secrets/alphavantage-api")
            if not os.path.exists(key_path): return {"status": "not_configured"}
            key = open(key_path).read().strip()
            req = urllib.request.Request(f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=1min&apikey={key}&datatype=json")
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
                if "Error Message" in data or "Note" in data:
                    return {"status": "limited", "info": data.get("Note", data.get("Error Message", ""))}
                return {"status": "connected", "info": "Alpha Vantage active"}
        return {"status": "unknown"}
    except Exception as e:
        return {"status": "error", "info": str(e)[:100]}

# ── Research/news/candidates (unchanged logic) ──────────────────────────

def get_research(ticker, date=None):
    if os.path.exists(DB_PATH):
        try:
            with db() as con:
                if date:
                    row = con.execute("SELECT * FROM research WHERE ticker=? AND research_date=? LIMIT 1", (ticker, date)).fetchone()
                else:
                    row = con.execute("SELECT * FROM research WHERE ticker=? ORDER BY research_date DESC LIMIT 1", (ticker,)).fetchone()
                if row:
                    d = dict(row)
                    if d.get("risk_flags"):
                        try: d["risk_flags"] = json.loads(d["risk_flags"])
                        except: pass
                    return d
        except: pass
    today = date or datetime.utcnow().strftime('%Y-%m-%d')
    fpath = os.path.join(RESEARCH_DIR, ticker, f"{today}.json")
    if os.path.exists(fpath):
        with open(fpath) as f: return json.load(f)
    return None

def get_all_news():
    news = []
    if os.path.exists(RESEARCH_DIR):
        for ticker in os.listdir(RESEARCH_DIR):
            tdir = os.path.join(RESEARCH_DIR, ticker)
            if not os.path.isdir(tdir): continue
            for fn in sorted(os.listdir(tdir), reverse=True):
                if not fn.endswith('.json') or 'trigger' in fn: continue
                try:
                    with open(os.path.join(tdir, fn)) as f: r = json.load(f)
                    date = fn.replace('.json','')
                    if r.get('catalyst'):
                        news.append({'ticker': ticker, 'headline': r['catalyst'], 'type': 'catalyst', 'verdict': r.get('verdict',''), 'date': date, 'source': 'Stock Scout'})
                    if r.get('sentiment'):
                        news.append({'ticker': ticker, 'headline': r['sentiment'], 'type': 'sentiment', 'date': date, 'source': 'Stock Scout'})
                except: pass
    if os.path.exists(DB_PATH):
        try:
            with db() as con:
                rows = con.execute("SELECT ticker, news, first_seen FROM candidates WHERE news IS NOT NULL ORDER BY first_seen DESC LIMIT 30").fetchall()
                for r in rows:
                    if r['news'] and len(r['news']) > 10:
                        news.append({'ticker': r['ticker'], 'headline': r['news'], 'type': 'scanner', 'date': r['first_seen'], 'source': 'EODHD'})
        except: pass
    news.sort(key=lambda x: x.get('date',''), reverse=True)
    return news

def get_candidates():
    if os.path.exists(DB_PATH):
        try:
            with db() as con:
                rows = con.execute("""SELECT ticker,name,price,gap_pct,relvol,float_m,news,first_seen,status,
                    scout_status,scan_date,former_momo,squeeze_5m,squeeze_10m,avgvol_1d,avgvol_200d,volume
                    FROM candidates ORDER BY first_seen DESC LIMIT 100""").fetchall()
                return {r['ticker']: dict(r) for r in rows}
        except: pass
    return {}

def get_history(days=7):
    if os.path.exists(DB_PATH):
        try:
            with db() as con:
                cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')
                rows = con.execute("""SELECT ticker,name,price,gap_pct,relvol,float_m,news,first_seen,status,
                    scout_status,scan_date,former_momo,squeeze_5m,squeeze_10m,avgvol_1d,avgvol_200d,volume
                    FROM candidates WHERE scan_date >= ? ORDER BY first_seen DESC""", (cutoff,)).fetchall()
                return [dict(r) for r in rows]
        except: pass
    return []

def update_daily_pnl(trade_date, pnl_amount):
    con = db()
    rows = con.execute("SELECT pnl FROM trades WHERE status='closed' AND date(exit_time)=?", (trade_date,)).fetchall()
    if not rows:
        con.execute("DELETE FROM daily_pnl WHERE date=?", (trade_date,))
        con.commit(); con.close(); return
    pnls = [r['pnl'] for r in rows if r['pnl'] is not None]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    con.execute("""INSERT OR REPLACE INTO daily_pnl (date, gross_pnl, num_trades, num_wins, num_losses, best_trade, worst_trade)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (trade_date, sum(pnls), len(pnls), len(wins), len(losses), max(pnls) if pnls else 0, min(pnls) if pnls else 0))
    con.commit(); con.close()


# ══════════════════════════════════════════════════════════════════════════
# NATIVE SCANNER — Ross Cameron 5 Pillars
# ══════════════════════════════════════════════════════════════════════════

_scan_results = {}          # { scanner_id: [stock, ...] }
_scan_status = {
    "five_pillars": {"last_run": None, "running": False, "count": 0, "error": None},
    "squeeze":       {"last_run": None, "running": False, "count": 0, "error": None},
    "former_momo":   {"last_run": None, "running": False, "count": 0, "error": None},
}
_scan_lock = threading.Lock()

AV_KEY_PATH = os.path.expanduser("~/.secrets/alphavantage-api")
_AV_KEY = None
def _av_key():
    global _AV_KEY
    if _AV_KEY is None and os.path.exists(AV_KEY_PATH):
        _AV_KEY = open(AV_KEY_PATH).read().strip()
    return _AV_KEY

def _get_finviz_tickers():
    """
    Query Finviz for US stocks: price $1-20, up 10%+, relVol >5.
    Uses Performance view (has Rel Volume) + Ownership view (has Float).
    Change is decimal (0.36 = 36%), Rel Volume is float multiplier.
    """
    FILTERS = {
        'Price': '$1 to $20',
        'Change': 'Up 10%',
        'Relative Volume': 'Over 5',
        'Country': 'USA',
    }
    try:
        # Performance view: has Rel Volume, Avg Volume, Change, Price
        from finvizfinance.screener.performance import Performance
        perf = Performance()
        perf.set_filter(filters_dict=FILTERS)
        df_perf = perf.screener_view(verbose=0)

        # Ownership view: has Float, Short Float, Avg Volume
        from finvizfinance.screener.ownership import Ownership
        own = Ownership()
        own.set_filter(filters_dict=FILTERS)
        df_own = own.screener_view(verbose=0)

        if df_perf is None or df_perf.empty:
            return _get_finviz_raw()

        # Build float map from ownership view
        float_map = {}
        if df_own is not None and not df_own.empty:
            for _, row in df_own.iterrows():
                ticker = str(row.get('Ticker', ''))
                try:
                    f = row.get('Float')
                    if f is not None and f != '' and str(f) not in ('nan', ''):
                        float_map[ticker] = float(f) / 1_000_000  # shares → millions
                except:
                    pass

        rows = []
        for _, row in df_perf.iterrows():
            try:
                ticker = str(row.get('Ticker', ''))
                price = float(row.get('Price', 0) or 0)
                # Change is decimal: 0.363 → 36.3%
                change_raw = row.get('Change', 0)
                gap_pct = float(change_raw or 0) * 100
                # Rel Volume is a float multiplier
                rv_raw = row.get('Rel Volume', 0)
                relvol = float(rv_raw or 0)
                vol_raw = row.get('Volume', 0)
                volume = float(vol_raw or 0)
                avg_vol_raw = row.get('Avg Volume', 0)
                avg_volume = float(avg_vol_raw or 0)
                name = ''
                # Float from ownership view (shares → millions)
                float_m = float_map.get(ticker)

                rows.append({
                    'ticker': ticker,
                    'name': name,
                    'price': price,
                    'gap_pct': gap_pct,
                    'relvol': relvol,
                    'volume': volume,
                    'avgvol_200d': avg_volume,
                    'float_m_finviz': float_m,  # pre-fetched float (may be None)
                })
            except Exception as ex:
                rows.append({'ticker': str(row.get('Ticker','')), 'name': '', 'price': 0,
                             'gap_pct': 0, 'relvol': 0, 'volume': 0, 'float_m_finviz': None})

        print(f"[Scanner] Finviz: {len(rows)} tickers, float_map: {len(float_map)}")
        return rows

    except Exception as e:
        print(f"[Scanner] Finviz error: {e}")
        import traceback; traceback.print_exc()
        return _get_finviz_raw()

def _get_finviz_raw():
    """Fallback raw HTML scrape from Finviz"""
    params = {'v': '111', 'f': 'geo_usa,price_u20,price_o1,ch_u10,relvol_o5', 'o': '-change'}
    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
    try:
        r = requests.get("https://finviz.com/screener.ashx", params=params, headers=headers, timeout=15)
        tickers = []
        for line in r.text.split('\n'):
            if 'screener-link-primary' in line:
                s = line.find('>') + 1
                e = line.find('<', s)
                t = line[s:e].strip()
                if t and len(t) <= 5 and t.replace('.','').isalpha():
                    tickers.append(t)
        tickers = list(dict.fromkeys(tickers))
        return [{'ticker': t, 'name': '', 'price': 0, 'gap_pct': 0, 'relvol': 0, 'volume': 0} for t in tickers]
    except Exception as e:
        print(f"[Scanner] Finviz raw error: {e}")
        return []

def _check_float_and_stats(ticker):
    """Get float + volume stats via yfinance"""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info
        float_shares = info.get('floatShares') or info.get('sharesFloat')
        float_m = float_shares / 1_000_000 if float_shares else None
        avg_vol = info.get('averageVolume') or info.get('averageDailyVolume10Day')
        avg_vol_200d = info.get('averageVolume10days') or info.get('averageVolume')
        # Current day volume
        today_vol = info.get('regularMarketVolume') or info.get('volume')
        # 10-day avg for relvol calc
        avg10 = info.get('averageDailyVolume10Day') or info.get('averageVolume10days')
        relvol = (today_vol / avg10) if (today_vol and avg10 and avg10 > 0) else None
        return {
            'float_m': float_m,
            'avgvol_1d': float(today_vol) if today_vol else None,
            'avgvol_200d': float(avg_vol) if avg_vol else None,
            'relvol_yf': relvol,
        }
    except Exception as e:
        return {'float_m': None, 'avgvol_1d': None, 'avgvol_200d': None, 'relvol_yf': None}

def _check_news_av(ticker):
    """Check EODHD for news today (replaces Alpha Vantage — no rate limits on our plan)"""
    try:
        key_path = os.path.expanduser("~/.secrets/eodhd-api")
        if not os.path.exists(key_path):
            return False, ''
        key = open(key_path).read().strip()
        today = datetime.utcnow().strftime('%Y-%m-%d')
        r = requests.get(
            f"https://eodhd.com/api/news",
            params={'s': f"{ticker}.US", 'limit': 5, 'api_token': key, 'fmt': 'json', 'from': today},
            timeout=8
        )
        if r.status_code == 200:
            items = r.json()
            if items and isinstance(items, list):
                return True, items[0].get('title', '')[:200]
        return False, ''
    except:
        return False, ''

def _upsert_candidate(con, data):
    """Insert or update a candidate row"""
    now = _now()
    today = _today()
    ticker = data['ticker']
    existing = con.execute("SELECT id, first_seen FROM candidates WHERE ticker=?", (ticker,)).fetchone()
    if existing:
        con.execute("""UPDATE candidates SET
            name=COALESCE(?, name), price=COALESCE(?, price), gap_pct=COALESCE(?, gap_pct),
            relvol=COALESCE(?, relvol), float_m=COALESCE(?, float_m),
            news=COALESCE(?, news), scan_date=?, last_updated=?,
            former_momo=COALESCE(?, former_momo),
            squeeze_5m=COALESCE(?, squeeze_5m), squeeze_10m=COALESCE(?, squeeze_10m),
            avgvol_1d=COALESCE(?, avgvol_1d), avgvol_200d=COALESCE(?, avgvol_200d),
            volume=COALESCE(?, volume)
            WHERE ticker=?""",
            (data.get('name'), data.get('price'), data.get('gap_pct'), data.get('relvol'),
             data.get('float_m'), data.get('news'), today, now,
             data.get('former_momo'), data.get('squeeze_5m'), data.get('squeeze_10m'),
             data.get('avgvol_1d'), data.get('avgvol_200d'), data.get('volume'), ticker))
    else:
        con.execute("""INSERT INTO candidates
            (ticker, name, price, gap_pct, relvol, float_m, news, scan_date, first_seen, last_updated,
             former_momo, squeeze_5m, squeeze_10m, avgvol_1d, avgvol_200d, volume)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ticker, data.get('name',''), data.get('price',0), data.get('gap_pct',0),
             data.get('relvol',0), data.get('float_m'), data.get('news',''),
             today, now, now,
             data.get('former_momo', 0), data.get('squeeze_5m', 0),
             data.get('squeeze_10m', 0), data.get('avgvol_1d'), data.get('avgvol_200d'),
             data.get('volume')))

def run_five_pillars_scan():
    """
    Ross Cameron 5 Pillars scanner.
    Returns dict keyed by scanner_id with lists of stock dicts.
    Also persists results to candidates DB.
    """
    _scan_status['five_pillars']['running'] = True
    _scan_status['five_pillars']['error'] = None
    results = {
        'lf_high_relvol': [],
        'lf_med_relvol': [],
        'lf_high_relvol_20': [],
        'gainers': [],
        'relvol': [],
    }
    try:
        print(f"[FivePillars] Starting scan at {datetime.utcnow().strftime('%H:%M:%S UTC')}")
        raw = _get_finviz_tickers()
        print(f"[FivePillars] Finviz returned {len(raw)} tickers")

        con = db()
        av_calls = 0

        for item in raw[:25]:  # Cap at 25 to avoid rate limits
            ticker = item['ticker']
            try:
                # Use Finviz float if available, fallback to yfinance
                float_m_finviz = item.get('float_m_finviz')
                if float_m_finviz is not None:
                    stats = {'float_m': float_m_finviz, 'avgvol_1d': item.get('volume'), 'avgvol_200d': item.get('avgvol_200d'), 'relvol_yf': None}
                else:
                    stats = _check_float_and_stats(ticker)
                float_m = stats.get('float_m')
                relvol = item.get('relvol') or stats.get('relvol_yf') or 0
                price = item.get('price') or 0
                gap_pct = item.get('gap_pct') or 0

                # Check news (AV rate limit: ~5 calls/min on free tier)
                has_news, headline = False, ''
                if av_calls < 15:
                    has_news, headline = _check_news_av(ticker)
                    av_calls += 1
                    time.sleep(1.3)  # Respect AV rate limit

                candidate = {
                    'ticker': ticker,
                    'name': item.get('name', ''),
                    'price': price,
                    'gap_pct': gap_pct,
                    'relvol': relvol,
                    'float_m': float_m,
                    'news': headline if has_news else '',
                    'avgvol_1d': stats.get('avgvol_1d'),
                    'avgvol_200d': stats.get('avgvol_200d'),
                    'volume': item.get('volume'),
                    'has_news': has_news,
                }

                # Tag with scanner IDs (RC 5 Pillars requires float <10M + news)
                # Low float (<10M)
                is_low_float = float_m is not None and float_m < 10
                passes_5_pillars = (
                    1 <= price <= 20 and
                    gap_pct >= 10 and
                    relvol >= 5 and
                    is_low_float and
                    has_news
                )
                scanner_tags = []
                if is_low_float and relvol >= 5 and 1 <= price <= 20 and gap_pct >= 10:
                    scanner_tags.append('lf_high_relvol')
                if is_low_float and 3 <= relvol < 5 and 1 <= price <= 20 and gap_pct >= 10:
                    scanner_tags.append('lf_med_relvol')
                if is_low_float and relvol >= 5 and price > 20 and gap_pct >= 10:
                    scanner_tags.append('lf_high_relvol_20')
                if gap_pct > 0:
                    scanner_tags.append('gainers')
                scanner_tags.append('relvol')  # All in relvol list

                candidate['scanner_tags'] = scanner_tags
                candidate['passes_5_pillars'] = passes_5_pillars

                # Persist to DB
                _upsert_candidate(con, candidate)

                # Add to results
                for tag in scanner_tags:
                    if tag in results:
                        results[tag].append(candidate)

            except Exception as e:
                print(f"[FivePillars] Error processing {ticker}: {e}")
                continue

        con.commit()
        con.close()

        # Sort each bucket
        results['lf_high_relvol'].sort(key=lambda x: x.get('relvol', 0), reverse=True)
        results['lf_med_relvol'].sort(key=lambda x: x.get('relvol', 0), reverse=True)
        results['lf_high_relvol_20'].sort(key=lambda x: x.get('relvol', 0), reverse=True)
        results['gainers'].sort(key=lambda x: x.get('gap_pct', 0), reverse=True)
        results['relvol'].sort(key=lambda x: x.get('relvol', 0), reverse=True)

        total = sum(len(v) for v in results.values())
        print(f"[FivePillars] Done — {len(raw)} scanned, results: lf_high={len(results['lf_high_relvol'])}, gainers={len(results['gainers'])}")

        with _scan_lock:
            _scan_results.update(results)
            _scan_status['five_pillars']['last_run'] = _now()
            _scan_status['five_pillars']['count'] = total
            _scan_status['five_pillars']['running'] = False

        return results

    except Exception as e:
        print(f"[FivePillars] Scan error: {e}")
        _scan_status['five_pillars']['error'] = str(e)
        _scan_status['five_pillars']['running'] = False
        return results

def run_squeeze_scan():
    """
    Squeeze scanner: checks 1-min yfinance data for current candidates.
    Detects: up 5% in last 5min, up 10% in last 10min.
    Returns dict with squeeze_5_5 and squeeze_10_10 buckets.
    """
    _scan_status['squeeze']['running'] = True
    _scan_status['squeeze']['error'] = None
    results = {'squeeze_5_5': [], 'squeeze_10_10': []}
    try:
        import yfinance as yf
        import pandas as pd

        # Get current candidates from DB (today's + recent)
        con = db()
        rows = con.execute("""SELECT ticker, name, price, float_m, relvol, gap_pct, news, former_momo
            FROM candidates WHERE scan_date >= ? ORDER BY last_updated DESC LIMIT 50""",
            (_today(),)).fetchall()
        candidates = [dict(r) for r in rows]
        con.close()

        if not candidates:
            # Fallback: get from in-memory results
            seen = set()
            for stocks in _scan_results.values():
                for s in stocks:
                    if s['ticker'] not in seen:
                        candidates.append(s)
                        seen.add(s['ticker'])

        print(f"[Squeeze] Checking {len(candidates)} tickers for squeeze")
        con = db()

        for cand in candidates[:30]:
            ticker = cand['ticker']
            try:
                df = yf.download(ticker, period='1d', interval='1m', progress=False, auto_adjust=True)
                if df is None or len(df) < 11:
                    continue

                closes = df['Close'].values.flatten().tolist()
                current = float(closes[-1]) if closes else 0
                if current <= 0:
                    continue

                # 5-min change: close[-1] vs close[-6]
                if len(closes) >= 6:
                    price_5m_ago = float(closes[-6])
                    change_5m = ((current - price_5m_ago) / price_5m_ago * 100) if price_5m_ago > 0 else 0
                else:
                    change_5m = 0

                # 10-min change: close[-1] vs close[-11]
                if len(closes) >= 11:
                    price_10m_ago = float(closes[-11])
                    change_10m = ((current - price_10m_ago) / price_10m_ago * 100) if price_10m_ago > 0 else 0
                else:
                    change_10m = 0

                # Volume in last 5 min vs avg 5-min volume
                vols = df['Volume'].values.flatten().tolist()
                recent_vol = sum(vols[-5:]) if len(vols) >= 5 else 0
                avg_5m_vol = (sum(vols[:-5]) / max(len(vols) - 5, 1)) * 5 if len(vols) > 5 else recent_vol
                vol_burst = (recent_vol / avg_5m_vol) if avg_5m_vol > 0 else 1.0

                # Update DB
                con.execute("""UPDATE candidates SET squeeze_5m=?, squeeze_10m=?, price=?, last_updated=?
                    WHERE ticker=?""", (round(change_5m, 2), round(change_10m, 2), round(current, 2), _now(), ticker))

                stock = dict(cand)
                stock['price'] = round(current, 2)
                stock['squeeze_5m'] = round(change_5m, 2)
                stock['squeeze_10m'] = round(change_10m, 2)
                stock['vol_burst_5m'] = round(vol_burst, 1)

                if change_5m >= 5:
                    results['squeeze_5_5'].append(stock)
                if change_10m >= 10:
                    results['squeeze_10_10'].append(stock)

            except Exception as e:
                print(f"[Squeeze] Error {ticker}: {e}")
                continue

        con.commit()
        con.close()

        results['squeeze_5_5'].sort(key=lambda x: x.get('squeeze_5m', 0), reverse=True)
        results['squeeze_10_10'].sort(key=lambda x: x.get('squeeze_10m', 0), reverse=True)

        print(f"[Squeeze] Done — squeeze_5_5: {len(results['squeeze_5_5'])}, squeeze_10_10: {len(results['squeeze_10_10'])}")

        with _scan_lock:
            _scan_results.update(results)
            _scan_status['squeeze']['last_run'] = _now()
            _scan_status['squeeze']['count'] = len(results['squeeze_5_5']) + len(results['squeeze_10_10'])
            _scan_status['squeeze']['running'] = False

        return results

    except Exception as e:
        print(f"[Squeeze] Scan error: {e}")
        _scan_status['squeeze']['error'] = str(e)
        _scan_status['squeeze']['running'] = False
        return results

def run_former_momo_scan():
    """
    Former Momo scanner: checks 12-month daily history for stocks
    that previously had a 20%+ day on high volume.
    Updates former_momo flag in DB and returns matches.
    """
    _scan_status['former_momo']['running'] = True
    _scan_status['former_momo']['error'] = None
    results = {'former_momo': []}
    try:
        import yfinance as yf
        import numpy as np

        # Check all candidates from last 30 days
        con = db()
        cutoff = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')
        rows = con.execute("""SELECT ticker, name, price, float_m, relvol, gap_pct, news
            FROM candidates WHERE scan_date >= ? ORDER BY scan_date DESC LIMIT 80""",
            (cutoff,)).fetchall()
        candidates = [dict(r) for r in rows]
        con.close()

        print(f"[FormerMomo] Checking {len(candidates)} tickers for 12-month history")
        con = db()

        for cand in candidates:
            ticker = cand['ticker']
            try:
                # Get 12-month daily data
                df = yf.download(ticker, period='1y', interval='1d', progress=False, auto_adjust=True)
                if df is None or len(df) < 30:
                    continue

                closes = df['Close'].values.flatten()
                vols = df['Volume'].values.flatten()

                # Look for days with 20%+ move on high volume
                is_momo = False
                best_run_pct = 0.0
                for i in range(1, len(closes)):
                    if closes[i-1] <= 0:
                        continue
                    daily_chg = (float(closes[i]) - float(closes[i-1])) / float(closes[i-1]) * 100
                    # High volume = at least 3x avg volume
                    avg_vol = float(np.mean(vols[max(0,i-20):i])) if i > 0 else 0
                    high_vol = vols[i] > avg_vol * 3 if avg_vol > 0 else False
                    if daily_chg >= 20 and high_vol:
                        is_momo = True
                        best_run_pct = max(best_run_pct, daily_chg)

                # Update DB
                con.execute("UPDATE candidates SET former_momo=? WHERE ticker=?",
                    (1 if is_momo else 0, ticker))

                if is_momo:
                    stock = dict(cand)
                    stock['former_momo'] = 1
                    stock['best_momo_pct'] = round(best_run_pct, 1)
                    results['former_momo'].append(stock)
                    print(f"[FormerMomo] {ticker} ✅ best run: +{best_run_pct:.1f}%")

            except Exception as e:
                print(f"[FormerMomo] Error {ticker}: {e}")
                continue

        con.commit()
        con.close()

        results['former_momo'].sort(key=lambda x: x.get('best_momo_pct', 0), reverse=True)
        print(f"[FormerMomo] Done — {len(results['former_momo'])} former momo stocks found")

        with _scan_lock:
            _scan_results.update(results)
            _scan_status['former_momo']['last_run'] = _now()
            _scan_status['former_momo']['count'] = len(results['former_momo'])
            _scan_status['former_momo']['running'] = False

        return results

    except Exception as e:
        print(f"[FormerMomo] Scan error: {e}")
        _scan_status['former_momo']['error'] = str(e)
        _scan_status['former_momo']['running'] = False
        return results

def _is_market_hours():
    """True during extended market hours (4am-5pm ET)."""
    now_utc = datetime.now(timezone.utc)
    # ET = UTC-4 (EDT) or UTC-5 (EST)
    # Approximate: 08:00-21:00 UTC covers 4am-5pm ET
    hour = now_utc.hour
    return 8 <= hour <= 21 and now_utc.weekday() < 5  # Mon-Fri

def _background_scanner():
    """Background thread: run scans on schedule."""
    print("[Scanner] Background scanner thread started")
    last_five_pillars = 0
    last_squeeze = 0
    last_former_momo = 0

    # Initial delay to let server start up
    time.sleep(10)

    while True:
        try:
            now = time.time()
            in_market = _is_market_hours()

            # Five pillars: every 60s during market hours, every 5min otherwise
            fp_interval = 60 if in_market else 300
            if now - last_five_pillars >= fp_interval:
                if not _scan_status['five_pillars']['running']:
                    threading.Thread(target=run_five_pillars_scan, daemon=True).start()
                    last_five_pillars = now

            # Squeeze: every 30s during market hours only
            if in_market and now - last_squeeze >= 30:
                if not _scan_status['squeeze']['running']:
                    threading.Thread(target=run_squeeze_scan, daemon=True).start()
                    last_squeeze = now

            # Former momo: every 15 minutes (slow, 12-month history lookups)
            if now - last_former_momo >= 900:
                if not _scan_status['former_momo']['running']:
                    threading.Thread(target=run_former_momo_scan, daemon=True).start()
                    last_former_momo = now

            time.sleep(5)

        except Exception as e:
            print(f"[Scanner] Background loop error: {e}")
            time.sleep(30)


# ── HTTP Handler ─────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    def send_json(self, data, code=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0: return {}
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        p = self.path.split('?')[0].strip('/')
        parts = p.split('/')

        if parts[0] == 'health':
            try:
                health_file = '/home/pai-server/trading/system-health.json'
                if os.path.exists(health_file):
                    with open(health_file) as f:
                        data = json.load(f)
                    hb_file = '/home/pai-server/trading/watchdog-heartbeat.json'
                    if os.path.exists(hb_file):
                        with open(hb_file) as hf:
                            hb = json.load(hf)
                        last_hb = datetime.fromisoformat(hb.get('timestamp', '2000-01-01').replace('Z', '+00:00'))
                        now_utc = datetime.now(timezone.utc)
                        secs_since = (now_utc - last_hb).total_seconds()
                        data['watchdog_ok'] = secs_since < 120
                        data['watchdog_last_seen'] = hb.get('timestamp')
                    return self.send_json(data)
                else:
                    return self.send_json({"overall": "unknown", "error": "health file not found"}, 503)
            except Exception as e:
                return self.send_json({"overall": "error", "error": str(e)}, 500)

        # ── Native Scanner endpoints ──────────────────────────────────────
        if parts[0] == 'scan':
            sub = parts[1] if len(parts) > 1 else 'results'

            if sub == 'five-pillars':
                # Trigger scan in background and return current cached results
                if not _scan_status['five_pillars']['running']:
                    threading.Thread(target=run_five_pillars_scan, daemon=True).start()
                with _scan_lock:
                    current = dict(_scan_results)
                return self.send_json({
                    'status': _scan_status['five_pillars'],
                    'results': {k: current.get(k, []) for k in ['lf_high_relvol', 'lf_med_relvol', 'lf_high_relvol_20', 'gainers', 'relvol']},
                    'candidates': get_candidates(),
                })

            if sub == 'squeeze':
                # Trigger squeeze scan and return results
                if not _scan_status['squeeze']['running']:
                    threading.Thread(target=run_squeeze_scan, daemon=True).start()
                with _scan_lock:
                    current = dict(_scan_results)
                return self.send_json({
                    'status': _scan_status['squeeze'],
                    'results': {k: current.get(k, []) for k in ['squeeze_5_5', 'squeeze_10_10']},
                })

            if sub == 'former-momo':
                # Trigger former momo scan and return results
                if not _scan_status['former_momo']['running']:
                    threading.Thread(target=run_former_momo_scan, daemon=True).start()
                with _scan_lock:
                    current = dict(_scan_results)
                return self.send_json({
                    'status': _scan_status['former_momo'],
                    'results': {'former_momo': current.get('former_momo', [])},
                })

            if sub == 'results':
                # Return all cached scan results
                with _scan_lock:
                    current = dict(_scan_results)
                return self.send_json({
                    'status': _scan_status,
                    'results': current,
                    'market_hours': _is_market_hours(),
                    'timestamp': _now(),
                })

            if sub == 'status':
                return self.send_json({
                    'status': _scan_status,
                    'market_hours': _is_market_hours(),
                    'result_counts': {k: len(v) for k, v in _scan_results.items()},
                })

        if parts[0] == 'research' and len(parts) >= 2:
            ticker = parts[1].upper()
            date = parts[2] if len(parts) > 2 and parts[2] != 'latest' else None
            r = get_research(ticker, date)
            return self.send_json(r or {}, 200 if r else 404)
        if parts[0] == 'news':
            return self.send_json(get_all_news())
        if parts[0] == 'candidates':
            if len(parts) > 1 and parts[1] == 'history':
                return self.send_json(get_history(7))
            return self.send_json(get_candidates())
        if parts[0] == 'history':
            if len(parts) > 1 and parts[1] == 'month':
                return self.send_json(get_history(30))
            return self.send_json(get_history(7))

        # Trades
        if parts[0] == 'trades':
            con = db()
            if len(parts) > 1 and parts[1] == 'open':
                rows = con.execute("SELECT * FROM trades WHERE status='open' ORDER BY entry_time DESC").fetchall()
                con.close(); return self.send_json([dict(r) for r in rows])
            if len(parts) > 1 and parts[1] == 'pnl':
                cutoff = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')
                rows = con.execute("SELECT * FROM daily_pnl WHERE date >= ? ORDER BY date DESC", (cutoff,)).fetchall()
                all_closed = con.execute("SELECT pnl, pnl_pct FROM trades WHERE status='closed'").fetchall()
                total_pnl = sum(r['pnl'] for r in all_closed if r['pnl'])
                total_trades = len(all_closed)
                total_wins = len([r for r in all_closed if r['pnl'] and r['pnl'] > 0])
                starting_balance = float(get_setting('starting_balance', '600'))
                con.close()
                return self.send_json({"daily": [dict(r) for r in rows], "total_pnl": total_pnl, "total_trades": total_trades, "total_wins": total_wins, "win_rate": (total_wins/total_trades*100) if total_trades>0 else 0, "starting_balance": starting_balance})
            cutoff = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')
            rows = con.execute("SELECT * FROM trades WHERE entry_time >= ? OR status='open' ORDER BY entry_time DESC", (cutoff,)).fetchall()
            con.close(); return self.send_json([dict(r) for r in rows])

        # Alpaca
        if parts[0] == 'alpaca':
            if len(parts) > 1 and parts[1] == 'account':
                acct = rc_alpaca.get_account()
                if isinstance(acct, dict):
                    acct['starting_balance'] = float(get_setting('starting_balance', '600'))
                    acct['_mode'] = rc_alpaca.get_mode()
                return self.send_json(acct)
            if len(parts) > 1 and parts[1] == 'positions':
                return self.send_json(rc_alpaca.get_positions())
            if len(parts) > 1 and parts[1] == 'orders':
                return self.send_json(rc_alpaca.get_orders())
            if len(parts) > 1 and parts[1] == 'mode':
                return self.send_json({"mode": rc_alpaca.get_mode()})
            if len(parts) > 1 and parts[1] == 'configured':
                return self.send_json({"configured": rc_alpaca.is_configured(), "mode": rc_alpaca.get_mode()})

        # Settings
        if parts[0] == 'settings':
            if len(parts) > 1 and parts[1] == 'api-status':
                result = {}
                for api in ['eodhd', 'alpaca_paper', 'alpaca_live', 'alphavantage']:
                    result[api] = test_api(api)
                return self.send_json(result)
            return self.send_json(get_all_settings())

        # Backtest
        if parts[0] == 'backtest':
            global _backtest_running, _backtest_progress
            if len(parts) > 1 and parts[1] == 'run':
                if _backtest_running:
                    return self.send_json({"status": "already_running", "progress": _backtest_progress})
                else:
                    def run_bt():
                        global _backtest_running, _backtest_progress
                        _backtest_running = True
                        try:
                            sys.path.insert(0, '/home/pai-server/bin')
                            if 'rc_backtest' in sys.modules:
                                import importlib; importlib.reload(sys.modules['rc_backtest'])
                            else:
                                import rc_backtest
                            sys.modules['rc_backtest'].run(_backtest_progress)
                        finally:
                            _backtest_running = False
                    threading.Thread(target=run_bt, daemon=True).start()
                    return self.send_json({"status": "started"})
            if len(parts) > 1 and parts[1] == 'status':
                return self.send_json({"running": _backtest_running, "progress": _backtest_progress})
            if len(parts) > 1 and parts[1] == 'results':
                con = db()
                rows = con.execute("SELECT * FROM backtest_results ORDER BY date, ticker").fetchall()
                con.close()
                return self.send_json([dict(r) for r in rows])
            if len(parts) > 1 and parts[1] == 'summary':
                con = db()
                try:
                    rows = con.execute("SELECT result, COUNT(*), SUM(pnl), AVG(pnl) FROM backtest_results GROUP BY result").fetchall()
                    total = con.execute("SELECT COUNT(*), SUM(pnl) FROM backtest_results WHERE result IN ('win','loss','timeout')").fetchone()
                    wins = con.execute("SELECT COUNT(*) FROM backtest_results WHERE result='win'").fetchone()[0]
                    trades = con.execute("SELECT COUNT(*) FROM backtest_results WHERE result IN ('win','loss','timeout')").fetchone()[0]
                    return self.send_json({
                        "total_candidates": con.execute("SELECT COUNT(*) FROM backtest_results").fetchone()[0],
                        "total_trades": trades,
                        "wins": wins,
                        "win_rate": round(wins/trades*100,1) if trades else 0,
                        "total_pnl": round((total[1] or 0), 2),
                        "by_result": [{"result":r[0],"count":r[1],"total_pnl":round(r[2] or 0,2),"avg_pnl":round(r[3] or 0,2)} for r in rows],
                        "running": _backtest_running,
                        "progress": _backtest_progress,
                    })
                finally:
                    con.close()

        self.send_response(404); self.end_headers()

    def do_POST(self):
        p = self.path.split('?')[0].strip('/')
        parts = p.split('/')

        # Manual trigger: POST /scan/five-pillars → run immediately, return results
        if parts[0] == 'scan':
            sub = parts[1] if len(parts) > 1 else ''
            if sub == 'five-pillars':
                results = run_five_pillars_scan()
                return self.send_json({'status': _scan_status['five_pillars'], 'results': results})
            if sub == 'squeeze':
                results = run_squeeze_scan()
                return self.send_json({'status': _scan_status['squeeze'], 'results': results})
            if sub == 'former-momo':
                results = run_former_momo_scan()
                return self.send_json({'status': _scan_status['former_momo'], 'results': results})

        if parts[0] == 'trades' and len(parts) == 1:
            body = self._read_body()
            ticker = body.get('ticker','').upper(); side = body.get('side','buy')
            qty = int(body.get('qty',0)); entry_price = float(body.get('entry_price',0))
            notes = body.get('notes',''); source = body.get('source','manual')
            alpaca_order_id = body.get('alpaca_order_id')
            if not ticker or qty<=0 or entry_price<=0:
                return self.send_json({"error": "Missing ticker, qty, or entry_price"}, 400)
            con = db()
            cur = con.execute("INSERT INTO trades (ticker,side,qty,entry_price,entry_time,status,notes,source,alpaca_order_id) VALUES (?,?,?,?,?,'open',?,?,?)",
                (ticker, side, qty, entry_price, _now(), notes, source, alpaca_order_id))
            tid = cur.lastrowid; con.commit()
            row = con.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone(); con.close()
            return self.send_json(dict(row), 201)

        if parts[0] == 'trades' and len(parts) == 3 and parts[2] == 'close':
            trade_id = int(parts[1]); body = self._read_body()
            exit_price = float(body.get('exit_price',0))
            if exit_price<=0: return self.send_json({"error": "Missing exit_price"}, 400)
            con = db(); trade = con.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
            if not trade: con.close(); return self.send_json({"error": "Trade not found"}, 404)
            t = dict(trade)
            if t['side']=='buy':
                pnl = (exit_price - t['entry_price'])*t['qty']; pnl_pct = ((exit_price - t['entry_price'])/t['entry_price'])*100
            else:
                pnl = (t['entry_price'] - exit_price)*t['qty']; pnl_pct = ((t['entry_price'] - exit_price)/t['entry_price'])*100
            exit_time = _now()
            con.execute("UPDATE trades SET exit_price=?,exit_time=?,status='closed',pnl=?,pnl_pct=? WHERE id=?",
                (exit_price, exit_time, round(pnl,2), round(pnl_pct,2), trade_id))
            con.commit(); update_daily_pnl(exit_time[:10], pnl)
            row = con.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone(); con.close()
            return self.send_json(dict(row))

        if parts[0] == 'alpaca' and len(parts)>1 and parts[1] == 'order':
            body = self._read_body(); ticker = body.get('ticker','').upper()
            side = body.get('side','buy'); qty = int(body.get('qty',0))
            if not ticker or qty<=0: return self.send_json({"error":"Missing ticker or qty"}, 400)
            result = rc_alpaca.submit_order(ticker, side, qty)
            if isinstance(result, dict) and result.get('id'):
                fp = float(result.get('filled_avg_price',0)) or float(body.get('entry_price',0))
                con = db()
                con.execute("INSERT INTO trades (ticker,side,qty,entry_price,entry_time,status,notes,source,alpaca_order_id) VALUES (?,?,?,?,?,'open',?,'alpaca',?)",
                    (ticker, side, qty, fp, _now(), f"Alpaca {rc_alpaca.get_mode()} order", result['id']))
                con.commit(); con.close()
            return self.send_json(result)

        if parts[0] == 'alpaca' and len(parts)>1 and parts[1] == 'mode':
            body = self._read_body(); mode = body.get('mode','paper')
            ok = rc_alpaca.set_mode(mode)
            return self.send_json({"mode": rc_alpaca.get_mode(), "switched": ok})

        if parts[0] == 'settings':
            body = self._read_body()
            save_settings(body)
            return self.send_json({"ok": True, "settings": get_all_settings()})

        self.send_response(404); self.end_headers()

    def log_message(self, *args): pass

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

init_tables()

# Start background scanner thread
_scanner_thread = threading.Thread(target=_background_scanner, daemon=True, name="rc-scanner")
_scanner_thread.start()

print(f"Research server on 0.0.0.0:{PORT}")
print(f"Scanner: five-pillars every 60s, squeeze every 30s, former-momo every 15min")
with ReusableTCPServer(("0.0.0.0", PORT), Handler) as httpd:
    httpd.serve_forever()
