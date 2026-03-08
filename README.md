# DayTradeDash.ai 🚀

> **Self-learning AI trading intelligence platform** — computer vision pattern recognition trained on verified professional trader records, with a live gap scanner, composite signal scoring, and a weekly self-improving feedback loop.

[![Status](https://img.shields.io/badge/status-active_development-green)](#)
[![Stack](https://img.shields.io/badge/stack-Python%20%7C%20React%20%7C%20YOLOv8%20%7C%20FastAPI-blue)](#)
[![GPU](https://img.shields.io/badge/GPU-RTX_5060_Ti_16GB-76B900)](#)
[![License](https://img.shields.io/badge/license-Private-red)](#)

---

## 🧠 What Is This?

DayTradeDash is built on a simple but powerful idea:

> **Don't code the rules. Learn from the winners.**

Instead of manually programming trading signals, we extract the **visual fingerprint** of proven winning setups directly from traders with documented, audited track records. YOLOv8 learns what a Ross Cameron bull flag looks like. What a Tom Hougaard DAX entry looks like. What the School Run setup looks like. Then it hunts for the same setups — live — every 90 seconds.

Every trade outcome feeds back into the model. Every week it retrains. Every week it gets sharper.

---

## ✅ Current Status (v0.1)

| Component | Status |
|-----------|--------|
| Gap Scanner (EODHD real-time) | ✅ Live |
| WebSocket bridge | ✅ Live |
| Research Server API | ✅ Live |
| React Dashboard (:3456) | ✅ Live |
| Column filters on scanner table | ✅ Live |
| 3-tier alert watchdog (Telegram + SMS) | ✅ Live |
| SQLite DB — 251 candidates / 27 days | ✅ Live |
| TraderTom CSV — 5,054 trades | ✅ In hand |
| PRD v2.0 | ✅ Complete |
| Build Plan | ✅ Complete |
| YOLOv8 vision engine | 🔧 In development |
| Chart generator (mplfinance) | 🔧 In development |
| Training Lab UI | 🔧 In development |
| Ross Cameron data pipeline | 🔧 Planned |
| Self-learning retrain loop | 🔧 Planned |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  pai-server (192.168.55.203)                                │
│                                                             │
│  ┌─────────────────┐  ┌──────────────┐  ┌───────────────┐ │
│  │  Gap Scanner    │  │  Research    │  │  Dashboard    │ │
│  │  EODHD :8765   │→ │  Server :8767│→ │  React :3456  │ │
│  └─────────────────┘  └──────────────┘  └───────────────┘ │
│           │                                      ↑          │
│  ┌─────────────────┐  ┌──────────────┐           │         │
│  │  Screenshot     │  │  Vision API  │           │         │
│  │  Scheduler      │→ │  :8769       │───────────┘         │
│  └─────────────────┘  └──────────────┘                     │
│                               │                             │
└───────────────────────────────┼─────────────────────────────┘
                                │ SSH / LAN
┌───────────────────────────────┼─────────────────────────────┐
│  ai-server (192.168.55.231)   │  RTX 5060 Ti 16GB           │
│                               ↓                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  YOLOv8 Inference Server :8770                      │   │
│  │  Fine-tuning Pipeline (weekly, Sunday 1am)          │   │
│  │  Model Storage: /mnt/ai_storage/models/daytrade-ai/ │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 👤 Trader Data Sources

### TraderTom (Tom Hougaard) — PRIMARY ✅
- **5,054 verified trades** (Jan 2021 – Apr 2024)
- Instruments: DAX, DOW, FTSE, NASDAQ
- Win rate: **56.84%** | Total P&L: **£1,951,006**
- Avg hold: 26.4 minutes
- Data: `all_trades.csv` — exact entry time, direction, exit, P&L per trade
- Usage: Render ±10 bar windows around each entry → labeled chart images → YOLOv8 training

### Ross Cameron (Warrior Trading) — GOLD STANDARD US SMALL CAPS
- Verified track record: **$583 → $12.5M+**
- Trades low-float small caps (gap >10%, float <10M, relvol >5x)
- Data source: warriortrading.com public trade log (8 years)
- Usage: Match green/red days to EODHD top gappers → render ±10 bar charts → labeled training data

### School Run Strategy — OUR OWN
- DAX opening range breakout
- Entry: 08:00 London, exit: 09:30
- Data: Backtest results from Pine Script
- Usage: Adds ORB pattern class to model

### Jay — TBC
- Trader identity pending confirmation
- Will follow same extraction pipeline as above

---

## 🤖 YOLOv8 Detection Classes

```yaml
0: bull_flag_forming        # Pole formed, consolidating — watch
1: bull_flag_breakout       # Green candle above flag high — BUY
2: bear_flag                # Short opportunity
3: opening_range_break_long # ORB long (School Run)
4: opening_range_break_short
5: macd_bullish_cross       # MACD line crosses signal upward
6: macd_bearish_cross       # MACD line crosses signal downward
7: macd_histogram_surge     # Histogram expanding — momentum
8: no_pattern               # Background / noise
```

---

## 📊 Composite Signal Score (0–100)

Every live scanner candidate receives a single actionable score:

| Signal | Weight |
|--------|--------|
| YOLOv8 visual pattern confidence | 30% |
| Ross Cameron match score | 20% |
| Tom Hougaard match score | 15% |
| Volume profile (surge/flag/breakout) | 20% |
| MACD confirmation | 10% |
| Time of day weighting | 5% |

- **≥ 80** → 🔴 Telegram alert + Chatterbox audio + screenshot with bounding boxes
- **60–79** → 🟡 Dashboard badge only
- **< 60** → ⚪ Scanner list, no alert

---

## 🔄 Self-Learning Feedback Loop

```
Scanner detects candidate
        ↓
Score > 6 → Screenshot TradingView 5-min chart
        ↓
YOLOv8 inference → bounding boxes + confidence
        ↓
Composite score calculated → alert if ≥ 80
        ↓
Trade taken or skipped → outcome recorded
        ↓
Sunday 1am → auto-retrain on ai-server
        ↓
New model deployed if mAP improved
        ↓
Telegram: "Model v1.4 | mAP: 77% (+2.1%) | 1,247 examples"
```

---

## 🗂️ Repository Structure

```
DayTradeDash/
├── docs/
│   ├── PRD-DAYTRADE-AI.md          Full product requirements (v2.0)
│   └── DAYTRADE-AI-BUILDPLAN.md    Week-by-week execution plan
├── dashboard/
│   ├── src/main.jsx                React dashboard (single file)
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── bin/                            (symlinked from /home/pai-server/bin/)
│   ├── rc-gap-scanner.py           EODHD gap scanner
│   ├── rc-ws-bridge.py             WebSocket broadcast
│   ├── rc-research-server.py       REST API
│   └── trading-watchdog.py         Health monitor + alerts
├── scripts/                        (planned)
│   ├── generate-charts.py          mplfinance chart renderer
│   ├── rc-log-scraper.py           Ross Cameron trade log scraper
│   ├── yolo-server.py              FastAPI inference server (ai-server)
│   └── retrain.py                  Weekly retrain pipeline
├── docs/
├── scanner-config.json
├── watchlist.json
└── README.md
```

---

## 🛣️ Roadmap

### Phase 1 — Foundation (Week 1) 🔧 In Progress
- [ ] YOLOv8 conda env on ai-server
- [ ] Download foduucom base model (HuggingFace)
- [ ] mplfinance TradingView-style chart generator
- [ ] Generate 5,054 TraderTom labeled chart images
- [ ] First YOLOv8 fine-tune (~25 mins, RTX 5060 Ti)
- [ ] `yolo-server` FastAPI endpoint on ai-server
- [ ] `pattern_events` + `trader_charts` DB tables

### Phase 2 — Live Vision Pipeline (Week 1–2)
- [ ] `screenshot-scheduler` systemd service
- [ ] `vision-api` orchestration layer (:8769)
- [ ] Dashboard: confidence badge per scanner row
- [ ] Dashboard: MACD/bull flag bounding box overlay with toggle
- [ ] Dashboard: Training Lab tab (keyboard shortcuts for labeling)
- [ ] Telegram alert with annotated screenshot
- [ ] Chatterbox TTS audio alerts ("RIME forming clean flag, 82% confidence")

### Phase 3 — Ross Cameron + Multi-Trader Data (Week 2)
- [ ] Ross Cameron trade log scraper (warriortrading.com)
- [ ] Match RC dates → EODHD top gappers → render ±10 bar charts
- [ ] RC Match Score column in scanner table
- [ ] School Run backtest → chart images
- [ ] Fine-tune v1.1 with ~7,000 images (Tom + RC + School Run + synthetic)
- [ ] Jay trader data (pending confirmation)

### Phase 4 — Self-Learning Loop (Week 3)
- [ ] Trade outcome auto-recording
- [ ] Automated Sunday 1am retrain pipeline on ai-server
- [ ] Model versioning + rollback (keep 5 versions)
- [ ] AI Model health tab in dashboard
- [ ] Full fine-tuning settings panel in dashboard

### Phase 5 — Intelligence Layer (Week 4+)
- [ ] Composite signal score live on all candidates
- [ ] Tom Hougaard match score live
- [ ] Multi-timeframe confluence (1-min + 5-min bull flag)
- [ ] Skip recommendations (bear flag = ⛔ don't trade)
- [ ] P&L attribution by signal source
- [ ] Portfolio heat — refuse signals if already in 2+ trades
- [ ] Regime detection — bull/bear/chop classifier adjusts thresholds
- [ ] Paper trading auto-evaluation track (parallel to live)

### Phase 6 — Product (Future)
- [ ] DayTradeDash.ai domain + landing page
- [ ] Mobile Trading Lab — label screenshots on the go
- [ ] Multi-user support (separate model per user)
- [ ] Community signals — anonymised composite scores
- [ ] SaaS packaging — subscription model

---

## 🔧 Setup

### Requirements
- Python 3.11+
- Node 22+
- EODHD API key (EOD+Intraday plan, $29.99/mo)
- AI server with CUDA GPU (RTX 5060 Ti or better)

### Services (pai-server)
```bash
systemctl --user start daytrade-dash        # Dashboard :3456
systemctl --user start rc-ws-bridge          # WebSocket :8765
systemctl --user start rc-research-server    # REST API :8767
systemctl --user start trading-watchdog      # Health monitor
systemctl --user start rc-gap-scanner        # Market hours only
```

### Dashboard
```bash
cd dashboard && npm install && npm run dev   # Dev
npm run build                                # Production
```

---

## 📈 Performance Targets

| Metric | Target |
|--------|--------|
| Bull flag precision | >75% |
| False positive rate | <30% |
| Screenshot → alert latency | <10s |
| Model weekly improvement | +2–5% mAP |
| Training dataset (12 weeks) | 8,000+ labeled images |

---

## 🔐 Security

- Repository: **Private**
- No API keys, secrets, or credentials committed (see `.gitignore`)
- All secrets stored in `~/.secrets/` on pai-server
- Database excluded from repo (backup copies in `/home/pai-server/trading/backups/`)
- Model weights stored on ai-server only

---

## 👨‍💻 Built By

**Kelvin Lee** — AI Technologist, Wolverhampton Science Park
**Nova (NovaPAI)** — Lead developer & architect

*"Don't code the rules. Learn from the winners."*

---

> ⚠️ **Disclaimer:** This software is for educational and research purposes. Trading involves significant risk of loss. Past performance of any trader or strategy does not guarantee future results.
