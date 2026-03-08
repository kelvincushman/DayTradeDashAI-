#!/usr/bin/env python3
"""Ross Cameron Bull Flag Backtest Engine"""
import os, sys, json, sqlite3, time, urllib.request
from datetime import datetime, timedelta

DB_PATH = "/home/pai-server/trading/rc-scanner.db"

def init_table():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS backtest_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT, date TEXT, gap_pct REAL, float_m REAL, relvol REAL,
        entry REAL, stop REAL, target REAL, exit_price REAL, shares INTEGER,
        result TEXT, pnl REAL, rr REAL, entry_time TEXT,
        created_at TEXT
    )""")
    con.commit()
    con.close()

def get_intraday(ticker, date_str):
    key = open(os.path.expanduser('~/.secrets/eodhd-api')).read().strip()
    url = f'https://eodhd.com/api/intraday/{ticker}.US?interval=1m&api_token={key}&from={date_str}&to={date_str}&fmt=json'
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            bars = json.loads(r.read())
        et_bars = []
        for b in bars:
            ts = datetime.utcfromtimestamp(b['timestamp'])
            month = ts.month
            offset = 4 if 3 <= month <= 10 else 5
            et_hour = (ts.hour - offset) % 24
            et_min = ts.minute
            if (et_hour == 9 and et_min >= 30) or (et_hour == 10) or (et_hour == 11 and et_min <= 30):
                et_bars.append({
                    'datetime': f'{et_hour:02d}:{et_min:02d}',
                    'open': float(b['open']),
                    'high': float(b['high']),
                    'low': float(b['low']),
                    'close': float(b['close']),
                    'volume': int(b['volume']),
                })
        return et_bars
    except:
        return []

def find_bull_flag_entry(bars):
    if len(bars) < 6:
        return None
    open_price = bars[0]['open']
    surge_high = max(b['high'] for b in bars[:10])
    if (surge_high - open_price) / open_price < 0.03:
        return None
    surge_bar_idx = next((i for i, b in enumerate(bars[:10]) if b['high'] == surge_high), 0)
    pullback_bars = []
    for bar in bars[surge_bar_idx+1:surge_bar_idx+9]:
        if bar['close'] < bar['open']:
            pullback_bars.append(bar)
        else:
            break
    if len(pullback_bars) < 2:
        return None
    pullback_low = min(b['low'] for b in pullback_bars)
    surge_range = surge_high - open_price
    if pullback_low < open_price + (surge_range * 0.5):
        return None
    last_red_high = pullback_bars[-1]['high']
    entry_bar_idx = surge_bar_idx + 1 + len(pullback_bars)
    for bar in bars[entry_bar_idx:entry_bar_idx+5]:
        if bar['close'] > bar['open'] and bar['close'] > last_red_high:
            entry_price = bar['close'] + 0.02
            stop_price = pullback_low
            risk = entry_price - stop_price
            if risk <= 0 or risk > entry_price * 0.15:
                continue
            target_price = entry_price + (risk * 2)
            return entry_price, stop_price, target_price, bar['datetime']
    return None

def run(progress=None):
    if progress is None:
        progress = {"total": 0, "done": 0, "trades": 0}
    init_table()
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM backtest_results")
    con.commit()
    candidates = con.execute(
        "SELECT ticker, scan_date, gap_pct, float_m, relvol, price FROM candidates ORDER BY scan_date"
    ).fetchall()
    con.close()
    progress["total"] = len(candidates)
    progress["done"] = 0
    progress["trades"] = 0
    results = []
    for ticker, scan_date, gap_pct, float_m, relvol, price in candidates:
        bars = get_intraday(ticker, scan_date)
        progress["done"] += 1
        if not bars:
            r = {'ticker': ticker, 'date': scan_date, 'gap_pct': gap_pct, 'float_m': float_m, 'relvol': relvol, 'result': 'no_data', 'pnl': 0, 'rr': 0}
            results.append(r); _save_result(r); continue
        entry = find_bull_flag_entry(bars)
        if not entry:
            r = {'ticker': ticker, 'date': scan_date, 'gap_pct': gap_pct, 'float_m': float_m, 'relvol': relvol, 'result': 'no_setup', 'pnl': 0, 'rr': 0}
            results.append(r); _save_result(r); continue
        entry_price, stop_price, target_price, entry_time = entry
        risk_per_share = entry_price - stop_price
        shares = int(120 / entry_price)
        if shares < 1:
            r = {'ticker': ticker, 'date': scan_date, 'gap_pct': gap_pct, 'float_m': float_m, 'relvol': relvol, 'result': 'no_setup', 'pnl': 0, 'rr': 0}
            results.append(r); _save_result(r); continue
        hit_target = hit_stop = False; exit_price = None; entry_bar_found = False
        for bar in bars:
            if bar['datetime'] == entry_time: entry_bar_found = True; continue
            if not entry_bar_found: continue
            if bar['high'] >= target_price: exit_price = target_price; hit_target = True; break
            if bar['low'] <= stop_price: exit_price = stop_price; hit_stop = True; break
        if not exit_price: exit_price = bars[-1]['close']
        pnl = (exit_price - entry_price) * shares
        rr = (exit_price - entry_price) / risk_per_share if risk_per_share > 0 else 0
        result = {
            'ticker': ticker, 'date': scan_date, 'gap_pct': gap_pct, 'float_m': float_m, 'relvol': relvol,
            'entry': entry_price, 'stop': stop_price, 'target': target_price, 'exit_price': exit_price,
            'shares': shares, 'result': 'win' if hit_target else ('loss' if hit_stop else 'timeout'),
            'pnl': round(pnl, 2), 'rr': round(rr, 2), 'entry_time': entry_time
        }
        results.append(result); _save_result(result); progress["trades"] += 1
        time.sleep(0.5)
    print_summary(results)
    return results

def _save_result(r):
    con = sqlite3.connect(DB_PATH)
    con.execute("""INSERT INTO backtest_results 
        (ticker, date, gap_pct, float_m, relvol, entry, stop, target, exit_price, shares, result, pnl, rr, entry_time)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (r.get('ticker'), r.get('date'), r.get('gap_pct'), r.get('float_m'), r.get('relvol'),
         r.get('entry'), r.get('stop'), r.get('target'), r.get('exit_price'), r.get('shares'),
         r.get('result'), r.get('pnl',0), r.get('rr',0), r.get('entry_time')))
    con.commit(); con.close()

def print_summary(results):
    trades = [r for r in results if r['result'] in ('win','loss','timeout')]
    wins = [r for r in trades if r['result'] == 'win']
    losses = [r for r in trades if r['result'] in ('loss','timeout')]
    total_pnl = sum(r['pnl'] for r in trades)
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = sum(r['pnl'] for r in wins) / len(wins) if wins else 0
    avg_loss = sum(r['pnl'] for r in losses) / len(losses) if losses else 0
    print(f"\n{'='*50}")
    print("ROSS CAMERON BULL FLAG BACKTEST RESULTS")
    print(f"{'='*50}")
    print(f"Candidates scanned:  {len(results)}")
    print(f"Setups found:        {len(trades)}")
    print(f"Win rate:            {win_rate:.1f}%")
    print(f"Total P&L:           ${total_pnl:.2f}")
    print(f"Avg win:             ${avg_win:.2f}")
    print(f"Avg loss:            ${avg_loss:.2f}")
    loss_total = sum(r['pnl'] for r in losses)
    win_total = sum(r['pnl'] for r in wins)
    print(f"Profit factor:       {abs(win_total/loss_total):.2f}" if loss_total != 0 else "Profit factor: N/A")
    print(f"\nBy float range:")
    for frange, label in [((0,2),'<2M'), ((2,5),'2-5M'), ((5,10),'5-10M'), ((10,50),'10-50M')]:
        subset = [r for r in trades if r.get('float_m') and frange[0] <= r['float_m'] < frange[1]]
        if subset:
            sr = len([r for r in subset if r['result']=='win'])/len(subset)*100
            sp = sum(r['pnl'] for r in subset)
            print(f"  Float {label}: {len(subset)} trades, {sr:.0f}% WR, ${sp:.2f} P&L")

if __name__ == '__main__':
    run()
