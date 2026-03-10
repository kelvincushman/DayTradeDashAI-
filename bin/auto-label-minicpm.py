#!/usr/bin/env python3
"""
Auto-labeller using MiniCPM-V-2 (local, on AI server GPU).
Classifies pattern_events screenshots — no API costs.

Run on ai-server:
  source ~/miniconda3/bin/activate wan2gp
  python3 /tmp/auto-label-minicpm.py
"""
import sqlite3, json, base64, time, sys, os, logging, io
from pathlib import Path
from datetime import datetime, timezone

DB_PATH  = "/home/pai-server/trading/rc-scanner.db"  # mounted from pai-server
LOG_PATH = "/tmp/auto-label-minicpm.log"
BATCH    = 1   # process one at a time (model handles one image per call)
TRUST_CONF = 0.80  # trust YOLO directly above this confidence

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

LABELS = {
    "bull_flag_forming",
    "bull_flag_breakout",
    "bear_flag",
    "orb",
    "macd_bullish_cross",
    "no_pattern",
}

PROMPT = """You are an expert at identifying stock chart patterns used in day trading.

Look at this 5-minute candlestick chart and classify the CURRENT pattern visible.

Respond with ONLY one of these exact labels (nothing else):
- bull_flag_forming   (strong upward move then 2-4 small pullback candles, not yet broken out)
- bull_flag_breakout  (bull flag that just broke out above flag to new highs)
- bear_flag           (strong downward move then small upward consolidation)
- orb                 (opening range breakout — price breaking above/below first 5-15 min range)
- macd_bullish_cross  (MACD line crossing above signal line with visible momentum)
- no_pattern          (none of the above, unclear, or random price action)

Your answer (one label only):"""

def load_model():
    log.info("Loading MiniCPM-V-2...")
    from transformers import AutoTokenizer, AutoModel
    import torch

    model_name = "openbmb/MiniCPM-V-2"
    log.info(f"Downloading/loading {model_name} ...")
    
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_name,
        trust_remote_code=True,
        torch_dtype=torch.float16,
    ).eval().cuda()
    
    log.info("Model loaded ✅")
    return model, tokenizer

def classify(model, tokenizer, img_bytes):
    from PIL import Image
    import torch
    
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    
    msgs = [{"role": "user", "content": PROMPT}]
    
    res = model.chat(
        image=img,
        msgs=msgs,
        tokenizer=tokenizer,
        sampling=False,
        max_new_tokens=20,
    )
    
    label = res.strip().lower().replace("*","").replace(":","").strip()
    
    # Match to valid label
    for v in LABELS:
        if v in label:
            return v
    
    # Fuzzy matches
    if "bull" in label and "flag" in label:
        return "bull_flag_forming"
    if "bear" in label:
        return "bear_flag"
    if "orb" in label or "opening" in label or "range" in label:
        return "orb"
    if "macd" in label or "momentum" in label:
        return "macd_bullish_cross"
    
    return "no_pattern"

def main():
    log.info("=== MiniCPM-V-2 Auto-labeller starting ===")
    
    # Check DB accessible
    if not os.path.exists(DB_PATH):
        log.error(f"DB not found at {DB_PATH} — is pai-server mounted?")
        sys.exit(1)
    
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    
    total     = conn.execute("SELECT COUNT(*) FROM pattern_events WHERE screenshot IS NOT NULL").fetchone()[0]
    done      = conn.execute("SELECT COUNT(*) FROM pattern_events WHERE human_label IS NOT NULL AND human_label != ''").fetchone()[0]
    remaining = total - done
    log.info(f"Total: {total} | Labelled: {done} | Remaining: {remaining}")
    
    if remaining == 0:
        log.info("All done!")
        return
    
    model, tokenizer = load_model()
    
    processed = 0
    errors    = 0
    start     = time.time()
    
    while True:
        rows = conn.execute("""
            SELECT id, ticker, pattern, confidence, screenshot
            FROM pattern_events
            WHERE screenshot IS NOT NULL
              AND (human_label IS NULL OR human_label = '')
            ORDER BY confidence DESC, detected_at ASC
            LIMIT 10
        """).fetchall()
        
        if not rows:
            break
        
        for row in rows:
            rid  = row["id"]
            tick = row["ticker"]
            yolo = row["pattern"] or "none"
            conf = row["confidence"] or 0.0
            
            # High confidence — trust YOLO
            if conf >= TRUST_CONF and yolo in LABELS:
                label = yolo
                src   = "YOLO"
            else:
                try:
                    label = classify(model, tokenizer, bytes(row["screenshot"]))
                    src   = "MiniCPM"
                    errors = 0
                except Exception as e:
                    log.error(f"[{rid}] {tick} classify error: {e}")
                    errors += 1
                    if errors >= 5:
                        log.error("Too many errors — aborting")
                        return
                    time.sleep(2)
                    continue
            
            conn.execute(
                "UPDATE pattern_events SET human_label=? WHERE id=?",
                (label, rid)
            )
            conn.commit()
            processed += 1
            log.info(f"[{rid}] {tick} → {label} [{src}] (YOLO:{yolo}@{conf:.2f})")
            
            # Progress every 100
            if processed % 100 == 0:
                elapsed = time.time() - start
                rate    = processed / elapsed
                eta_min = (remaining - processed) / rate / 60 if rate > 0 else 0
                log.info(f"── Progress: {done+processed}/{total} | {rate:.1f}/s | ETA {eta_min:.0f}min ──")
    
    elapsed = time.time() - start
    log.info(f"=== Done! {processed} labelled in {elapsed/60:.1f} minutes ===")
    
    # Final stats
    stats = conn.execute("""
        SELECT human_label, COUNT(*) as cnt FROM pattern_events
        WHERE human_label IS NOT NULL
        GROUP BY human_label ORDER BY cnt DESC
    """).fetchall()
    log.info("Label distribution:")
    for s in stats:
        log.info(f"  {s['human_label']}: {s['cnt']}")
    
    conn.close()

if __name__ == "__main__":
    main()
