#!/usr/bin/env python3
import os, json, time, sqlite3, urllib.request, datetime, subprocess
import yfinance as yf

import os as _os
BOT_TOKEN = _os.path.expanduser and open(_os.path.expanduser("~/.secrets/telegram-signals-bot")).read().strip()
CHAT_ID = "1486798034"  # noqa - not a secret, chat ID is not sensitive
LOG="/tmp/bt-yf.log"

def log(msg):
    with open(LOG,'a') as f: f.write(msg+'\n')
    print(msg, flush=True)

def tg(msg):
    try:
        data=json.dumps({"chat_id":CHAT,"text":msg}).encode()
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{BOT}/sendMessage",
            data=data, headers={"Content-Type":"application/json"}), timeout=5)
    except: pass

def tg_photo(path, cap):
    subprocess.run(["curl","-s","-X","POST",
        f"https://api.telegram.org/bot{BOT}/sendPhoto",
        "-F",f"chat_id={CHAT}","-F",f"photo=@{path}","-F",f"caption={cap}"],
        capture_output=True)

def get_bars_5m(ticker, date_str):
    """Get 5-min bars for ticker on date_str, filtered to 9:30-11:30 ET."""
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(interval="5m", period="60d")
        if df.empty: return []
        # Filter to target date and 9:30-11:30 ET
        target = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        bars = []
        for ts, row in df.iterrows():
            # yfinance returns tz-aware timestamps
            local_ts = ts.tz_convert('America/New_York') if ts.tzinfo else ts
            if local_ts.date() != target: continue
            h, m = local_ts.hour, local_ts.minute
            if (h == 9 and m >= 30) or h == 10 or (h == 11 and m <= 30):
                bars.append({
                    't': f'{h}:{m:02d}',
                    'o': round(float(row['Open']),4),
                    'h': round(float(row['High']),4),
                    'l': round(float(row['Low']),4),
                    'c': round(float(row['Close']),4)
                })
        return bars
    except: return []

def find_bull_flag(bars):
    """
    Ross Cameron 5-min bull flag:
    1. Strong surge candle (green, big body, 5%+ move)
    2. 2-4 red consolidation candles holding above 50% of surge
    3. Entry: green candle breaking above flag high
    """
    if len(bars) < 5: return None
    op = bars[0]['o']
    if op <= 0: return None

    # Find the surge — look for a strong green candle in first 12 bars (first hour)
    for si in range(len(bars)-4):
        b = bars[si]
        if b['c'] <= b['o']: continue  # must be green
        body = b['c'] - b['o']
        surge_pct = body / max(b['o'], 0.01) * 100
        if surge_pct < 5: continue  # need 5%+ body

        # Pullback: next 2-5 bars mostly red, tight consolidation
        pb = []
        for b2 in bars[si+1:si+6]:
            if b2['c'] <= b2['o']:
                pb.append(b2)
            else:
                break
        if len(pb) < 1: continue

        flag_low  = min(b2['l'] for b2 in pb)
        flag_high = max(b2['h'] for b2 in pb)
        surge_top = b['h']
        surge_bot = b['o']

        # Flag must hold above 50% of surge candle body
        midpoint = surge_bot + (surge_top - surge_bot) * 0.5
        if flag_low < midpoint: continue

        # Flag range must be tight (< 5% of price)
        flag_range = flag_high - flag_low
        if flag_range > b['c'] * 0.05: continue

        # Entry: first green candle that breaks above flag high
        for b3 in bars[si+1+len(pb):si+1+len(pb)+5]:
            if b3['c'] > b3['o'] and b3['h'] > flag_high:
                entry = round(b3['c'] + 0.02, 4)
                stop  = round(flag_low - 0.01, 4)
                risk  = round(entry - stop, 4)
                if risk <= 0 or risk > entry * 0.25: continue
                return {
                    'entry': entry, 'stop': stop,
                    'target': round(entry + risk*2, 4),
                    'risk': risk, 'time': b3['t'],
                    'surge_pct': round(surge_pct, 1)
                }
    return None

def simulate(bars, setup):
    in_trade = False
    for b in bars:
        if b['t'] == setup['time']: in_trade = True; continue
        if not in_trade: continue
        if b['h'] >= setup['target']: return 'win', setup['target']
        if b['l'] <= setup['stop']:   return 'loss', setup['stop']
    return 'timeout', bars[-1]['c'] if bars else setup['entry']

# Load candidates
open(LOG,'w').close()
con = sqlite3.connect('/home/pai-server/trading/rc-scanner.db')
candidates = con.execute(
    'SELECT ticker, scan_date, gap_pct, float_m FROM candidates ORDER BY scan_date, ticker'
).fetchall()
con.close()

log(f"RC Bull Flag Backtest (5-min yfinance) — {len(candidates)} candidates")
tg(f"🏁 RC Bull Flag Backtest (5-min yfinance)\n{len(candidates)} candidates — ~15 mins")

results=[]; no_data=0; no_setup=0

for i, (ticker, date, gap, flt) in enumerate(candidates):
    bars = get_bars_5m(ticker, date)
    if not bars:
        no_data += 1
        time.sleep(0.3)
        continue
    setup = find_bull_flag(bars)
    if not setup:
        no_setup += 1
        time.sleep(0.1)
        continue
    outcome, exit_p = simulate(bars, setup)
    shares = max(1, int(120 / setup['entry']))
    pnl = round((exit_p - setup['entry']) * shares, 2)
    results.append({
        'ticker':ticker,'date':date,'gap':gap,'float':flt,
        'entry':setup['entry'],'stop':setup['stop'],'target':setup['target'],
        'exit':round(exit_p,4),'shares':shares,'outcome':outcome,'pnl':pnl,
        'surge':setup['surge_pct']
    })
    flag = 'WIN' if outcome=='win' else ('LOSS' if outcome=='loss' else 'TIMEOUT')
    log(f"[{i+1}/{len(candidates)}] {ticker} {date} gap={gap}% surge={setup['surge_pct']}% -> {flag} ${pnl:+.2f}")
    if (i+1) % 50 == 0:
        w = len([r for r in results if r['outcome']=='win'])
        tg(f"⏳ {i+1}/{len(candidates)} | Setups: {len(results)} | Wins: {w}")
    time.sleep(0.3)

with open('/tmp/bt-yf-results.json','w') as f:
    json.dump(results, f, indent=2)

if not results:
    msg = f"⚠️ Done — 0 setups\nNo data: {no_data} | No setup: {no_setup}"
    log(msg); tg(msg)
else:
    wins=[r for r in results if r['outcome']=='win']
    losses=[r for r in results if r['outcome']=='loss']
    tos=[r for r in results if r['outcome']=='timeout']
    wr=round(len(wins)/len(results)*100,1)
    total=round(sum(r['pnl'] for r in results),2)
    avg_w=round(sum(r['pnl'] for r in wins)/len(wins),2) if wins else 0
    avg_l=round(sum(r['pnl'] for r in losses)/len(losses),2) if losses else 0
    gl=abs(sum(r['pnl'] for r in losses))
    pf=round(sum(r['pnl'] for r in wins)/gl,2) if gl>0 else 'N/A'

    msg=f"""🏁 RC BULL FLAG (5-min) BACKTEST

Candidates : {len(candidates)}
No data    : {no_data} | No setup: {no_setup}
Setups     : {len(results)}
✅ Wins    : {len(wins)}
❌ Losses  : {len(losses)}
⏱ Timeouts: {len(tos)}
Win Rate   : {wr}%
Total P&L  : ${total:+.2f}
Avg Win    : ${avg_w:+.2f}
Avg Loss   : ${avg_l:+.2f}
Profit Fac : {pf}x

By Float:"""
    for lo,hi,lb in [(0,2,'<2M'),(2,5,'2-5M'),(5,10,'5-10M'),(10,50,'10-50M')]:
        sub=[r for r in results if r['float'] and lo<=r['float']<hi]
        if sub:
            sr=round(len([r for r in sub if r['outcome']=='win'])/len(sub)*100,1)
            msg+=f"\n  {lb}: {len(sub)} trades | {sr}% WR | ${round(sum(r['pnl'] for r in sub),2):+.2f}"
    msg+="\nBy Gap %:"
    for lo,hi,lb in [(10,20,'10-20%'),(20,50,'20-50%'),(50,200,'50%+')]:
        sub=[r for r in results if lo<=(r['gap'] or 0)<hi]
        if sub:
            sr=round(len([r for r in sub if r['outcome']=='win'])/len(sub)*100,1)
            msg+=f"\n  {lb}: {len(sub)} trades | {sr}% WR | ${round(sum(r['pnl'] for r in sub),2):+.2f}"
    log(msg); tg(msg)

    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt, pandas as pd
    df=pd.DataFrame(results)
    fig,axes=plt.subplots(2,2,figsize=(14,9))
    fig.patch.set_facecolor('#0f1320')
    plt.suptitle('RC Bull Flag 5-min Backtest',color='#e2e8f0',fontsize=14,fontweight='bold')
    for ax in axes.flat:
        ax.set_facecolor('#161b2e'); ax.tick_params(colors='#9ca3af')
        for sp in ax.spines.values(): sp.set_edgecolor('#1e2a44')
    cum=df.sort_values('date').pnl.cumsum().reset_index(drop=True)
    axes[0,0].plot(cum.index, cum.values, color='#22c55e' if cum.iloc[-1]>=0 else '#ef4444', linewidth=2)
    axes[0,0].fill_between(cum.index, cum.values, 0, alpha=0.2, color='#22c55e' if cum.iloc[-1]>=0 else '#ef4444')
    axes[0,0].axhline(0,color='#4b5563',lw=0.8)
    axes[0,0].set_title('Equity Curve',color='#e2e8f0',fontweight='bold')
    axes[0,0].set_ylabel('Cumulative P&L ($)',color='#9ca3af')
    sz=[len(wins),len(losses),len(tos)]
    vd=[(s,l,c) for s,l,c in zip(sz,[f'Win({len(wins)})',f'Loss({len(losses)})',f'T/O({len(tos)})'],['#22c55e','#ef4444','#6b7280']) if s>0]
    axes[0,1].pie([v[0] for v in vd],labels=[v[1] for v in vd],colors=[v[2] for v in vd],autopct='%1.0f%%',textprops={'color':'#e2e8f0'})
    axes[0,1].set_title(f'Outcomes — {wr}% WR',color='#e2e8f0',fontweight='bold')
    fl,fp,fw=[],[],[]
    for lo,hi,lb in [(0,2,'<2M'),(2,5,'2-5M'),(5,10,'5-10M'),(10,50,'10-50M')]:
        sub=df[(df['float']>=lo)&(df['float']<hi)]
        if len(sub): fl.append(lb); fp.append(sub.pnl.sum()); fw.append(len(sub[sub.outcome=='win'])/len(sub)*100)
    if fl:
        b2=axes[1,0].bar(fl,fp,color=['#22c55e' if p>=0 else '#ef4444' for p in fp])
        for bar,w in zip(b2,fw): axes[1,0].text(bar.get_x()+bar.get_width()/2,max(bar.get_height(),0)+0.1,f'{w:.0f}%',ha='center',color='#9ca3af',fontsize=9)
    axes[1,0].set_title('P&L by Float',color='#e2e8f0',fontweight='bold'); axes[1,0].set_ylabel('P&L ($)',color='#9ca3af')
    gl2,gp=[],[]
    for lo,hi,lb in [(10,20,'10-20%'),(20,50,'20-50%'),(50,200,'50%+')]:
        sub=df[(df.gap>=lo)&(df.gap<hi)]
        if len(sub): gl2.append(lb); gp.append(sub.pnl.sum())
    if gl2: axes[1,1].bar(gl2,gp,color=['#22c55e' if p>=0 else '#ef4444' for p in gp])
    axes[1,1].set_title('P&L by Gap %',color='#e2e8f0',fontweight='bold'); axes[1,1].set_ylabel('P&L ($)',color='#9ca3af')
    plt.tight_layout()
    plt.savefig('/tmp/bt-yf-charts.png',dpi=120,bbox_inches='tight',facecolor='#0f1320')
    tg_photo('/tmp/bt-yf-charts.png',f'RC Bull Flag 5-min | {wr}% WR | ${total:+.2f}')

log("COMPLETE")
