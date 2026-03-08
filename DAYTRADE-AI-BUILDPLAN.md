# DayTrade AI — Full Execution Plan
**Created:** 2026-03-08 | **Owner:** Kelvin Lee | **Lead:** Nova

---

## ENVIRONMENT SNAPSHOT

| Resource | Status | Detail |
|----------|--------|--------|
| AI Server GPU | ✅ RTX 5060 Ti | 16GB VRAM, 28MB currently free |
| AI Storage | ✅ 1.1TB free | /mnt/ai_storage |
| Conda Envs | ✅ wan2gp, voice-clone, comfyui available | PyTorch present in wan2gp |
| pai-server | ✅ Dev browser live | Playwright :9222 |
| Dashboard | ✅ Running :3456 | React/Vite, SQLite DB |
| EODHD | ✅ $29.99/mo plan | Real-time + intraday |
| Apify | ✅ Account live | YouTube scraper available |
| HuggingFace | ✅ foduucom model ready | YOLOv8s weights |

---

## MASTER TIMELINE

```
WEEK 1 (NOW)   Foundation + First Inference
WEEK 2         Vision Pipeline Live + RC Data
WEEK 3         Self-Learning Loop Active
WEEK 4+        Intelligence Layer + Production
```

---

## ═══════════════════════════════════════
## WEEK 1 — FOUNDATION + FIRST INFERENCE
## ═══════════════════════════════════════

---

### DAY 1 (TODAY) — Environment + Base Model

#### TASK 1.1 — Create YOLOv8 Conda Environment on AI Server
```bash
# On ai-server
conda create -n yolov8 python=3.11 -y
conda activate yolov8
pip install ultralytics==8.3.0      # YOLOv8 framework
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install fastapi uvicorn pillow requests huggingface_hub
```
**Expected time:** 8 mins | **VRAM needed:** 0 (install only)

---

#### TASK 1.2 — Download foduucom Base Model
```bash
# On ai-server
mkdir -p /mnt/ai_storage/models/daytrade-ai/{base,v1.0,training_data/{images,labels,rc-analysis}}

# Download from HuggingFace
python3 -c "
from huggingface_hub import hf_hub_download
path = hf_hub_download(
    repo_id='foduucom/stockmarket-pattern-detection-yolov8',
    filename='best.pt',
    local_dir='/mnt/ai_storage/models/daytrade-ai/base'
)
print('Downloaded to:', path)
"
```
**Expected time:** 2 mins | **Model size:** ~22MB
**Existing classes:** Head&Shoulders, Triangle, W-Bottom, M-Head, StockLine

---

#### TASK 1.3 — Test Inference on Sample Chart
```bash
# Screenshot a TradingView chart first (from pai-server dev-browser)
# Then test:
python3 -c "
from ultralytics import YOLO
model = YOLO('/mnt/ai_storage/models/daytrade-ai/base/best.pt')
results = model('/tmp/test-chart.png', conf=0.25, save=True, project='/tmp/yolo-test')
for r in results:
    for box in r.boxes:
        print(f'Class: {r.names[int(box.cls)]} | Conf: {box.conf.item():.2f}')
"
```
**Success criteria:** Model runs, detects at least 1 pattern on a real chart image

---

#### TASK 1.4 — Generate Synthetic Bull Flag Training Data
```python
# Script: /home/pai-server/trading/generate-bull-flags.py
# Library: mplfinance + numpy
# Output: /mnt/ai_storage/models/daytrade-ai/training_data/

# Generates:
#   500 × bull_flag_forming images  (class 0)
#   500 × bull_flag_breakout images (class 1)
#   300 × bear_flag images          (class 2)
#   400 × no_pattern images         (class 6)
#   YOLO format .txt labels alongside each image

# Each image: 640×480px, dark theme matching TradingView
# Randomised: surge height (5-30%), pullback depth (30-50%),
#             flag duration (2-6 bars), volume profile, price level
```
**Expected time:** 20 mins to generate 1700 images | **Storage:** ~850MB

---

#### TASK 1.5 — MACD Synthetic Data
```python
# Additional 400 images with MACD pane visible:
#   200 × macd_bullish_cross (class 3)
#   200 × macd_bearish_cross (class 4)
# Two-pane charts: price (top 70%) + MACD (bottom 30%)
# MACD lines clearly visible, crossover annotated
```

---

### DAY 2 — YOLO Server + Screenshot Pipeline

#### TASK 2.1 — Build YOLO Inference Server (ai-server)
```python
# /mnt/ai_storage/projects/yolo-server/server.py
# FastAPI on port 8770
# Endpoints:
#   POST /infer         — accepts image bytes, returns bounding boxes + classes
#   GET  /health        — model loaded, GPU status
#   POST /infer/batch   — bulk inference for training validation
#   GET  /classes       — list of supported pattern classes

# Request format:
# { "image_b64": "<base64>", "conf_threshold": 0.50, "ticker": "RIME" }

# Response format:
# { "detections": [
#     { "class": "bull_flag_breakout", "confidence": 0.82,
#       "bbox": [x, y, w, h], "normalized": true }
#   ],
#   "inference_ms": 6,
#   "model_version": "v1.0"
# }
```
**Model pre-loaded into GPU at startup** — inference <10ms per image
**Start as systemd service:** `yolo-server.service` on ai-server

---

#### TASK 2.2 — Screenshot Scheduler (pai-server)
```python
# /home/pai-server/bin/screenshot-scheduler.py
# Systemd service: screenshot-scheduler.service
#
# Logic:
# 1. Every 90 seconds, check WS bridge for current candidates
# 2. For each candidate with score >6: take screenshot
# 3. Screenshot via dev-browser (Playwright) → TradingView 5-min chart
# 4. Crop to chart area (remove TradingView header/sidebar)
# 5. POST to yolo-server (ai-server:8770)
# 6. Store result in pattern_events table
# 7. If confidence > threshold: trigger Telegram alert with image

# TradingView URL format:
# https://www.tradingview.com/chart/?symbol=NASDAQ:{ticker}&interval=5
```

---

#### TASK 2.3 — Vision API (pai-server)
```python
# /home/pai-server/bin/vision-api.py
# FastAPI on port 8769
# Bridges dashboard ↔ ai-server

# Endpoints:
#   GET  /pattern/{ticker}/latest    — latest detection for ticker
#   GET  /pattern/{ticker}/history   — all detections for ticker
#   POST /pattern/label              — submit human label from Training Lab
#   GET  /training/stats             — labeled count, accuracy, pending
#   POST /training/retrain           — trigger retrain on ai-server
#   GET  /model/versions             — list available model versions
#   POST /model/activate/{version}   — switch active model
```

---

#### TASK 2.4 — Add Confidence Badge to Scanner Table
```jsx
// In dashboard ScannerRow component:
// New column: "AI" between RV5min and Gap%
// Badge: coloured dot + percentage
//   🟢 72%  = bull_flag_breakout, high confidence
//   🟡 58%  = bull_flag_forming, medium confidence
//   🔵 81%  = macd_bullish + flag
//   ⚪ —    = no pattern detected / not yet screenshotted
// Click badge → opens modal with screenshot + bounding boxes
```

---

### DAY 3 — MACD Overlay + Training Lab UI

#### TASK 3.1 — MACD Bounding Box Overlay
```jsx
// Dashboard: new overlay system on TradingView chart embed
// Canvas layer on top of TradingView iframe
// Receives bounding box coords from vision-api
// Toggle buttons: [🚩 Flag] [📊 MACD] [✓ Both] [✗ Off]
//
// Bounding box styles:
//   bull_flag_forming:  dashed amber border, "FLAG 58%" label
//   bull_flag_breakout: solid green border, "BREAKOUT 82%" label
//   macd_bullish_cross: solid blue border, "MACD BUY 71%" label
//   macd_bearish_cross: solid red border, "MACD SELL 68%" label
```
**Note:** TradingView iframe cross-origin blocks direct canvas overlay.
**Solution:** Screenshot-based overlay — render detected boxes on the
saved screenshot image, display as separate panel beside TradingView embed.

---

#### TASK 3.2 — Training Lab UI Tab
```jsx
// New tab: "🏷️ Training" in dashboard
// Shows unreviewed pattern_events screenshots
// Keyboard shortcuts: b=bull_flag, n=none, w=win, l=loss, →=next
// Progress bar: X labeled / target 1000
// Filters: by date, by ticker, by model prediction, by outcome
// Mobile optimised: large tap targets (56px buttons)
```

---

#### TASK 3.3 — Pattern Events Database Table
```sql
-- Add to rc-scanner.db
CREATE TABLE IF NOT EXISTS pattern_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker      TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  scan_date   TEXT,
  pattern     TEXT,              -- model's prediction
  confidence  REAL,
  screenshot  BLOB,              -- PNG bytes stored in DB (<100KB compressed)
  bboxes      TEXT,              -- JSON array of detections
  trade_taken INTEGER DEFAULT 0,
  entry       REAL,
  exit_price  REAL,
  outcome     TEXT,              -- win/loss/timeout/skip/watch
  pnl         REAL,
  human_label TEXT,              -- override from Training Lab
  model_ver   TEXT,
  used_in_training INTEGER DEFAULT 0,
  notes       TEXT
);

CREATE INDEX idx_pe_ticker ON pattern_events(ticker);
CREATE INDEX idx_pe_date ON pattern_events(detected_at);
CREATE INDEX idx_pe_label ON pattern_events(human_label);
```

---

### DAY 4 — First Fine-Tune

#### TASK 4.1 — Prepare Training Dataset (YOLO Format)
```
/mnt/ai_storage/models/daytrade-ai/training_data/
  dataset.yaml:
    path: /mnt/ai_storage/models/daytrade-ai/training_data
    train: images/train
    val:   images/val
    nc: 7
    names:
      0: bull_flag_forming
      1: bull_flag_breakout
      2: bear_flag
      3: macd_bullish_cross
      4: macd_bearish_cross
      5: macd_histogram_surge
      6: no_pattern

  images/train/  (80% — ~1360 images)
  images/val/    (20% — ~340 images)
  labels/train/  (.txt YOLO format: class cx cy w h)
  labels/val/
```

---

#### TASK 4.2 — Fine-Tune on AI Server
```bash
# On ai-server, conda activate yolov8
python3 -c "
from ultralytics import YOLO
model = YOLO('/mnt/ai_storage/models/daytrade-ai/base/best.pt')
results = model.train(
    data='/mnt/ai_storage/models/daytrade-ai/training_data/dataset.yaml',
    epochs=100,
    imgsz=640,
    batch=16,
    device=0,               # GPU 0 (RTX 5060 Ti)
    project='/mnt/ai_storage/models/daytrade-ai',
    name='v1.0',
    patience=20,            # early stopping
    lr0=0.001,
    momentum=0.937,
    weight_decay=0.0005,
    augment=True,           # random flips, brightness, crop
    save_period=10,         # checkpoint every 10 epochs
)
print('Best mAP:', results.results_dict['metrics/mAP50(B)'])
"
```
**Expected time:** ~25 mins | **VRAM usage:** ~5.5GB
**Expected mAP50 on synthetic data:** >0.75

---

## ═══════════════════════════════════════
## WEEK 2 — ROSS CAMERON DATA + LIVE PIPELINE
## ═══════════════════════════════════════

---

### DAY 5 — Ross Cameron Trade Log Scrape

#### TASK 5.1 — Scrape warriortrading.com/trade-log/
```python
# /home/pai-server/bin/rc-scraper.py
# Uses: dev-browser (Playwright) — already available
#
# warriortrading.com/trade-log/ shows:
#   - Daily P&L table: date | gross P&L | net P&L
#   - Green days (profit) vs red days (loss)
#
# Extract all available history (~8 years)
# Store in: rc_trade_log table in rc-scanner.db
#
# Schema:
CREATE TABLE rc_trade_log (
  date TEXT PRIMARY KEY,
  gross_pnl REAL,
  net_pnl REAL,
  green_day INTEGER,    -- 1=profit, 0=loss
  tickers TEXT,         -- from YouTube recap matching
  notes TEXT
);
```

---

#### TASK 5.2 — Match RC Dates to EODHD Tickers
```python
# For each green day in Ross's log:
# → Query EODHD for top gappers that day (gap >10%, float <10M)
# → Those are likely his candidates
# → High gap% + green day = probably his winner
# → Store as "probable_rc_trade" with confidence score
```

---

### DAY 6 — YouTube Recap Analysis

#### TASK 6.1 — Apify YouTube Scraper
```python
# Use existing Apify account (token in ~/.secrets/apify-api)
# Actor: YouTube channel video list
# Channel: @DaytradeWarrior
# Extract: title, description, date, video_id for all Daily Recap videos
# Filter: title contains "Day Trading Recap" or "Daily Recap"
# Output: ~500+ video IDs
```

---

#### TASK 6.2 — Extract Chart Frames from Videos
```python
# For each recap video:
# 1. Download via yt-dlp (360p — just need frames, not HD)
# 2. Extract transcript/subtitles (YouTube auto-captions)
# 3. Search transcript for keywords: "bull flag", "flag", "entry", "breakout"
# 4. Extract video frame at those timestamps ±5 seconds
# 5. Save as PNG: rc-analysis/{date}_{ticker}_{timestamp}.png
#
# Then: match video date to trade log → label frame win/loss
# These become highest-quality training examples
```

---

#### TASK 6.3 — RC Match Score Algorithm
```python
def rc_match_score(candidate):
    """
    Score 0-100 how similar this candidate is to Ross Cameron's winners
    """
    score = 0

    # Float (20 points)
    f = candidate.float_m or 99
    if f < 2:   score += 20
    elif f < 5: score += 15
    elif f < 10: score += 8

    # RelVol (20 points)
    rv = candidate.relvol or 0
    if rv >= 20:  score += 20
    elif rv >= 10: score += 15
    elif rv >= 5:  score += 8

    # Gap % (15 points) — Ross's sweet spot: 20-150%
    g = candidate.gap_pct or 0
    if 20 <= g <= 150: score += 15
    elif 10 <= g < 20: score += 8
    elif g > 150:       score += 10

    # Time of day (15 points) — 9:30-10:00 is prime
    from datetime import datetime
    now = datetime.now()
    h, m = now.hour, now.minute
    if h == 9 and 30 <= m <= 59: score += 15
    elif h == 10 and m <= 30:    score += 10
    elif h == 10:                 score += 5

    # Volume profile (15 points) — from EODHD
    # surge vol >> flag vol (drying up) >> breakout vol expanding
    if candidate.volume_profile_score: score += min(15, candidate.volume_profile_score)

    # YOLO confidence (15 points)
    if candidate.yolo_confidence:
        score += int(candidate.yolo_confidence * 15)

    return min(100, score)
```

---

### DAY 7 — Fine-Tune v1.1 with RC Data

#### TASK 7.1 — Merge RC Frames into Training Set
```
Total training data at this point:
  1700  synthetic images (from Day 1)
  ~200  RC YouTube chart frames (labeled win/loss)
  ~50   live session captures (from 5 days of running)
  ───────────────────────────────
  ~1950 total training images
```

---

#### TASK 7.2 — Retrain v1.1
```bash
# Same training command as TASK 4.2
# Add RC data to training/val split
# Expected improvement: +5-10% mAP due to real chart examples
# Model saved to: /mnt/ai_storage/models/daytrade-ai/v1.1/
```

---

#### TASK 7.3 — A/B Test v1.0 vs v1.1
```
Run both models on last 7 days of captured screenshots
Compare: precision, recall, false positives
Winner becomes active model
Dashboard shows: "Model: v1.1 | Accuracy: 74.2%"
```

---

## ═══════════════════════════════════════
## WEEK 3 — SELF-LEARNING LOOP
## ═══════════════════════════════════════

---

### DAY 8-10 — Feedback Integration

#### TASK 8.1 — Trade Outcome Auto-Recording
```python
# Extend trades table to link to pattern_events
# When Kelvin records a trade via dashboard:
#   → Auto-match to pattern_event by ticker + time
#   → Mark as used_in_training = False (pending review)
# Weekly: all outcomes reviewed → used_in_training = True → retrain
```

---

#### TASK 8.2 — Automated Weekly Retrain Cron
```bash
# On ai-server, runs every Sunday 1:00am
0 1 * * 0 /home/aiserver/miniconda3/bin/conda run -n yolov8 \
  python3 /mnt/ai_storage/projects/yolo-server/retrain.py \
  >> /mnt/ai_storage/logs/retrain.log 2>&1

# retrain.py:
# 1. Pull all labeled pattern_events from pai-server DB via SSH/API
# 2. Export images + labels to YOLO format
# 3. Train new model version
# 4. Evaluate on held-out test set
# 5. If mAP > current model: auto-promote to active
# 6. Notify Kelvin via Telegram: "Model v1.3 trained | mAP: 77.2% (+2.1%)"
```

---

#### TASK 8.3 — Model Health Dashboard Tab
```jsx
// New section in 🛡 System tab OR new "🤖 AI" tab

// Live metrics card:
//   Model: v1.3 | Trained: 2026-03-15 | Examples: 1,247
//   Bull Flag Precision: 74% | Recall: 81% | F1: 77%
//   MACD Precision: 82% | Recall: 76%

// Weekly accuracy chart (line graph)
// Per-class performance breakdown
// Recent detections feed with outcomes
// [🔄 Retrain Now] [📊 Full Report] [⬇ Export Model]
```

---

## ═══════════════════════════════════════
## WEEK 4+ — INTELLIGENCE LAYER
## ═══════════════════════════════════════

---

### TASK 9.1 — Composite Signal Score
```
Every live candidate gets a single COMPOSITE SCORE (0-100):

  YOLOv8 Bull Flag Confidence  × 0.30
  RC Match Score               × 0.25
  Volume Profile Score         × 0.20
  MACD Confirmation            × 0.15
  Time of Day Weight           × 0.10

  ≥ 80: 🔴 HIGH CONFIDENCE — Telegram alert + audio
  60-79: 🟡 MEDIUM — dashboard badge only
  < 60:  ⚪ LOW — scanner only, no alert
```

---

### TASK 9.2 — Multi-Timeframe Confluence
```
Bull flag on 5-min chart AND 1-min chart simultaneously:
  +10 bonus to composite score
  Visual indicator: "MTF ✓" badge on scanner row
```

---

### TASK 9.3 — Skip Recommendations
```
When model has high confidence in bear flag or MACD bearish:
  Show "⛔ SKIP" recommendation for that ticker
  Log if Kelvin trades anyway → outcome tracked
  Model learns from overrides
```

---

### TASK 9.4 — Audio Alerts (Chatterbox TTS)
```
When composite score ≥ 80:
  Nova voice (Chatterbox, Kelvin's voice clone settings):
  "RIME is forming a clean bull flag. Confidence 82%.
   Entry around $2.14, stop $1.89, target $2.64.
   Ross Cameron match score: 74 out of 100."
```

---

### TASK 9.5 — P&L Attribution
```
Dashboard "Analytics" section:
  Revenue by signal source (what's actually making money):
    YOLOv8 only:      $XXX | X% WR
    MACD confirmed:   $XXX | X% WR
    RC score >80:     $XXX | X% WR
    Composite >80:    $XXX | X% WR (composite = best combination)
```

---

## FINE-TUNING SETTINGS PANEL (in Dashboard)

### Full Settings Spec
```
🤖 AI MODEL SETTINGS
────────────────────────────────────────
Active Model:       v1.3 ▼         [Upload .pt file]
Detection Mode:     Both ▼         Bull Flag / MACD / Both / Off

CONFIDENCE THRESHOLDS
  Bull Flag alert:  ████░ 0.65     [slider: 0.40 – 0.95]
  MACD alert:       █████ 0.70     [slider: 0.40 – 0.95]
  RC Match alert:   ████░ 70       [slider: 0 – 100]
  Composite alert:  ████░ 80       [slider: 0 – 100]

SCREENSHOT CAPTURE
  Enabled:          ✅ On
  Interval:         90s            [60 / 90 / 120 / 180]
  Trigger score:    6/10           [slider: 4 – 9]
  Chart timeframe:  5min ▼         [1m / 5m / 15m]
  Lookback:         1 day ▼        [intraday / 2d / 5d]
  Save screenshots: ✅ Yes

MACD OVERLAY
  Show on chart:    ✅ On
  Pane visible:     ✅ On          (render MACD below price)
  Box style:        Filled ▼       [Outline / Filled / Dashed]

RC MATCH SCORE
  Enabled:          ✅ On
  Sync frequency:   Daily ▼        [Manual / Daily / Weekly]
  Last sync:        2026-03-08
  [↺ Sync Now]

TRAINING
  Auto-retrain:     Weekly ▼       [Off / Weekly / Bi-weekly]
  Min examples:     50
  Retrain day:      Sunday ▼       [Mon–Sun]
  Retrain time:     01:00
  [🔄 Retrain Now]
  [📊 Training Log]
  [⬇ Export Labels (JSON)]
  [⬆ Import Labels (JSON)]

ALERTS
  Telegram:         ✅ Enabled
  Audio (TTS):      ✅ Enabled     (Chatterbox)
  Threshold:        80             (composite score)
  Send screenshot:  ✅ With alert
```

---

## TODAY'S IMMEDIATE BUILD ORDER

```
Hour 1 (NOW):
  → TASK 1.1: Create yolov8 conda env on ai-server
  → TASK 1.2: Download foduucom base model

Hour 2:
  → TASK 1.3: Test inference on TradingView screenshot
  → TASK 1.4: Start synthetic data generation script

Hour 3:
  → TASK 2.1: Build yolo-server FastAPI on ai-server
  → TASK 3.3: Add pattern_events table to DB

Hour 4:
  → TASK 4.1: Prepare YOLO training dataset
  → TASK 4.2: Kick off first fine-tune (runs ~25 mins)
  → While training: TASK 3.2: Build Training Lab UI tab

Evening:
  → TASK 2.2: Screenshot scheduler
  → TASK 2.4: Confidence badge in scanner table
  → TASK 5.1: RC trade log scraper
```

---

## DECISION LOG

| Decision | Rationale |
|----------|-----------|
| YOLOv8s not YOLOv8m | Inference speed priority; s model = 6ms vs 12ms; upgrade if accuracy insufficient |
| Screenshots not live video | TradingView iframe blocks direct manipulation; screenshots sufficient for 5-min patterns |
| SQLite not Postgres for pattern_events | Consistency with existing DB; migrate later if >1M rows |
| Store screenshots as BLOBs not files | Simpler backup/transfer; compress to <100KB PNG per image |
| Weekly retraining not continuous | Prevents overfitting to recent market regime; weekly gives enough new data |
| mplfinance synthetic data | Fills cold start problem; RC + live data replaces it over time |

---

*Build Plan v1.0 — DayTrade AI | Nova (NovaPAI) | 2026-03-08*
