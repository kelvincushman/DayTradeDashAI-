#!/usr/bin/env python3
"""Serves Stock Scout research + news + trades + Alpaca + settings for the dashboard."""
import http.server, socketserver, os, json, sqlite3, sys, urllib.request, urllib.error
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
    """)
    for k, v in DEFAULTS.items():
        row = c.execute("SELECT 1 FROM settings WHERE key=?", (k,)).fetchone()
        if not row:
            c.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (k, v))
    c.commit(); c.close()
    write_scanner_config()

# init_tables() moved to after all defs

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
            # Direct HTTP call using live credentials to avoid module cache issues
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
                rows = con.execute("SELECT ticker,name,price,gap_pct,relvol,float_m,news,first_seen,status,scout_status,scan_date,former_momo FROM candidates ORDER BY first_seen DESC LIMIT 100").fetchall()
                return {r['ticker']: dict(r) for r in rows}
        except: pass
    return {}

def get_history(days=7):
    if os.path.exists(DB_PATH):
        try:
            with db() as con:
                cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')
                rows = con.execute("SELECT ticker,name,price,gap_pct,relvol,float_m,news,first_seen,status,scout_status,scan_date,former_momo FROM candidates WHERE scan_date >= ? ORDER BY first_seen DESC", (cutoff,)).fetchall()
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

init_tables()

# ── HTTP Handler ─────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
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
                    import threading
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
                cols = [d[0] for d in rows[0].keys()] if rows else []
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

print(f"Research server on 0.0.0.0:{PORT}")
with ReusableTCPServer(("0.0.0.0", PORT), Handler) as httpd:
    httpd.serve_forever()
