# DayTrade AI — Multi-Layer Signal System
## Plan & To-Do List
*Updated: 2026-03-10*

---

## 🎯 THE GOAL
Automate Ross Cameron's bull flag strategy.
Watch the scanner → detect setup → fire a signal (paper trade first, live later).

---

## 🏗️ ARCHITECTURE (3 Layers + Aggregator)

```
Scanner → Chart Screenshots → [Layer 1] → [Layer 2] → [Layer 3] → Signal
```

| Layer | Model | What it does | Speed |
|-------|-------|-------------|-------|
| 1 | YOLO-Candle | Detect individual candle types (hammer, doji, marubozu etc.) | 10ms |
| 2 | YOLO-Pattern | Combine candle signals → bull flag, ORB, etc. | 10ms |
| 3 | MiniCPM | Higher timeframe context (15min / daily chart read) | 1-2s |
| 4 | Aggregator | Weighted score from all layers → GO / NO-GO + confidence % | instant |

---

## 📋 TO-DO LIST (Priority Order)

### ✅ DONE
- [x] Gap scanner (5 Pillars — gap %, float, relVol, price range)
- [x] Multi-timeframe chart grid (5min / 1min / 1D / 10s)
- [x] Position sizing with stop-based risk calc
- [x] Paper trading via Alpaca
- [x] YOLO v1-synthetic12 (trained on synthetic charts)
- [x] Screenshot scheduler (takes chart screenshots every 90s)
- [x] 7,665 chart screenshots stored in DB

---

### 🔴 PHASE 1 — Candlestick Training Data (This Week)

- [ ] **1.1** Search Kaggle for labelled candlestick datasets
  - Keywords: "candlestick pattern dataset", "stock candlestick YOLO"
  - Target: hammer, doji, marubozu, engulfing, spinning top, shooting star, shooting star

- [ ] **1.2** Build synthetic candlestick generator
  - Draw individual candle shapes programmatically (PIL/matplotlib)
  - Vary: body size, wick length, colour, background noise
  - Generate 500-1000 examples per candle type
  - Auto-label in YOLO format (.txt files with bboxes)

- [ ] **1.3** Combine Kaggle + synthetic into YOLO training set
  - YOLO format: images/train, images/val, labels/train, labels/val
  - Target: 5,000+ labelled candles across 8-10 types
  - dataset.yaml with class names

---

### 🟡 PHASE 2 — Train YOLO-Candle Model

- [ ] **2.1** Train on AI server (RTX 5060 Ti)
  - Base: YOLOv8n or YOLOv8s (small/fast)
  - Expected time: 30-60 mins
  - Target mAP: >85%

- [ ] **2.2** Evaluate — does it correctly detect candle types on real TradingView screenshots?

- [ ] **2.3** Deploy to yolo-server (replace or run alongside v1-synthetic12)

---

### 🟡 PHASE 3 — Fix MiniCPM Labelling (Offline)

- [ ] **3.1** Fix conda env issue on AI server
  - Option A: Create venv with transformers==4.40 (no /storage pip cache conflict)
  - Option B: Use the yolov8 conda env (has compatible PyTorch, install transformers there)

- [ ] **3.2** Run MiniCPM-V-2 to label all 7,665 existing screenshots overnight

- [ ] **3.3** Review label distribution — are there enough real bull flags to train on?

---

### 🟡 PHASE 4 — Train YOLO-Pattern Model

- [ ] **4.1** Use MiniCPM labels + Kaggle chart patterns as training data
- [ ] **4.2** Train YOLO-Pattern on full 5-min chart screenshots
  - Classes: bull_flag_forming, bull_flag_breakout, bear_flag, orb, no_pattern
- [ ] **4.3** Compare against v1-synthetic12 — is it better on real charts?

---

### 🔵 PHASE 5 — MiniCPM Higher Timeframe Integration

- [ ] **5.1** Fine-tune MiniCPM-V-2 on labelled chart data (LoRA, AI server)
  - Use classified screenshots as training pairs
  - Q: "What pattern is visible?" A: "bull_flag_forming"

- [ ] **5.2** Wire into research server — call MiniCPM on 15min + daily charts
  - Runs as background process (1-2s latency OK for higher TF context)

- [ ] **5.3** Add MiniCPM output to scanner candidate row in dashboard

---

### 🔵 PHASE 6 — Signal Aggregator

- [ ] **6.1** Build aggregator script
  ```
  score = (
    yolo_candle_confidence   * 0.25  +  # right candle types present?
    yolo_pattern_confidence  * 0.40  +  # pattern detected?
    minicpm_context_score    * 0.20  +  # higher TF agrees?
    five_pillars_score       * 0.15     # scanner fundamentals
  )
  if score > 0.75: signal = "GO"
  ```

- [ ] **6.2** Add signal score to dashboard scanner row
- [ ] **6.3** Fire Telegram alert when score > threshold
- [ ] **6.4** Auto paper trade when score > 0.85 (with position sizing)

---

### 🔵 PHASE 7 — RC Knowledge Capture

- [ ] **7.1** Add Apify credits → scrape Ross Cameron YouTube recaps
  - Extract frames where RC highlights a bull flag setup
  - Label those frames → gold standard training data

- [ ] **7.2** Retrain all models on RC-verified examples
  - These are the highest quality labels we can get

- [ ] **7.3** Build "RC Score" — how closely does this setup match RC's historical trades?

---

## 🎯 IMMEDIATE NEXT STEPS (Do Now)

1. **Kaggle search** — find candlestick datasets
2. **Synthetic candle generator** — build script, generate 5,000 candles
3. **Fix MiniCPM env** — try yolov8 conda env instead of wan2gp
4. **Update dashboard** — show which layer triggered the signal

---

## 📊 DATA SOURCES

| Source | Data | Status |
|--------|------|--------|
| Scanner DB | 7,665 chart screenshots (unlabelled) | ✅ Ready |
| Alpaca | Live/paper price data | ✅ Ready |
| EODHD | News + fundamentals | ✅ Ready |
| TraderTom charts | 7,662 index charts | ❌ Wrong style |
| Kaggle | Labelled candlestick patterns | 🔲 To download |
| RC YouTube | Real bull flag setups | 🔲 Awaiting Apify credits |

---

## 💡 KEY INSIGHT (from Kelvin)

> "Individual candlestick shapes feed into patterns. YOLO detects shapes,
> patterns emerge from combinations, MiniCPM reads the bigger picture.
> 2-5 detection signals fused into one GO/NO-GO."

This is the architecture. Each layer is simple and trainable separately.
The intelligence comes from combining them.
