#!/usr/bin/env python3
"""
Batch processor — send TraderTom chart JPGs through YOLO and store results in pattern_events.
"""
import os, sys, json, sqlite3, glob, threading, time, logging
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import httpx
except ImportError:
    import requests as httpx  # fallback

DB_PATH = "/home/pai-server/trading/rc-scanner.db"
YOLO_URL = "http://192.168.55.231:8770/predict"
TOM_DIR = "/home/pai-server/uploads/TraderTom Live Day Trading"
ERROR_LOG = "/tmp/batch_tom_errors.log"
MAX_WORKERS = 8

# thread-local DB connections
_local = threading.local()

logging.basicConfig(
    filename=ERROR_LOG, filemode="a",
    format="%(asctime)s %(message)s", level=logging.ERROR,
)


def get_db():
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(DB_PATH, timeout=30)
    return _local.conn


def already_processed(filename: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM pattern_events WHERE notes LIKE ? LIMIT 1",
        (f"%{filename}%",),
    ).fetchone()
    return row is not None


def extract_scan_date(folder_name: str) -> str:
    """Convert '2018_01' → '2018-01'."""
    parts = folder_name.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return folder_name


def process_image(filepath: str, idx: int, total: int):
    filename = os.path.basename(filepath)
    folder_name = os.path.basename(os.path.dirname(filepath))
    scan_date = extract_scan_date(folder_name)

    # Skip if already in DB
    if already_processed(filename):
        return {"status": "skipped", "file": filename}

    # Read image bytes
    with open(filepath, "rb") as f:
        img_bytes = f.read()

    # Call YOLO
    try:
        if hasattr(httpx, "Client"):  # httpx library
            r = httpx.post(
                YOLO_URL,
                files={"file": (filename, img_bytes, "image/jpeg")},
                timeout=30,
            )
        else:  # requests fallback
            r = httpx.post(
                YOLO_URL,
                files={"file": (filename, img_bytes, "image/jpeg")},
                timeout=30,
            )
        r.raise_for_status()
        yolo = r.json()
    except Exception as e:
        logging.error(f"YOLO failed for {filepath}: {e}")
        return {"status": "error", "file": filename, "error": str(e)}

    preds = yolo.get("predictions", [])
    if preds:
        best = max(preds, key=lambda x: x.get("confidence", 0))
        pattern = best.get("class", "no_pattern")
        confidence = best.get("confidence", 0.0)
    else:
        pattern = "no_pattern"
        confidence = 0.0

    # Insert into DB
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute(
        """INSERT INTO pattern_events
           (ticker, detected_at, scan_date, pattern, confidence, screenshot, bboxes, model_ver, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "TOMCHART",
            now,
            scan_date,
            pattern,
            confidence,
            img_bytes,
            json.dumps(preds),
            "v1-synthetic12",
            f"tradertom:{filename}",
        ),
    )
    conn.commit()
    return {"status": "ok", "file": filename, "pattern": pattern, "confidence": confidence}


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # 0 = all

    # Gather all JPGs
    all_jpgs = sorted(glob.glob(os.path.join(TOM_DIR, "**", "*.jpg"), recursive=True))
    total = len(all_jpgs)
    print(f"Found {total} JPG files in TraderTom directory")

    if limit:
        all_jpgs = all_jpgs[:limit]
        total = len(all_jpgs)
        print(f"  (limited to first {total} for this run)")

    processed = 0
    skipped = 0
    errors = 0
    pattern_counts = {}
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(process_image, fp, i, total): fp
            for i, fp in enumerate(all_jpgs)
        }
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                errors += 1
                logging.error(f"Unhandled: {futures[future]}: {e}")
                continue

            processed += 1
            if result["status"] == "skipped":
                skipped += 1
            elif result["status"] == "error":
                errors += 1
            else:
                pat = result.get("pattern", "unknown")
                pattern_counts[pat] = pattern_counts.get(pat, 0) + 1

            if processed % 100 == 0:
                pct = processed / total * 100
                print(f"Progress: {processed}/{total} ({pct:.1f}%)")

    elapsed = time.time() - t0

    print(f"\n{'='*50}")
    print(f"DONE in {elapsed:.1f}s")
    print(f"  Processed: {processed}  Skipped: {skipped}  Errors: {errors}")
    print(f"\nPattern distribution:")
    for pat, cnt in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        print(f"  {pat}: {cnt}")


if __name__ == "__main__":
    main()
