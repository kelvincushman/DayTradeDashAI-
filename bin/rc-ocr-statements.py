#!/usr/bin/env python3
"""
RC Statement OCR Pipeline — IBM Docling
Extracts daily P&L data from Ross Cameron's Lightspeed broker statement images.
Outputs: rc-trading-days.json + rc-trading-days.csv
"""

import os, sys, json, csv, re
from pathlib import Path
from datetime import datetime

STATEMENTS_DIR = Path('/home/pai-server/trading/rc-data/statements')
OUTPUT_JSON    = Path('/home/pai-server/trading/rc-data/rc-trading-days.json')
OUTPUT_CSV     = Path('/home/pai-server/trading/rc-data/rc-trading-days.csv')

def extract_year_from_filename(fname):
    """Extract year from filename like '2023_October-2023-Profits.png'"""
    m = re.match(r'^(\d{4})_', fname)
    return m.group(1) if m else None

def parse_pl_value(s):
    """Parse P&L string like '10,607.56' or '(-1,299.81)' -> float"""
    s = s.strip().replace(',', '').replace('$', '').replace(' ', '')
    if s.startswith('(') and s.endswith(')'):
        return -float(s[1:-1])
    try:
        return float(s)
    except:
        return None

def parse_date(s, year_hint=None):
    """Parse date like '01/02/2024' or '1/2/24'"""
    for fmt in ['%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y']:
        try:
            return datetime.strptime(s.strip(), fmt).strftime('%Y-%m-%d')
        except:
            continue
    return None

def process_with_docling(image_path):
    """Use Docling to extract table data from broker statement image."""
    from docling.document_converter import DocumentConverter
    
    converter = DocumentConverter()
    result = converter.convert(str(image_path))
    
    # Get markdown representation (preserves table structure)
    md = result.document.export_to_markdown()
    return md

def parse_markdown_table(md, year_hint=None):
    """Parse markdown table from Docling output -> list of day records."""
    records = []
    lines = md.split('\n')
    
    in_table = False
    headers = []
    
    for line in lines:
        line = line.strip()
        if not line:
            in_table = False
            continue
            
        # Detect table rows (contain |)
        if '|' in line:
            cells = [c.strip() for c in line.split('|') if c.strip()]
            
            if not cells:
                continue
                
            # Skip separator rows (---|---|---)
            if all(re.match(r'^-+$', c) for c in cells):
                in_table = True
                continue
            
            # Header row
            if not in_table:
                headers = [c.lower() for c in cells]
                in_table = True
                continue
            
            # Data row — try to identify date + net P&L columns
            if len(cells) < 3:
                continue
            
            # Try first cell as date
            date_str = parse_date(cells[0], year_hint)
            if not date_str:
                continue
            
            # Find gross P&L and net P&L (typically col 4 and col 9)
            # Lightspeed format: Date, EOD Equity, Cash In/Out, Balance, Gross P&L, Commission, Reg Fees, Fee Cost, Other, Net P&L
            gross_pl = None
            net_pl   = None
            
            if len(cells) >= 5:
                gross_pl = parse_pl_value(cells[4])
            if len(cells) >= 10:
                net_pl = parse_pl_value(cells[9])
            elif len(cells) >= 9:
                net_pl = parse_pl_value(cells[-1])
            
            # Skip zero days (not trading)
            if gross_pl == 0 and net_pl == 0:
                continue
            if gross_pl is None and net_pl is None:
                continue
                
            records.append({
                'date':     date_str,
                'gross_pl': gross_pl,
                'net_pl':   net_pl,
                'result':   'Win' if (net_pl or gross_pl or 0) > 0 else 'Loss',
            })
    
    return records

def run():
    from docling.document_converter import DocumentConverter
    print("Docling loaded ✅")

    images = sorted(STATEMENTS_DIR.glob('*.png'))
    # Exclude ad images
    images = [p for p in images if 'ad-free' not in p.name and 'beginner' not in p.name]
    print(f"Processing {len(images)} statement images...")

    all_records = []
    errors = []

    for i, img_path in enumerate(images):
        year = extract_year_from_filename(img_path.name)
        print(f"  [{i+1}/{len(images)}] {img_path.name} (year={year})...", flush=True)
        
        try:
            md = process_with_docling(img_path)
            records = parse_markdown_table(md, year_hint=year)
            
            # Tag each record with source file
            for r in records:
                r['source'] = img_path.name
            
            all_records.extend(records)
            print(f"    → {len(records)} trading days extracted", flush=True)
            
            # Save progress incrementally
            if len(records) > 0:
                print(f"    Sample: {records[0]}", flush=True)
                
        except Exception as e:
            print(f"    ERROR: {e}", flush=True)
            errors.append({'file': img_path.name, 'error': str(e)})

    # Deduplicate by date (take highest |net_pl| if multiple accounts same day)
    by_date = {}
    for r in all_records:
        d = r['date']
        if d not in by_date or abs(r.get('net_pl') or 0) > abs(by_date[d].get('net_pl') or 0):
            by_date[d] = r

    final = sorted(by_date.values(), key=lambda x: x['date'])

    # Save JSON
    with open(OUTPUT_JSON, 'w') as f:
        json.dump({'records': final, 'errors': errors, 'total': len(final)}, f, indent=2)

    # Save CSV
    with open(OUTPUT_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date','gross_pl','net_pl','result','source'])
        writer.writeheader()
        writer.writerows(final)

    # Summary
    wins   = sum(1 for r in final if r['result'] == 'Win')
    losses = sum(1 for r in final if r['result'] == 'Loss')
    total_net = sum(r.get('net_pl') or 0 for r in final)
    
    print(f"\n✅ Done!")
    print(f"   Total trading days: {len(final)}")
    print(f"   Wins: {wins} | Losses: {losses} | WR: {wins/(wins+losses)*100:.1f}%")
    print(f"   Total Net P&L: ${total_net:,.2f}")
    print(f"   Errors: {len(errors)}")
    print(f"   Output: {OUTPUT_JSON}")
    print(f"          {OUTPUT_CSV}")

if __name__ == '__main__':
    run()
