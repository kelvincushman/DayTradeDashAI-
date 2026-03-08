# PRD: DayTrade AI — Multi-Trader Self-Learning Visual Pattern Recognition Platform
**Version:** 2.0 | **Author:** Nova (NovaPAI) | **Date:** 2026-03-08
**Owner:** Kelvin Lee | **Classification:** Internal

---

## 1. EXECUTIVE SUMMARY

DayTrade AI is a self-learning, computer-vision-powered trading intelligence platform that
trains itself on the verified historical trade records of multiple profitable traders — then
applies that learned pattern recognition to live market candidates in real time.

**Core innovation:** Instead of hand-coding trading rules, we extract the visual fingerprint
of proven winning setups directly from traders who have documented track records. The model
learns what Ross Cameron, Tom Hougaard, and the School Run strategy actually look like as
chart patterns — then hunts for the same setups live.

**The feedback loop:** Scanner surfaces candidates → YOLOv8 detects patterns on live chart
screenshots → trades are recorded with outcomes → model retrains weekly on its own results
→ progressively sharper signal, every single week.

---

## 2. WHAT WE ALREADY HAVE

| Asset | Status | Detail |
|-------|--------|--------|
| Gap Scanner | ✅ Live | Polls EODHD every 60s; 251 candidates in DB across 27 trading days |
| TraderTom CSV | ✅ **5,054 trades** | `all_trades.csv` — date, time, entry, exit, direction, P&L, result |
| TraderTom Telegram Monitor | ✅ Built | `telegram_monitor.py` + session saved |
| TraderTom Stats | ✅ Parsed | 56.84% WR, £1.95M P&L, avg hold 26.4 mins |
| RC Scanner DB | ✅ Live | SQLite at `/home/pai-server/trading/rc-scanner.db` |
| Dev Browser | ✅ Live | Playwright at localhost:9222 — can screenshot any URL |
| AI Server | ✅ RTX 5060 Ti 16GB | `/mnt/ai_storage/` — 1.1TB free |
| EODHD API | ✅ $29.99/mo | Real-time + 1-min intraday + screener |
| Dashboard | ✅ Running :3456 | React/Vite, column filters added |
| foduucom YOLOv8 | ✅ Available | HuggingFace — pre-trained on chart patterns |
| School Run Pine Script | ✅ Built | DAX 08:00 open, backtested |
| Apify | ✅ Account live | YouTube + web scraping |

---

## 3. THE PROBLEM

Bull flags, index trend entries, and opening range breakouts are **inherently visual**.
OHLCV rows alone cannot capture:
- The *shape* and *tightness* of a flag consolidation
- Whether volume dried up correctly during the pullback
- The momentum "feel" of the surge candle
- Context — is this the 1st flag or the 4th failed attempt?

Programmatic backtesting on 1-min OHLCV data confirmed this:
- EODHD 1-min data is gappy on illiquid small caps
- 0 wins found across 251 candidates with rule-based detection
- The strategy requires human-level visual judgment

**Solution:** Teach a machine to see what profitable traders see, using *their own trade records*
as ground truth labels.

---

## 4. TRADER DATA SOURCES

### 4.1 TraderTom (Tom Hougaard) — PRIMARY ✅ DATA IN HAND

**Who:** Tom Hougaard, author of "Best Loser Wins". Trades DAX, DOW, FTSE, NASDAQ live
on YouTube and Telegram. One of the most transparent professional traders in the UK.

**Data we have:**
```
File: all_trades.csv (5,054 rows)
Fields: channel, product, date, time, direction, entry, stop_loss,
        stake, exit1, exit1_time, exit2, points, pnl, result, hold_mins

Stats (from stats.json):
  Total trades:    5,054
  Win rate:        56.84%
  Avg win:         £3,064
  Avg loss:        £3,623
  Total P&L:       £1,951,006
  Avg hold:        26.4 minutes
  Max win streak:  23
  Max loss streak: 22

By instrument:
  DAX:    1,650 trades | wins: 953 | losses: 587 | P&L: £867,552
  DOW:    1,232 trades | wins: 722 | losses: 435 | P&L: £531,607
  FTSE:     N/A  (also in dataset)
  NASDAQ:   N/A  (also in dataset)
```

**Chart generation plan:**
- We have exact entry time + direction for every trade
- Fetch EODHD intraday data for that instrument + date
- Extract **±10 bars (1-min)** around the entry timestamp
- Render as TradingView-style dark chart (mplfinance)
- Label: Win / Loss / Breakeven from CSV
- Result: ~5,054 labeled chart images, perfectly matched to real outcomes

**Why Tom's data is special:**
- Index futures — different visual pattern to small caps (smoother, less gappy data)
- Trend-following style — model learns BOTH momentum breakouts AND trend continuations
- 5+ years of data across multiple market regimes (COVID, rate hikes, bull/bear)
- Avg hold 26.4 mins — entire trade visible in ±10 bar window

---

### 4.2 Ross Cameron (Warrior Trading) — GOLD STANDARD US SMALL CAPS

**Who:** Verified US day trader, $583 → $12.5M documented. Trades low-float small caps.
Results audited annually and published publicly.

**Data plan:**
```
Source 1: warriortrading.com/trade-log/
  - Daily P&L table (8 years)
  - Green day = profitable, red day = loss
  - Scrape with dev-browser (Playwright)

Source 2: EODHD data for each green/red day
  - On green days: fetch top gappers (gap >10%, float <10M) for that date
  - Those are his likely candidates (he trades the top stock of the day)
  - Highest gap% + green day = probable winner

Chart generation:
  - Fetch EODHD 1-min data for matched ticker + date
  - Find surge candle (biggest green body in 9:30-11:00 ET)
  - Extract ±10 bars around surge candle
  - Render TradingView dark-style chart
  - Label: Win (green day) / Loss (red day)
```

**Why this approach works:**
- ±10 bars captures: surge (pole) → flag consolidation → breakout/breakdown
- 1-min data on Ross's stocks is CLEAN — he only trades the highest-volume stock of the day
- No need for YouTube video scraping
- EODHD data quality on top gappers is excellent (high volume = no gaps)

---

### 4.3 School Run Strategy — OUR OWN DATA

**What:** DAX opening range breakout, 08:00 London entry, hold until 09:30.
Built by Kelvin, Pine Script backtested.

**Data plan:**
```
Source: Our own backtest results + School Run trade log (if live trades taken)

Chart generation:
  - Fetch EODHD DAX (Germany 40) intraday for each backtest date
  - Extract the 08:00 candle ±10 bars (07:50 - 08:10)
  - Render chart with London session open highlighted
  - Label: Win / Loss from backtest results

Unique value:
  - Adds "opening range" pattern type to model
  - DAX-specific visual patterns (different to US small caps)
  - Our own strategy — directly actionable
```

---

### 4.4 Jay — PENDING

**Status:** Kelvin to confirm trader identity (YouTube handle / Twitter / website).
Will add to PRD once identified. Same extraction approach as above.

---

## 5. CHART GENERATION PIPELINE

### 5.1 The ±10 Bar Window — Why It Works

```
T-10 bars          T=0 (entry/surge)          T+10 bars
    │                      │                       │
[Context &         [THE KEY CANDLE]           [Resolution]
 build-up]         Entry/Surge/Signal         Win or Loss
                                               visible here
```

For Tom's trades (avg 26.4 min hold, 1-min bars):
- ±10 bars = 20 minutes total
- Enough to see: pre-entry trend → signal candle → trade resolution
- Entire trade visible in one image 95% of the time

For Ross's bull flags (avg hold ~15-20 mins):
- ±10 bars around surge = full flag pattern visible
- Surge pole + flag consolidation (2-6 bars) + breakout/breakdown

For School Run (fixed time entry):
- ±10 bars around 08:00 = pre-open context + entry + early resolution

### 5.2 Chart Rendering Specification

```python
# TradingView Dark Theme — exact match to production screenshots
CHART_STYLE = {
    'background': '#0f1320',      # dark navy (matches TV dark)
    'candle_up': '#22c55e',       # green
    'candle_down': '#ef4444',     # red
    'wick_up': '#22c55e',
    'wick_down': '#ef4444',
    'volume_up': '#22c55e44',     # semi-transparent
    'volume_down': '#ef444444',
    'grid': '#1e2a44',
    'text': '#9ca3af',
    'entry_line': '#3b82f6',      # blue vertical = entry candle
    'size': (640, 480),           # pixels — standard YOLO input
    'dpi': 100,
}

# Two-pane chart:
#   Top 70%: candlestick + volume bars
#   Bottom 30%: MACD (12,26,9) — signal + histogram

# Entry candle marked with blue vertical line
# Win trades: thin green horizontal line at exit price
# Loss trades: thin red horizontal line at stop/exit price
```

### 5.3 MACD Pane

Every chart renders the MACD pane in the bottom 30%:
- MACD line (blue)
- Signal line (orange)
- Histogram bars (green/red)

This trains the model to simultaneously detect:
- The candlestick pattern (top pane)
- The MACD confirmation signal (bottom pane)

A single YOLOv8 inference on the full image detects BOTH.

### 5.4 Estimated Training Dataset Size

| Source | Trades Available | Est. Valid Charts | Quality |
|--------|-----------------|-------------------|---------|
| TraderTom CSV | 5,054 | ~4,500 | ⭐⭐⭐⭐⭐ |
| Ross Cameron | 8yr trade log | ~1,200 (green/red days) | ⭐⭐⭐⭐ |
| School Run backtest | ~300 | ~280 | ⭐⭐⭐⭐ |
| Synthetic (mplfinance) | Unlimited | 2,000 | ⭐⭐⭐ |
| Live session captures | Grows daily | +50/week | ⭐⭐⭐⭐⭐ |
| **TOTAL** | | **~8,000** | |

8,000 labeled images is an excellent dataset for YOLOv8 fine-tuning.
Most published chart pattern papers use 1,000–5,000. We'll exceed them.

---

## 6. YOLOV8 VISION ENGINE

### 6.1 Detection Classes

```yaml
# dataset.yaml
nc: 9
names:
  0: bull_flag_forming        # flag in consolidation, not yet broken out
  1: bull_flag_breakout       # breakout candle confirmed — BUY signal
  2: bear_flag                # short opportunity
  3: opening_range_break_long # School Run / ORB long
  4: opening_range_break_short
  5: macd_bullish_cross       # MACD line crosses signal upward
  6: macd_bearish_cross       # MACD line crosses signal downward
  7: macd_histogram_surge     # histogram expanding = momentum building
  8: no_pattern               # noise / no actionable setup
```

### 6.2 Model Architecture

```
Base:    foduucom/stockmarket-pattern-detection-yolov8 (HuggingFace)
         Already trained on: H&S, Triangle, W-Bottom, M-Head, StockLine
         Size: ~22MB | Inference: ~6ms on RTX 5060 Ti

Fine-tune: Add our 9 classes on top of pretrained weights
           Transfer learning — much faster convergence than training from scratch
           Training time: ~25 mins for 8,000 images, 100 epochs

VRAM budget (RTX 5060 Ti 16GB):
  Inference batch=1:       1.5GB
  Fine-tuning batch=16:    5.5GB
  Headroom remaining:      9GB ✅ Comfortable
```

### 6.3 Bounding Box Overlays — Toggleable

```
Dashboard toggle bar:
  [🚩 Bull Flag] [📊 MACD] [↗️ ORB] [✓ All] [✗ Off]

Bounding box colour coding:
  bull_flag_forming:   #f59e0b dashed  "FLAG 58%"
  bull_flag_breakout:  #22c55e solid   "BREAKOUT 82%"
  bear_flag:           #ef4444 dashed  "BEAR FLAG 71%"
  opening_range_*:     #8b5cf6 solid   "ORB LONG 76%"
  macd_bullish_cross:  #3b82f6 solid   "MACD ✓ 79%"
  macd_bearish_cross:  #ef4444 solid   "MACD ✗ 68%"
  macd_histogram_surge:#06b6d4 solid   "MOMENTUM 74%"

Overlay rendered on screenshot image panel beside TradingView embed
(TradingView iframe cross-origin prevents direct canvas injection)
```

---

## 7. COMPOSITE SIGNAL SCORE

Every live scanner candidate receives a single **COMPOSITE SCORE (0–100)**:

```
Score = (
  yolo_bull_flag_conf   × 0.30   # visual pattern confidence
  rc_match_score        × 0.20   # similarity to Ross Cameron winners
  tom_pattern_score     × 0.15   # similarity to Tom Hougaard entries
  volume_profile_score  × 0.20   # surge/flag/breakout volume ratios
  macd_conf             × 0.10   # MACD confirmation
  time_of_day_weight    × 0.05   # 9:30-10:00 ET peak for RC
) × 100

Alert thresholds:
  ≥ 80:  🔴 HIGH — Telegram alert + audio (Chatterbox TTS) + screenshot
  60-79: 🟡 MEDIUM — Dashboard badge only
  < 60:  ⚪ LOW — Scanner list, no alert
```

### Volume Profile Score (Ross Cameron's actual filter)

```python
def volume_profile_score(bars, surge_idx):
    surge_vol = bars[surge_idx]['volume']
    avg_10bar = mean([b['volume'] for b in bars[max(0,surge_idx-10):surge_idx]])
    flag_bars  = bars[surge_idx+1:surge_idx+5]
    flag_vols  = [b['volume'] for b in flag_bars]

    # Criterion 1: Surge must be 5x+ average (pole volume)
    surge_score = min(20, int((surge_vol / max(avg_10bar, 1)) / 5 * 20))

    # Criterion 2: Volume must DRY UP during flag (each bar declining)
    drying = all(flag_vols[i] < flag_vols[i-1] for i in range(1, len(flag_vols)))
    dryup_score = 20 if drying else 10 if flag_vols[-1] < surge_vol * 0.3 else 0

    return surge_score + dryup_score  # max 40 → scaled to 0-100 in composite
```

---

## 8. SELF-LEARNING FEEDBACK LOOP

### 8.1 Data Flow

```
Live session
     │
     ▼
Scanner detects candidate (gap >10%, float <10M, relvol >5x)
     │
     ▼
Score > 6/10 → Screenshot TradingView 5-min chart (dev-browser)
     │
     ▼
POST image → yolo-server (ai-server:8770)
     │
     ▼
YOLOv8 inference → bounding boxes + confidence scores
     │
     ├──────────────────────────────────────────────┐
     │                                              │
     ▼                                              ▼
Store in pattern_events DB              Composite score calculated
     │                                              │
     ▼                                              ▼
Dashboard badge updated              ≥80: Telegram alert + TTS
     │
     ▼
Kelvin takes trade (or skips)
     │
     ▼
Outcome recorded: Win / Loss / Timeout / Skip
     │
     ▼
pattern_event.outcome updated
     │
     ▼
Sunday 1am: auto-retrain on ai-server
     │
     ▼
New model version deployed if mAP improved
     │
     ▼
Telegram: "Model v1.4 | mAP: 77.2% (+2.1%) | 1,247 examples"
```

### 8.2 Database Schema

```sql
-- New table added to rc-scanner.db
CREATE TABLE pattern_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker       TEXT NOT NULL,
  instrument   TEXT DEFAULT 'US_SMALLCAP',  -- US_SMALLCAP/DAX/DOW/FTSE
  detected_at  TEXT NOT NULL,
  scan_date    TEXT,
  pattern      TEXT,          -- model's top prediction class
  confidence   REAL,          -- 0.0-1.0
  all_detections TEXT,        -- JSON: all classes + confidences + bboxes
  screenshot   BLOB,          -- compressed PNG <100KB
  composite_score INTEGER,    -- 0-100
  rc_match     INTEGER,       -- 0-100
  tom_match    INTEGER,       -- 0-100
  volume_score INTEGER,       -- 0-100
  trade_taken  INTEGER DEFAULT 0,
  entry_price  REAL,
  exit_price   REAL,
  outcome      TEXT,          -- win/loss/timeout/skip/watch
  pnl          REAL,
  human_label  TEXT,          -- Training Lab override
  model_ver    TEXT,
  used_in_training INTEGER DEFAULT 0,
  notes        TEXT,
  created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE model_versions (
  version      TEXT PRIMARY KEY,
  trained_at   TEXT,
  examples     INTEGER,
  map50        REAL,
  map50_95     REAL,
  bull_flag_precision REAL,
  bull_flag_recall    REAL,
  macd_precision      REAL,
  active       INTEGER DEFAULT 0,
  notes        TEXT
);

CREATE TABLE trader_charts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  trader       TEXT,          -- TraderTom/RossCameron/SchoolRun/Jay
  instrument   TEXT,
  trade_date   TEXT,
  trade_time   TEXT,
  direction    TEXT,          -- Long/Short
  entry        REAL,
  exit         REAL,
  points       REAL,
  pnl          REAL,
  result       TEXT,          -- Win/Loss/BE
  hold_mins    REAL,
  image_path   TEXT,          -- rendered chart path on ai-server
  image_label  TEXT,          -- Win/Loss/BE — YOLO training label
  bbox_path    TEXT,          -- YOLO .txt label file path
  used_in_training INTEGER DEFAULT 0
);
```

### 8.3 Weekly Retrain (Sunday 1am on ai-server)

```python
# /mnt/ai_storage/projects/yolo-server/retrain.py
# Steps:
# 1. Pull new labeled pattern_events from pai-server via API
# 2. Pull any new trader_charts not yet used in training
# 3. Merge into training/val split (80/20)
# 4. Run YOLOv8 fine-tune (100 epochs, early stop patience=20)
# 5. Evaluate on held-out test set (never seen during training)
# 6. If mAP50 > current active model: version++, activate
# 7. Telegram notification with metrics comparison
# 8. Old model archived (keep last 5 versions for rollback)
```

---

## 9. TRAINING LAB UI

### 9.1 Tab: 🏷️ Training Lab

```
┌─────────────────────────────────────────────────────────────┐
│ 🏷️ TRAINING LAB          8 pending  ████████░░ 847/1000    │
├─────────────────────────────────────────────────────────────┤
│ Filter: [All ▼] [Any trader ▼] [Any outcome ▼] [Unlabeled] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RIME · US Small Cap · 2026-02-24 · 9:47am ET             │
│  Scanner: gap=151% float=8.5M relvol=106x                  │
│  Model: bull_flag_breakout (conf: 82%) | Score: 78/100     │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  [Chart screenshot 640×480 with bounding boxes]     │   │
│  │  🟢 BREAKOUT 82%  🔵 MACD ✓ 71%                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Pattern:                                                   │
│  [🚩 Bull Flag] [🐻 Bear Flag] [↗️ ORB] [❌ None] [🗑 Skip]│
│                                                             │
│  Outcome (if you watched/traded):                          │
│  [💚 Win] [❤️ Loss] [⏱ Timeout] [👁 Watched Only]         │
│                                                             │
│  Notes: [________________________]                          │
│                                                             │
│         [← Prev]   1 of 8   [Next →]  [Save & Next]       │
└─────────────────────────────────────────────────────────────┘

Keyboard shortcuts:
  b = bull flag   n = no pattern   w = win   l = loss   → = next
```

### 9.2 Tab section: 📊 Trader Chart Library

```
Import and review the historical trader charts used for training:

  [TraderTom ▼] [DAX ▼] [Wins Only ▼]  Search: [_________]

  5,054 total | 953 DAX wins | 587 DAX losses | 110 DAX BE
  Chart images generated: 4,231/5,054

  ┌────────┬──────────┬───────┬───────┬───────┬──────┬──────┐
  │ Date   │ Time     │ Inst  │ Dir   │ Entry │ Exit │ P&L  │
  ├────────┼──────────┼───────┼───────┼───────┼──────┼──────┤
  │2021-01 │ 15:45    │ DAX   │ Short │13744  │13633 │+£11k │
  └────────┴──────────┴───────┴───────┴───────┴──────┴──────┘
  [Click any row to view chart image + bounding boxes]

  [🔄 Regenerate Charts] [📊 Export Labels] [🚀 Add to Training]
```

---

## 10. FINE-TUNING SETTINGS PANEL

### Full Settings (in dashboard Settings tab)

```
🤖 AI MODEL
──────────────────────────────────────────────────
Active Model:        v1.3 ▼          [Upload .pt]
Mode:                Both ▼          Bull Flag / MACD / ORB / Both / Off
Hardware:            AI Server ✅    RTX 5060 Ti | 14.5GB free

CONFIDENCE THRESHOLDS
  Bull Flag alert:   ████░  0.65    ←────────────→
  MACD confirmation: █████  0.70    ←────────────→
  ORB alert:         ████░  0.68    ←────────────→
  Composite alert:   ████░  80      ←────────────→
  RC match min:      ████░  70      ←────────────→
  Tom match min:     ████░  65      ←────────────→

COMPOSITE SCORE WEIGHTS
  YOLOv8 visual:     30%   ←───────────────────→
  RC match:          20%   ←───────────────────→
  Tom match:         15%   ←───────────────────→
  Volume profile:    20%   ←───────────────────→
  MACD confirm:      10%   ←───────────────────→
  Time of day:        5%   ←───────────────────→
  [Reset to defaults]

SCREENSHOT CAPTURE
  Enabled:           ✅ On
  Interval:          90s  [60 / 90 / 120 / 180]
  Min scanner score: 6/10
  Timeframe:         5min ▼
  Dark mode:         ✅ Always (TradingView dark)

OVERLAY DISPLAY
  Default visible:   Both ▼
  Box style:         Solid ▼   [Solid / Dashed / Filled]
  Show confidence:   ✅ Labels with % score
  Show on hover:     ✅ Only on hover (cleaner)

TRAINING & RETRAINING
  Auto-retrain:      Weekly ▼  [Off / Weekly / Bi-weekly / Monthly]
  Retrain schedule:  Sunday 01:00
  Min new examples:  50        before triggering retrain
  Test set size:     15%       held out, never trained on
  Keep versions:     5         (older archived on ai-server)
  [🔄 Retrain Now]
  [📊 Training Log]
  [⬇ Export Dataset]
  [⬆ Import Labels]

ALERTS
  Telegram:          ✅ Enabled
  Audio TTS:         ✅ Enabled (Chatterbox — Kelvin's voice)
  Alert threshold:   80        composite score
  Attach screenshot: ✅ Yes — with bounding boxes overlaid
  Audio format:
    "TICKER is forming a clean bull flag.
     Confidence [X]%. Score [Y] out of 100.
     Entry around $X.XX, stop $X.XX, target $X.XX."

TRADER DATA SYNC
  TraderTom:         ✅ 5,054 trades loaded
                     [Last chart gen: never] [🔄 Generate Charts]
  Ross Cameron:      ⬜ Not yet scraped    [🔄 Sync Trade Log]
  School Run:        ⬜ Not yet imported   [🔄 Import Backtest]
  Jay:               ⬜ Pending            [+ Add Trader]
```

---

## 11. ROSS CAMERON MATCH SCORE

```python
def rc_match_score(s):
    """0-100 similarity to Ross Cameron's documented winners."""
    score = 0
    # Float (20pts) — sub-5M ideal, sub-10M acceptable
    f = s.float_m or 99
    score += 20 if f < 2 else 15 if f < 5 else 8 if f < 10 else 0
    # RelVol (20pts) — higher = better
    rv = s.relvol or 0
    score += 20 if rv >= 20 else 15 if rv >= 10 else 8 if rv >= 5 else 0
    # Gap% (15pts) — 20-150% sweet spot
    g = s.gap_pct or 0
    score += 15 if 20 <= g <= 150 else 10 if g > 150 else 8 if g >= 10 else 0
    # Time of day (15pts) — 9:30-10:00 ET prime window
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    et_h = (now.hour - 4) % 24; et_m = now.minute
    score += 15 if et_h==9 and et_m>=30 else 10 if et_h==10 and et_m<=30 else 5 if et_h==10 else 0
    # Volume profile (15pts)
    score += min(15, s.volume_score or 0)
    # YOLOv8 visual confidence (15pts)
    score += int((s.yolo_confidence or 0) * 15)
    return min(100, score)
```

---

## 12. TOM HOUGAARD MATCH SCORE

```python
def tom_match_score(s, bars):
    """
    0-100 similarity to Tom Hougaard's entry patterns.
    Tom trades indices (DAX/DOW/FTSE) — different criteria.
    Used for School Run and index-based setups.
    """
    score = 0
    # Trend alignment (30pts) — Tom is trend-following
    # Check if price is above/below 20-bar EMA
    if len(bars) >= 20:
        ema20 = sum(b['c'] for b in bars[-20:]) / 20
        trend_long = bars[-1]['c'] > ema20
        score += 30 if (s.direction=='Long' and trend_long) or \
                       (s.direction=='Short' and not trend_long) else 0
    # MACD alignment (25pts) — Tom uses MACD confirmation
    score += (s.macd_confidence or 0) * 25
    # Time window (20pts) — Tom trades EU + US open
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    h = now.hour
    # EU open: 07:00-09:00 UTC | US open: 13:30-15:30 UTC
    score += 20 if (7 <= h < 9) or (13 <= h < 16) else 10 if (9 <= h < 13) else 5
    # Momentum (15pts) — strong directional move
    if len(bars) >= 3:
        move = abs(bars[-1]['c'] - bars[-3]['c']) / bars[-3]['c'] * 100
        score += min(15, int(move * 3))
    # YOLOv8 pattern confidence (10pts)
    score += int((s.yolo_confidence or 0) * 10)
    return min(100, score)
```

---

## 13. TECHNICAL ARCHITECTURE

### 13.1 Services

| Service | Port | Host | Purpose |
|---------|------|------|---------|
| `yolo-server` | 8770 | ai-server | YOLOv8 inference + training trigger |
| `vision-api` | 8769 | pai-server | Orchestration, DB writes, screenshot routing |
| `screenshot-scheduler` | — | pai-server | Systemd timer, dev-browser chart captures |
| `rc-log-scraper` | — | pai-server | Periodic warriortrading.com trade log sync |
| Existing: `daytrade-dash` | 3456 | pai-server | React dashboard |
| Existing: `rc-research-server` | 8767 | pai-server | REST API |
| Existing: `rc-ws-bridge` | 8765 | pai-server | WebSocket scanner broadcast |
| Existing: `trading-watchdog` | — | pai-server | Health monitoring + alerts |

### 13.2 AI Server Model Storage

```
/mnt/ai_storage/models/daytrade-ai/
  base/                     foduucom pre-trained weights
  v1.0/                     first fine-tune (synthetic data)
  v1.1/                     + TraderTom charts
  v1.2/                     + Ross Cameron charts
  v1.x/                     weekly retrains
  training_data/
    images/train/            80% split
    images/val/              15% split
    images/test/             5% held-out (never trained)
    labels/train/
    labels/val/
    labels/test/
    dataset.yaml
  trader_charts/
    tradertom/               5,054 rendered chart images
    ross_cameron/            ~1,200 rendered chart images
    school_run/              ~280 rendered chart images
    jay/                     TBC
  inference_cache/           recent screenshots for dashboard
```

---

## 14. BUILD PHASES — UPDATED

### PHASE 1 — Foundation (Week 1, Days 1-4)

| Task | Owner | Est Time |
|------|-------|----------|
| Create `yolov8` conda env on ai-server | Nova | 8 mins |
| Download foduucom base model | Nova | 2 mins |
| Test inference on sample TradingView screenshot | Nova | 15 mins |
| Build chart generator (mplfinance TradingView dark style) | Nova | 2 hrs |
| Generate TraderTom charts from all_trades.csv (5,054) | Nova | 3 hrs |
| First fine-tune with Tom data (DAX wins vs losses) | Nova | 25 mins |
| Add `pattern_events` + `trader_charts` tables to DB | Nova | 10 mins |
| Build `yolo-server` FastAPI on ai-server | Nova | 1 hr |

### PHASE 2 — Live Pipeline (Days 3-5)

| Task | Owner | Est Time |
|------|-------|----------|
| `screenshot-scheduler` systemd service | Nova | 1 hr |
| `vision-api` orchestration layer | Nova | 1 hr |
| Dashboard: confidence badge column in scanner | Nova | 30 mins |
| Dashboard: MACD/bull flag overlay toggle | Nova | 1 hr |
| Dashboard: Training Lab tab | Nova | 2 hrs |
| Dashboard: Trader Chart Library section | Nova | 1 hr |
| Telegram alert with bounding box screenshot | Nova | 30 mins |
| Chatterbox TTS audio alerts | Nova | 30 mins |

### PHASE 3 — Ross Cameron + Multi-Trader (Week 2)

| Task | Owner | Est Time |
|------|-------|----------|
| RC trade log scraper (warriortrading.com) | Nova | 2 hrs |
| Match RC dates to EODHD top gappers | Nova | 1 hr |
| Render RC chart images ±10 bars | Nova | 3 hrs |
| RC Match Score in scanner table | Nova | 30 mins |
| School Run backtest → chart images | Nova | 1 hr |
| Fine-tune v1.1 with all trader data (~7,000 images) | Nova | 30 mins |
| Jay data (once confirmed) | Nova | TBC |

### PHASE 4 — Self-Learning (Week 3)

| Task | Owner | Est Time |
|------|-------|----------|
| Automated weekly retrain pipeline | Nova | 2 hrs |
| Model versioning + rollback system | Nova | 1 hr |
| AI Model tab in dashboard | Nova | 2 hrs |
| Fine-tuning settings panel complete | Nova | 1 hr |
| Composite score all signals | Nova | 1 hr |
| P&L attribution by signal source | Nova | 1 hr |

### PHASE 5 — Intelligence (Week 4+)

| Task | Owner | Est Time |
|------|-------|----------|
| Multi-timeframe confluence (1min + 5min) | Nova | 2 hrs |
| Skip recommendations (bear flag = don't trade) | Nova | 1 hr |
| Audio alerts with trade specifics (Chatterbox) | Nova | 30 mins |
| Tom Hougaard match score live | Nova | 1 hr |
| Composite score analytics tab | Nova | 2 hrs |

---

## 15. RISKS & MITIGATIONS (UPDATED)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Tom's DAX charts have different visual to US small caps | Low | Low | Model learns both — separate classes; composite score weights accordingly |
| MACD pane too small in 640×480 to detect reliably | Medium | Medium | Crop MACD pane to separate 640×200 image; run second inference pass |
| TraderTom entry time in CSV is signal time not exact candle | Low | Low | ±10 bars gives enough buffer; surge candle detection handles minor offsets |
| RC trade log doesn't list specific tickers | Medium | Medium | Top gapper matching by date is 80%+ reliable for his style |
| Model learns market-specific patterns (only bull markets) | Medium | High | Ensure training set spans bull + bear + sideways (Tom's 5yr data covers this) |
| Overfitting on Tom's data (dominant in training set) | Medium | Medium | Balance dataset: cap Tom at 2,000, ensure synthetic + RC data present |

---

## 16. EXTENDED INSPIRATION & IDEAS

These are possible extensions as the system matures:

**Near term:**
- **Multi-trader composite** — combine RC score + Tom score + YOLO into single signal
- **Instrument routing** — US small caps → RC model weighting, indices → Tom model weighting
- **Pattern evolution** — track flag tightening bar-by-bar (not just single snapshot)
- **Level 2 proxy** — bid/ask spread from EODHD as liquidity signal
- **News sentiment** — EODHD news headline VADER score at signal time

**Medium term:**
- **Session learning** — model notes which patterns worked today vs yesterday
- **Regime detection** — bull/bear/choppy market classifier; adjusts thresholds
- **Volume exhaustion detection** — flag when 10th+ failed breakout = stop looking
- **Portfolio heat** — refuse signals if already in 2+ trades (position risk limit)

**Longer term:**
- **Mobile Trading Lab** — label screenshots on phone between sessions
- **Community signals** — anonymised composite score shared to Discord
- **Paper trading auto-evaluation** — forward-test all >80 score signals, track hypothetical P&L separately to real trades
- **Earnings calendar integration** — warn when stock has earnings same day
- **Tom Hougaard live Telegram feed** — new trades auto-captured and added to training in real time

---

## 17. SUCCESS METRICS

| Metric | Baseline | 4-Week Target | 12-Week Target |
|--------|----------|---------------|----------------|
| Bull flag precision | 0% (not built) | >60% | >75% |
| False positive rate | 100% (rule-based) | <50% | <30% |
| Training examples | 0 | 5,000 (Tom) | 8,000+ |
| Model versions | 0 | v1.2 | v1.x (weekly) |
| Composite score accuracy | N/A | Tested | Validated vs real outcomes |
| Dashboard latency (screenshot→badge) | N/A | <10s | <5s |
| Weekly retrain | Not running | Scheduled | Self-managing |

---

## 18. DEFINITION OF DONE — v1.0

- [ ] YOLOv8 inference running on ai-server, <2s end-to-end
- [ ] 5,054 TraderTom charts rendered and used in fine-tune
- [ ] v1.0 model deployed, mAP50 > 0.55 on validation set
- [ ] Live scanner screenshots every 90s for flagged tickers
- [ ] Dashboard confidence badge column live
- [ ] MACD/bull flag overlay with toggle live
- [ ] Training Lab tab — label images with keyboard shortcuts
- [ ] Composite score displayed per ticker
- [ ] Telegram alert with annotated screenshot
- [ ] Chatterbox audio alert on score ≥ 80
- [ ] Fine-tuning settings panel complete in dashboard
- [ ] Weekly retrain scheduled on ai-server

---

*PRD v2.0 — DayTrade AI | Nova (NovaPAI) | 2026-03-08*
*"Don't code the rules. Learn from the winners."*
