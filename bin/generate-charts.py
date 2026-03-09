#!/usr/bin/env python3
"""
DayTradeDash Chart Generator
Renders ±10 bar windows around each trade entry as TradingView-style
dark theme charts for YOLOv8 training.

Sources:
  - TraderTom: all_trades.csv
  - Ross Cameron: (future)
  - School Run: (future)

Data source: EODHD intraday API (replaces yfinance — full history support)
"""

import os, sys, csv, json, sqlite3, time, math
import datetime as dt
from pathlib import Path
import requests
from functools import lru_cache
import pandas as pd
import numpy as np
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ── Config ──────────────────────────────────────────────────────────────────

OUTPUT_DIR  = Path('/mnt/ai_storage/models/daytrade-ai/trader_charts')
TRADES_CSV  = Path('/home/pai-server/.openclaw/workspace/projects/tradertom/all_trades.csv')
WINDOW      = 10          # bars each side of entry
IMG_W, IMG_H = 640, 480  # YOLO standard input size
MACD_PANE   = True        # render MACD in bottom 30%

# ── EODHD Config ─────────────────────────────────────────────────────────────

EODHD_KEY = open(os.path.expanduser('~/.secrets/eodhd-api')).read().strip()

# Instrument → EODHD symbol mapping
EODHD_MAP = {
    'DAX':    'GDAXI.INDX',
    'DOW':    'DJI.INDX',
    'NASDAQ': 'IXIC.INDX',
    'FTSE':   'FTSE.INDX',
    'SP500':  'GSPC.INDX',
    'GOLD':   'GC.COMM',
    'SILVER': 'SI.COMM',
    'OIL':    'CL.COMM',
}

# ── Theme Definitions ─────────────────────────────────────────────────────────

# TradingView dark theme colours
TV = dict(
    bg           = '#0f1320',
    panel_bg     = '#161b2e',
    up           = '#26a69a',     # TV default green
    down         = '#ef5350',     # TV default red
    wick_up      = '#26a69a',
    wick_down    = '#ef5350',
    vol_up       = '#26a69a66',   # green ~40% alpha
    vol_down     = '#ef535066',   # red ~40% alpha
    vol_sma      = '#ffffff55',   # white semi-transparent for vol SMA
    entry_line   = '#2196f3',     # blue
    win_line     = '#22c55e',     # green exit
    loss_line    = '#ef4444',     # red exit
    text         = '#9ca3af',
    grid         = '#1e2a4422',
    ema9         = '#f59e0b',     # orange
    ema20        = '#a855f7',     # purple
    ema200       = '#6b7280',     # grey
    vwap         = '#26a69a',     # teal
    # MACD 4-colour histogram
    macd_line    = '#2196f3',
    signal_line  = '#ff9800',
    hist_pos_up  = '#26a69a',     # bright green: positive AND rising
    hist_pos_dn  = '#a5d6a7',     # faded green:  positive AND falling
    hist_neg_up  = '#ffcdd2',     # faded red:    negative AND rising
    hist_neg_dn  = '#ef5350',     # bright red:   negative AND falling
)

TV_LIGHT = dict(
    bg           = '#ffffff',
    panel_bg     = '#f5f5f5',
    up           = '#26a69a',
    down         = '#ef5350',
    wick_up      = '#26a69a',
    wick_down    = '#ef5350',
    vol_up       = '#26a69a66',
    vol_down     = '#ef535066',
    vol_sma      = '#00000055',
    entry_line   = '#1565c0',
    win_line     = '#22c55e',
    loss_line    = '#ef4444',
    text         = '#333333',
    grid         = '#e0e0e044',
    ema9         = '#e65100',
    ema20        = '#7b1fa2',
    ema200       = '#9e9e9e',
    vwap         = '#00695c',
    macd_line    = '#1565c0',
    signal_line  = '#e65100',
    hist_pos_up  = '#26a69a',
    hist_pos_dn  = '#a5d6a7',
    hist_neg_up  = '#ffcdd2',
    hist_neg_dn  = '#ef5350',
)

# ── Data Fetching ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=50)
def fetch_bars_eodhd(instrument, trade_date_str, interval='1m'):
    """
    Fetch intraday bars from EODHD for a given instrument and date.
    NOTE: EODHD ignores from/to params — fetches full history, filters locally.
    Falls back to 5m if 1m returns empty for that date.
    Returns a DataFrame with OHLCV columns or None.
    """
    symbol = EODHD_MAP.get(instrument.upper())
    if not symbol:
        print(f'  No EODHD symbol mapping for: {instrument}')
        return None

    url = f'https://eodhd.com/api/intraday/{symbol}'
    params = {
        'interval':  interval,
        'api_token': EODHD_KEY,
        'fmt':       'json',
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            print(f'  EODHD HTTP {r.status_code} for {symbol}')
            return None
        data = r.json()
        if not data or not isinstance(data, list):
            return None

        df = pd.DataFrame(data)
        df['datetime'] = pd.to_datetime(df['datetime'])

        # Filter to the target trade date
        df = df[df['datetime'].dt.strftime('%Y-%m-%d') == trade_date_str]

        if df.empty and interval == '1m':
            return fetch_bars_eodhd(instrument, trade_date_str, '5m')

        if df.empty:
            return None

        df = df.set_index('datetime')
        df = df.rename(columns={
            'open':   'Open',
            'high':   'High',
            'low':    'Low',
            'close':  'Close',
            'volume': 'Volume',
        })
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]

    except Exception as e:
        print(f'  EODHD error {instrument} {trade_date_str}: {e}')
        return None

def find_entry_bar(df, entry_time_str, entry_price):
    """Find the bar index closest to entry time."""
    if df is None or df.empty:
        return None

    try:
        parts = entry_time_str.strip().split(':')
        h, m = int(parts[0]), int(parts[1])
    except Exception:
        return None

    best_idx = None
    best_diff = float('inf')
    for i, ts in enumerate(df.index):
        diff = abs((ts.hour - h) * 60 + (ts.minute - m))
        if diff < best_diff:
            best_diff = diff
            best_idx = i
        if diff == 0:
            break

    return best_idx

def extract_window(df, center_idx, window=10):
    """Extract +-window bars around center_idx."""
    start = max(0, center_idx - window)
    end   = min(len(df), center_idx + window + 1)
    return df.iloc[start:end], center_idx - start

# ── Indicators ────────────────────────────────────────────────────────────────

def calc_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def calc_vwap(df):
    """Simple session VWAP."""
    typical    = (df['High'] + df['Low'] + df['Close']) / 3
    cum_tp_vol = (typical * df['Volume']).cumsum()
    cum_vol    = df['Volume'].cumsum()
    with np.errstate(divide='ignore', invalid='ignore'):
        vwap = np.where(cum_vol > 0, cum_tp_vol / cum_vol, typical)
    return pd.Series(vwap, index=df.index)

def calc_macd(df, fast=12, slow=26, signal=9):
    close       = df['Close']
    ema_fast    = close.ewm(span=fast,   adjust=False).mean()
    ema_slow    = close.ewm(span=slow,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram

def vol_sma(volume_series, period=9):
    return volume_series.rolling(window=period, min_periods=1).mean()

# ── Chart Rendering ───────────────────────────────────────────────────────────

def render_chart(window_df, local_entry_idx, trade, output_path, theme=None):
    """
    Render a TradingView-style chart matching Ross Cameron's exact setup:
      Price pane (top ~70%):
        - Candlesticks
        - EMA 9 (orange), EMA 20 (purple), EMA 200 (grey dotted)
        - VWAP (teal dashed)
        - Volume bars at base of price pane (green/red, ~40% alpha)
        - Volume SMA-9 line overlaid on volume bars
      MACD pane (bottom ~30%):
        - MACD line (blue/teal) + Signal line (orange)
        - 4-colour histogram:
            bright green  = positive AND rising
            faded green   = positive AND falling
            faded red     = negative AND rising
            bright red    = negative AND falling
      Both dark (TV) and light (TV_LIGHT) themes generated per trade.
    """
    n = len(window_df)
    if n < 3:
        return False
    TVt = theme if theme is not None else TV

    # ── Layout ─────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(IMG_W / 100, IMG_H / 100), dpi=100)
    fig.patch.set_facecolor(TVt['bg'])

    if MACD_PANE:
        ax_price = fig.add_axes([0.05, 0.32, 0.93, 0.64])
        ax_macd  = fig.add_axes([0.05, 0.02, 0.93, 0.26])
    else:
        ax_price = fig.add_axes([0.05, 0.05, 0.93, 0.92])
        ax_macd  = None

    ax_price.set_facecolor(TVt['panel_bg'])

    opens  = window_df['Open'].values
    highs  = window_df['High'].values
    lows   = window_df['Low'].values
    closes = window_df['Close'].values
    vols   = window_df['Volume'].values if 'Volume' in window_df.columns else np.zeros(n)
    x      = np.arange(n)

    price_min   = lows.min()
    price_max   = highs.max()
    price_range = price_max - price_min or price_max * 0.01

    # ── Volume bars at base of price pane (bottom 15% of price range) ──────
    vol_max   = vols.max() if vols.max() > 0 else 1
    vol_scale = (price_range * 0.15) / vol_max

    for i in range(n):
        vc    = TVt['vol_up'] if closes[i] >= opens[i] else TVt['vol_down']
        bar_h = vols[i] * vol_scale
        rect  = plt.Rectangle((i - 0.35, price_min), 0.7, bar_h, color=vc, zorder=1)
        ax_price.add_patch(rect)

    # Volume SMA-9 line
    vsma = vol_sma(window_df['Volume'], 9).values * vol_scale
    ax_price.plot(x, price_min + vsma, color=TVt['vol_sma'],
                  linewidth=0.8, zorder=2)

    # ── Candlesticks ────────────────────────────────────────────────────────
    for i in range(n):
        c = TVt['up'] if closes[i] >= opens[i] else TVt['down']
        ax_price.plot([i, i], [lows[i], highs[i]], color=c, linewidth=0.8, zorder=3)
        body_h = abs(closes[i] - opens[i]) or (highs[i] - lows[i]) * 0.01
        body_y = min(opens[i], closes[i])
        rect   = plt.Rectangle((i - 0.35, body_y), 0.7, body_h, color=c, zorder=4)
        ax_price.add_patch(rect)

    # ── EMAs ────────────────────────────────────────────────────────────────
    close_s  = window_df['Close']
    ema9_v   = calc_ema(close_s,   9).values
    ema20_v  = calc_ema(close_s,  20).values
    ema200_v = calc_ema(close_s, 200).values

    ax_price.plot(x, ema9_v,   color=TVt['ema9'],   linewidth=0.9, zorder=5)
    ax_price.plot(x, ema20_v,  color=TVt['ema20'],  linewidth=0.9, zorder=5)
    ax_price.plot(x, ema200_v, color=TVt['ema200'], linewidth=0.8, linestyle=':', zorder=5)

    # ── VWAP ────────────────────────────────────────────────────────────────
    vwap_v = calc_vwap(window_df).values
    ax_price.plot(x, vwap_v, color=TVt['vwap'], linewidth=0.9, linestyle='--', zorder=5)

    # ── Entry vertical line ─────────────────────────────────────────────────
    ax_price.axvline(x=local_entry_idx, color=TVt['entry_line'],
                     linewidth=1.5, linestyle='--', alpha=0.9, zorder=6)

    # ── Exit price line ─────────────────────────────────────────────────────
    if trade.get('exit1') and float(trade.get('exit1') or 0) > 0:
        exit_p = float(trade['exit1'])
        lc     = TVt['win_line'] if trade['result'] == 'Win' else TVt['loss_line']
        ax_price.axhline(y=exit_p, color=lc, linewidth=1.0, linestyle=':', alpha=0.7, zorder=6)

    # ── Labels ──────────────────────────────────────────────────────────────
    result_colour = {'Win': '#22c55e', 'Loss': '#ef4444', 'BE': '#f59e0b'}.get(trade['result'], '#9ca3af')
    ax_price.text(0.02, 0.97,
                  f"{trade['instrument']} {trade['direction']} | {trade['result']}",
                  transform=ax_price.transAxes,
                  color=result_colour, fontsize=7, va='top', fontweight='bold')
    ax_price.text(0.02, 0.88,
                  f"Entry: {trade['entry']}  Exit: {trade.get('exit1', '-')}",
                  transform=ax_price.transAxes,
                  color=TVt['text'], fontsize=6, va='top')

    # ── Price axis styling ──────────────────────────────────────────────────
    ax_price.set_xlim(-0.5, n - 0.5)
    ax_price.set_ylim(price_min - price_range * 0.02, price_max + price_range * 0.05)
    ax_price.set_xticks([])
    ax_price.tick_params(colors=TVt['text'], labelsize=6)
    for spine in ax_price.spines.values():
        spine.set_edgecolor(TVt['grid'])
    ax_price.grid(axis='y', color=TVt['grid'], linewidth=0.5)

    # ── MACD pane ───────────────────────────────────────────────────────────
    if ax_macd is not None:
        macd_line, sig_line, histogram = calc_macd(window_df)
        hist_vals = histogram.values

        # 4-colour histogram — exact Ross Cameron logic
        for i in range(n):
            prev_h = hist_vals[i - 1] if i > 0 else hist_vals[i]
            h_val  = hist_vals[i]
            if h_val >= 0:
                hc = TVt['hist_pos_up'] if h_val >= prev_h else TVt['hist_pos_dn']
            else:
                hc = TVt['hist_neg_up'] if h_val > prev_h else TVt['hist_neg_dn']
            ax_macd.bar(i, h_val, color=hc, alpha=0.85, width=0.7, zorder=1)

        ax_macd.plot(x, macd_line.values, color=TVt['macd_line'],   linewidth=1.0, zorder=2)
        ax_macd.plot(x, sig_line.values,  color=TVt['signal_line'], linewidth=1.0, zorder=2)
        ax_macd.axhline(0, color=TVt['text'], linewidth=0.5, alpha=0.5)
        ax_macd.axvline(x=local_entry_idx, color=TVt['entry_line'],
                        linewidth=1.5, linestyle='--', alpha=0.7, zorder=3)

        ax_macd.set_facecolor(TVt['panel_bg'])
        ax_macd.set_xlim(-0.5, n - 0.5)
        ax_macd.set_xticks([])
        ax_macd.tick_params(colors=TVt['text'], labelsize=5)
        for spine in ax_macd.spines.values():
            spine.set_edgecolor(TVt['grid'])
        ax_macd.grid(axis='y', color=TVt['grid'], linewidth=0.4)
        ax_macd.text(0.02, 0.92, 'MACD(12,26,9)',
                     transform=ax_macd.transAxes,
                     color=TVt['text'], fontsize=5, va='top')

    plt.savefig(output_path, dpi=100, bbox_inches='tight',
                facecolor=TVt['bg'], edgecolor='none')
    plt.close(fig)
    return True

# ── YOLO Label Generation ─────────────────────────────────────────────────────

def make_yolo_label(result, direction, output_path):
    """
    Classes:
      9: tradertom_long_win   10: tradertom_long_loss
      11: tradertom_short_win  12: tradertom_short_loss
    """
    is_long = direction.strip().lower() == 'long'
    is_win  = result.strip() == 'Win'

    if is_long and is_win:       cls = 9
    elif is_long:                cls = 10
    elif not is_long and is_win: cls = 11
    else:                        cls = 12

    label_line = f'{cls} 0.500 0.350 1.000 0.680\n'
    label_path = str(output_path).replace('.png', '.txt')
    with open(label_path, 'w') as f:
        f.write(label_line)
    return label_path

# ── Main Pipeline ─────────────────────────────────────────────────────────────

def run_tradertom(limit=None, instruments=None):
    """Generate charts for all TraderTom trades."""
    instruments = instruments or ['DAX', 'DOW', 'FTSE', 'NASDAQ']

    out_base = OUTPUT_DIR / 'tradertom'
    for sub in ['images/train', 'images/val', 'images/test',
                'labels/train', 'labels/val', 'labels/test']:
        (out_base / sub).mkdir(parents=True, exist_ok=True)

    trades_path = TRADES_CSV
    if not trades_path.exists():
        trades_path = Path('/home/pai-server/openclaw-backup/openclaw/workspace/projects/tradertom/all_trades.csv')

    with open(trades_path) as f:
        trades = list(csv.DictReader(f))

    trades = [t for t in trades if t['product'] in instruments]
    if limit:
        trades = trades[:limit]

    print(f'Processing {len(trades)} TraderTom trades...')
    success, skipped, errors = 0, 0, 0

    for i, t in enumerate(trades):
        instrument = t['product']
        date_str   = t['date']
        time_str   = t.get('time', '').strip()
        direction  = t.get('direction', '').strip()
        result     = t.get('result', '').strip()
        entry      = t.get('entry', '').strip()

        if not all([date_str, time_str, direction, result, entry]):
            skipped += 1
            continue

        rng   = i % 20
        split = 'train' if rng < 16 else ('val' if rng < 19 else 'test')

        fname   = f"tom_{instrument}_{date_str}_{time_str.replace(':','')}_{result[:1]}_{i}.png"
        out_img = out_base / f'images/{split}/{fname}'

        if out_img.exists():
            success += 1
            continue

        # ── Fetch EODHD data ────────────────────────────────────────────────
        df = fetch_bars_eodhd(instrument, date_str)
        if df is None or df.empty:
            skipped += 1
            if i % 50 == 0:
                print(f'  [{i+1}/{len(trades)}] No data: {instrument} {date_str}')
            continue

        try:
            entry_price = float(entry)
        except Exception:
            skipped += 1
            continue

        entry_idx = find_entry_bar(df, time_str, entry_price)
        if entry_idx is None:
            skipped += 1
            continue

        window_df, local_idx = extract_window(df, entry_idx, WINDOW)
        if len(window_df) < 5:
            skipped += 1
            continue

        trade_meta = {
            'instrument': instrument,
            'direction':  direction,
            'result':     result,
            'entry':      entry,
            'exit1':      t.get('exit1', ''),
        }

        # ── Dark theme (primary) ────────────────────────────────────────────
        ok = render_chart(window_df, local_idx, trade_meta, str(out_img), theme=TV)
        if ok:
            make_yolo_label(result, direction, out_img)

            # ── Light theme version ─────────────────────────────────────────
            out_light = Path(str(out_img).replace('.png', '_l.png'))
            render_chart(window_df, local_idx, trade_meta, str(out_light), theme=TV_LIGHT)
            make_yolo_label(result, direction, out_light)

            success += 1
        else:
            errors += 1

        if (i + 1) % 100 == 0:
            print(f'  [{i+1}/{len(trades)}] '
                  f'✅ {success} rendered | ⏭ {skipped} skipped | ❌ {errors} errors')

        time.sleep(0.05)

    print(f'\n✅ Done: {success} charts | {skipped} skipped | {errors} errors')
    print(f'Output: {out_base}')
    return success


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='DayTradeDash Chart Generator')
    p.add_argument('--source',      default='tradertom', choices=['tradertom', 'rc', 'schoolrun'])
    p.add_argument('--limit',       type=int, default=None)
    p.add_argument('--instruments', nargs='+', default=['DAX', 'DOW', 'FTSE', 'NASDAQ'])
    args = p.parse_args()

    if args.source == 'tradertom':
        run_tradertom(limit=args.limit, instruments=args.instruments)
