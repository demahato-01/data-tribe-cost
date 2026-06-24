#!/usr/bin/env python3
"""
AWS Cost Monitor — grpn-dnd-prod + grpn-teradata-prod
Week-over-week cost tracking, per-account service breakdown, monthly trends.
Usage: python3 build_dashboard.py
Requires: boto3, AWS profiles 'dnd-prod' and 'teradata-prod'
"""
import boto3, json, calendar, os, shutil
from datetime import date

ACCOUNTS = [
    {'profile': 'dnd-prod',      'id': '458721635755', 'name': 'grpn-dnd-prod',      'color': '#ed8936'},
    {'profile': 'teradata-prod', 'id': '851725417994', 'name': 'grpn-teradata-prod', 'color': '#4299e1'},
]
OUTPUT = '/Users/demahato/work/git/data-tribe-cost/aws-cost/dashboard.html'

TODAY         = date.today()
DAYS_IN_MONTH = calendar.monthrange(TODAY.year, TODAY.month)[1]
MONTH_START   = TODAY.replace(day=1).isoformat()
TODAY_STR     = TODAY.isoformat()
WEEK_END      = TODAY.replace(day=22).isoformat()

def nth_month_ago(n):
    m, y = TODAY.month - n, TODAY.year
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)

month_starts = [nth_month_ago(i) for i in range(3, -1, -1)]
MONTHS       = [d.strftime('%Y-%m') for d in month_starts]
MLABELS      = [d.strftime('%b') for d in month_starts]
hist_start   = month_starts[0].isoformat()
cur_month    = MONTHS[-1]

DIM_SVC = [{'Type': 'DIMENSION', 'Key': 'SERVICE'}]

def ce_get(ce_client, start, end, granularity, group_by):
    kwargs = dict(
        TimePeriod={'Start': start, 'End': end},
        Granularity=granularity,
        Metrics=['UnblendedCost'],
        GroupBy=group_by,
    )
    out = []
    while True:
        r = ce_client.get_cost_and_usage(**kwargs)
        out.extend(r['ResultsByTime'])
        tok = r.get('NextPageToken')
        if not tok:
            break
        kwargs['NextPageToken'] = tok
    return out

def amt(g):
    return float(g['Metrics']['UnblendedCost']['Amount'])

def agg_weekly(daily_periods):
    w = [{}, {}, {}]
    for period in daily_periods:
        d = date.fromisoformat(period['TimePeriod']['Start'])
        if d.day <= 7:    wi = 0
        elif d.day <= 14: wi = 1
        elif d.day <= 21: wi = 2
        else: continue
        for g in period['Groups']:
            svc = g['Keys'][0]
            w[wi][svc] = w[wi].get(svc, 0.0) + amt(g)
    return w

# ── Fetch and process per account ─────────────────────────────────────────────
acct_results = []

for acct in ACCOUNTS:
    print(f"Fetching {acct['name']}...")
    ce = boto3.Session(profile_name=acct['profile']).client('ce', region_name='us-east-1')

    hist  = ce_get(ce, hist_start,   TODAY_STR, 'MONTHLY', DIM_SVC)
    daily = ce_get(ce, MONTH_START,  WEEK_END,  'DAILY',   DIM_SVC)

    svc_monthly = {}
    for period in hist:
        m = period['TimePeriod']['Start'][:7]
        for g in period['Groups']:
            svc = g['Keys'][0]
            svc_monthly.setdefault(svc, {})[m] = amt(g)

    wsvc = agg_weekly(daily)

    services = []
    for svc in sorted(svc_monthly, key=lambda x: -svc_monthly[x].get(cur_month, 0)):
        mtd = svc_monthly[svc].get(cur_month, 0.0)
        monthly = [round(svc_monthly[svc].get(m, 0.0), 2) for m in MONTHS]
        w1 = wsvc[0].get(svc, 0.0)
        w2 = wsvc[1].get(svc, 0.0)
        w3 = wsvc[2].get(svc, 0.0)
        delta = round(w3 - w2, 2)
        delta_pct = round(delta / w2 * 100, 1) if w2 > 0 else None
        services.append({
            'name': svc,
            'mtd': round(mtd, 2),
            'monthly': monthly,
            'w1': round(w1, 2), 'w2': round(w2, 2), 'w3': round(w3, 2),
            'delta': delta, 'delta_pct': delta_pct,
        })

    mtd_total = round(sum(svc_monthly[s].get(cur_month, 0) for s in svc_monthly), 2)
    last_m    = round(sum(svc_monthly[s].get(MONTHS[-2], 0) for s in svc_monthly), 2)
    prev_m    = round(sum(svc_monthly[s].get(MONTHS[-3], 0) for s in svc_monthly), 2)
    projected = round(mtd_total * DAYS_IN_MONTH / TODAY.day, 2)
    mom_pct   = round((projected - last_m) / last_m * 100, 1) if last_m else None
    monthly   = [round(sum(svc_monthly[s].get(m, 0) for s in svc_monthly), 2) for m in MONTHS]

    w1t = round(sum(wsvc[0].values()), 2)
    w2t = round(sum(wsvc[1].values()), 2)
    w3t = round(sum(wsvc[2].values()), 2)
    w2w3_delta = round(w3t - w2t, 2)
    w2w3_pct   = round(w2w3_delta / w2t * 100, 1) if w2t else 0
    w1w2_pct   = round((w2t - w1t) / w1t * 100, 1) if w1t else 0

    movers = sorted([s for s in services if s['w2'] > 5], key=lambda x: -abs(x['delta']))[:10]

    acct_results.append({
        **acct,
        'mtd': mtd_total, 'projected': projected,
        'last_month': last_m, 'prev_month': prev_m, 'mom_pct': mom_pct,
        'monthly': monthly,
        'w1t': w1t, 'w2t': w2t, 'w3t': w3t,
        'w2w3_delta': w2w3_delta, 'w2w3_pct': w2w3_pct, 'w1w2_pct': w1w2_pct,
        'services': services,
        'movers': movers,
        'service_count': len([s for s in services if s['mtd'] > 0]),
    })

print('Building dashboard...')

comb_mtd    = round(sum(a['mtd'] for a in acct_results), 2)
comb_proj   = round(sum(a['projected'] for a in acct_results), 2)
comb_last   = round(sum(a['last_month'] for a in acct_results), 2)
comb_prev   = round(sum(a['prev_month'] for a in acct_results), 2)
comb_mom    = round((comb_proj - comb_last) / comb_last * 100, 1) if comb_last else 0
comb_monthly= [round(sum(a['monthly'][i] for a in acct_results), 2) for i in range(len(MONTHS))]
comb_w1t    = round(sum(a['w1t'] for a in acct_results), 2)
comb_w2t    = round(sum(a['w2t'] for a in acct_results), 2)
comb_w3t    = round(sum(a['w3t'] for a in acct_results), 2)
comb_w2w3   = round(comb_w3t - comb_w2t, 2)
comb_w2w3p  = round(comb_w2w3 / comb_w2t * 100, 1) if comb_w2t else 0
comb_w1w2p  = round((comb_w2t - comb_w1t) / comb_w1t * 100, 1) if comb_w1t else 0

D = {
    'generatedDate': TODAY_STR,
    'currentMonthLabel': TODAY.strftime('%B %Y'),
    'dayOfMonth': TODAY.day, 'daysInMonth': DAYS_IN_MONTH,
    'months': MLABELS,
    'lastMonthLabel': MLABELS[-2] if len(MLABELS) >= 2 else '',
    'prevMonthLabel': MLABELS[-3] if len(MLABELS) >= 3 else '',
    'combined': {
        'mtd': comb_mtd, 'projected': comb_proj,
        'last_month': comb_last, 'prev_month': comb_prev, 'mom_pct': comb_mom,
        'monthly': comb_monthly,
        'w1t': comb_w1t, 'w2t': comb_w2t, 'w3t': comb_w3t,
        'w2w3_delta': comb_w2w3, 'w2w3_pct': comb_w2w3p, 'w1w2_pct': comb_w1w2p,
    },
    'accounts': acct_results,
}
D_JSON = json.dumps(D, separators=(',', ':'))

# ── HTML ──────────────────────────────────────────────────────────────────────
HEAD = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AWS Cost Monitor</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0b0e17;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px}
.container{max-width:1600px;margin:0 auto;padding:20px}

/* Header */
.header{display:flex;justify-content:space-between;align-items:flex-start;background:#131825;border:1px solid #1e2a3a;border-radius:12px;padding:20px 24px;margin-bottom:20px;gap:20px}
.header-title{font-size:22px;font-weight:700;color:#f7fafc;display:flex;align-items:center;gap:10px}
.aws-pill{background:#f90;color:#000;font-weight:800;font-size:11px;padding:3px 8px;border-radius:4px}
.header-meta{color:#4a5568;font-size:12px;margin-top:5px}
.combined-strip{display:flex;gap:28px;flex-wrap:wrap}
.cs-item{text-align:right}
.cs-label{display:block;color:#4a5568;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px}
.cs-val{display:block;font-size:20px;font-weight:700;font-family:monospace;color:#f7fafc}
.cs-sub{display:block;font-size:11px;color:#718096;margin-top:1px}

/* Account cards */
.acct-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.acct-card{background:#131825;border:2px solid;border-radius:12px;padding:20px}
.acct-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px}
.acct-name{font-size:16px;font-weight:700;margin-bottom:2px}
.acct-id{font-size:11px;color:#4a5568;font-family:monospace}
.acct-svc-count{text-align:right}
.acct-svc-num{font-size:24px;font-weight:700;color:#f7fafc;font-family:monospace}
.acct-svc-lbl{font-size:10px;color:#718096;text-transform:uppercase;letter-spacing:.5px}
.acct-stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px}
.acct-stat{background:#0b0e17;border-radius:8px;padding:12px}
.acct-stat-lbl{color:#718096;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.acct-stat-val{font-size:16px;font-weight:700;font-family:monospace;color:#f7fafc}
.acct-stat-sub{font-size:11px;color:#718096;margin-top:2px}
.wow-strip{background:#0b0e17;border-radius:8px;padding:14px}
.wow-strip-title{color:#718096;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px}
.wow-weeks{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
.wow-week{text-align:center}
.wow-week-lbl{font-size:10px;color:#4a5568;margin-bottom:3px}
.wow-week-val{font-size:15px;font-weight:700;font-family:monospace;color:#f7fafc}
.wow-week-chg{font-size:11px;font-weight:700;margin-top:2px}
.wow-arrow{font-size:11px;color:#4a5568;align-self:center;text-align:center;padding-top:14px}

/* Section */
.section{background:#131825;border:1px solid #1e2a3a;border-radius:12px;padding:20px;margin-bottom:20px}
h2{font-size:17px;font-weight:600;color:#e2e8f0;margin-bottom:16px;display:flex;align-items:center;gap:8px}
h3{font-size:13px;font-weight:600;color:#a0aec0;margin-bottom:10px}
.tag{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;padding:2px 8px;border-radius:4px;margin-left:4px}

/* WoW summary table */
.wow-summary{width:100%;border-collapse:collapse;margin-bottom:20px;font-size:13px}
.wow-summary th{background:#0b0e17;color:#718096;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;padding:10px 14px;text-align:right;border-bottom:1px solid #1e2a3a}
.wow-summary th:first-child{text-align:left}
.wow-summary td{padding:12px 14px;border-bottom:1px solid #1a2030;text-align:right;font-family:monospace}
.wow-summary td:first-child{text-align:left;font-family:-apple-system,sans-serif}
.wow-summary tr:last-child td{border-bottom:none;font-weight:700;color:#f7fafc;background:#0b0e1766}
.wow-summary tr:hover td{background:#1e2a3a44}

/* Breakdown grid */
.breakdown-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.breakdown-card{background:#131825;border:2px solid;border-radius:12px;padding:18px}
.breakdown-title{font-size:14px;font-weight:700;margin-bottom:4px}
.breakdown-sub{font-size:11px;color:#4a5568;margin-bottom:14px}

/* Service tables */
.svc-table{width:100%;border-collapse:collapse;font-size:12px}
.svc-table th{background:#0b0e17;color:#718096;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;padding:8px 10px;text-align:right;border-bottom:1px solid #1e2a3a;cursor:pointer;white-space:nowrap}
.svc-table th:first-child{text-align:left}
.svc-table th:hover{color:#e2e8f0}
.svc-table td{padding:8px 10px;border-bottom:1px solid #1a2030;text-align:right;vertical-align:middle}
.svc-table td:first-child{text-align:left}
.svc-table tr:hover td{background:#1e2a3a44}
.svc-name{font-size:11px;color:#e2e8f0;white-space:nowrap}
.svc-bar-wrap{height:2px;background:#1e2a3a;border-radius:1px;margin-top:3px;width:100%;min-width:60px}
.svc-bar{height:2px;border-radius:1px}
.mono{font-family:monospace;color:#cbd5e0}
.dim{color:#4a5568}
.up{color:#fc8181;font-weight:700}
.dn{color:#68d391;font-weight:700}
.neutral{color:#718096}

/* Charts */
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.g2-35{display:grid;grid-template-columns:3fr 2fr;gap:16px}
.cbox{background:#0b0e17;border:1px solid #1e2a3a;border-radius:8px;padding:16px}
.cbox canvas{max-height:260px}

/* Monthly */
.monthly-grid{display:grid;grid-template-columns:2fr 1fr;gap:16px}
</style>
</head>
<body>
<div class="container">

<!-- Header -->
<div class="header">
  <div>
    <div class="header-title">AWS Cost Monitor <span class="aws-pill">AWS</span></div>
    <div class="header-meta" id="header-meta"></div>
  </div>
  <div class="combined-strip" id="combined-strip"></div>
</div>

<!-- Account Cards -->
<div class="acct-grid" id="acct-cards"></div>

<!-- WoW Section -->
<div class="section">
  <h2>Week-over-Week <span class="tag" id="wow-tag" style="color:#a0aec0;background:#1e2a3a"></span></h2>
  <table class="wow-summary" id="wow-table"></table>
  <div class="g2-35">
    <div class="cbox"><h3>Weekly Spend by Account</h3><canvas id="wowChart"></canvas></div>
    <div>
      <h3 style="margin-bottom:12px">Biggest Cost Movers W2 → W3</h3>
      <div class="g2" id="movers-grid" style="gap:12px"></div>
    </div>
  </div>
</div>

<!-- Per-account service breakdown -->
<div class="breakdown-grid" id="breakdown"></div>

<!-- Monthly trends -->
<div class="section">
  <h2>Monthly Trends</h2>
  <div class="g2">
    <div class="cbox"><h3>Total Spend by Account (Last 4 Months)</h3><canvas id="monthlyChart"></canvas></div>
    <div class="cbox"><h3>Top 5 Services per Account — MTD</h3><canvas id="topSvcChart"></canvas></div>
  </div>
</div>

</div>
<script>
const D = '''

TAIL = ''';

function fmt(v,d){d=d===undefined?2:d;return(v||0).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});}
function fmtW(v){return fmt(v,0);}

function deltaHtml(delta,pct,size){
  if(delta===null||delta===undefined)return '<span class="neutral">—</span>';
  var up=delta>0;
  var cls=up?'up':'dn';
  var arrow=up?'▲':'▼';
  var s=size==='sm'?'font-size:11px':'font-size:13px';
  var p=pct!==null&&pct!==undefined?' <span style="opacity:.65">('+Math.abs(pct)+'%)</span>':'';
  return '<span class="'+cls+'" style="'+s+'">'+arrow+' $'+fmt(Math.abs(delta))+p+'</span>';
}

function momHtml(pct){
  if(pct===null||pct===undefined)return '<span class="neutral">—</span>';
  var up=pct>0,cls=up?'up':'dn';
  return '<span class="'+cls+'">'+(up?'▲':'▼')+' '+Math.abs(pct)+'%</span>';
}

// ── Header ──────────────────────────────────────────────────────────────────
var C=D.combined;
document.getElementById('header-meta').textContent=
  D.accounts.map(function(a){return a.name+' ('+a.id+')';}).join(' · ')+
  ' · Generated '+D.generatedDate+' · MTD = '+D.currentMonthLabel+' 1–'+D.dayOfMonth;

document.getElementById('combined-strip').innerHTML=
  '<div class="cs-item"><span class="cs-label">Combined MTD</span><span class="cs-val">$'+fmt(C.mtd)+'</span><span class="cs-sub">Projected $'+fmt(C.projected)+'</span></div>'+
  '<div class="cs-item"><span class="cs-label">vs '+D.lastMonthLabel+'</span><span class="cs-val">'+momHtml(C.mom_pct)+'</span><span class="cs-sub">Last: $'+fmt(C.last_month)+'</span></div>'+
  '<div class="cs-item"><span class="cs-label">W2 → W3</span><span class="cs-val">'+deltaHtml(C.w2w3_delta,C.w2w3_pct)+'</span><span class="cs-sub">W3: $'+fmt(C.w3t)+'</span></div>'+
  '<div class="cs-item"><span class="cs-label">W1 → W2</span><span class="cs-val">'+deltaHtml(C.w2t-C.w1t,C.w1w2_pct)+'</span><span class="cs-sub">W2: $'+fmt(C.w2t)+'</span></div>';

// ── Account cards ────────────────────────────────────────────────────────────
document.getElementById('acct-cards').innerHTML=D.accounts.map(function(a){
  var wchg1=a.w1w2_pct!==0?deltaHtml(a.w2t-a.w1t,a.w1w2_pct,'sm'):'<span class="neutral">—</span>';
  var wchg2=deltaHtml(a.w2w3_delta,a.w2w3_pct,'sm');
  return '<div class="acct-card" style="border-color:'+a.color+'44">'+
    '<div class="acct-header">'+
      '<div><div class="acct-name" style="color:'+a.color+'">'+a.name+'</div><div class="acct-id">'+a.id+'</div></div>'+
      '<div class="acct-svc-count"><div class="acct-svc-num">'+a.service_count+'</div><div class="acct-svc-lbl">services</div></div>'+
    '</div>'+
    '<div class="acct-stats">'+
      '<div class="acct-stat"><div class="acct-stat-lbl">MTD Spend</div><div class="acct-stat-val">$'+fmt(a.mtd)+'</div><div class="acct-stat-sub">Proj $'+fmt(a.projected)+'</div></div>'+
      '<div class="acct-stat"><div class="acct-stat-lbl">'+D.lastMonthLabel+' (Full)</div><div class="acct-stat-val">$'+fmt(a.last_month)+'</div><div class="acct-stat-sub">MoM '+momHtml(a.mom_pct)+'</div></div>'+
      '<div class="acct-stat"><div class="acct-stat-lbl">'+D.prevMonthLabel+'</div><div class="acct-stat-val">$'+fmt(a.prev_month)+'</div><div class="acct-stat-sub" style="color:#4a5568">prior month</div></div>'+
    '</div>'+
    '<div class="wow-strip">'+
      '<div class="wow-strip-title">Week-over-Week — '+D.currentMonthLabel+'</div>'+
      '<div class="wow-weeks">'+
        '<div class="wow-week"><div class="wow-week-lbl">W1 · Jun 1–7</div><div class="wow-week-val">$'+fmt(a.w1t)+'</div><div class="wow-week-chg neutral">baseline</div></div>'+
        '<div class="wow-week"><div class="wow-week-lbl">W2 · Jun 8–14</div><div class="wow-week-val">$'+fmt(a.w2t)+'</div><div class="wow-week-chg">'+wchg1+'</div></div>'+
        '<div class="wow-week"><div class="wow-week-lbl">W3 · Jun 15–21</div><div class="wow-week-val">$'+fmt(a.w3t)+'</div><div class="wow-week-chg">'+wchg2+'</div></div>'+
      '</div>'+
    '</div>'+
  '</div>';
}).join('');

// ── WoW summary table ────────────────────────────────────────────────────────
var mon=D.currentMonthLabel.split(' ')[0].slice(0,3);
document.getElementById('wow-tag').textContent=D.currentMonthLabel+' — Jun 1–21';
var wrows=D.accounts.map(function(a){
  return '<tr>'+
    '<td><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:'+a.color+';margin-right:8px"></span>'+a.name+'</td>'+
    '<td class="mono">$'+fmt(a.w1t)+'</td>'+
    '<td class="mono">$'+fmt(a.w2t)+'</td>'+
    '<td class="mono">'+deltaHtml(a.w2t-a.w1t,a.w1w2_pct,'sm')+'</td>'+
    '<td class="mono">$'+fmt(a.w3t)+'</td>'+
    '<td class="mono">'+deltaHtml(a.w2w3_delta,a.w2w3_pct,'sm')+'</td>'+
  '</tr>';
}).join('');
var ctot='<tr>'+
  '<td style="color:#a0aec0;font-family:sans-serif"><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#555;margin-right:8px"></span>Combined</td>'+
  '<td class="mono">$'+fmt(C.w1t)+'</td>'+
  '<td class="mono">$'+fmt(C.w2t)+'</td>'+
  '<td class="mono">'+deltaHtml(C.w2t-C.w1t,C.w1w2_pct,'sm')+'</td>'+
  '<td class="mono">$'+fmt(C.w3t)+'</td>'+
  '<td class="mono">'+deltaHtml(C.w2w3_delta,C.w2w3_pct,'sm')+'</td>'+
'</tr>';
document.getElementById('wow-table').innerHTML=
  '<thead><tr>'+
    '<th style="text-align:left">Account</th>'+
    '<th>W1 ('+mon+' 1–7)</th><th>W2 ('+mon+' 8–14)</th><th>W1→W2 Δ</th>'+
    '<th>W3 ('+mon+' 15–21)</th><th>W2→W3 Δ</th>'+
  '</tr></thead><tbody>'+wrows+ctot+'</tbody>';

// ── WoW chart ────────────────────────────────────────────────────────────────
new Chart(document.getElementById('wowChart'),{
  type:'bar',
  data:{
    labels:['W1 (Jun 1–7)','W2 (Jun 8–14)','W3 (Jun 15–21)'],
    datasets:D.accounts.map(function(a){return{
      label:a.name,
      data:[a.w1t,a.w2t,a.w3t],
      backgroundColor:a.color,
      borderRadius:4,
    };})
  },
  options:{
    responsive:true,
    plugins:{legend:{labels:{color:'#a0aec0',font:{size:11}}}},
    scales:{
      x:{ticks:{color:'#718096'},grid:{color:'#1e2a3a'}},
      y:{ticks:{color:'#718096',callback:function(v){return '$'+fmtW(v);}},grid:{color:'#1e2a3a'}}
    }
  }
});

// ── Movers per account ───────────────────────────────────────────────────────
document.getElementById('movers-grid').innerHTML=D.accounts.map(function(a){
  var rows=a.movers.map(function(m){
    var up=m.delta>0,cls=up?'up':'dn',arrow=up?'▲':'▼';
    return '<tr>'+
      '<td style="font-size:11px;color:#a0aec0;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+m.name+'</td>'+
      '<td class="mono dim" style="font-size:11px">$'+fmt(m.w2)+'</td>'+
      '<td class="mono" style="font-size:11px">$'+fmt(m.w3)+'</td>'+
      '<td class="'+cls+'" style="font-size:11px;white-space:nowrap">'+arrow+' $'+fmt(Math.abs(m.delta))+'</td>'+
    '</tr>';
  }).join('');
  return '<div>'+
    '<div style="font-size:12px;font-weight:700;color:'+a.color+';margin-bottom:8px">'+a.name+'</div>'+
    '<table class="svc-table" style="font-size:11px">'+
      '<thead><tr><th style="text-align:left">Service</th><th>W2</th><th>W3</th><th>Δ</th></tr></thead>'+
      '<tbody>'+rows+'</tbody>'+
    '</table>'+
  '</div>';
}).join('');

// ── Per-account service breakdown ────────────────────────────────────────────
function sortTable(tbodyId,col,asc){
  var tbody=document.getElementById(tbodyId);
  if(!tbody)return;
  var rows=Array.from(tbody.querySelectorAll('tr'));
  rows.sort(function(a,b){
    var av=parseFloat(a.dataset['c'+col]||0),bv=parseFloat(b.dataset['c'+col]||0);
    return asc?av-bv:bv-av;
  });
  rows.forEach(function(r){tbody.appendChild(r);});
}
document.addEventListener('click',function(e){
  var th=e.target.closest('.sh');
  if(!th)return;
  sortTable(th.dataset.t,parseInt(th.dataset.c),false);
});

document.getElementById('breakdown').innerHTML=D.accounts.map(function(a,ai){
  var maxMtd=a.services[0]?a.services[0].mtd:1;
  var tbId='svc-tbody-'+ai;
  var rows=a.services.map(function(s,i){
    var bp=Math.min((s.mtd/maxMtd*100),100).toFixed(1);
    var delta_html=deltaHtml(s.delta,s.delta_pct,'sm');
    return '<tr data-c0="'+s.mtd+'" data-c1="'+s.w1+'" data-c2="'+s.w2+'" data-c3="'+s.w3+'" data-c4="'+s.delta+'">'+
      '<td><div class="svc-name">'+s.name+'</div>'+
           '<div class="svc-bar-wrap"><div class="svc-bar" style="width:'+bp+'%;background:'+a.color+'66"></div></div></td>'+
      '<td class="mono">$'+fmt(s.mtd)+'</td>'+
      '<td class="mono dim">$'+fmt(s.w1)+'</td>'+
      '<td class="mono dim">$'+fmt(s.w2)+'</td>'+
      '<td class="mono dim">$'+fmt(s.w3)+'</td>'+
      '<td>'+delta_html+'</td>'+
    '</tr>';
  }).join('');

  return '<div class="breakdown-card" style="border-color:'+a.color+'44">'+
    '<div class="breakdown-title" style="color:'+a.color+'">'+a.name+'</div>'+
    '<div class="breakdown-sub">'+a.id+' · '+a.service_count+' services · MTD $'+fmt(a.mtd)+'</div>'+
    '<div style="overflow-x:auto">'+
      '<table class="svc-table">'+
        '<thead><tr>'+
          '<th class="sh" data-t="'+tbId+'" data-c="0" style="text-align:left">Service ↕</th>'+
          '<th class="sh" data-t="'+tbId+'" data-c="0">MTD ↕</th>'+
          '<th class="sh" data-t="'+tbId+'" data-c="1">W1</th>'+
          '<th class="sh" data-t="'+tbId+'" data-c="2">W2</th>'+
          '<th class="sh" data-t="'+tbId+'" data-c="3">W3</th>'+
          '<th class="sh" data-t="'+tbId+'" data-c="4">W2→W3 Δ ↕</th>'+
        '</tr></thead>'+
        '<tbody id="'+tbId+'">'+rows+'</tbody>'+
      '</table>'+
    '</div>'+
  '</div>';
}).join('');

// ── Monthly charts ───────────────────────────────────────────────────────────
new Chart(document.getElementById('monthlyChart'),{
  type:'bar',
  data:{
    labels:D.months,
    datasets:D.accounts.map(function(a){return{
      label:a.name,
      data:a.monthly,
      backgroundColor:a.color,
      borderRadius:4,
    };})
  },
  options:{
    responsive:true,
    plugins:{legend:{labels:{color:'#a0aec0',font:{size:11}}}},
    scales:{
      x:{ticks:{color:'#718096'},grid:{color:'#1e2a3a'}},
      y:{ticks:{color:'#718096',callback:function(v){return '$'+fmtW(v);}},grid:{color:'#1e2a3a'}}
    }
  }
});

// Top 5 services per account (horizontal bar, grouped)
var allSvcs={};
D.accounts.forEach(function(a){
  a.services.slice(0,5).forEach(function(s){allSvcs[s.name]=true;});
});
var topLabels=Object.keys(allSvcs).slice(0,8);
new Chart(document.getElementById('topSvcChart'),{
  type:'bar',
  data:{
    labels:topLabels,
    datasets:D.accounts.map(function(a){return{
      label:a.name,
      data:topLabels.map(function(n){var s=a.services.find(function(x){return x.name===n;});return s?s.mtd:0;}),
      backgroundColor:a.color,
      borderRadius:3,
    };})
  },
  options:{
    indexAxis:'y',
    responsive:true,
    plugins:{legend:{labels:{color:'#a0aec0',font:{size:11}}}},
    scales:{
      x:{ticks:{color:'#718096',callback:function(v){return '$'+fmtW(v);}},grid:{color:'#1e2a3a'}},
      y:{ticks:{color:'#718096',font:{size:10}},grid:{display:false}}
    }
  }
});

</script>
</body>
</html>'''

html = HEAD + D_JSON + TAIL

with open(OUTPUT, 'w') as f:
    f.write(html)

REPORTS_DIR = os.path.join(os.path.dirname(OUTPUT), 'reports', TODAY.strftime('%Y-%m-%d'))
os.makedirs(REPORTS_DIR, exist_ok=True)
shutil.copy2(OUTPUT, os.path.join(REPORTS_DIR, 'dashboard.html'))

print(f"Dashboard written to {OUTPUT}")
for a in acct_results:
    print(f"  {a['name']}: MTD=${a['mtd']:,.2f}  W1=${a['w1t']:,.2f}  W2=${a['w2t']:,.2f}  W3={a['w3t']:,.2f}  W2→W3 Δ={'+'if a['w2w3_delta']>=0 else ''}{a['w2w3_delta']:,.2f} ({a['w2w3_pct']:+.1f}%)")
print(f"Combined MTD: ${D['combined']['mtd']:,.2f}  Projected: ${D['combined']['projected']:,.2f}")
