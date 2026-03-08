#!/usr/bin/env python3
import os,json,time,sqlite3,urllib.request,datetime,subprocess

KEY=open(os.path.expanduser('~/.secrets/eodhd-api')).read().strip()
import os as _os
BOT_TOKEN = _os.path.expanduser and open(_os.path.expanduser("~/.secrets/telegram-signals-bot")).read().strip()
CHAT_ID = "1486798034"  # noqa - not a secret, chat ID is not sensitive
LOG="/tmp/bt.log"

def log(msg):
    with open(LOG,'a') as f: f.write(msg+'\n')
    print(msg,flush=True)

def tg(msg):
    try:
        data=json.dumps({"chat_id":CHAT,"text":msg}).encode()
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{BOT}/sendMessage",
            data=data,headers={"Content-Type":"application/json"}),timeout=5)
    except: pass

def tg_photo(path,cap):
    subprocess.run(["curl","-s","-X","POST",
        f"https://api.telegram.org/bot{BOT}/sendPhoto",
        "-F",f"chat_id={CHAT}","-F",f"photo=@{path}","-F",f"caption={cap}"],
        capture_output=True)

def get_bars(ticker,date_str):
    url=f'https://eodhd.com/api/intraday/{ticker}.US?interval=1m&api_token={KEY}&fmt=json'
    try:
        with urllib.request.urlopen(url,timeout=20) as r: raw=json.loads(r.read())
        target=datetime.datetime.strptime(date_str,'%Y-%m-%d').date()
        bars=[]
        for b in raw:
            ts=datetime.datetime.fromtimestamp(b['timestamp'],tz=datetime.timezone.utc)
            if ts.date()!=target: continue
            eh=(ts.hour-4)%24; em=ts.minute
            if (eh==9 and em>=30) or eh==10 or (eh==11 and em<=30):
                bars.append({'t':f'{eh}:{em:02d}','o':float(b['open']),'h':float(b['high']),'l':float(b['low']),'c':float(b['close'])})
        del raw; return bars
    except: return []

def find_setup(bars):
    if len(bars)<6: return None
    op=bars[0]['o']
    if op<=0: return None
    si,sh=0,0
    for i,b in enumerate(bars[:60]):
        if b['h']>sh: sh,si=b['h'],i
    if (sh-op)/op<0.03: return None
    pb=[]
    for b in bars[si+1:si+12]:
        if b['c']<=b['o']: pb.append(b)
        elif len(pb)>=2: break
    if not pb: return None
    pb_low=min(b['l'] for b in pb)
    if pb_low<op+(sh-op)*0.3: return None
    trigger_h=max(b['h'] for b in pb)
    for b in bars[si+1+len(pb):si+1+len(pb)+8]:
        if b['c']>b['o'] and b['c']>trigger_h:
            entry=round(b['c']+0.02,4); stop=pb_low; risk=round(entry-stop,4)
            if risk<=0 or risk>entry*0.30: continue
            return {'entry':entry,'stop':stop,'target':round(entry+risk*2,4),'risk':risk,'time':b['t'],'surge':round((sh-op)/op*100,1)}
    return None

def simulate(bars,setup):
    go=False
    for b in bars:
        if b['t']==setup['time']: go=True; continue
        if not go: continue
        if b['h']>=setup['target']: return 'win',setup['target']
        if b['l']<=setup['stop']: return 'loss',setup['stop']
    return 'timeout',bars[-1]['c'] if bars else setup['entry']

open(LOG,'w').close()
con=sqlite3.connect('/home/pai-server/trading/rc-scanner.db')
candidates=con.execute('SELECT ticker,scan_date,gap_pct,float_m FROM candidates ORDER BY scan_date,ticker').fetchall()
con.close()

log(f"Starting backtest: {len(candidates)} candidates")
tg(f"🔁 Backtest starting — {len(candidates)} candidates\nProgress updates every 50 tickers")

results=[]; no_data=0; no_setup=0

for i,(ticker,date,gap,flt) in enumerate(candidates):
    bars=get_bars(ticker,date)
    if not bars: no_data+=1; time.sleep(0.5); continue
    setup=find_setup(bars)
    if not setup: no_setup+=1; time.sleep(0.3); continue
    outcome,exit_p=simulate(bars,setup)
    shares=max(1,int(120/setup['entry']))
    pnl=round((exit_p-setup['entry'])*shares,2)
    results.append({'ticker':ticker,'date':date,'gap':gap,'float':flt,
        'entry':setup['entry'],'stop':setup['stop'],'target':setup['target'],
        'exit':round(exit_p,4),'shares':shares,'outcome':outcome,'pnl':pnl,'surge':setup['surge']})
    flag='WIN' if outcome=='win' else('LOSS' if outcome=='loss' else'TIMEOUT')
    log(f"[{i+1}/{len(candidates)}] {ticker} {date} gap={gap}% surge={setup['surge']}% -> {flag} ${pnl:+.2f}")
    if (i+1)%50==0:
        w=len([r for r in results if r['outcome']=='win'])
        tg(f'Progress: {i+1}/{len(candidates)} | Setups: {len(results)} | Wins: {w}')
    time.sleep(0.5)

with open('/tmp/backtest-results.json','w') as f: json.dump(results,f,indent=2)
log(f"COMPLETE: {len(results)} trades found")

if not results:
    tg(f"⚠️ Done — 0 setups found\nNo data: {no_data} | No setup: {no_setup}")
else:
    wins=[r for r in results if r['outcome']=='win']
    losses=[r for r in results if r['outcome']=='loss']
    timeouts=[r for r in results if r['outcome']=='timeout']
    wr=round(len(wins)/len(results)*100,1)
    total=round(sum(r['pnl'] for r in results),2)
    avg_w=round(sum(r['pnl'] for r in wins)/len(wins),2) if wins else 0
    avg_l=round(sum(r['pnl'] for r in losses)/len(losses),2) if losses else 0
    gw=sum(r['pnl'] for r in wins); gl=abs(sum(r['pnl'] for r in losses))
    pf=round(gw/gl,2) if gl>0 else 'N/A'
    msg=f"""🔁 RC BULL FLAG BACKTEST RESULTS

Candidates : {len(candidates)}
No data    : {no_data} | No setup: {no_setup}
Setups     : {len(results)}
✅ Wins    : {len(wins)} | ❌ Losses: {len(losses)} | ⏱ Timeouts: {len(timeouts)}
Win Rate   : {wr}%
Total P&L  : ${total:+.2f}
Avg Win    : ${avg_w:+.2f} | Avg Loss: ${avg_l:+.2f}
Profit Fac : {pf}x\n\nBy Float:"""
    for lo,hi,lb in [(0,2,'<2M'),(2,5,'2-5M'),(5,10,'5-10M'),(10,50,'10-50M')]:
        sub=[r for r in results if r['float'] and lo<=r['float']<hi]
        if sub:
            sr=round(len([r for r in sub if r['outcome']=='win'])/len(sub)*100,1)
            msg+=f"\n  {lb}: {len(sub)} trades | {sr}% WR | ${round(sum(r['pnl'] for r in sub),2):+.2f}"
    msg+="\nBy Gap %:"
    for lo,hi,lb in [(10,20,'10-20%'),(20,50,'20-50%'),(50,200,'50-200%'),(200,999,'200%+')]:
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
    plt.suptitle('Ross Cameron Bull Flag Backtest',color='#e2e8f0',fontsize=14,fontweight='bold')
    for ax in axes.flat:
        ax.set_facecolor('#161b2e'); ax.tick_params(colors='#9ca3af')
        for sp in ax.spines.values(): sp.set_edgecolor('#1e2a44')
    cum=df.sort_values('date').pnl.cumsum().reset_index(drop=True)
    axes[0,0].bar(cum.index,cum,color=['#22c55e' if v>=0 else '#ef4444' for v in cum],width=0.8)
    axes[0,0].axhline(0,color='#4b5563',lw=0.8)
    axes[0,0].set_title('Equity Curve',color='#e2e8f0',fontweight='bold')
    axes[0,0].set_ylabel('Cumulative P&L ($)',color='#9ca3af')
    sz=[len(wins),len(losses),len(timeouts)]
    vd=[(s,l,c) for s,l,c in zip(sz,[f'Win({len(wins)})',f'Loss({len(losses)})',f'T/O({len(timeouts)})'],['#22c55e','#ef4444','#6b7280']) if s>0]
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
    for lo,hi,lb in [(10,20,'10-20%'),(20,50,'20-50%'),(50,200,'50-200%'),(200,999,'200%+')]:
        sub=df[(df.gap>=lo)&(df.gap<hi)]
        if len(sub): gl2.append(lb); gp.append(sub.pnl.sum())
    if gl2: axes[1,1].bar(gl2,gp,color=['#22c55e' if p>=0 else '#ef4444' for p in gp])
    axes[1,1].set_title('P&L by Gap %',color='#e2e8f0',fontweight='bold'); axes[1,1].set_ylabel('P&L ($)',color='#9ca3af')
    plt.tight_layout()
    plt.savefig('/tmp/backtest-charts.png',dpi=120,bbox_inches='tight',facecolor='#0f1320')
    tg_photo('/tmp/backtest-charts.png',f'RC Bull Flag Charts | {wr}% WR | ${total:+.2f} P&L')
    log("Charts sent to Telegram")
