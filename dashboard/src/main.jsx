import React, { useState, useEffect, useRef, useCallback } from 'react'
import { createRoot } from 'react-dom/client'

document.documentElement.style.colorScheme = 'dark'
document.documentElement.style.background = '#0f1320'

// ── Mobile detection ────────────────────────────────────────────────────────
function useIsMobile() {
  const [mobile, setMobile] = useState(window.innerWidth < 768)
  useEffect(() => {
    const fn = () => setMobile(window.innerWidth < 768)
    window.addEventListener('resize', fn)
    return () => window.removeEventListener('resize', fn)
  }, [])
  return mobile
}

// Inject global mobile CSS
// Mobile CSS is in index.html


// ── Helpers ────────────────────────────────────────────────────────────────

function getMarketStatus() {
  const et = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const h = et.getHours(), m = et.getMinutes(), d = et.getDay()
  if (d === 0 || d === 6) return { text: 'CLOSED', color: '#555', bg: '#1a1a1a' }
  if (h < 4) return { text: 'CLOSED', color: '#555', bg: '#1a1a1a' }
  if (h < 9 || (h === 9 && m < 30)) return { text: 'PRE-MARKET', color: '#f59e0b', bg: '#2a1f00' }
  if (h < 16) return { text: 'MARKET OPEN', color: '#22c55e', bg: '#0a2a0a' }
  if (h < 20) return { text: 'AFTER HOURS', color: '#a78bfa', bg: '#1a0a2a' }
  return { text: 'CLOSED', color: '#555', bg: '#1a1a1a' }
}

function floatColor(fm) {
  if (fm == null) return '#6b7280'
  if (fm < 1) return '#00ffff'; if (fm < 3) return '#00e5cc'; if (fm < 5) return '#00cc99'
  if (fm < 10) return '#00aa66'; if (fm < 20) return '#007744'; return '#9ca3af'
}
function gapGreen(p) {
  if (p == null) return '#6b7280'
  if (p >= 500) return '#00ff44'; if (p >= 100) return '#00cc33'; if (p >= 50) return '#009922'
  if (p >= 20) return '#006611'; if (p >= 10) return '#004400'; return '#9ca3af'
}
function gapColor(p) {
  if (p >= 100) return '#ff1a1a'; if (p >= 50) return '#ff4444'; if (p >= 30) return '#ff7700'
  if (p >= 20) return '#ffaa00'; return '#eab308'
}
function negColor(p) {
  if (p <= -50) return '#ff1a1a'; if (p <= -30) return '#ff4444'; if (p <= -20) return '#ff7700'; return '#f87171'
}
function pnlColor(v) { return v > 0 ? '#22c55e' : v < 0 ? '#ef4444' : '#6b7280' }
function fmt(n, d = 2) { return n != null ? Number(n).toFixed(d) : '—' }
function fmtMoney(n) { return n != null ? '$' + Number(n).toFixed(2) : '—' }
function fmtVol(n) {
  if (n == null) return '—'; if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'; if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K'; return String(n)
}
function fmtTime(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
function fmtTimeShort(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit' })
}
function timeAgo(ts) {
  if (!ts) return '—'
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'; if (mins < 60) return mins + 'm ago'
  const hrs = Math.floor(mins / 60); if (hrs < 24) return hrs + 'h ago'
  return Math.floor(hrs / 24) + 'd ago'
}

const API = (path, opts) => fetch('/' + path, opts).then(r => r.json()).catch(() => null)
const POST = (path, body) => API(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// ── Scanner config ─────────────────────────────────────────────────────────

const SCANNERS = [
  { id: 'lf_high_relvol',    label: 'Low Float · High RelVol',         icon: '🚀', group: 'rc', hot: true },
  { id: 'lf_med_relvol',     label: 'Low Float · Med RelVol',          icon: '⚡', group: 'rc' },
  { id: 'lf_high_relvol_20', label: 'Low Float · High RelVol · $20+',  icon: '💎', group: 'rc' },
  { id: 'former_momo',       label: 'Former Momo Stock',               icon: '🔥', group: 'rc' },
  { id: 'squeeze_5_5',       label: 'Squeeze · +5% in 5min',           icon: '🔴', group: 'squeeze', live: true },
  { id: 'squeeze_10_10',     label: 'Squeeze · +10% in 10min',         icon: '🆘', group: 'squeeze', live: true },
  { id: 'gainers',           label: 'Top Gainers',                     icon: '📈', group: 'watchlist' },
  { id: 'relvol',            label: 'Top Relative Volume',             icon: '📊', group: 'watchlist' },
  { id: 'halt',              label: 'Trading Halt',                    icon: '🛑', group: 'watchlist' },
]

const C = {
  bg: '#0f1320', panel: '#161b2e', rowAlt: '#1a2035', header: '#0f1320',
  border: '#1e2a44', textPrimary: '#e2e8f0', textSecondary: '#9ca3af',
  textMuted: '#6b7280', accent: '#60a5fa', pink: '#e879f9',
}
const mono = "'SF Mono','Cascadia Code','Consolas',monospace"
const sans = "'Inter','Segoe UI',system-ui,-apple-system,sans-serif"

// ── Small components ────────────────────────────────────────────────────────

function ScoutBadge({ status }) {
  const cfg = {
    done: { label: '✅', bg: '#052e16', color: '#22c55e', border: '#166534' },
    pending: { label: '🔬', bg: '#1e1b4b', color: '#818cf8', border: '#3730a3' },
    none: { label: '—', bg: 'transparent', color: '#333', border: 'transparent' },
  }
  const s = cfg[status] || cfg.none
  return <span style={{ background: s.bg, color: s.color, border: '1px solid ' + s.border, padding: '2px 6px', borderRadius: 3, fontSize: 10, fontWeight: 700 }}>{s.label}</span>
}

function RiskRow({ flag, level }) {
  const color = level.includes('CRITICAL') ? '#ef4444' : level.includes('HIGH') ? '#f97316' : level.includes('MEDIUM') ? '#eab308' : '#22c55e'
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 4 }}>
      <span style={{ color, fontSize: 10, fontWeight: 700, whiteSpace: 'nowrap', marginTop: 1 }}>{level.replace(/🔴|🟠|🟢/g, '').trim()}</span>
      <span style={{ fontSize: 11, color: '#94a3b8' }}>{flag}</span>
    </div>
  )
}

function VerdictBadge({ verdict }) {
  if (!verdict) return null
  const color = verdict.startsWith('A') ? '#22c55e' : verdict.startsWith('B') ? '#60a5fa' : verdict.startsWith('C') ? '#f59e0b' : '#ef4444'
  return <span style={{ background: color + '22', color, border: '1px solid ' + color + '55', borderRadius: 4, padding: '3px 10px', fontWeight: 900, fontSize: 14 }}>{verdict}</span>
}

function ResearchPanel({ r }) {
  if (!r) return <div style={{ padding: '20px 24px', color: C.textMuted, fontSize: 13, fontStyle: 'italic' }}>🔬 Stock Scout is researching…</div>
  const risks = typeof r.risk_flags === 'string' ? JSON.parse(r.risk_flags || '[]') : (r.risk_flags || [])
  return (
    <div style={{ padding: '16px 20px', background: C.panel, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 20 }} className="dt-research-grid">
      <div>
        <div style={{ color: C.textMuted, fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>🎯 Catalyst</div>
        <div style={{ fontSize: 12, lineHeight: 1.6, color: C.textPrimary }}>{r.catalyst || 'Unknown'}</div>
        <div style={{ color: C.textMuted, fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8, marginTop: 14 }}>🏢 Company</div>
        <div style={{ fontSize: 12, lineHeight: 1.6, color: C.textPrimary }}>{r.what_it_does || '—'}</div>
        {r.ceo && <div style={{ fontSize: 11, color: C.textMuted, marginTop: 4 }}>CEO: {r.ceo}</div>}
      </div>
      <div>
        <div style={{ color: C.textMuted, fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>⚠️ Risk Flags</div>
        {risks.map(function (f, i) { return <RiskRow key={i} flag={f.flag} level={f.level} /> })}
        {r.sentiment && <>
          <div style={{ color: C.textMuted, fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8, marginTop: 14 }}>📱 Sentiment</div>
          <div style={{ fontSize: 11, color: '#94a3b8', lineHeight: 1.5 }}>{r.sentiment}</div>
        </>}
      </div>
      <div>
        <div style={{ color: C.textMuted, fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>🏆 Scout Verdict</div>
        <VerdictBadge verdict={r.verdict} />
        {r.verdict_note && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 10, lineHeight: 1.6 }}>{r.verdict_note}</div>}
      </div>
    </div>
  )
}

function Toast({ message, type, onDone }) {
  useEffect(function () { const t = setTimeout(onDone, 3000); return function () { clearTimeout(t) } }, [])
  const bg = type === 'success' ? '#052e16' : type === 'error' ? '#450a0a' : '#1e1b4b'
  const border = type === 'success' ? '#166534' : type === 'error' ? '#991b1b' : '#3730a3'
  return (
    <div style={{ position: 'fixed', top: 60, right: 20, background: bg, border: '1px solid ' + border, borderRadius: 6, padding: '10px 20px', color: '#e2e8f0', fontSize: 13, zIndex: 9999, boxShadow: '0 4px 20px rgba(0,0,0,.5)' }}>
      {type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'} {message}
    </div>
  )
}


const PATTERN_SHORT = {
  bull_flag_breakout: 'BF↑',
  bull_flag_forming: 'BF~',
  bear_flag_breakout: 'BF↓',
  macd_momentum: 'MACD',
  gap_and_go: 'GAP',
  orb: 'ORB',
  no_pattern: null,
}

function AiBadge({ aiData }) {
  if (!aiData || aiData.pattern === 'no_pattern') return <span style={{ color: '#4b5563', fontSize: 11 }}>⚪ —</span>
  const short = PATTERN_SHORT[aiData.pattern] || aiData.pattern
  const conf = aiData.confidence || 0
  const green = conf >= 0.65, amber = conf >= 0.45
  if (!green && !amber) return <span style={{ color: '#4b5563', fontSize: 11 }}>⚪ —</span>
  const bg = green ? 'rgba(34,197,94,0.15)' : 'rgba(245,158,11,0.15)'
  const color = green ? '#22c55e' : '#f59e0b'
  const border = green ? 'rgba(34,197,94,0.4)' : 'rgba(245,158,11,0.4)'
  return (
    <span style={{ background: bg, color, border: '1px solid ' + border, borderRadius: 4, padding: '2px 6px', fontSize: 10, fontWeight: 700, whiteSpace: 'nowrap' }}>
      {green ? '🟢' : '🟡'} {short} {(conf * 100).toFixed(0)}%
    </span>
  )
}

// ── Scanner Row (with TRADE button) ─────────────────────────────────────

function ScannerRow({ s, research, idx, onTickerClick, onTrade, aiData }) {
  const [open, setOpen] = useState(false)
  const scoutStatus = research ? 'done' : (s.scout_status === 'pending' ? 'pending' : 'none')
  const isGainer = (s.gap_pct || 0) >= 0
  const rowBg = idx % 2 === 0 ? C.panel : C.rowAlt
  const relvolDaily = (s.avgvol_1d && s.avgvol_200d) ? (s.avgvol_1d / s.avgvol_200d) : (s.relvol || null)
  return (
    <>
      <tr style={{ background: open ? '#0d1525' : rowBg, cursor: 'pointer', borderBottom: '1px solid ' + C.border + '22' }}
        onMouseEnter={function (e) { e.currentTarget.style.background = '#1e2a44' }}
        onMouseLeave={function (e) { e.currentTarget.style.background = open ? '#0d1525' : rowBg }}>
        <td onClick={function () { onTickerClick(s.ticker) }} style={{ padding: '8px 12px', fontWeight: 700, color: C.accent, fontSize: 13, fontFamily: mono, cursor: 'pointer' }}>{s.ticker}</td>
        <td style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right', fontWeight: 600, color: C.textPrimary }}>${fmt(s.price)}</td>
        <td className="dt-col-vol" style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right', color: C.textSecondary, fontSize: 12 }}>{fmtVol(s.avgvol_1d || s.volume)}</td>
        <td style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right', fontWeight: 700, color: floatColor(s.float_m), fontSize: 12 }}>{s.float_m != null ? fmt(s.float_m, 1) + 'M' : '—'}</td>
        <td style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right', color: relvolDaily >= 10 ? '#22c55e' : relvolDaily >= 5 ? '#f59e0b' : C.textSecondary, fontWeight: relvolDaily >= 5 ? 700 : 400 }}>{relvolDaily != null ? fmt(relvolDaily, 1) + 'x' : '—'}</td>
        <td className="dt-col-rvol5m" style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right', color: C.textMuted }}>—</td>
        <td style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right', fontWeight: 700, color: isGainer ? gapGreen(s.gap_pct) : negColor(s.gap_pct), fontSize: 13 }}>{isGainer ? '+' : ''}{fmt(s.gap_pct)}%</td>
        <td className="dt-col-chg" style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right', fontWeight: 600, color: isGainer ? gapGreen(s.gap_pct) : negColor(s.gap_pct), fontSize: 12 }}>{isGainer ? '+' : ''}{fmt(s.gap_pct)}%</td>
        <td onClick={function () { setOpen(function (o) { return !o }) }} style={{ padding: '8px 10px', fontSize: 11, color: C.textMuted, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.news || '—'}</td>
        <td style={{ padding: '8px 8px', textAlign: 'center' }}><AiBadge aiData={aiData} /></td>
        <td style={{ padding: '8px 8px', textAlign: 'center' }}><ScoutBadge status={scoutStatus} /></td>
        <td style={{ padding: '8px 8px', textAlign: 'center' }}>
          <button onClick={function (e) { e.stopPropagation(); onTrade(s.ticker, s.price) }} style={{ background: '#1e3a5f', border: '1px solid #2563eb44', color: '#60a5fa', padding: '3px 8px', borderRadius: 3, fontSize: 10, fontWeight: 700, cursor: 'pointer' }}
            onMouseEnter={function (e) { e.currentTarget.style.background = '#2563eb' }}
            onMouseLeave={function (e) { e.currentTarget.style.background = '#1e3a5f' }}>TRADE</button>
        </td>
      </tr>
      {open && <tr style={{ borderBottom: '2px solid ' + C.border }}><td colSpan={12} style={{ padding: 0 }}><ResearchPanel r={research} /></td></tr>}
    </>
  )
}

function ScannerTable({ stocks, research, title, emptyMsg, onTickerClick, onTrade }) {
  const [aiPatterns, setAiPatterns] = React.useState({})
  React.useEffect(function () {
    function fetchAI() {
      fetch('http://localhost:8769/patterns/today').then(function(r){ return r.json() }).then(function(data){
        var map = {}
        data.forEach(function(d){ map[d.ticker] = d })
        setAiPatterns(map)
      }).catch(function(){})
    }
    fetchAI()
    var t = setInterval(fetchAI, 90000)
    return function(){ clearInterval(t) }
  }, [])
  const cols = [
    { label: 'Symbol',   cls: '' },
    { label: 'Price',    cls: '' },
    { label: 'Vol Today',cls: 'dt-col-vol' },
    { label: 'Float',    cls: '' },
    { label: 'RelVol',   cls: '' },
    { label: 'RV 5min',  cls: 'dt-col-rvol5m' },
    { label: 'Gap %',    cls: '' },
    { label: 'Chg %',    cls: 'dt-col-chg' },
    { label: 'News',     cls: '' },
    { label: '🤖 AI',   cls: '' },
    { label: '',         cls: '' },
    { label: '',         cls: '' },
  ]
  const _cf = React.useState({ sym: '', minPrice: '', maxPrice: '', minFloat: '', maxFloat: '', minRV: '', maxRV: '', minGap: '', maxGap: '', news: '' })
  const cf = _cf[0], setCf = _cf[1]
  const set = function(k,v){ setCf(function(p){ return Object.assign({},p,{[k]:v}) }) }

  const inp = function(k, ph, w) {
    return React.createElement('input', { value: cf[k], onChange: function(e){set(k,e.target.value)}, placeholder: ph,
      style: { width: w||34, background: '#0d1117', border: '1px solid #1e2a44', borderRadius: 3,
        color: '#9ca3af', fontSize: 10, padding: '2px 4px', textAlign: 'center', outline: 'none' } })
  }

  const displayed = stocks.filter(function(s) {
    var rv = (s.avgvol_1d && s.avgvol_200d) ? s.avgvol_1d/s.avgvol_200d : (s.relvol||0)
    if (cf.sym && !s.ticker.toUpperCase().includes(cf.sym.toUpperCase())) return false
    if (cf.minPrice !== '' && (s.price||0) < parseFloat(cf.minPrice)) return false
    if (cf.maxPrice !== '' && (s.price||0) > parseFloat(cf.maxPrice)) return false
    if (cf.minFloat !== '' && (s.float_m||999) < parseFloat(cf.minFloat)) return false
    if (cf.maxFloat !== '' && (s.float_m||999) > parseFloat(cf.maxFloat)) return false
    if (cf.minRV !== '' && rv < parseFloat(cf.minRV)) return false
    if (cf.maxRV !== '' && rv > parseFloat(cf.maxRV)) return false
    if (cf.minGap !== '' && (s.gap_pct||0) < parseFloat(cf.minGap)) return false
    if (cf.maxGap !== '' && (s.gap_pct||0) > parseFloat(cf.maxGap)) return false
    if (cf.news && !(s.news||'').toLowerCase().includes(cf.news.toLowerCase())) return false
    return true
  })

  var hasFilter = Object.values(cf).some(function(v){return v!==''})

  return (
    <div style={{ background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, overflow: 'hidden', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ background: C.header, padding: '8px 16px', borderBottom: '1px solid ' + C.border, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <span style={{ fontWeight: 700, fontSize: 13, color: C.textPrimary }}>{title}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {hasFilter && <button onClick={function(){setCf({sym:'',minPrice:'',maxPrice:'',minFloat:'',maxFloat:'',minRV:'',maxRV:'',minGap:'',maxGap:'',news:''})}}
            style={{ fontSize: 10, color: '#ef4444', background: 'transparent', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 3, padding: '2px 6px', cursor: 'pointer' }}>x Clear</button>}
          <span style={{ fontSize: 11, color: C.textMuted }}>{displayed.length}/{stocks.length}</span>
        </div>
      </div>
      <div className="dt-scroll" style={{ flex: 1, overflowY: 'auto' }}>
        <table className="dt-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead style={{ position: 'sticky', top: 0, zIndex: 1 }}>
            <tr style={{ background: C.header, borderBottom: '1px solid #1e2a44' }}>
              {cols.map(function (c, i) { return <th key={i} className={c.cls} style={{ padding: '7px 12px', color: C.textMuted, fontSize: 10, textAlign: i === 0 || i === 8 ? 'left' : i >= 9 ? 'center' : 'right', textTransform: 'uppercase', letterSpacing: 0.8, fontWeight: 600, whiteSpace: 'nowrap' }}>{c.label}</th> })}
            </tr>
            <tr style={{ background: '#0d1117', borderBottom: '2px solid ' + C.border }}>
              <td style={{ padding: '3px 8px' }}>{inp('sym','SYM',50)}</td>
              <td style={{ padding: '3px 4px', textAlign: 'right' }}>{inp('minPrice','min')}{' '}{inp('maxPrice','max')}</td>
              <td className="dt-col-vol" style={{ padding: '3px 4px' }}></td>
              <td style={{ padding: '3px 4px', textAlign: 'right' }}>{inp('minFloat','min')}{' '}{inp('maxFloat','max')}</td>
              <td style={{ padding: '3px 4px', textAlign: 'right' }}>{inp('minRV','min')}{' '}{inp('maxRV','max')}</td>
              <td className="dt-col-rvol5m" style={{ padding: '3px 4px' }}></td>
              <td style={{ padding: '3px 4px', textAlign: 'right' }}>{inp('minGap','min')}{' '}{inp('maxGap','max')}</td>
              <td className="dt-col-chg" style={{ padding: '3px 4px' }}></td>
              <td style={{ padding: '3px 8px' }}>{inp('news','keyword',78)}</td>
              <td></td><td></td><td></td>
            </tr>
          </thead>
          <tbody>
            {displayed.length === 0
              ? <tr><td colSpan={12} style={{ padding: '40px 20px', textAlign: 'center', color: C.textMuted, fontSize: 12 }}>{hasFilter ? 'No stocks match filters' : emptyMsg}</td></tr>
              : displayed.map(function (s, i) { return <ScannerRow key={s.ticker + i} s={s} research={research[s.ticker]} idx={i} onTickerClick={onTickerClick} onTrade={onTrade} aiData={aiPatterns[s.ticker]} /> })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── TradingView Chart ───────────────────────────────────────────────────────

function TradingViewChart({ symbol, interval, height }) {
  const containerRef = useRef(null)
  const widgetRef = useRef(null)
  useEffect(function () {
    if (!containerRef.current) return
    containerRef.current.innerHTML = ''
    const div = document.createElement('div'); div.id = 'tv_' + interval + '_' + Date.now()
    div.style.width = '100%'; div.style.height = '100%'; containerRef.current.appendChild(div)
    function init() {
      if (window.TradingView) {
        widgetRef.current = new window.TradingView.widget({
          container_id: div.id, symbol: symbol || 'SPY', interval: interval || '1', theme: 'dark', style: '1',
          locale: 'en', width: '100%', height: '100%',
          studies: ['Volume@tv-basicstudies', 'MAExp@tv-basicstudies', 'MAExp@tv-basicstudies', 'MAExp@tv-basicstudies', 'VWAP@tv-basicstudies'],
          hide_top_toolbar: false, allow_symbol_change: false, save_image: false,
          timezone: 'America/New_York', backgroundColor: C.bg,
        })
      }
    }
    if (window.TradingView) { init() } else {
      const s = document.createElement('script'); s.src = 'https://s3.tradingview.com/tv.js'
      s.async = true; s.onload = init; document.head.appendChild(s)
    }
    return function () { widgetRef.current = null }
  }, [symbol, interval])
  return <div ref={containerRef} style={{ width: '100%', height: height || '100%' }} />
}

// ── Multi-Timeframe Chart Grid (Ross Cameron style) ─────────────────────────

const ALL_FRAMES = [
  { label: '5min', interval: '5' },
  { label: '1min', interval: '1' },
  { label: '1D',   interval: '1D' },
  { label: '10s',  interval: '10S' },
]

const GRID_LAYOUTS = {
  1: { cols: '1fr',        rows: '1fr',        count: 1 },
  2: { cols: '1fr 1fr',   rows: '1fr',        count: 2 },
  3: { cols: '1fr 1fr',   rows: '1fr 1fr',    count: 3 },
  4: { cols: '1fr 1fr',   rows: '1fr 1fr',    count: 4 },
}

function MultiTimeframeCharts({ symbol, viewCount }) {
  const layout = GRID_LAYOUTS[viewCount] || GRID_LAYOUTS[4]
  const frames = ALL_FRAMES.slice(0, layout.count)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: layout.cols, gridTemplateRows: layout.rows, gap: 6, width: '100%', height: '100%' }}>
      {frames.map(function (f) {
        return (
          <div key={f.interval} style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', border: '1px solid ' + C.border, borderRadius: 4 }}>
            <div style={{ padding: '3px 8px', background: C.panel, borderBottom: '1px solid ' + C.border, fontSize: 10, fontWeight: 700, color: C.textMuted, letterSpacing: 1, flexShrink: 0 }}>
              {f.label}
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <TradingViewChart symbol={symbol} interval={f.interval} height="100%" />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Breaking News Item ──────────────────────────────────────────────────────

function BreakingNewsItem({ item }) {
  const headline = item.headline || item.title || ''
  const parts = headline.split(/(\$[A-Z]{1,5})/g)
  return (
    <div style={{ padding: '12px 16px', borderBottom: '1px solid ' + C.border + '22', display: 'flex', justifyContent: 'space-between', gap: 16 }}
      onMouseEnter={function (e) { e.currentTarget.style.background = C.rowAlt }}
      onMouseLeave={function (e) { e.currentTarget.style.background = 'transparent' }}>
      <div style={{ flex: 1, fontSize: 13, color: C.textPrimary, lineHeight: 1.5 }}>
        {item.ticker && <span style={{ color: C.pink, fontWeight: 700, marginRight: 8 }}>${item.ticker}</span>}
        {parts.map(function (p, i) { return p.startsWith('$') ? <span key={i} style={{ color: C.pink, fontWeight: 700 }}>{p}</span> : <span key={i}>{p}</span> })}
      </div>
      <span style={{ color: C.textMuted, fontSize: 11, whiteSpace: 'nowrap', flexShrink: 0, marginTop: 2 }}>{item.time || fmtTimeShort(item.published || item.timestamp) || ''}</span>
    </div>
  )
}

// ── PnL Bar Chart (inline SVG) ──────────────────────────────────────────────

function PnlBarChart({ daily }) {
  if (!daily || daily.length === 0) return <div style={{ color: C.textMuted, fontSize: 11, padding: 10 }}>No P&L data yet</div>
  const sorted = [...daily].sort(function (a, b) { return a.date < b.date ? -1 : 1 })
  const maxAbs = Math.max(1, ...sorted.map(function (d) { return Math.abs(d.gross_pnl || 0) }))
  const barW = Math.max(8, Math.floor(400 / sorted.length) - 2)
  const h = 120, mid = h / 2
  return (
    <svg width={sorted.length * (barW + 2) + 10} height={h + 20} style={{ display: 'block' }}>
      <line x1={0} y1={mid} x2={sorted.length * (barW + 2) + 10} y2={mid} stroke="#1e2a44" strokeWidth={1} />
      {sorted.map(function (d, i) {
        var val = d.gross_pnl || 0
        var barH = Math.abs(val) / maxAbs * (mid - 5)
        var y = val >= 0 ? mid - barH : mid
        var fill = val >= 0 ? '#22c55e' : '#ef4444'
        return (
          <g key={i}>
            <rect x={i * (barW + 2) + 5} y={y} width={barW} height={Math.max(1, barH)} fill={fill} rx={1} />
            <title>{d.date}: ${val.toFixed(2)}</title>
          </g>
        )
      })}
    </svg>
  )
}

// ── Trade Entry Form ────────────────────────────────────────────────────────

function TradeForm({ prefill, alpacaMode, settings, onSubmit, onAlpaca }) {
  const [ticker, setTicker] = useState('')
  const [side, setSide] = useState('buy')
  const [qty, setQty] = useState('')
  const [price, setPrice] = useState('')
  const [stopPrice, setStopPrice] = useState('')
  const [qtyOverride, setQtyOverride] = useState(false)
  const [notes, setNotes] = useState('')

  useEffect(function () {
    if (prefill) {
      if (prefill.ticker) setTicker(prefill.ticker)
      if (prefill.price) setPrice(String(prefill.price))
      setQty(''); setStopPrice(''); setQtyOverride(false)
    }
  }, [prefill])

  var startingBalance = parseFloat(settings.starting_balance || '600')
  var maxRiskPct = parseFloat(settings.max_risk_pct || '2')
  var maxPosPct = parseFloat(settings.max_position_pct || '20')
  var riskPerTrade = startingBalance * maxRiskPct / 100
  var maxPosSize = startingBalance * maxPosPct / 100

  var entryPrice = parseFloat(price) || 0
  var stop = parseFloat(stopPrice) || 0
  var riskPerShare = (entryPrice > 0 && stop > 0 && stop < entryPrice) ? entryPrice - stop : 0

  // Foolproof qty: risk-based if stop set, else max-position-based
  var calcQty = 0
  var sizeMethod = ''
  if (riskPerShare > 0) {
    calcQty = Math.floor(riskPerTrade / riskPerShare)
    sizeMethod = 'risk-based'
  } else if (entryPrice > 0) {
    calcQty = Math.floor(maxPosSize / entryPrice)
    sizeMethod = 'position-based'
  }
  // Cap at max position size
  if (calcQty > 0 && entryPrice > 0) {
    calcQty = Math.min(calcQty, Math.floor(maxPosSize / entryPrice))
  }

  // Use override qty or calculated qty
  var effectiveQty = qtyOverride ? (parseInt(qty) || 0) : calcQty
  var totalCost = effectiveQty * entryPrice
  var totalRisk = riskPerShare > 0 ? effectiveQty * riskPerShare : null
  var riskPct = totalRisk ? (totalRisk / startingBalance * 100) : null

  // Risk status
  var riskStatus = null
  if (totalRisk != null) {
    if (totalRisk > riskPerTrade * 1.5) riskStatus = { color: '#ef4444', label: '🚨 OVER LIMIT', bg: '#5c1a1a' }
    else if (totalRisk > riskPerTrade) riskStatus = { color: '#f97316', label: '⚠️ Above max risk', bg: '#3a1f00' }
    else riskStatus = { color: '#22c55e', label: '✅ Within limits', bg: '#0a2a0a' }
  } else if (totalCost > startingBalance * 0.5) {
    riskStatus = { color: '#ef4444', label: '🚨 >50% of account — set a stop!', bg: '#5c1a1a' }
  }

  var inputStyle = { background: C.header, border: '1px solid ' + C.border, color: C.textPrimary, padding: '6px 10px', borderRadius: 3, fontSize: 13, fontFamily: mono, outline: 'none', width: 90 }
  var labelStyle = { fontSize: 11, color: C.textMuted, marginBottom: 2 }

  function handleSubmit(useAlpaca) {
    var finalQty = effectiveQty
    if (!finalQty || finalQty <= 0) return
    var payload = { ticker, side, qty: finalQty, entry_price: entryPrice, stop_price: stop || null, notes }
    if (useAlpaca) onAlpaca(payload)
    else onSubmit(payload)
    setQty(''); setStopPrice(''); setQtyOverride(false); setNotes('')
  }

  return (
    <div style={{ background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, padding: 16 }}>
      <div style={{ fontSize: 14, fontWeight: 700, color: C.textPrimary, marginBottom: 12 }}>📝 New Trade</div>

      {/* Row 1: inputs */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 10 }}>
        <div><div style={labelStyle}>Ticker</div>
          <input value={ticker} onChange={function(e){setTicker(e.target.value.toUpperCase())}} style={{...inputStyle,width:80}} placeholder="PRSO" />
        </div>
        <div><div style={labelStyle}>Side</div>
          <select value={side} onChange={function(e){setSide(e.target.value)}} style={{...inputStyle,width:80}}>
            <option value="buy">BUY</option><option value="sell">SELL</option>
          </select>
        </div>
        <div><div style={labelStyle}>Entry $</div>
          <input type="number" step="0.01" value={price} onChange={function(e){setPrice(e.target.value)}} style={inputStyle} placeholder="2.04" />
        </div>
        <div>
          <div style={labelStyle}>Stop $ <span style={{color:'#f59e0b',fontSize:10}}>(bottom of flag)</span></div>
          <input type="number" step="0.01" value={stopPrice} onChange={function(e){setStopPrice(e.target.value)}} style={{...inputStyle, borderColor: stop > 0 && stop < entryPrice ? '#22c55e' : C.border}} placeholder="1.94" />
        </div>
        <div>
          <div style={labelStyle}>
            Shares
            {!qtyOverride && calcQty > 0 && <span style={{color:'#22c55e',marginLeft:6,fontSize:10}}>auto ✓</span>}
            {!qtyOverride && <button onClick={function(){setQtyOverride(true);setQty(String(calcQty))}} style={{marginLeft:8,background:'none',border:'none',color:C.textMuted,fontSize:10,cursor:'pointer',textDecoration:'underline'}}>override</button>}
            {qtyOverride && <button onClick={function(){setQtyOverride(false);setQty('')}} style={{marginLeft:8,background:'none',border:'none',color:'#f59e0b',fontSize:10,cursor:'pointer',textDecoration:'underline'}}>reset</button>}
          </div>
          {qtyOverride
            ? <input type="number" value={qty} onChange={function(e){setQty(e.target.value)}} style={{...inputStyle,borderColor:'#f59e0b'}} />
            : <div style={{...inputStyle, color: calcQty > 0 ? '#22c55e' : C.textMuted, fontWeight:700, display:'flex', alignItems:'center', height:32}}>
                {calcQty > 0 ? calcQty : '—'}
              </div>
          }
        </div>
        <div style={{flex:1,minWidth:140}}><div style={labelStyle}>Notes</div>
          <input value={notes} onChange={function(e){setNotes(e.target.value)}} style={{...inputStyle,width:'100%'}} placeholder="Bull flag setup" />
        </div>
      </div>

      {/* Row 2: risk breakdown */}
      {entryPrice > 0 && effectiveQty > 0 && (
        <div style={{background: riskStatus ? riskStatus.bg : C.header, border:'1px solid '+(riskStatus ? riskStatus.color+'44' : C.border), borderRadius:4, padding:'8px 12px', marginBottom:10, display:'flex', gap:24, flexWrap:'wrap', alignItems:'center'}}>
          {riskPerShare > 0 && <span style={{fontSize:12}}><span style={{color:C.textMuted}}>Risk/share: </span><span style={{color:'#f59e0b',fontWeight:700}}>${riskPerShare.toFixed(2)}</span></span>}
          <span style={{fontSize:12}}><span style={{color:C.textMuted}}>Shares: </span><span style={{color:C.accent,fontWeight:700}}>{effectiveQty}</span></span>
          <span style={{fontSize:12}}><span style={{color:C.textMuted}}>Total cost: </span><span style={{color:C.textPrimary,fontWeight:700}}>${totalCost.toFixed(2)}</span></span>
          {totalRisk != null && <span style={{fontSize:12}}><span style={{color:C.textMuted}}>Max loss: </span><span style={{color:riskStatus.color,fontWeight:700}}>${totalRisk.toFixed(2)} ({riskPct.toFixed(1)}%)</span></span>}
          {riskStatus && <span style={{fontSize:12,fontWeight:700,color:riskStatus.color,marginLeft:'auto'}}>{riskStatus.label}</span>}
          {sizeMethod && !qtyOverride && <span style={{fontSize:10,color:C.textMuted}}>({sizeMethod})</span>}
        </div>
      )}

      {/* Row 3: action buttons */}
      <div style={{display:'flex',gap:10,flexWrap:'wrap'}}>
        <button onClick={function(){handleSubmit(false)}} disabled={effectiveQty <= 0 || !ticker}
          style={{background: effectiveQty > 0 ? '#1e3a5f' : '#111', border:'1px solid '+(effectiveQty > 0 ? '#2563eb' : C.border), color: effectiveQty > 0 ? '#60a5fa' : C.textMuted, padding:'8px 16px', borderRadius:4, fontWeight:700, fontSize:12, cursor: effectiveQty > 0 ? 'pointer' : 'not-allowed'}}
          onMouseEnter={function(e){if(effectiveQty>0)e.currentTarget.style.background='#2563eb'}}
          onMouseLeave={function(e){e.currentTarget.style.background=effectiveQty>0?'#1e3a5f':'#111'}}>
          Log Manual
        </button>
        <button onClick={function(){handleSubmit(true)}} disabled={effectiveQty <= 0 || !ticker || (riskStatus && riskStatus.label.includes('OVER'))}
          style={{background: alpacaMode==='live' ? '#5c1a1a' : '#1a3a1a', border:'1px solid '+(alpacaMode==='live'?'#ef4444':'#22c55e'), color: alpacaMode==='live'?'#fca5a5':'#86efac', padding:'8px 16px', borderRadius:4, fontWeight:700, fontSize:12, cursor:'pointer'}}
          onMouseEnter={function(e){e.currentTarget.style.opacity='0.8'}}
          onMouseLeave={function(e){e.currentTarget.style.opacity='1'}}>
          {alpacaMode==='live' ? '⚠️ SEND LIVE ORDER' : '📄 Send Paper Order'}
        </button>
        <span style={{fontSize:11,color:C.textMuted,alignSelf:'center'}}>
          Budget: <b style={{color:'#f59e0b'}}>${riskPerTrade.toFixed(2)}</b> risk · <b style={{color:'#f59e0b'}}>${maxPosSize.toFixed(2)}</b> max pos
        </span>
      </div>
    </div>
  )
}

// ── Confirm Modal ───────────────────────────────────────────────────────────

function ConfirmModal({ title, message, onConfirm, onCancel }) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10000 }}>
      <div style={{ background: '#1a1a2e', border: '1px solid #ef444488', borderRadius: 8, padding: 24, maxWidth: 420, width: '90%' }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: '#fca5a5', marginBottom: 12 }}>{title}</div>
        <div style={{ fontSize: 13, color: C.textSecondary, lineHeight: 1.6, marginBottom: 20 }}>{message}</div>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <button onClick={onCancel} style={{ background: C.panel, border: '1px solid ' + C.border, color: C.textMuted, padding: '8px 20px', borderRadius: 4, cursor: 'pointer', fontSize: 13 }}>Cancel</button>
          <button onClick={onConfirm} style={{ background: '#991b1b', border: '1px solid #ef4444', color: '#fff', padding: '8px 20px', borderRadius: 4, cursor: 'pointer', fontSize: 13, fontWeight: 700 }}>Confirm</button>
        </div>
      </div>
    </div>
  )
}

// ── Settings Tab ────────────────────────────────────────────────────────────

function SettingsTab({ settings, onSave, alpacaMode, onModeSwitch }) {
  const [local, setLocal] = useState({})
  const [apiStatus, setApiStatus] = useState(null)
  const [testing, setTesting] = useState(false)

  useEffect(function () { setLocal(Object.assign({}, settings)) }, [settings])

  var set = function (k, v) { setLocal(function (prev) { var n = Object.assign({}, prev); n[k] = v; return n }) }
  var startBal = parseFloat(local.starting_balance || '600')
  var maxRiskPct = parseFloat(local.max_risk_pct || '2')
  var maxPosPct = parseFloat(local.max_position_pct || '20')

  function testApis() {
    setTesting(true)
    API('settings/api-status').then(function (d) { setApiStatus(d); setTesting(false) })
  }

  var inputStyle = { background: C.header, border: '1px solid ' + C.border, color: C.textPrimary, padding: '6px 10px', borderRadius: 3, fontSize: 13, fontFamily: mono, outline: 'none', width: 80 }
  var sectionStyle = { background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, padding: 16, marginBottom: 12 }
  var labelStyle = { fontSize: 11, color: C.textMuted, width: 180, flexShrink: 0 }
  var rowStyle = { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }

  function Toggle({ value, onChange, labelOn, labelOff }) {
    var on = value === 'on' || value === true
    return (
      <button onClick={function () { onChange(on ? 'off' : 'on') }} style={{
        background: on ? '#052e16' : '#1a1a2e', border: '1px solid ' + (on ? '#166534' : C.border),
        color: on ? '#22c55e' : C.textMuted, padding: '4px 12px', borderRadius: 12, fontSize: 11, fontWeight: 700, cursor: 'pointer',
      }}>{on ? '● ' + (labelOn || 'ON') : (labelOff || 'OFF')}</button>
    )
  }

  function ApiDot({ name }) {
    if (!apiStatus || !apiStatus[name]) return <span style={{ color: C.textMuted, fontSize: 11 }}>—</span>
    var s = apiStatus[name]
    var color = s.status === 'connected' ? '#22c55e' : s.status === 'not_configured' ? '#f59e0b' : '#ef4444'
    return <span style={{ fontSize: 11 }}><span style={{ color }}>●</span> <span style={{ color: C.textSecondary }}>{s.info || s.status}</span></span>
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 16, maxWidth: 700 }}>
      {/* Account */}
      <div style={sectionStyle}>
        <div style={{ fontSize: 14, fontWeight: 700, color: C.textPrimary, marginBottom: 12 }}>💰 Account Settings</div>
        <div style={rowStyle}><span style={labelStyle}>Starting Balance</span><span style={{ color: C.textMuted }}>$</span><input value={local.starting_balance || ''} onChange={function (e) { set('starting_balance', e.target.value) }} style={inputStyle} /></div>
        <div style={rowStyle}><span style={labelStyle}>Max Risk Per Trade</span><input value={local.max_risk_pct || ''} onChange={function (e) { set('max_risk_pct', e.target.value) }} style={{ ...inputStyle, width: 50 }} /><span style={{ color: C.textMuted, fontSize: 11 }}>% → <span style={{ color: '#f59e0b' }}>${(startBal * maxRiskPct / 100).toFixed(2)}</span> per trade</span></div>
        <div style={rowStyle}><span style={labelStyle}>Max Position Size</span><input value={local.max_position_pct || ''} onChange={function (e) { set('max_position_pct', e.target.value) }} style={{ ...inputStyle, width: 50 }} /><span style={{ color: C.textMuted, fontSize: 11 }}>% → <span style={{ color: '#f59e0b' }}>${(startBal * maxPosPct / 100).toFixed(2)}</span> max position</span></div>
        <div style={rowStyle}><span style={labelStyle}>Max Positions Open</span><input type="number" value={local.max_positions_open || ''} onChange={function (e) { set('max_positions_open', e.target.value) }} style={{ ...inputStyle, width: 50 }} /></div>
        <div style={rowStyle}><span style={labelStyle}>Trading Mode</span>
          <button onClick={function () { onModeSwitch('paper') }} style={{ background: alpacaMode === 'paper' ? '#3a2800' : C.header, border: '1px solid ' + (alpacaMode === 'paper' ? '#f59e0b' : C.border), color: alpacaMode === 'paper' ? '#f59e0b' : C.textMuted, padding: '4px 14px', borderRadius: '4px 0 0 4px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>📄 PAPER</button>
          <button onClick={function () { onModeSwitch('live') }} style={{ background: alpacaMode === 'live' ? '#5c1a1a' : C.header, border: '1px solid ' + (alpacaMode === 'live' ? '#ef4444' : C.border), color: alpacaMode === 'live' ? '#ef4444' : C.textMuted, padding: '4px 14px', borderRadius: '0 4px 4px 0', fontSize: 11, fontWeight: 700, cursor: 'pointer', marginLeft: -1 }}>💰 LIVE</button>
        </div>
      </div>

      {/* Scanner */}
      <div style={sectionStyle}>
        <div style={{ fontSize: 14, fontWeight: 700, color: C.textPrimary, marginBottom: 12 }}>🔍 Scanner Settings</div>
        <div style={rowStyle}><span style={labelStyle}>Min Gap %</span><input value={local.min_gap_pct || ''} onChange={function (e) { set('min_gap_pct', e.target.value) }} style={{ ...inputStyle, width: 60 }} /></div>
        <div style={rowStyle}><span style={labelStyle}>Max Gap %</span><input value={local.max_gap_pct || ''} onChange={function (e) { set('max_gap_pct', e.target.value) }} style={{ ...inputStyle, width: 60 }} /></div>
        <div style={rowStyle}><span style={labelStyle}>Min Relative Volume</span><input value={local.min_relvol || ''} onChange={function (e) { set('min_relvol', e.target.value) }} style={{ ...inputStyle, width: 60 }} /><span style={{ color: C.textMuted, fontSize: 11 }}>x</span></div>
        <div style={rowStyle}><span style={labelStyle}>Max Float</span><input value={local.max_float_m || ''} onChange={function (e) { set('max_float_m', e.target.value) }} style={{ ...inputStyle, width: 60 }} /><span style={{ color: C.textMuted, fontSize: 11 }}>M shares</span></div>
        <div style={rowStyle}><span style={labelStyle}>Min Price</span><span style={{ color: C.textMuted }}>$</span><input value={local.min_price || ''} onChange={function (e) { set('min_price', e.target.value) }} style={{ ...inputStyle, width: 60 }} /></div>
        <div style={rowStyle}><span style={labelStyle}>Max Price</span><span style={{ color: C.textMuted }}>$</span><input value={local.max_price || ''} onChange={function (e) { set('max_price', e.target.value) }} style={{ ...inputStyle, width: 60 }} /></div>
        <div style={rowStyle}><span style={labelStyle}>Scan Interval</span><input value={local.scan_interval || ''} onChange={function (e) { set('scan_interval', e.target.value) }} style={{ ...inputStyle, width: 60 }} /><span style={{ color: C.textMuted, fontSize: 11 }}>seconds</span></div>
        <div style={rowStyle}><span style={labelStyle}>Active Hours (ET)</span><input value={local.active_hours_start || ''} onChange={function (e) { set('active_hours_start', e.target.value) }} style={{ ...inputStyle, width: 60 }} /><span style={{ color: C.textMuted }}>to</span><input value={local.active_hours_end || ''} onChange={function (e) { set('active_hours_end', e.target.value) }} style={{ ...inputStyle, width: 60 }} /></div>
      </div>

      {/* Notifications */}
      <div style={sectionStyle}>
        <div style={{ fontSize: 14, fontWeight: 700, color: C.textPrimary, marginBottom: 12 }}>🔔 Notifications</div>
        <div style={rowStyle}><span style={labelStyle}>Telegram Alerts</span><Toggle value={local.telegram_alerts} onChange={function (v) { set('telegram_alerts', v) }} /></div>
        <div style={rowStyle}><span style={labelStyle}>Alert on new candidate</span><Toggle value={local.alert_new_candidate} onChange={function (v) { set('alert_new_candidate', v) }} /></div>
        <div style={rowStyle}><span style={labelStyle}>Alert on Scout research</span><Toggle value={local.alert_scout_done} onChange={function (v) { set('alert_scout_done', v) }} /></div>
        <div style={rowStyle}><span style={labelStyle}>Alert on trade executed</span><Toggle value={local.alert_trade_executed} onChange={function (v) { set('alert_trade_executed', v) }} /></div>
        <div style={rowStyle}><span style={labelStyle}>Min Gap % to alert</span><input value={local.min_gap_alert || ''} onChange={function (e) { set('min_gap_alert', e.target.value) }} style={{ ...inputStyle, width: 60 }} /><span style={{ color: C.textMuted, fontSize: 11 }}>%</span></div>
      </div>

      {/* API */}
      <div style={sectionStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: C.textPrimary }}>🤖 API Connections</span>
          <button onClick={testApis} style={{ background: C.header, border: '1px solid ' + C.border, color: C.accent, padding: '4px 12px', borderRadius: 3, fontSize: 11, cursor: 'pointer' }}>{testing ? 'Testing…' : 'Test All'}</button>
        </div>
        <div style={rowStyle}><span style={labelStyle}>EODHD</span><ApiDot name="eodhd" /></div>
        <div style={rowStyle}><span style={labelStyle}>Alpaca Paper</span><ApiDot name="alpaca_paper" /></div>
        <div style={rowStyle}><span style={labelStyle}>Alpaca Live</span><ApiDot name="alpaca_live" /></div>
        <div style={rowStyle}><span style={labelStyle}>Alpha Vantage</span><ApiDot name="alphavantage" /></div>
      </div>

      {/* Save */}
      <button onClick={function () { onSave(local) }} style={{ background: '#1e3a5f', border: '1px solid #2563eb', color: '#60a5fa', padding: '10px 28px', borderRadius: 4, fontWeight: 700, fontSize: 14, cursor: 'pointer', width: '100%' }}
        onMouseEnter={function (e) { e.currentTarget.style.background = '#2563eb' }}
        onMouseLeave={function (e) { e.currentTarget.style.background = '#1e3a5f' }}>💾 Save Settings</button>
    </div>
  )
}

// ── Main App ────────────────────────────────────────────────────────────────

function App() {
  var _s = useState, _e = useEffect, _r = useRef, _cb = useCallback
  var _as = _s('lf_high_relvol'), activeScanner = _as[0], setActiveScanner = _as[1]
  var _at = _s('scanners'), activeTab = _at[0], setActiveTab = _at[1]
  var _st = _s([]), stocks = _st[0], setStocks = _st[1]
  var _hi = _s([]), history = _hi[0], setHistory = _hi[1]
  var _rs = _s({}), research = _rs[0], setResearch = _rs[1]
  var _nw = _s([]), news = _nw[0], setNews = _nw[1]
  var _ms = _s(getMarketStatus()), status = _ms[0], setStatus = _ms[1]
  var _cn = _s(false), connected = _cn[0], setConnected = _cn[1]
  var _lu = _s(null), lastUpdate = _lu[0], setLastUpdate = _lu[1]
  var _cs = _s('SPY'), chartSymbol = _cs[0], setChartSymbol = _cs[1]
  var _cv = _s(4), chartViewCount = _cv[0], setChartViewCount = _cv[1]
  var _am = _s('paper'), alpacaMode = _am[0], setAlpacaMode = _am[1]
  var _aa = _s(null), alpacaAcct = _aa[0], setAlpacaAcct = _aa[1]
  var _ot = _s([]), openTrades = _ot[0], setOpenTrades = _ot[1]
  var _at2 = _s([]), allTrades = _at2[0], setAllTrades = _at2[1]
  var _pnl = _s(null), pnlData = _pnl[0], setPnlData = _pnl[1]
  var _tf = _s(null), tradePrefill = _tf[0], setTradePrefill = _tf[1]
  var _se = _s({}), settings = _se[0], setSettings = _se[1]
  var _to = _s(null), toast = _to[0], setToast = _to[1]
  var _cm = _s(null), confirmModal = _cm[0], setConfirmModal = _cm[1]
  var _hf = _s('month'), histFilter = _hf[0], setHistFilter = _hf[1]
  var ws = _r(null)

  var handleTickerClick = _cb(function (t) { setChartSymbol(t); setActiveTab('charts') }, [])
  var handleTrade = _cb(function (ticker, price) { setTradePrefill({ ticker: ticker, price: price, _ts: Date.now() }); setActiveTab('trades') }, [])

  function showToast(msg, type) { setToast({ message: msg, type: type || 'success' }) }

  function loadResearch(ticker) {
    if (research[ticker]) return
    API('research/' + ticker + '/latest').then(function (d) { if (d && Object.keys(d).length) setResearch(function (p) { var n = Object.assign({}, p); n[ticker] = d; return n }) })
  }

  function refresh() {
    API('trades/open').then(function (d) { if (d) setOpenTrades(d) })
    API('trades').then(function (d) { if (d) setAllTrades(d) })
    API('trades/pnl').then(function (d) { if (d) setPnlData(d) })
    API('alpaca/account').then(function (d) { if (d) setAlpacaAcct(d) })
    API('alpaca/mode').then(function (d) { if (d) setAlpacaMode(d.mode || 'paper') })
    API('settings').then(function (d) { if (d) setSettings(d) })
  }

  function switchMode(mode) {
    if (mode === 'live') {
      setConfirmModal({
        title: '⚠️ Switch to LIVE Trading',
        message: 'You are switching to LIVE trading with real money. All Alpaca orders will execute against your live account ($600 starting balance). Are you sure?',
        onConfirm: function () { POST('alpaca/mode', { mode: 'live' }).then(function () { setAlpacaMode('live'); setConfirmModal(null); refresh(); showToast('Switched to LIVE trading', 'error') }) },
      })
    } else {
      POST('alpaca/mode', { mode: 'paper' }).then(function () { setAlpacaMode('paper'); refresh(); showToast('Switched to PAPER trading') })
    }
  }

  function submitManual(data) {
    if (!data.ticker || !data.qty || !data.entry_price) return showToast('Fill all fields', 'error')
    POST('trades', data).then(function (r) {
      if (r && r.id) { showToast('Trade logged: ' + data.ticker); refresh() }
      else showToast('Error: ' + (r && r.error || 'unknown'), 'error')
    })
  }

  function submitAlpaca(data) {
    if (!data.ticker || !data.qty) return showToast('Fill ticker and qty', 'error')
    var action = function () {
      POST('alpaca/order', data).then(function (r) {
        if (r && r.id) { showToast('Alpaca order submitted: ' + data.ticker); refresh() }
        else showToast('Alpaca error: ' + JSON.stringify(r && r.error || r), 'error')
      })
    }
    if (alpacaMode === 'live') {
      setConfirmModal({
        title: '⚠️ LIVE Order Confirmation',
        message: 'You are about to submit a LIVE ' + data.side.toUpperCase() + ' order for ' + data.qty + ' shares of ' + data.ticker + ' with real money.',
        onConfirm: function () { setConfirmModal(null); action() },
      })
    } else { action() }
  }

  function closeTrade(id) {
    var exitStr = prompt('Enter exit price:')
    if (!exitStr) return
    POST('trades/' + id + '/close', { exit_price: parseFloat(exitStr) }).then(function (r) {
      if (r && r.id) { showToast('Trade closed: ' + r.ticker + ' P&L: $' + (r.pnl || 0).toFixed(2)); refresh() }
      else showToast('Error closing trade', 'error')
    })
  }

  function saveSettings(s) {
    POST('settings', s).then(function (r) {
      if (r && r.ok) { setSettings(r.settings); showToast('Settings saved') }
      else showToast('Error saving settings', 'error')
    })
  }

  _e(function () {
    var tick = setInterval(function () { setStatus(getMarketStatus()) }, 30000)
    function connect() {
      ws.current = new WebSocket('ws://' + window.location.hostname + ':8765')
      ws.current.onopen = function () { setConnected(true) }
      ws.current.onclose = function () { setConnected(false); setTimeout(connect, 4000) }
      ws.current.onmessage = function (e) {
        try {
          var data = JSON.parse(e.data)
          var arr = Object.values(data).sort(function (a, b) { return new Date(b.first_seen || b.timestamp) - new Date(a.first_seen || a.timestamp) })
          setStocks(arr); setLastUpdate(new Date())
          arr.forEach(function (s) { loadResearch(s.ticker) })
        } catch (ex) {}
      }
    }
    connect(); refresh()
    API('news').then(function (d) { if (d) setNews(d) })
    API('candidates/history').then(function (d) { if (d) setHistory(d) })
    // Always load candidates via REST on mount (don't rely solely on WS)
    API('candidates').then(function (d) { if (d) { var arr = Object.values(d).sort(function(a,b){return new Date(b.first_seen||b.timestamp)-new Date(a.first_seen||a.timestamp)}); if (arr.length) { setStocks(arr); setLastUpdate(new Date()) } } })
    var poll = setInterval(function () {
      if (!connected) API('candidates').then(function (d) { if (d) setStocks(Object.values(d)) })
      API('news').then(function (d) { if (d) setNews(d) })
      refresh()
    }, 15000)
    return function () { clearInterval(tick); clearInterval(poll); if (ws.current) ws.current.close() }
  }, [])

  var filtered = (function () {
    var arr = [].concat(stocks)
    switch (activeScanner) {
      case 'lf_high_relvol':
        return arr.filter(function(s){return (s.float_m||99)<10 && s.relvol>=5 && s.price>=2 && s.price<=20 && s.gap_pct>=10}).sort(function(a,b){return b.relvol-a.relvol})
      case 'lf_med_relvol':
        return arr.filter(function(s){return (s.float_m||99)<10 && s.relvol>=3 && s.relvol<5 && s.price>=2 && s.price<=20 && s.gap_pct>=10}).sort(function(a,b){return b.relvol-a.relvol})
      case 'lf_high_relvol_20':
        return arr.filter(function(s){return (s.float_m||99)<10 && s.relvol>=5 && s.price>20 && s.gap_pct>=10}).sort(function(a,b){return b.relvol-a.relvol})
      case 'former_momo':
        return arr.filter(function(s){return s.former_momo===true||s.former_momo===1}).sort(function(a,b){return b.gap_pct-a.gap_pct})
      case 'squeeze_5_5':
        return arr.filter(function(s){return (s.squeeze_5m||0)>=5}).sort(function(a,b){return b.squeeze_5m-a.squeeze_5m})
      case 'squeeze_10_10':
        return arr.filter(function(s){return (s.squeeze_10m||0)>=10}).sort(function(a,b){return b.squeeze_10m-a.squeeze_10m})
      case 'gainers': return arr.filter(function(s){return s.gap_pct>0}).sort(function(a,b){return b.gap_pct-a.gap_pct})
      case 'relvol': return arr.sort(function(a,b){return b.relvol-a.relvol})
      case 'halt': return arr.filter(function(s){return s.status==='halt'})
      default: return arr
    }
  })()

  var activeLabel = (SCANNERS.find(function (s) { return s.id === activeScanner }) || {}).label || ''
  var scannerGroups = { rc: SCANNERS.filter(function(s){return s.group==='rc'}), squeeze: SCANNERS.filter(function(s){return s.group==='squeeze'}), watchlist: SCANNERS.filter(function(s){return s.group==='watchlist'}) }

  // Health monitoring
  var _hl = _s(null), health = _hl[0], setHealth = _hl[1]
  var _ha = _s(null), healthAge = _ha[0], setHealthAge = _ha[1]

  useEffect(function () {
    var load = function () { API('health').then(function (d) { if (d) { setHealth(d); setHealthAge(new Date()) } }) }
    load()
    var t = setInterval(load, 15000)
    return function () { clearInterval(t) }
  }, [])


  // Backtest state
  var _bt = _s(null), btSummary = _bt[0], setBtSummary = _bt[1]
  var _bt2 = _s([]), btResults = _bt2[0], setBtResults = _bt2[1]
  var _bt3 = _s(false), btRunning = _bt3[0], setBtRunning = _bt3[1]
  var _bt4 = _s({total:0,done:0,trades:0}), btProgress = _bt4[0], setBtProgress = _bt4[1]

  // Load backtest data when tab active
  _e(function () {
    if (activeTab !== 'backtest') return
    API('backtest/summary').then(function (d) { if (d) { setBtSummary(d); setBtRunning(d.running); setBtProgress(d.progress || {total:0,done:0,trades:0}) } })
    API('backtest/results').then(function (d) { if (d && Array.isArray(d)) setBtResults(d) })
  }, [activeTab])

  // Poll while running
  _e(function () {
    if (!btRunning) return
    var t = setInterval(function () {
      API('backtest/status').then(function (d) {
        if (d) { setBtRunning(d.running); setBtProgress(d.progress || {total:0,done:0,trades:0}) }
        if (d && !d.running) {
          API('backtest/summary').then(function (s) { if (s) setBtSummary(s) })
          API('backtest/results').then(function (r) { if (r && Array.isArray(r)) setBtResults(r) })
        }
      })
    }, 5000)
    return function () { clearInterval(t) }
  }, [btRunning])

  var tabs = [
    ['scanners', '🔍 Scanners'],
    ['charts', '📊 Charts'],
    ['trades', '💰 Trades'],
    ['news', '📰 News'],
    ['history', '🕐 History'],
    ['settings', '⚙️ Settings'],
    ['system', '🛡️ System'],
    ['backtest', '🔁 Backtest'],
    ['training', '🏷️ Training'],
  ]

  var startingBalance = parseFloat(settings.starting_balance || '600')
  var acctEquity = alpacaAcct && alpacaAcct.equity ? parseFloat(alpacaAcct.equity) : null
  var totalReturn = acctEquity != null ? ((acctEquity - (alpacaMode === 'paper' ? 100000 : startingBalance)) / (alpacaMode === 'paper' ? 100000 : startingBalance) * 100) : null

  // History filtering
  var filteredHistory = (function () {
    if (!history || !history.length) return []
    var now = new Date()
    var cutoff = histFilter === 'today' ? new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString().slice(0, 10) :
                 histFilter === 'week' ? new Date(now - 7 * 86400000).toISOString().slice(0, 10) :
                 new Date(now - 30 * 86400000).toISOString().slice(0, 10)
    return history.filter(function (s) { return (s.scan_date || '') >= cutoff })
  })()

  // Load 30d history when filter changes
  _e(function () {
    if (activeTab !== 'history') return
    var days = histFilter === 'today' ? 1 : histFilter === 'week' ? 7 : 30
    var endpoint = days > 7 ? 'history/month' : 'candidates/history'
    API(endpoint).then(function (d) { if (d) setHistory(d) })
  }, [histFilter, activeTab])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: C.bg, color: C.textPrimary, fontFamily: sans, overflow: 'hidden' }}>

      {/* LIVE banner */}
      {alpacaMode === 'live' && (
        <div style={{ background: '#5c1a1a', borderBottom: '2px solid #ef4444', padding: '6px 20px', textAlign: 'center', fontSize: 13, fontWeight: 700, color: '#fca5a5', animation: 'pulse 2s infinite', flexShrink: 0 }}>
          ⚠️ LIVE TRADING ACTIVE — Real money at risk (${startingBalance} starting balance)
        </div>
      )}

      {/* Top Bar */}
      <div className="dt-topbar" style={{ background: C.header, borderBottom: '1px solid ' + C.border, padding: '0 20px', display: 'flex', alignItems: 'center', gap: 0, height: 48, flexShrink: 0 }}>
        <div className="dt-topbar-title" style={{ fontWeight: 900, fontSize: 17, color: C.accent, letterSpacing: -0.5, marginRight: 32 }}>
          📈 Day<span style={{ color: '#22c55e' }}>Trade</span><span style={{ color: C.textPrimary, fontWeight: 400 }}> Dash</span>
        </div>
        <div className="dt-tabs dt-nav" style={{ display: 'flex', overflow: 'hidden' }}>{tabs.map(function (t) {
          return <button key={t[0]} onClick={function () { setActiveTab(t[0]) }} style={{
            background: 'none', border: 'none', color: activeTab === t[0] ? '#60a5fa' : C.textMuted,
            borderBottom: activeTab === t[0] ? '2px solid #60a5fa' : '2px solid transparent',
            padding: '0 16px', height: 48, cursor: 'pointer', fontSize: 12, fontWeight: activeTab === t[0] ? 700 : 400, whiteSpace: 'nowrap',
          }}>{t[1]}</button>
        })}</div>
        <div className="dt-topbar-right" style={{ marginLeft: 'auto', display: 'flex', gap: 12, alignItems: 'center' }}>
          {/* Mode toggle */}
          <button onClick={function () { switchMode(alpacaMode === 'paper' ? 'live' : 'paper') }} style={{
            background: alpacaMode === 'live' ? '#5c1a1a' : '#2a1f00', border: '1px solid ' + (alpacaMode === 'live' ? '#ef4444' : '#f59e0b'),
            color: alpacaMode === 'live' ? '#fca5a5' : '#f59e0b', padding: '4px 10px', borderRadius: 4, fontSize: 10, fontWeight: 700, cursor: 'pointer',
          }}>{alpacaMode === 'live' ? '💰 LIVE' : '📄 PAPER'}</button>
          {lastUpdate && <span className="dt-last-update" style={{ fontSize: 10, color: C.textMuted }}>Updated {lastUpdate.toLocaleTimeString()}</span>}
          <span style={{ color: connected ? '#22c55e' : '#ef4444', fontSize: 11, fontWeight: 600 }}>● {connected ? 'LIVE' : 'OFFLINE'}</span>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: health ? (health.overall === 'healthy' ? '#22c55e' : '#ef4444') : '#555', display: 'inline-block', animation: health && health.overall !== 'healthy' ? 'pulse-red 1.2s ease-in-out infinite' : 'none' }} title={'System: ' + (health ? health.overall : 'loading')} />
          <span className="dt-market-badge" style={{ background: status.bg, color: status.color, border: '1px solid ' + status.color + '44', padding: '4px 12px', borderRadius: 4, fontWeight: 700, fontSize: 10, letterSpacing: 0.5 }}>{status.text}</span>
        </div>
      </div>

      {/* Mobile scanner pills - outside flex row */}
      {activeTab === 'scanners' && (
        <div className="dt-scanner-pills">
          {SCANNERS.map(s => (
            <button key={s.id} className={`dt-scanner-pill${activeScanner === s.id ? ' active' : ''}`}
              onClick={() => setActiveScanner(s.id)}>
              {s.icon} {s.label}
            </button>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left Sidebar */}
        <div className="dt-sidebar" style={{ width: 210, background: C.panel, borderRight: '1px solid ' + C.border, flexShrink: 0, overflowY: 'auto', padding: '10px 0', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '4px 14px 6px', fontSize: 9, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1.2, fontWeight: 700 }}>RC Scanners</div>
          {scannerGroups.rc.map(function (s) {
            return <button key={s.id} onClick={function () { setActiveScanner(s.id); setActiveTab('scanners') }} style={{
              width: '100%', background: activeScanner === s.id && activeTab === 'scanners' ? '#1e2a44' : 'none',
              border: 'none', borderLeft: activeScanner === s.id && activeTab === 'scanners' ? '3px solid #3b82f6' : '3px solid transparent',
              color: activeScanner === s.id && activeTab === 'scanners' ? '#93c5fd' : C.textMuted, padding: '7px 14px',
              textAlign: 'left', cursor: 'pointer', fontSize: 11, fontWeight: activeScanner === s.id ? 700 : 400, display: 'flex', alignItems: 'center', gap: 8,
            }}>{s.icon} {s.label}{s.hot ? <span style={{width:6,height:6,borderRadius:'50%',background:'#ef4444',display:'inline-block',marginLeft:4,flexShrink:0}}></span> : null}</button>
          })}
          <div style={{ padding: '10px 14px 6px', fontSize: 9, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1.2, fontWeight: 700, marginTop: 4, borderTop: '1px solid ' + C.border }}>Squeeze Alerts</div>
          {scannerGroups.squeeze.map(function (s) {
            return <button key={s.id} onClick={function () { setActiveScanner(s.id); setActiveTab('scanners') }} style={{
              width: '100%', background: activeScanner === s.id && activeTab === 'scanners' ? '#2d1b4e' : 'none',
              border: 'none', borderLeft: activeScanner === s.id && activeTab === 'scanners' ? '3px solid #a78bfa' : '3px solid transparent',
              color: activeScanner === s.id && activeTab === 'scanners' ? '#c4b5fd' : C.textMuted, padding: '7px 14px',
              textAlign: 'left', cursor: 'pointer', fontSize: 11, fontWeight: activeScanner === s.id ? 700 : 400, display: 'flex', alignItems: 'center', gap: 8,
            }}>{s.icon} {s.label}{s.live ? <span className="pulse-dot"></span> : null}</button>
          })}
          <div style={{ padding: '10px 14px 6px', fontSize: 9, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1.2, fontWeight: 700, marginTop: 4, borderTop: '1px solid ' + C.border }}>Watchlist</div>
          {scannerGroups.watchlist.map(function (s) {
            return <button key={s.id} onClick={function () { setActiveScanner(s.id); setActiveTab('scanners') }} style={{
              width: '100%', background: activeScanner === s.id && activeTab === 'scanners' ? '#1e2a44' : 'none',
              border: 'none', borderLeft: activeScanner === s.id && activeTab === 'scanners' ? '3px solid #3b82f6' : '3px solid transparent',
              color: activeScanner === s.id && activeTab === 'scanners' ? '#93c5fd' : C.textMuted, padding: '7px 14px',
              textAlign: 'left', cursor: 'pointer', fontSize: 11, fontWeight: activeScanner === s.id ? 700 : 400, display: 'flex', alignItems: 'center', gap: 8,
            }}>{s.icon} {s.label}</button>
          })}
          <div style={{ marginTop: 'auto', padding: '0 10px 10px' }}>
            <div style={{ background: C.header, borderRadius: 4, padding: 10, border: '1px solid ' + C.border }}>
              <div style={{ fontSize: 9, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>Stats</div>
              {[
                { label: 'Candidates', val: stocks.length, color: '#60a5fa' },
                { label: 'Float ≤5M', val: stocks.filter(function (s) { return s.float_m <= 5 }).length, color: '#22c55e' },
                { label: 'Gap ≥30%', val: stocks.filter(function (s) { return s.gap_pct >= 30 }).length, color: '#f97316' },
                { label: 'Researched', val: Object.keys(research).length, color: '#a78bfa' },
              ].map(function (x) {
                return <div key={x.label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 10, color: C.textMuted }}>{x.label}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: x.color, fontFamily: mono }}>{x.val}</span>
                </div>
              })}
            </div>
          </div>
        </div>


        {/* Main Content */}
        <div className="dt-content" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>

          {activeTab === 'scanners' && (
            <div style={{ flex: 1, overflow: 'hidden', padding: 12 }}>
              <ScannerTable stocks={filtered} research={research} title={activeLabel} emptyMsg={'No stocks in ' + activeLabel + ' — scanner active during market hours'} onTickerClick={handleTickerClick} onTrade={handleTrade} />
            </div>
          )}

          {activeTab === 'charts' && (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div style={{ padding: '8px 16px', background: C.panel, borderBottom: '1px solid ' + C.border, display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 12, color: C.textMuted }}>Symbol:</span>
                <input type="text" value={chartSymbol} onChange={function (e) { setChartSymbol(e.target.value.toUpperCase()) }}
                  style={{ background: C.header, border: '1px solid ' + C.border, color: C.accent, padding: '4px 10px', borderRadius: 3, fontSize: 14, fontWeight: 700, fontFamily: mono, width: 100, outline: 'none' }} />
                <span style={{ fontSize: 14, fontWeight: 700, color: C.textPrimary }}>{chartSymbol}</span>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
                  {[1,2,3,4].map(function(n) {
                    const icons = ['▣','⊞','⊟','⊞⊞']
                    const labels = ['1','2','3','4']
                    return (
                      <button key={n} onClick={function(){ setChartViewCount(n) }} style={{
                        background: chartViewCount === n ? '#1e3a5f' : C.header,
                        border: '1px solid ' + (chartViewCount === n ? '#2563eb' : C.border),
                        color: chartViewCount === n ? '#60a5fa' : C.textMuted,
                        padding: '4px 10px', borderRadius: 3, fontSize: 12, fontWeight: 700, cursor: 'pointer', minWidth: 32
                      }}>{labels[n-1]}</button>
                    )
                  })}
                </div>
              </div>
              <div style={{ flex: 1, padding: 8, minHeight: 0 }}><MultiTimeframeCharts symbol={chartSymbol} viewCount={chartViewCount} /></div>
            </div>
          )}

          {/* TRADES TAB */}
          {activeTab === 'trades' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {/* Account Summary */}
              {alpacaAcct && (
                <div className="dt-stats" style={{ display: 'flex', gap: 12 }}>
                  <div style={{ background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, padding: 14, flex: 1 }}>
                    <div style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Account Equity</div>
                    <div style={{ fontSize: 22, fontWeight: 900, fontFamily: mono, color: C.textPrimary }}>{acctEquity != null ? fmtMoney(acctEquity) : '—'}</div>
                    <div style={{ fontSize: 11, color: C.textMuted }}>Starting: ${alpacaMode === 'paper' ? '100,000' : startingBalance.toLocaleString()} ({alpacaMode})</div>
                  </div>
                  <div style={{ background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, padding: 14, flex: 1 }}>
                    <div style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Buying Power</div>
                    <div style={{ fontSize: 22, fontWeight: 900, fontFamily: mono, color: '#60a5fa' }}>{alpacaAcct.buying_power ? fmtMoney(parseFloat(alpacaAcct.buying_power)) : '—'}</div>
                  </div>
                  <div style={{ background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, padding: 14, flex: 1 }}>
                    <div style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Total Return</div>
                    <div style={{ fontSize: 22, fontWeight: 900, fontFamily: mono, color: totalReturn != null ? pnlColor(totalReturn) : C.textMuted }}>{totalReturn != null ? (totalReturn >= 0 ? '+' : '') + totalReturn.toFixed(2) + '%' : '—'}</div>
                  </div>
                  {pnlData && (
                    <div style={{ background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, padding: 14, flex: 1 }}>
                      <div style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Win Rate</div>
                      <div style={{ fontSize: 22, fontWeight: 900, fontFamily: mono, color: (pnlData.win_rate || 0) >= 50 ? '#22c55e' : '#f59e0b' }}>{fmt(pnlData.win_rate || 0, 1)}%</div>
                      <div style={{ fontSize: 11, color: C.textMuted }}>{pnlData.total_wins || 0}W / {(pnlData.total_trades || 0) - (pnlData.total_wins || 0)}L ({pnlData.total_trades || 0} trades)</div>
                    </div>
                  )}
                </div>
              )}

              {/* Open Positions */}
              <div style={{ background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ background: C.header, padding: '8px 16px', borderBottom: '1px solid ' + C.border }}>
                  <span style={{ fontWeight: 700, fontSize: 13 }}>📊 Open Positions ({openTrades.length})</span>
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr style={{ background: C.header, borderBottom: '1px solid ' + C.border }}>
                    {['Ticker', 'Side', 'Qty', 'Entry', 'Current', 'P&L $', 'P&L %', 'Time Open', 'Source', ''].map(function (h) {
                      return <th key={h} style={{ padding: '7px 12px', color: C.textMuted, fontSize: 10, textTransform: 'uppercase', textAlign: h === 'Ticker' || h === 'Side' || h === 'Source' ? 'left' : 'right' }}>{h}</th>
                    })}
                  </tr></thead>
                  <tbody>
                    {openTrades.length === 0
                      ? <tr><td colSpan={10} style={{ padding: 30, textAlign: 'center', color: C.textMuted, fontSize: 12 }}>No open positions</td></tr>
                      : openTrades.map(function (t) {
                        return <tr key={t.id} style={{ borderBottom: '1px solid ' + C.border + '22' }}>
                          <td style={{ padding: '8px 12px', fontWeight: 700, color: C.accent, fontFamily: mono }}>{t.ticker}</td>
                          <td style={{ padding: '8px 12px', color: t.side === 'buy' ? '#22c55e' : '#ef4444', fontWeight: 600, textTransform: 'uppercase', fontSize: 11 }}>{t.side}</td>
                          <td style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right' }}>{t.qty}</td>
                          <td style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right' }}>${fmt(t.entry_price)}</td>
                          <td style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right', color: C.textMuted }}>—</td>
                          <td style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right', color: C.textMuted }}>—</td>
                          <td style={{ padding: '8px 12px', fontFamily: mono, textAlign: 'right', color: C.textMuted }}>—</td>
                          <td style={{ padding: '8px 12px', fontSize: 11, color: C.textMuted, textAlign: 'right' }}>{timeAgo(t.entry_time)}</td>
                          <td style={{ padding: '8px 12px', fontSize: 10, color: C.textMuted }}>{t.source}</td>
                          <td style={{ padding: '8px 8px', textAlign: 'center' }}>
                            <button onClick={function () { closeTrade(t.id) }} style={{ background: '#5c1a1a', border: '1px solid #ef444466', color: '#fca5a5', padding: '3px 10px', borderRadius: 3, fontSize: 10, fontWeight: 700, cursor: 'pointer' }}>Close</button>
                          </td>
                        </tr>
                      })}
                  </tbody>
                </table>
              </div>

              {/* Trade Entry Form */}
              <TradeForm prefill={tradePrefill} alpacaMode={alpacaMode} settings={settings} onSubmit={submitManual} onAlpaca={submitAlpaca} />

              {/* P&L Chart */}
              {pnlData && pnlData.daily && pnlData.daily.length > 0 && (
                <div style={{ background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, padding: 16 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: C.textPrimary, marginBottom: 8 }}>📈 Daily P&L (30 days)</div>
                  <PnlBarChart daily={pnlData.daily} />
                </div>
              )}

              {/* Trade History */}
              <div style={{ background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ background: C.header, padding: '8px 16px', borderBottom: '1px solid ' + C.border }}>
                  <span style={{ fontWeight: 700, fontSize: 13 }}>📋 Trade History (30 days)</span>
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead><tr style={{ background: C.header, borderBottom: '1px solid ' + C.border }}>
                    {['Ticker', 'Side', 'Qty', 'Entry', 'Exit', 'P&L $', 'P&L %', 'Date', 'Source'].map(function (h) {
                      return <th key={h} style={{ padding: '7px 12px', color: C.textMuted, fontSize: 10, textTransform: 'uppercase', textAlign: h === 'Ticker' || h === 'Side' || h === 'Source' || h === 'Date' ? 'left' : 'right' }}>{h}</th>
                    })}
                  </tr></thead>
                  <tbody>
                    {allTrades.filter(function (t) { return t.status === 'closed' }).length === 0
                      ? <tr><td colSpan={9} style={{ padding: 30, textAlign: 'center', color: C.textMuted, fontSize: 12 }}>No closed trades yet</td></tr>
                      : allTrades.filter(function (t) { return t.status === 'closed' }).map(function (t) {
                        return <tr key={t.id} style={{ borderBottom: '1px solid ' + C.border + '22' }}>
                          <td style={{ padding: '7px 12px', fontWeight: 700, color: C.accent, fontFamily: mono, fontSize: 12 }}>{t.ticker}</td>
                          <td style={{ padding: '7px 12px', color: t.side === 'buy' ? '#22c55e' : '#ef4444', fontWeight: 600, textTransform: 'uppercase', fontSize: 11 }}>{t.side}</td>
                          <td style={{ padding: '7px 12px', fontFamily: mono, textAlign: 'right', fontSize: 12 }}>{t.qty}</td>
                          <td style={{ padding: '7px 12px', fontFamily: mono, textAlign: 'right', fontSize: 12 }}>${fmt(t.entry_price)}</td>
                          <td style={{ padding: '7px 12px', fontFamily: mono, textAlign: 'right', fontSize: 12 }}>${fmt(t.exit_price)}</td>
                          <td style={{ padding: '7px 12px', fontFamily: mono, textAlign: 'right', fontWeight: 700, color: pnlColor(t.pnl) }}>{t.pnl >= 0 ? '+' : ''}{fmt(t.pnl)}</td>
                          <td style={{ padding: '7px 12px', fontFamily: mono, textAlign: 'right', color: pnlColor(t.pnl_pct) }}>{t.pnl_pct >= 0 ? '+' : ''}{fmt(t.pnl_pct)}%</td>
                          <td style={{ padding: '7px 12px', fontSize: 11, color: C.textMuted }}>{(t.exit_time || '').slice(0, 10)}</td>
                          <td style={{ padding: '7px 12px', fontSize: 10, color: C.textMuted }}>{t.source}</td>
                        </tr>
                      })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === 'news' && (
            <div style={{ flex: 1, overflow: 'hidden', padding: 12 }}>
              <div style={{ background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, overflow: 'hidden', height: '100%', display: 'flex', flexDirection: 'column' }}>
                <div style={{ background: C.header, padding: '10px 16px', borderBottom: '1px solid ' + C.border, flexShrink: 0 }}>
                  <span style={{ fontWeight: 700, fontSize: 14, color: C.textPrimary }}>Breaking News</span>
                </div>
                <div style={{ flex: 1, overflowY: 'auto' }}>
                  {news.length === 0
                    ? <div style={{ padding: 40, textAlign: 'center', color: C.textMuted, fontSize: 13 }}>No news yet</div>
                    : news.map(function (n, i) { return <BreakingNewsItem key={i} item={n} /> })}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'history' && (
            <div style={{ flex: 1, overflow: 'hidden', padding: 12 }}>
              <div style={{ background: C.panel, border: '1px solid ' + C.border, borderRadius: 4, overflow: 'hidden', height: '100%', display: 'flex', flexDirection: 'column' }}>
                <div style={{ background: C.header, padding: '8px 16px', borderBottom: '1px solid ' + C.border, display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
                  <span style={{ fontWeight: 700, fontSize: 13 }}>🕐 Candidate History</span>
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
                    {[['today', 'Today'], ['week', '1 Week'], ['month', '1 Month']].map(function (f) {
                      return <button key={f[0]} onClick={function () { setHistFilter(f[0]) }} style={{
                        background: histFilter === f[0] ? '#1e3a5f' : C.header, border: '1px solid ' + (histFilter === f[0] ? '#2563eb' : C.border),
                        color: histFilter === f[0] ? '#60a5fa' : C.textMuted, padding: '3px 10px', borderRadius: 3, fontSize: 10, fontWeight: 700, cursor: 'pointer',
                      }}>{f[1]}</button>
                    })}
                  </div>
                </div>
                <div style={{ flex: 1, overflowY: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead style={{ position: 'sticky', top: 0, zIndex: 1 }}>
                      <tr style={{ background: C.header, borderBottom: '1px solid ' + C.border }}>
                        {['Date', 'Ticker', 'Company', 'Price', 'Gap%', 'RelVol', 'Float', 'Scout'].map(function (h) {
                          return <th key={h} style={{ padding: '7px 12px', color: C.textMuted, fontSize: 10, textAlign: h === 'Date' || h === 'Ticker' || h === 'Company' ? 'left' : 'right', textTransform: 'uppercase', letterSpacing: 0.8 }}>{h}</th>
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredHistory.length === 0
                        ? <tr><td colSpan={8} style={{ padding: 40, textAlign: 'center', color: C.textMuted }}>No history for this period</td></tr>
                        : filteredHistory.map(function (s, i) {
                          return <tr key={i} style={{ borderBottom: '1px solid ' + C.border + '22', background: i % 2 === 0 ? C.panel : C.rowAlt, cursor: 'pointer' }}
                            onClick={function () { handleTickerClick(s.ticker) }}>
                            <td style={{ padding: '7px 12px', fontSize: 11, color: C.textMuted }}>{s.scan_date}</td>
                            <td style={{ padding: '7px 12px', fontWeight: 700, color: C.accent, fontFamily: mono }}>{s.ticker}</td>
                            <td style={{ padding: '7px 12px', fontSize: 11, color: C.textMuted }}>{s.name}</td>
                            <td style={{ padding: '7px 12px', fontFamily: mono, textAlign: 'right' }}>${fmt(s.price)}</td>
                            <td style={{ padding: '7px 12px', fontFamily: mono, textAlign: 'right', color: gapGreen(s.gap_pct), fontWeight: 700 }}>+{fmt(s.gap_pct)}%</td>
                            <td style={{ padding: '7px 12px', fontFamily: mono, textAlign: 'right', color: C.textSecondary }}>{fmt(s.relvol, 1)}x</td>
                            <td style={{ padding: '7px 12px', fontFamily: mono, textAlign: 'right', color: floatColor(s.float_m) }}>{fmt(s.float_m, 1)}M</td>
                            <td style={{ padding: '7px 12px', textAlign: 'right' }}><ScoutBadge status={s.scout_status === 'done' ? 'done' : 'none'} /></td>
                          </tr>
                        })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'system' && (
            <div style={{ padding: 20 }}>
              {/* Overall status banner */}
              {health ? (
                <div style={{
                  background: health.overall === 'healthy' ? '#0a2a0a' : health.overall === 'degraded' ? '#2a1f00' : '#2a0a0a',
                  border: '1px solid ' + (health.overall === 'healthy' ? '#22c55e44' : health.overall === 'degraded' ? '#f59e0b44' : '#ef444444'),
                  borderRadius: 8, padding: '16px 24px', marginBottom: 20, textAlign: 'center'
                }}>
                  <div style={{ fontSize: 24, marginBottom: 4 }}>
                    {health.overall === 'healthy' ? '🟢' : health.overall === 'degraded' ? '🟡' : '🔴'}
                  </div>
                  <div style={{
                    fontSize: 16, fontWeight: 700, letterSpacing: 1,
                    color: health.overall === 'healthy' ? '#22c55e' : health.overall === 'degraded' ? '#f59e0b' : '#ef4444',
                    animation: health.overall === 'down' ? 'pulse-red 1.2s ease-in-out infinite' : 'none'
                  }}>
                    {health.overall === 'healthy' ? 'ALL SYSTEMS OPERATIONAL' : health.overall === 'degraded' ? 'DEGRADED — some services affected' : 'SYSTEM OUTAGE DETECTED'}
                  </div>
                  <div style={{ fontSize: 10, color: C.textMuted, marginTop: 4 }}>Last check: {health.timestamp ? new Date(health.timestamp).toLocaleTimeString() : '—'}</div>
                </div>
              ) : (
                <div style={{ background: C.panel, borderRadius: 8, padding: 20, textAlign: 'center', color: C.textMuted }}>Loading health data...</div>
              )}

              {/* Service cards */}
              {health && health.services && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12, marginBottom: 20 }}>
                  {Object.entries(health.services).map(function (entry) {
                    var name = entry[0], svc = entry[1]
                    var isUp = svc.status === 'up'
                    return (
                      <div key={name} style={{
                        background: C.panel, borderRadius: 8, padding: 16,
                        border: '1px solid ' + (isUp ? '#22c55e33' : '#ef444433')
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                          <span style={{ fontWeight: 600, fontSize: 13, color: C.textPrimary }}>{svc.label}</span>
                          <span style={{ width: 12, height: 12, borderRadius: '50%', background: isUp ? '#22c55e' : '#ef4444', display: 'inline-block', animation: !isUp ? 'pulse-red 1.2s ease-in-out infinite' : 'none' }} />
                        </div>
                        <div style={{ fontSize: 11, color: C.textSecondary }}>
                          <div>Status: <span style={{ color: isUp ? '#22c55e' : '#ef4444', fontWeight: 600 }}>{isUp ? 'UP' : 'DOWN'}</span></div>
                          <div>Port: {svc.port_ok ? '✅ open' : '❌ closed'}</div>
                          <div>Uptime: {Math.floor(svc.uptime_mins)}m</div>
                        </div>
                        <div style={{ fontSize: 9, color: C.textMuted, marginTop: 6 }}>{name}</div>
                      </div>
                    )
                  })}
                </div>
              )}

              {/* API + DB + Watchdog row */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12, marginBottom: 20 }}>
                {/* API Status */}
                <div style={{ background: C.panel, borderRadius: 8, padding: 16 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: C.textPrimary, marginBottom: 8 }}>API Status</div>
                  {health && (
                    <div style={{ fontSize: 11, color: C.textSecondary }}>
                      <div><span style={{ color: health.eodhd && health.eodhd.status === 'up' ? '#22c55e' : '#ef4444' }}>●</span> EODHD: {health.eodhd ? health.eodhd.status : '—'}</div>
                    </div>
                  )}
                </div>

                {/* DB Status */}
                <div style={{ background: C.panel, borderRadius: 8, padding: 16 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: C.textPrimary, marginBottom: 8 }}>Database</div>
                  {health && health.db && (
                    <div style={{ fontSize: 11, color: C.textSecondary }}>
                      <div><span style={{ color: health.db.status === 'up' ? '#22c55e' : '#ef4444' }}>●</span> {health.db.status}</div>
                      <div>Size: {health.db.size_mb}MB</div>
                      <div>Candidates: {health.db.candidates}</div>
                      <div>Trades: {health.db.trades}</div>
                    </div>
                  )}
                </div>

                {/* Watchdog */}
                <div style={{ background: C.panel, borderRadius: 8, padding: 16 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: C.textPrimary, marginBottom: 8 }}>Watchdog</div>
                  {health && (
                    <div style={{ fontSize: 11, color: C.textSecondary }}>
                      <div><span style={{ color: health.watchdog_ok ? '#22c55e' : '#ef4444' }}>●</span> {health.watchdog_ok ? 'Active' : 'STALE'}</div>
                      {health.watchdog_last_seen && <div>Last seen: {(function(){
                        var d = (Date.now() - new Date(health.watchdog_last_seen).getTime()) / 1000
                        return d < 60 ? Math.floor(d) + 's ago' : Math.floor(d/60) + 'm ago'
                      })()}</div>}
                    </div>
                  )}
                </div>
              </div>

              {/* Alert log */}
              {health && health.alerts && health.alerts.length > 0 && (
                <div style={{ background: C.panel, borderRadius: 8, padding: 16 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: C.textPrimary, marginBottom: 8 }}>Recent Alerts</div>
                  {health.alerts.slice(-5).reverse().map(function (a, i) {
                    return (
                      <div key={i} style={{ fontSize: 11, color: C.textSecondary, padding: '4px 0', borderBottom: '1px solid ' + C.border }}>
                        <span style={{ color: C.textMuted, marginRight: 8 }}>{new Date(a.time).toLocaleTimeString()}</span>
                        <span style={{ color: a.message.includes('RECOVERED') ? '#22c55e' : a.message.includes('SMS') ? '#ef4444' : '#f59e0b' }}>{a.message}</span>
                      </div>
                    )
                  })}
                </div>
              )}

              {health && (!health.alerts || health.alerts.length === 0) && (
                <div style={{ background: C.panel, borderRadius: 8, padding: 16, textAlign: 'center', color: C.textMuted, fontSize: 12 }}>
                  No recent alerts — all quiet ✅
                </div>
              )}
            </div>
          )}

          {activeTab === 'settings' && (
            <SettingsTab settings={settings} onSave={saveSettings} alpacaMode={alpacaMode} onModeSwitch={switchMode} />
          )}
        </div>
      </div>

      {/* Footer */}
      <div style={{ background: C.header, borderTop: '1px solid ' + C.border, padding: '5px 20px', display: 'flex', justifyContent: 'space-between', fontSize: 10, color: C.textMuted, flexShrink: 0 }}>
        <span>DayTrade Dash · Built by Nova · Data: EODHD + Alpaca</span>
        <span>Click ticker to chart · TRADE button to open trade form</span>
      </div>

      {/* Toast */}
      {toast && <Toast message={toast.message} type={toast.type} onDone={function () { setToast(null) }} />}


      {activeTab === 'backtest' && (
        <div style={{ padding: 20 }}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            <button onClick={function () {
              if (btRunning) return
              setBtRunning(true); setBtProgress({total:0,done:0,trades:0})
              API('backtest/run').then(function (d) { if (d && d.status === 'started') setBtRunning(true) })
            }} style={{
              background: btRunning ? '#374151' : '#2563eb', color: '#fff', border: 'none',
              padding: '10px 20px', borderRadius: 8, cursor: btRunning ? 'not-allowed' : 'pointer',
              fontWeight: 700, fontSize: 14
            }}>{btRunning ? '⏳ Running...' : '▶ Run Backtest'}</button>
            {btRunning && btProgress.total > 0 && (
              <div style={{ flex: 1, minWidth: 200 }}>
                <div style={{ background: '#1e293b', borderRadius: 8, height: 20, overflow: 'hidden' }}>
                  <div style={{ background: '#3b82f6', height: '100%', width: (btProgress.done/btProgress.total*100)+'%', transition: 'width 0.5s', borderRadius: 8 }} />
                </div>
                <div style={{ color: '#94a3b8', fontSize: 12, marginTop: 4 }}>
                  {btProgress.done}/{btProgress.total} candidates · {btProgress.trades} setups found
                </div>
              </div>
            )}
            {!btRunning && btSummary && <span style={{ color: '#94a3b8', fontSize: 13 }}>{btSummary.total_candidates || 0} candidates processed</span>}
          </div>

          {/* Summary Cards */}
          {btSummary && btSummary.total_trades > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 24 }}>
              {[
                ['Setups Found', btSummary.total_trades],
                ['Win Rate', btSummary.win_rate + '%'],
                ['Total P&L', (btSummary.total_pnl >= 0 ? '+' : '') + '$' + btSummary.total_pnl.toFixed(2)],
                ['Profit Factor', (function () {
                  var wins = (btSummary.by_result || []).find(function(r){return r.result==='win'})
                  var losses = (btSummary.by_result || []).filter(function(r){return r.result==='loss'||r.result==='timeout'})
                  var wt = wins ? wins.total_pnl : 0
                  var lt = losses.reduce(function(s,r){return s+Math.abs(r.total_pnl)},0)
                  return lt > 0 ? (wt/lt).toFixed(1) + 'x' : 'N/A'
                })()],
              ].map(function (c) {
                return <div key={c[0]} style={{ background: '#111827', border: '1px solid #1e293b', borderRadius: 10, padding: 16, textAlign: 'center' }}>
                  <div style={{ color: '#94a3b8', fontSize: 11, marginBottom: 4 }}>{c[0]}</div>
                  <div style={{ color: '#e2e8f0', fontSize: 22, fontWeight: 700 }}>{c[1]}</div>
                </div>
              })}
            </div>
          )}

          {/* Float Breakdown */}
          {btResults.length > 0 && (function () {
            var trades = btResults.filter(function(r){return r.result==='win'||r.result==='loss'||r.result==='timeout'})
            if (!trades.length) return null
            var ranges = [[0,2,'<2M'],[2,5,'2-5M'],[5,10,'5-10M'],[10,50,'10-50M']]
            var rows = ranges.map(function(rng) {
              var sub = trades.filter(function(t){return t.float_m && t.float_m >= rng[0] && t.float_m < rng[1]})
              if (!sub.length) return null
              var w = sub.filter(function(t){return t.result==='win'})
              var l = sub.filter(function(t){return t.result!=='win'})
              return {label:rng[2], count:sub.length, wr:Math.round(w.length/sub.length*100),
                avgWin: w.length ? (w.reduce(function(s,t){return s+t.pnl},0)/w.length).toFixed(2) : '0',
                avgLoss: l.length ? (l.reduce(function(s,t){return s+t.pnl},0)/l.length).toFixed(2) : '0',
                pnl: sub.reduce(function(s,t){return s+t.pnl},0).toFixed(2)}
            }).filter(Boolean)
            return <div style={{ marginBottom: 24 }}>
              <h3 style={{ color: '#e2e8f0', marginBottom: 8, fontSize: 14 }}>Float Breakdown</h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead><tr style={{ borderBottom: '1px solid #1e293b' }}>
                  {['Float Range','Trades','Win Rate','Avg Win','Avg Loss','P&L'].map(function(h){return <th key={h} style={{padding:'6px 10px',color:'#94a3b8',textAlign:'right',fontWeight:500}}>{h}</th>})}
                </tr></thead>
                <tbody>{rows.map(function(r){return <tr key={r.label} style={{borderBottom:'1px solid #111827'}}>
                  <td style={{padding:'6px 10px',color:'#e2e8f0',textAlign:'right'}}>{r.label}</td>
                  <td style={{padding:'6px 10px',color:'#e2e8f0',textAlign:'right'}}>{r.count}</td>
                  <td style={{padding:'6px 10px',color:'#e2e8f0',textAlign:'right'}}>{r.wr}%</td>
                  <td style={{padding:'6px 10px',color:'#22c55e',textAlign:'right'}}>${r.avgWin}</td>
                  <td style={{padding:'6px 10px',color:'#ef4444',textAlign:'right'}}>${r.avgLoss}</td>
                  <td style={{padding:'6px 10px',color:parseFloat(r.pnl)>=0?'#22c55e':'#ef4444',textAlign:'right'}}>${r.pnl}</td>
                </tr>})}</tbody>
              </table>
            </div>
          })()}

          {/* Equity Curve */}
          {btResults.length > 0 && (function () {
            var trades = btResults.filter(function(r){return r.result==='win'||r.result==='loss'||r.result==='timeout'}).sort(function(a,b){return a.date<b.date?-1:1})
            if (!trades.length) return null
            var byDay = {}; trades.forEach(function(t){ byDay[t.date] = (byDay[t.date]||0) + t.pnl })
            var days = Object.keys(byDay).sort()
            var cum = 0; var points = days.map(function(d){ cum += byDay[d]; return {date:d, pnl:cum} })
            var maxPnl = Math.max.apply(null, points.map(function(p){return Math.abs(p.pnl)})) || 1
            var w = 700, h = 160, barW = Math.max(4, Math.min(20, (w-40)/points.length - 2))
            return <div style={{ marginBottom: 24 }}>
              <h3 style={{ color: '#e2e8f0', marginBottom: 8, fontSize: 14 }}>Equity Curve (Cumulative P&L)</h3>
              <svg viewBox={'0 0 '+w+' '+h} style={{ width: '100%', maxWidth: 700, background: '#111827', borderRadius: 8, padding: 8 }}>
                <line x1="30" y1={h/2} x2={w} y2={h/2} stroke="#1e293b" strokeWidth="1" />
                {points.map(function(p, i) {
                  var barH = Math.abs(p.pnl) / maxPnl * (h/2 - 10)
                  var y = p.pnl >= 0 ? h/2 - barH : h/2
                  var x = 35 + i * ((w-40)/points.length)
                  return <rect key={i} x={x} y={y} width={barW} height={Math.max(1,barH)} fill={p.pnl>=0?'#22c55e':'#ef4444'} rx="2" />
                })}
              </svg>
            </div>
          })()}

          {/* Trade Log */}
          {btResults.length > 0 && (function () {
            var trades = btResults.filter(function(r){return r.result==='win'||r.result==='loss'||r.result==='timeout'})
            if (!trades.length) return <div style={{color:'#94a3b8'}}>No setups found in backtest results.</div>
            return <div>
              <h3 style={{ color: '#e2e8f0', marginBottom: 8, fontSize: 14 }}>Trade Log ({trades.length} trades)</h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead><tr style={{ borderBottom: '1px solid #1e293b' }}>
                    {['Date','Ticker','Gap%','Float','Entry','Stop','Target','Exit','Result','P&L'].map(function(h){return <th key={h} style={{padding:'6px 8px',color:'#94a3b8',textAlign:'right',fontWeight:500,whiteSpace:'nowrap'}}>{h}</th>})}
                  </tr></thead>
                  <tbody>{trades.map(function(t,i){
                    var rc = t.result==='win'?'#22c55e':t.result==='loss'?'#ef4444':'#6b7280'
                    return <tr key={i} style={{borderBottom:'1px solid #111827'}}>
                      <td style={{padding:'5px 8px',color:'#e2e8f0',textAlign:'right',whiteSpace:'nowrap'}}>{t.date}</td>
                      <td style={{padding:'5px 8px',color:'#60a5fa',textAlign:'right',fontWeight:600}}>{t.ticker}</td>
                      <td style={{padding:'5px 8px',color:'#eab308',textAlign:'right'}}>{t.gap_pct?t.gap_pct.toFixed(0)+'%':'—'}</td>
                      <td style={{padding:'5px 8px',color:'#22d3ee',textAlign:'right'}}>{t.float_m?t.float_m.toFixed(1)+'M':'—'}</td>
                      <td style={{padding:'5px 8px',color:'#e2e8f0',textAlign:'right'}}>{t.entry?'$'+t.entry.toFixed(2):'—'}</td>
                      <td style={{padding:'5px 8px',color:'#ef4444',textAlign:'right'}}>{t.stop?'$'+t.stop.toFixed(2):'—'}</td>
                      <td style={{padding:'5px 8px',color:'#22c55e',textAlign:'right'}}>{t.target?'$'+t.target.toFixed(2):'—'}</td>
                      <td style={{padding:'5px 8px',color:'#e2e8f0',textAlign:'right'}}>{t.exit_price?'$'+t.exit_price.toFixed(2):'—'}</td>
                      <td style={{padding:'5px 8px',color:rc,textAlign:'right',fontWeight:600}}>{t.result.toUpperCase()}</td>
                      <td style={{padding:'5px 8px',color:t.pnl>=0?'#22c55e':'#ef4444',textAlign:'right',fontWeight:600}}>{(t.pnl>=0?'+':'')+('$'+t.pnl.toFixed(2))}</td>
                    </tr>
                  })}</tbody>
                </table>
              </div>
            </div>
          })()}

          {btResults.length === 0 && !btRunning && <div style={{ color: '#94a3b8', textAlign: 'center', padding: 40 }}>
            No backtest results yet. Click <b>▶ Run Backtest</b> to start.<br/>
            <span style={{ fontSize: 12 }}>251 candidates · Est. ~8 mins (EODHD rate limited)</span>
          </div>}
        </div>
      )}

      {activeTab === 'training' && React.createElement(TrainingLab, null)}

      {/* Confirm Modal */}
      {confirmModal && <ConfirmModal title={confirmModal.title} message={confirmModal.message} onConfirm={confirmModal.onConfirm} onCancel={function () { setConfirmModal(null) }} />}

      {/* Pulse animation for live banner */}
      <style>{'\
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.7} }\
        @keyframes pulse-red { 0%,100%{opacity:1} 50%{opacity:0.3} }\
        .pulse-dot { width:7px; height:7px; border-radius:50%; background:#ef4444; display:inline-block; animation:pulse-red 1.2s ease-in-out infinite; margin-left:4px; flex-shrink:0; }\
      '}</style>
    </div>
  )
}


// ── Training Lab ────────────────────────────────────────────────────────────
function TrainingLab() {
  var VISION = 'http://localhost:8769'
  var _s = React.useState
  var _e = React.useEffect
  var _cb = React.useCallback
  var _ref = React.useRef

  var _ticker = _s(''); var ticker = _ticker[0]; var setTicker = _ticker[1]
  var _queue = _s([]); var queue = _queue[0]; var setQueue = _queue[1]
  var _idx = _s(0); var idx = _idx[0]; var setIdx = _idx[1]
  var _stats = _s(null); var stats = _stats[0]; var setStats = _stats[1]
  var _capturing = _s(false); var capturing = _capturing[0]; var setCapturing = _capturing[1]
  var _capMsg = _s(''); var capMsg = _capMsg[0]; var setCapMsg = _capMsg[1]
  var _selectedLabel = _s(null); var selectedLabel = _selectedLabel[0]; var setSelectedLabel = _selectedLabel[1]
  var _selectedOutcome = _s(null); var selectedOutcome = _selectedOutcome[0]; var setSelectedOutcome = _selectedOutcome[1]
  var _submitting = _s(false); var submitting = _submitting[0]; var setSubmitting = _submitting[1]
  var _imgErr = _s({}); var imgErr = _imgErr[0]; var setImgErr = _imgErr[1]

  var loadQueue = _cb(function () {
    fetch(VISION + '/pattern/unlabeled?limit=50')
      .then(function(r){return r.json()}).then(function(d){setQueue(d||[])}).catch(function(){})
  }, [])

  var loadStats = _cb(function () {
    fetch(VISION + '/training/stats')
      .then(function(r){return r.json()}).then(function(d){setStats(d)}).catch(function(){})
  }, [])

  _e(function () { loadQueue(); loadStats(); }, [])

  var current = queue[idx] || null

  // Reset label/outcome when card changes
  _e(function () { setSelectedLabel(null); setSelectedOutcome(null) }, [idx, current && current.id])

  // Keyboard shortcuts
  _e(function () {
    var labelMap = { b: 'bull_flag_confirmed', f: 'bull_flag_forming', d: 'bear', m: 'macd', g: 'gap', o: 'orb', n: 'none' }
    var outcomeMap = { w: 'win', l: 'loss' }
    function onKey(e) {
      if (e.target.tagName === 'INPUT') return
      var lbl = labelMap[e.key]
      var out = outcomeMap[e.key]
      if (lbl) { setSelectedLabel(lbl); return }
      if (out) { setSelectedOutcome(out); return }
      if (e.key === 'ArrowRight' || e.key === 's') {
        setIdx(function(i){ return Math.min(i+1, queue.length-1) })
      }
    }
    window.addEventListener('keydown', onKey)
    return function () { window.removeEventListener('keydown', onKey) }
  }, [queue.length])

  var submitLabel = _cb(function (label, outcome) {
    if (!current || submitting) return
    setSubmitting(true)
    fetch(VISION + '/pattern/label', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({id: current.id, label: label, outcome: outcome})
    }).then(function(){
      setQueue(function(q){ return q.filter(function(item){ return item.id !== current.id }) })
      setIdx(function(i){ return Math.max(0, Math.min(i, queue.length - 2)) })
      setSelectedLabel(null); setSelectedOutcome(null)
      loadStats()
    }).catch(function(){}).finally(function(){ setSubmitting(false) })
  }, [current, submitting, queue.length])

  var doCapture = _cb(function () {
    if (!ticker.trim() || capturing) return
    setCapturing(true); setCapMsg('📸 Capturing ' + ticker.toUpperCase() + '...')
    fetch(VISION + '/capture/' + ticker.trim().toUpperCase(), {method:'POST'})
      .then(function(r){return r.json()}).then(function(d){
        setCapMsg('✅ ' + d.ticker + ' captured · pattern: ' + d.pattern + ' (' + (d.confidence*100).toFixed(0) + '%)')
        loadQueue(); loadStats()
      }).catch(function(e){ setCapMsg('❌ Capture failed') })
      .finally(function(){ setCapturing(false); setTimeout(function(){setCapMsg('')}, 5000) })
  }, [ticker, capturing])

  var LABELS = [
    {key:'bull_flag_confirmed', emoji:'🚩', text:'Bull Flag↑', short:'b'},
    {key:'bull_flag_forming',   emoji:'🏳', text:'Bull Flag~', short:'f'},
    {key:'bear',                emoji:'📉', text:'Bear',       short:'d'},
    {key:'macd',                emoji:'📊', text:'MACD',       short:'m'},
    {key:'gap',                 emoji:'🚀', text:'GAP',        short:'g'},
    {key:'orb',                 emoji:'⭕', text:'ORB',        short:'o'},
    {key:'none',                emoji:'❌', text:'None',       short:'n'},
  ]

  var bg = '#0f1320'; var panel = '#161b2e'; var border = '#1e2a44'
  var text = '#e2e8f0'; var muted = '#6b7280'; var accent = '#60a5fa'

  return React.createElement('div', {style:{padding:20, maxWidth:1100, margin:'0 auto'}},
    // Top bar
    React.createElement('div', {style:{display:'flex',alignItems:'center',gap:12,marginBottom:16,flexWrap:'wrap'}},
      React.createElement('input', {
        value: ticker,
        onChange: function(e){setTicker(e.target.value.toUpperCase())},
        onKeyDown: function(e){ if(e.key==='Enter') doCapture() },
        placeholder: 'Ticker e.g. AAPL',
        style:{background:'#1a2035',border:'1px solid '+border,color:text,padding:'8px 12px',borderRadius:6,fontSize:14,width:140,fontFamily:'monospace'}
      }),
      React.createElement('button', {
        onClick: doCapture,
        disabled: capturing || !ticker.trim(),
        style:{background:capturing?'#374151':'#2563eb',color:'#fff',border:'none',padding:'8px 16px',borderRadius:6,cursor:capturing?'not-allowed':'pointer',fontWeight:600,fontSize:14}
      }, capturing ? '⏳ Capturing...' : '📸 Capture'),
      capMsg && React.createElement('span', {style:{color:'#94a3b8',fontSize:13}}, capMsg),
      React.createElement('div', {style:{marginLeft:'auto',display:'flex',gap:16,fontSize:13,color:muted}},
        stats && [
          React.createElement('span', {key:'l'}, React.createElement('b', {style:{color:'#22c55e'}}, stats.labeled), ' labeled'),
          React.createElement('span', {key:'p'}, React.createElement('b', {style:{color:'#f59e0b'}}, stats.pending_label), ' pending'),
          React.createElement('span', {key:'t'}, React.createElement('b', {style:{color:accent}}, stats.used_in_training), ' trained'),
        ]
      )
    ),

    // Main content
    queue.length === 0
      ? React.createElement('div', {style:{textAlign:'center',padding:80,color:muted}},
          React.createElement('div', {style:{fontSize:40,marginBottom:12}}, '🎉'),
          React.createElement('div', {style:{fontSize:16}}, 'No unlabeled patterns — queue is clear!'),
          React.createElement('div', {style:{fontSize:13,marginTop:8}}, 'Use the Capture button above to add new charts.')
        )
      : React.createElement('div', {style:{display:'grid',gridTemplateColumns:'1fr 320px',gap:20,alignItems:'start'}},
          // Left: chart card
          React.createElement('div', {style:{background:panel,borderRadius:10,border:'1px solid '+border,overflow:'hidden'}},
            current && React.createElement('div', null,
              // Image
              React.createElement('div', {style:{background:'#0a0f1a',position:'relative'}},
                imgErr[current.id]
                  ? React.createElement('div', {style:{height:300,display:'flex',alignItems:'center',justifyContent:'center',color:muted,fontSize:13}}, '🖼 No screenshot stored')
                  : React.createElement('img', {
                      src: VISION + '/pattern/' + current.id + '/image',
                      alt: 'chart',
                      style:{width:'100%',display:'block',maxHeight:380,objectFit:'contain'},
                      onError: function(){ setImgErr(function(e){ var n={};Object.assign(n,e);n[current.id]=true;return n }) }
                    })
              ),
              // Card info
              React.createElement('div', {style:{padding:'14px 16px'}},
                React.createElement('div', {style:{display:'flex',alignItems:'center',gap:10,marginBottom:10}},
                  React.createElement('span', {style:{fontSize:22,fontWeight:700,fontFamily:'monospace',color:text}}, current.ticker),
                  React.createElement('span', {style:{fontSize:12,color:muted}},
                    new Date(current.detected_at).toLocaleString('en-US',{timeZone:'America/New_York',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) + ' ET'
                  ),
                  React.createElement('span', {style:{marginLeft:'auto',background:'#1a2a4a',padding:'3px 10px',borderRadius:20,fontSize:12,color:accent,fontWeight:600}},
                    'YOLO: ' + (current.pattern||'?') + ' ' + ((current.confidence||0)*100).toFixed(0) + '%'
                  )
                ),
                // Label buttons
                React.createElement('div', {style:{marginBottom:10}},
                  React.createElement('div', {style:{fontSize:11,color:muted,marginBottom:6,textTransform:'uppercase',letterSpacing:'0.05em'}}, 'Pattern Label'),
                  React.createElement('div', {style:{display:'flex',gap:6,flexWrap:'wrap'}},
                    LABELS.map(function(l){
                      var active = selectedLabel === l.key
                      return React.createElement('button', {
                        key: l.key,
                        onClick: function(){ setSelectedLabel(active ? null : l.key) },
                        style:{
                          background: active ? '#1d4ed8' : '#1a2035',
                          border: '1px solid ' + (active ? '#3b82f6' : border),
                          color: active ? '#fff' : text,
                          padding:'6px 12px',borderRadius:6,cursor:'pointer',fontSize:13,fontWeight:active?700:400
                        }
                      }, l.emoji + ' ' + l.text + ' [' + l.short + ']')
                    })
                  )
                ),
                // Outcome buttons
                React.createElement('div', {style:{marginBottom:14}},
                  React.createElement('div', {style:{fontSize:11,color:muted,marginBottom:6,textTransform:'uppercase',letterSpacing:'0.05em'}}, 'Outcome'),
                  React.createElement('div', {style:{display:'flex',gap:8}},
                    React.createElement('button', {
                      onClick: function(){ setSelectedOutcome(selectedOutcome==='win'?null:'win') },
                      style:{background:selectedOutcome==='win'?'#166534':'#1a2035',border:'1px solid '+(selectedOutcome==='win'?'#22c55e':border),color:text,padding:'7px 18px',borderRadius:6,cursor:'pointer',fontSize:14,fontWeight:600}
                    }, '✅ Win [w]'),
                    React.createElement('button', {
                      onClick: function(){ setSelectedOutcome(selectedOutcome==='loss'?null:'loss') },
                      style:{background:selectedOutcome==='loss'?'#7f1d1d':'#1a2035',border:'1px solid '+(selectedOutcome==='loss'?'#ef4444':border),color:text,padding:'7px 18px',borderRadius:6,cursor:'pointer',fontSize:14,fontWeight:600}
                    }, '❌ Loss [l]'),
                    React.createElement('button', {
                      onClick: function(){ setIdx(function(i){return Math.min(i+1,queue.length-1)}) },
                      style:{background:'#1a2035',border:'1px solid '+border,color:muted,padding:'7px 18px',borderRadius:6,cursor:'pointer',fontSize:14}
                    }, '⏭ Skip [→]')
                  )
                ),
                // Submit
                React.createElement('button', {
                  onClick: function(){ if(selectedLabel) submitLabel(selectedLabel, selectedOutcome) },
                  disabled: !selectedLabel || submitting,
                  style:{
                    width:'100%',background:selectedLabel?'#1d4ed8':'#1a2035',color:selectedLabel?'#fff':muted,
                    border:'1px solid '+(selectedLabel?'#3b82f6':border),
                    padding:'10px',borderRadius:6,cursor:selectedLabel?'pointer':'not-allowed',
                    fontWeight:700,fontSize:15
                  }
                }, submitting ? '⏳ Saving...' : selectedLabel ? '💾 Save Label' : 'Select a label above')
              )
            )
          ),

          // Right: queue list
          React.createElement('div', {style:{background:panel,borderRadius:10,border:'1px solid '+border,overflow:'hidden'}},
            React.createElement('div', {style:{padding:'12px 16px',borderBottom:'1px solid '+border,fontWeight:600,fontSize:13,color:text}},
              '📋 Queue (' + queue.length + ')'
            ),
            React.createElement('div', {style:{overflowY:'auto',maxHeight:500}},
              queue.map(function(item, i){
                var active = i === idx
                return React.createElement('div', {
                  key: item.id,
                  onClick: function(){ setIdx(i) },
                  style:{
                    padding:'10px 14px',cursor:'pointer',
                    background: active ? '#1a2a4a' : i%2===0?panel:'#0f1320',
                    borderLeft: '3px solid ' + (active ? accent : 'transparent'),
                    borderBottom: '1px solid ' + border
                  }
                },
                  React.createElement('div', {style:{display:'flex',justifyContent:'space-between',alignItems:'center'}},
                    React.createElement('span', {style:{fontWeight:600,fontFamily:'monospace',color:active?accent:text,fontSize:14}}, item.ticker),
                    React.createElement('span', {style:{fontSize:11,color:muted}}, ((item.confidence||0)*100).toFixed(0)+'%')
                  ),
                  React.createElement('div', {style:{fontSize:11,color:muted,marginTop:2}}, item.pattern||'unknown')
                )
              })
            )
          )
        ),

    // Keyboard shortcut legend
    React.createElement('div', {style:{marginTop:16,padding:'10px 16px',background:panel,borderRadius:8,border:'1px solid '+border,fontSize:12,color:muted}},
      '⌨️ Shortcuts: ',
      React.createElement('b',{style:{color:text}},'b'),
      '=bull↑  ',
      React.createElement('b',{style:{color:text}},'f'),
      '=forming  ',
      React.createElement('b',{style:{color:text}},'d'),
      '=bear  ',
      React.createElement('b',{style:{color:text}},'m'),
      '=macd  ',
      React.createElement('b',{style:{color:text}},'g'),
      '=gap  ',
      React.createElement('b',{style:{color:text}},'o'),
      '=orb  ',
      React.createElement('b',{style:{color:text}},'n'),
      '=none  ',
      React.createElement('b',{style:{color:text}},'w'),
      '=win  ',
      React.createElement('b',{style:{color:text}},'l'),
      '=loss  ',
      React.createElement('b',{style:{color:text}},'→'),
      '=skip'
    )
  )
}

createRoot(document.getElementById('root')).render(<App />)
