#!/usr/bin/env python3
"""
Auto-labeller for pattern_events screenshots.
Uses GPT-4o-mini vision to classify each TradingView chart screenshot.
Runs as background job — resumes from where it left off.
"""
import sqlite3, json, base64, time, sys, os, logging
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH   = "/home/pai-server/trading/rc-scanner.db"
LOG_PATH  = "/tmp/auto-label.log"
BATCH     = 5          # concurrent API calls per batch
SLEEP     = 1.5        # seconds between batches (rate limit)
MODEL     = "gpt-4o-mini"
MAX_ERRORS= 10         # abort if too many consecutive errors

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ── OpenAI key ────────────────────────────────────────────────────────────────
def get_openai_key():
    cfg = json.load(open("/home/pai-server/.openclaw/openclaw.json"))
    return cfg["models"]["providers"]["openai"]["apiKey"]

# ── Classification prompt ──────────────────────────────────────────────────────
SYSTEM = """You are a stock chart pattern expert specialising in small-cap day trading patterns used by Ross Cameron / Warrior Trading.

Classify the chart screenshot into EXACTLY ONE of these labels (respond with only the label, nothing else):
- bull_flag_forming   : Strong upward move (pole), then 2-4 small pullback candles, not yet broken out
- bull_flag_breakout  : Bull flag pattern that has just broken out above the flag to new highs
- bear_flag           : Strong downward move, then small upward consolidation, bearish
- orb                 : Opening Range Breakout — price breaking above/below the first 5-15 minute range
- macd_bullish_cross  : MACD line crossing above signal line with visible momentum
- no_pattern          : None of the above, random price action, or chart is unclear

Be decisive. If unsure, pick the closest match or no_pattern."""

USER = "Classify this stock chart screenshot using exactly one of the specified labels."

def classify_image(img_bytes, openai_key):
    """Send image to GPT-4o-mini, return label string."""
    import urllib.request, urllib.error
    b64 = base64.b64encode(img_bytes).decode()
    payload = {
        "model": MODEL,
        "max_tokens": 20,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": USER},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"}}
            ]}
        ]
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            label = data["choices"][0]["message"]["content"].strip().lower()
            # Validate
            valid = {"bull_flag_forming","bull_flag_breakout","bear_flag","orb","macd_bullish_cross","no_pattern"}
            # Fuzzy match
            for v in valid:
                if v in label:
                    return v
            return "no_pattern"
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 429:
            log.warning("Rate limited — sleeping 60s")
            time.sleep(60)
            return None
        log.error(f"HTTP {e.code}: {body[:200]}")
        return None
    except Exception as ex:
        log.error(f"API error: {ex}")
        return None

def main():
    log.info("=== Auto-labeller starting ===")
    key = get_openai_key()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    # Count work
    total   = conn.execute("SELECT COUNT(*) FROM pattern_events WHERE screenshot IS NOT NULL").fetchone()[0]
    done    = conn.execute("SELECT COUNT(*) FROM pattern_events WHERE human_label IS NOT NULL AND human_label != ''").fetchone()[0]
    remaining = total - done
    log.info(f"Total: {total} | Already labelled: {done} | Remaining: {remaining}")

    if remaining == 0:
        log.info("All done! Nothing to label.")
        return

    errors = 0
    processed = 0
    start = time.time()

    while True:
        # Fetch next batch of unlabelled
        rows = conn.execute("""
            SELECT id, ticker, pattern, confidence, screenshot
            FROM pattern_events
            WHERE screenshot IS NOT NULL
              AND (human_label IS NULL OR human_label = '')
            ORDER BY confidence DESC, detected_at ASC
            LIMIT ?
        """, (BATCH,)).fetchall()

        if not rows:
            log.info("All done!")
            break

        for row in rows:
            rid    = row["id"]
            ticker = row["ticker"]
            yolo   = row["pattern"]
            conf   = row["confidence"]

            # High confidence: trust YOLO directly
            if conf and conf >= 0.75 and yolo in ("bull_flag_forming","bull_flag_breakout","bear_flag","orb","macd_bullish_cross","no_pattern"):
                label = yolo
                log.info(f"[{rid}] {ticker} — auto-trusted YOLO: {label} ({conf:.2f})")
            else:
                label = classify_image(bytes(row["screenshot"]), key)
                if label is None:
                    errors += 1
                    if errors >= MAX_ERRORS:
                        log.error("Too many errors — aborting")
                        return
                    time.sleep(5)
                    continue
                errors = 0
                log.info(f"[{rid}] {ticker} — GPT: {label} (YOLO was {yolo} @ {conf:.2f})")

            conn.execute(
                "UPDATE pattern_events SET human_label=? WHERE id=?",
                (label, rid)
            )
            conn.commit()
            processed += 1

            # Progress report every 100
            if processed % 100 == 0:
                elapsed = time.time() - start
                rate = processed / elapsed
                remaining_est = (remaining - processed) / rate if rate > 0 else 0
                log.info(f"Progress: {done+processed}/{total} | Rate: {rate:.1f}/s | ETA: {remaining_est/60:.0f}min")

        time.sleep(SLEEP)

    elapsed = time.time() - start
    log.info(f"=== Complete! {processed} labelled in {elapsed/60:.1f} minutes ===")

    # Final stats
    stats = conn.execute("""
        SELECT human_label, COUNT(*) as cnt
        FROM pattern_events WHERE human_label IS NOT NULL
        GROUP BY human_label ORDER BY cnt DESC
    """).fetchall()
    log.info("Label distribution:")
    for s in stats:
        log.info(f"  {s['human_label']}: {s['cnt']}")
    conn.close()

if __name__ == "__main__":
    main()
