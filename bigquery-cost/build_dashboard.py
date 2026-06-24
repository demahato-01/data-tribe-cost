#!/usr/bin/env python3
import json, csv, re, calendar
from datetime import date

SERVICE_PORTAL = '/Users/demahato/work/git/data-tribe-cost/Service Portal info.csv'
OUTPUT = '/Users/demahato/work/git/data-tribe-cost/bigquery-cost/dashboard.html'
TODAY = date.today()
DAYS_IN_MONTH = calendar.monthrange(TODAY.year, TODAY.month)[1]

def load_json(path):
    raw = open(path).read()
    idx = raw.find('[')
    return json.loads(raw[idx:]) if idx >= 0 else []

with open(SERVICE_PORTAL) as f:
    svc_rows = list(csv.DictReader(f))
svc_lookup = {r['Service'].lower().strip(): r for r in svc_rows}

def clean(name):
    return re.sub(r'\s*\(Inactive\)|\s*\(Unconfirmed\)', '', name or '').strip()

def is_active(name):
    return bool(name) and '(Inactive)' not in name and '(Unconfirmed)' not in name

def effective_owner(row):
    so, tl, po = row.get('Service Owner',''), row.get('Tech Lead',''), row.get('Product Owner','')
    if is_active(so): return clean(so), 'SO'
    if is_active(tl): return clean(tl), 'TL'
    if is_active(po): return clean(po), 'PO'
    return '', ''

EXTRA_MAP = {'decision-science':'revmgmt-decision-science','gcp-data-catalog':'data-catalog'}

labels_data = load_json('/tmp/bq_project_labels.json')
owner_map = {}
for r in labels_data:
    pid, pname = r['project_id'], r['project_name']
    label = r['service_label'].lower().strip()
    key = label if label in svc_lookup else EXTRA_MAP.get(label)
    if key and key in svc_lookup:
        row = svc_lookup[key]
        owner, role = effective_owner(row)
        so_r, tl_r, po_r = row.get('Service Owner',''), row.get('Tech Lead',''), row.get('Product Owner','')
        info = {
            'service': row['Service'],
            'product_owner': clean(po_r) if is_active(po_r) else '',
            'service_owner': clean(so_r) if is_active(so_r) else '',
            'tech_lead': clean(tl_r) if is_active(tl_r) else '',
            'team_email': row['Team Email'],
            'owner': owner, 'role': role,
        }
    else:
        info = {'service':label,'product_owner':'','service_owner':'','tech_lead':'','team_email':'','owner':'','role':''}
    owner_map[pid] = info
    owner_map[pname] = info

cur_data      = load_json('/tmp/bq_current.json')
monthly_data  = load_json('/tmp/bq_monthly.json')
skus_per_proj = load_json('/tmp/bq_skus.json')
by_sku        = load_json('/tmp/bq_by_sku.json')
sku_mon_data  = load_json('/tmp/bq_sku_monthly.json')
weekly_data   = load_json('/tmp/bq_weekly.json')

months_all = sorted(set(r['month'] for r in monthly_data))
months = months_all[-4:] if len(months_all) >= 4 else months_all
MLABELS = [date(int(m[:4]), int(m[5:]), 1).strftime('%b') for m in months]

monthly_by_proj = {}
for r in monthly_data:
    monthly_by_proj.setdefault(r['project_id'], {})[r['month']] = float(r['monthly_cost'])

skus_by_proj = {}
for r in skus_per_proj:
    skus_by_proj.setdefault(r['project_id'], []).append({'sku': r['sku'], 'cost': float(r['sku_cost'])})

weekly_by_proj = {}
for r in weekly_data:
    if r['week_num'] is not None:
        weekly_by_proj.setdefault(r['project_id'], {})[str(r['week_num'])] = float(r['week_cost'])

projects = []
for r in cur_data:
    pid, pname = r['project_id'], r['project_name']
    current = float(r['current_month_cost'])
    info = owner_map.get(pname) or owner_map.get(pid) or {'service':'','product_owner':'','service_owner':'','tech_lead':'','team_email':'','owner':'','role':''}
    monthly = [monthly_by_proj.get(pid, {}).get(m, 0.0) for m in months]
    projected = round(current * DAYS_IN_MONTH / TODAY.day, 2)
    last_full = monthly[-2] if len(monthly) >= 2 else 0.0
    mom_pct = round((projected - last_full) / last_full * 100, 1) if last_full > 0 else None
    wk = weekly_by_proj.get(pid, {})
    w1, w2, w3 = wk.get('1', 0.0), wk.get('2', 0.0), wk.get('3', 0.0)
    wow_pct = round((w3 - w2) / w2 * 100, 1) if w2 > 0 else None
    projects.append({
        'id': pid, 'name': pname,
        'current': current, 'projected': projected,
        'monthly': monthly, 'mom_pct': mom_pct,
        'weekly': [w1, w2, w3], 'wow_pct': wow_pct,
        'app_service': info['service'], 'service_owner': info['service_owner'],
        'tech_lead': info['tech_lead'], 'product_owner': info['product_owner'],
        'team_email': info['team_email'], 'owner': info['owner'], 'role': info['role'],
        'skus': skus_by_proj.get(pid, [])[:10],
    })
projects.sort(key=lambda x: -x['current'])

mtd_total        = round(sum(p['current'] for p in projects), 2)
proj_total       = round(mtd_total * DAYS_IN_MONTH / TODAY.day, 2)
last_month_total = round(sum(p['monthly'][-2] if len(p['monthly'])>=2 else 0 for p in projects), 2)
prev_month_total = round(sum(p['monthly'][-3] if len(p['monthly'])>=3 else 0 for p in projects), 2)
mom_total        = round((proj_total - last_month_total) / last_month_total * 100, 1) if last_month_total > 0 else 0

skus_list = sorted([{'sku': r['sku'], 'total': float(r['total_cost']), 'projects': int(r['project_count'])} for r in by_sku], key=lambda x: -x['total'])

sku_mon_dict = {}
for r in sku_mon_data:
    sku_mon_dict.setdefault(r['sku'], {})[r['month']] = float(r['total_cost'])
sku_monthly_by_month = {sku: [md.get(m, 0.0) for m in months] for sku, md in sku_mon_dict.items()}

w1t = round(sum(p['weekly'][0] for p in projects), 2)
w2t = round(sum(p['weekly'][1] for p in projects), 2)
w3t = round(sum(p['weekly'][2] for p in projects), 2)
w1w2_pct = round((w2t - w1t) / w1t * 100, 1) if w1t > 0 else 0
w2w3_pct = round((w3t - w2t) / w2t * 100, 1) if w2t > 0 else 0

wow_by_owner = {}
for p in projects:
    o = p['owner'] or '(Unidentified)'
    if o not in wow_by_owner: wow_by_owner[o] = [0.0, 0.0, 0.0]
    for i in range(3): wow_by_owner[o][i] += p['weekly'][i]
wow_by_owner_top = dict(sorted(wow_by_owner.items(), key=lambda x: -sum(x[1]))[:10])

top_movers = []
for p in projects:
    w1, w2, w3 = p['weekly']
    if w2 > 10:
        wp = round((w3-w2)/w2*100, 1) if w2 > 0 else 0
        top_movers.append({'name':p['name'],'owner':p['owner'],'role':p['role'],'app_service':p['app_service'],'w1':w1,'w2':w2,'w3':w3,'wow_pct':wp,'_d':abs(w3-w2)})
top_movers.sort(key=lambda x: -x['_d'])
top_movers = [{k:v for k,v in m.items() if k!='_d'} for m in top_movers[:15]]

owner_sum = {}
for p in projects:
    o = p['owner'] or '(Unidentified)'
    if o not in owner_sum:
        owner_sum[o] = {'owner':o,'role':p['role'],'current':0.0,'monthly':[0.0]*len(months),'projects':0}
    owner_sum[o]['current'] += p['current']
    for i,v in enumerate(p['monthly']): owner_sum[o]['monthly'][i] += v
    owner_sum[o]['projects'] += 1
for o in owner_sum.values():
    lf = o['monthly'][-2] if len(o['monthly'])>=2 else 0
    pr = round(o['current']*DAYS_IN_MONTH/TODAY.day, 2)
    o['projected'] = pr
    o['mom_pct'] = round((pr-lf)/lf*100,1) if lf>0 else None
owner_summary = sorted(owner_sum.values(), key=lambda x: -x['current'])

distinct_owners = len(set(p['owner'] for p in projects if p['owner']))

D = {
    'mtdTotal': mtd_total, 'projectedTotal': proj_total,
    'lastMonthTotal': last_month_total, 'prevMonthTotal': prev_month_total,
    'momTotal': mom_total, 'months': MLABELS,
    'projectCount': len(projects), 'ownerCount': distinct_owners,
    'generatedDate': TODAY.strftime('%Y-%m-%d'),
    'currentMonthLabel': TODAY.strftime('%B %Y'),
    'dayOfMonth': TODAY.day, 'daysInMonth': DAYS_IN_MONTH,
    'lastMonthLabel': MLABELS[-2] if len(MLABELS)>=2 else '',
    'prevMonthLabel': MLABELS[-3] if len(MLABELS)>=3 else '',
    'prevPrevLabel':  MLABELS[-4] if len(MLABELS)>=4 else '',
    'projects': projects, 'skus': skus_list,
    'skuMonthly': sku_monthly_by_month,
    'wowByOwner': wow_by_owner_top, 'topMovers': top_movers,
    'w1Total': w1t, 'w2Total': w2t, 'w3Total': w3t,
    'w1w2Pct': w1w2_pct, 'w2w3Pct': w2w3_pct,
    'ownerSummary': owner_summary,
}

D_JSON = json.dumps(D, separators=(',',':'))

# ── HTML ──────────────────────────────────────────────────────────────────────
HEAD = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Groupon BigQuery Cost Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f1117;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px}
.container{max-width:1600px;margin:0 auto;padding:20px}
h1{font-size:24px;font-weight:700;color:#f7fafc}
h2{font-size:18px;font-weight:600;color:#e2e8f0;margin-bottom:14px}
h3{font-size:14px;font-weight:600;color:#a0aec0;margin-bottom:10px}
.header{background:#1a1f2e;border:1px solid #2d3748;border-radius:10px;padding:20px 24px;margin-bottom:20px}
.header-sub{color:#a0aec0;font-size:12px;margin-top:6px;line-height:1.6}
.kpi-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:20px}
.kpi{background:#1a1f2e;border:1px solid #2d3748;border-radius:10px;padding:18px}
.kpi-label{color:#718096;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.kpi-value{font-size:26px;font-weight:700;color:#f7fafc;font-family:monospace}
.kpi-sub{color:#718096;font-size:11px;margin-top:4px}
.trend-up{color:#fc8181}.trend-down{color:#68d391}
.section{background:#1a1f2e;border:1px solid #2d3748;border-radius:10px;padding:20px;margin-bottom:20px}
.g3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.cbox{background:#151b2a;border:1px solid #2d3748;border-radius:8px;padding:16px}
.cbox canvas{max-height:250px}
.wow-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:20px}
.wow-kpi{background:#151b2a;border:1px solid #2d3748;border-radius:8px;padding:16px}
.wk-label{color:#718096;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px}
.wk-range{color:#4a5568;font-size:10px;margin-bottom:4px}
.wk-val{font-size:22px;font-weight:700;color:#f7fafc;font-family:monospace}
.wk-chg{font-size:13px;font-weight:700;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:#151b2a;color:#718096;font-weight:600;text-transform:uppercase;font-size:10px;letter-spacing:.5px;padding:10px 12px;text-align:left;border-bottom:1px solid #2d3748;position:sticky;top:0;z-index:1}
td{padding:10px 12px;border-bottom:1px solid #1e2535;vertical-align:middle}
tr:hover td{background:#1e2535}
.cost{font-family:monospace;color:#e2e8f0}.cost.dim{color:#4a5568}
.pname{font-size:12px;color:#e2e8f0;font-family:monospace}
.cbar{height:3px;background:#4299e1;border-radius:2px;margin-top:4px}
.obadge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;margin-right:4px}
.rbadge{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:700}
.xbtn{background:none;border:1px solid #2d3748;color:#718096;padding:3px 8px;border-radius:4px;cursor:pointer;font-size:11px}
.xbtn:hover{border-color:#4299e1;color:#4299e1}
.svcrow{display:none;background:#0f1117}
.svcrow td{padding:6px 12px;color:#718096;font-size:11px}
.svc-inner{padding:8px 16px}
.search{width:100%;padding:10px 14px;background:#151b2a;border:1px solid #2d3748;border-radius:8px;color:#e2e8f0;font-size:13px;margin-bottom:14px;outline:none}
.search:focus{border-color:#4299e1}
.trend{font-weight:700}.trend.up{color:#fc8181}.trend.down{color:#68d391}
.slabel{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:#4299e1;background:#4299e122;padding:2px 8px;border-radius:4px;margin-left:10px;vertical-align:middle}

</style>
</head>
<body>
<div class="container">

<div class="header">
  <h1>Groupon BigQuery Cost Dashboard</h1>
  <div class="header-sub" id="header-sub"></div>
</div>

<div class="kpi-grid">
  <div class="kpi"><div class="kpi-label">MTD BigQuery Spend</div><div class="kpi-value">$<span id="kpi-mtd"></span></div><div class="kpi-sub">Projected full month: $<span id="kpi-proj"></span></div></div>
  <div class="kpi"><div class="kpi-label" id="kpi-last-lbl">Last Full Month</div><div class="kpi-value">$<span id="kpi-last"></span></div><div class="kpi-sub"><span id="kpi-prev-lbl"></span>: $<span id="kpi-prev"></span></div></div>
  <div class="kpi"><div class="kpi-label">MoM Trend (Proj vs <span id="kpi-mom-lbl"></span>)</div><div class="kpi-value" id="kpi-mom"></div><div class="kpi-sub">Projected vs last full month</div></div>
  <div class="kpi"><div class="kpi-label">Projects with BQ Cost</div><div class="kpi-value" id="kpi-pc"></div><div class="kpi-sub">across all Groupon GCP projects</div></div>
  <div class="kpi"><div class="kpi-label">Identified Service Owners</div><div class="kpi-value" id="kpi-ow"></div><div class="kpi-sub">via Service Portal lookup</div></div>
</div>

<div class="section">
  <h2>Week-over-Week <span class="slabel" id="wow-lbl"></span></h2>
  <div class="wow-grid">
    <div class="wow-kpi"><div class="wk-label">Week 1</div><div class="wk-range" id="wr1"></div><div class="wk-val">$<span id="w1"></span></div><div class="wk-chg" style="color:#718096">baseline</div></div>
    <div class="wow-kpi"><div class="wk-label">Week 2</div><div class="wk-range" id="wr2"></div><div class="wk-val">$<span id="w2"></span></div><div class="wk-chg" id="w1w2"></div></div>
    <div class="wow-kpi"><div class="wk-label">Week 3</div><div class="wk-range" id="wr3"></div><div class="wk-val">$<span id="w3"></span></div><div class="wk-chg" id="w2w3"></div></div>
  </div>
  <div class="g2">
    <div class="cbox"><h3>Weekly BigQuery Spend by Owner (Top 10)</h3><canvas id="wowChart" style="max-height:300px"></canvas></div>
    <div style="overflow-x:auto">
      <h3 style="margin-bottom:10px">Top Movers &mdash; Week 3 vs Week 2</h3>
      <table><thead><tr><th>Project</th><th>Owner</th><th>W1</th><th>W2</th><th>W3</th><th>W2&rarr;W3</th></tr></thead>
      <tbody id="movers"></tbody></table>
    </div>
  </div>
</div>

<div class="section">
  <h2>BigQuery SKU Breakdown</h2>
  <div class="g3">
    <div class="cbox"><h3>Share of Spend (Top 8 SKUs)</h3><canvas id="skuDonut"></canvas></div>
    <div class="cbox"><h3>Top BigQuery SKUs MTD</h3><canvas id="skuHbar"></canvas></div>
    <div class="cbox"><h3>Monthly Trend (Top 5 SKUs)</h3><canvas id="skuLine"></canvas></div>
  </div>
  <table><thead><tr><th>BigQuery SKU</th><th>MTD</th><th id="sm2"></th><th id="sm1"></th><th id="sm0"></th><th>% Total</th><th>Projects</th></tr></thead><tbody id="skutbl"></tbody></table>
</div>

<div class="section">
  <h2>Cost by Service Owner <span class="slabel">BigQuery spend only</span></h2>
  <div class="g2">
    <div class="cbox"><h3>Top Owners by BigQuery MTD Spend</h3><canvas id="ownerHbar" style="max-height:320px"></canvas></div>
    <div style="overflow-x:auto">
      <table><thead><tr><th>Service Owner</th><th>MTD</th><th id="om2"></th><th id="om1"></th><th id="om0"></th><th>% Total</th><th>MoM Trend</th><th>Projects</th></tr></thead>
      <tbody id="ownertbl"></tbody></table>
    </div>
  </div>
</div>

<div class="section">
  <h2>Projects <span class="slabel">BigQuery spend only &mdash; all Groupon GCP projects</span></h2>
  <input class="search" id="psearch" placeholder="Filter projects by name..." oninput="filterProjects()">
  <div style="overflow-x:auto">
    <table><thead><tr><th>#</th><th>Project</th><th>MTD</th><th id="pm2"></th><th id="pm1"></th><th id="pm0"></th><th>Trend vs <span id="ptl"></span></th><th>Service Name</th><th>Service Owner</th><th>Team Email</th><th>BQ SKUs</th></tr></thead>
    <tbody id="projtbl"></tbody></table>
  </div>
</div>


</div>
<script>
const D = '''

TAIL = ''';

const PALETTE=[
  "#4299e1","#48bb78","#ed8936","#9f7aea","#fc8181",
  "#38b2ac","#f687b3","#d69e2e","#667eea","#e53e3e",
  "#dd6b20","#319795","#805ad5","#d53f8c","#2b6cb0"
];
const SKU_PAL=[
  "#4299e1","#48bb78","#ed8936","#9f7aea","#fc8181",
  "#38b2ac","#f687b3","#d69e2e","#667eea","#e53e3e",
  "#dd6b20","#319795","#805ad5"
];

const OWNER_COLORS={};
(function(){
  var idx=0;
  Object.keys(D.wowByOwner).forEach(function(o){if(!OWNER_COLORS[o])OWNER_COLORS[o]=PALETTE[idx++%PALETTE.length];});
  D.ownerSummary.forEach(function(o){if(o.owner&&!OWNER_COLORS[o.owner])OWNER_COLORS[o.owner]=PALETTE[idx++%PALETTE.length];});
  D.projects.forEach(function(p){if(p.owner&&!OWNER_COLORS[p.owner])OWNER_COLORS[p.owner]=PALETTE[idx++%PALETTE.length];});
})();
const ROLE_COLORS={"SO":"#48bb78","TL":"#ecc94b","PO":"#4299e1"};
const SKU_COLORS={};
D.skus.forEach(function(s,i){SKU_COLORS[s.sku]=SKU_PAL[i%SKU_PAL.length];});

function fmt(v){return(v||0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});}
function fmtW(v){return(v||0).toLocaleString('en-US',{minimumFractionDigits:0,maximumFractionDigits:0});}

function wowHtml(pct,delta){
  if(pct===null||pct===undefined)return '<span style="color:#718096">—</span>';
  var up=pct>0,c=up?'#fc8181':'#68d391',a=up?'▲':'▼',s=delta>=0?'+':'-';
  return '<span style="color:'+c+';font-weight:700">'+a+' '+Math.abs(pct)+'%</span> <span style="color:#4a5568;font-size:11px">'+s+'$'+fmtW(Math.abs(delta))+'</span>';
}

function toggleSku(btn,pid){
  var row=document.getElementById('sku-'+pid);
  if(!row)return;
  if(row.style.display==='table-row'){row.style.display='none';btn.textContent=btn.textContent.replace('▼','▶');}
  else{row.style.display='table-row';btn.textContent=btn.textContent.replace('▶','▼');}
}

function filterProjects(){
  var q=document.getElementById('psearch').value.toLowerCase();
  document.querySelectorAll('tr.prow').forEach(function(tr){
    var show=!q||(tr.dataset.name||'').includes(q);
    tr.style.display=show?'':'none';
    var sr=document.getElementById('sku-'+tr.dataset.id);
    if(sr&&!show)sr.style.display='none';
  });
}

// Header
var mo=D.currentMonthLabel;
document.getElementById('header-sub').innerHTML=
  '<strong>Scope:</strong> All Groupon GCP projects &middot; <strong>Service:</strong> BigQuery only &middot; '+
  '<strong>Projects:</strong> '+D.projectCount+' with BigQuery costs &middot; '+
  '<strong>Identified owners:</strong> '+D.ownerCount+' &middot; '+
  '<strong>Generated:</strong> '+D.generatedDate+' (Day '+D.dayOfMonth+' of '+D.daysInMonth+') &middot; '+
  '<strong>MTD = '+mo+' 1–'+D.dayOfMonth+'</strong>';

// KPIs
document.getElementById('kpi-mtd').textContent=fmt(D.mtdTotal);
document.getElementById('kpi-proj').textContent=fmt(D.projectedTotal);
document.getElementById('kpi-last-lbl').textContent='Last Full Month ('+D.lastMonthLabel+')';
document.getElementById('kpi-last').textContent=fmt(D.lastMonthTotal);
document.getElementById('kpi-prev-lbl').textContent=D.prevMonthLabel;
document.getElementById('kpi-prev').textContent=fmt(D.prevMonthTotal);
document.getElementById('kpi-mom-lbl').textContent=D.lastMonthLabel;
var mu=D.momTotal>0;
document.getElementById('kpi-mom').innerHTML='<span class="'+(mu?'trend-up':'trend-down')+'">'+(mu?'▲':'▼')+' '+Math.abs(D.momTotal)+'%</span>';
document.getElementById('kpi-pc').textContent=D.projectCount;
document.getElementById('kpi-ow').textContent=D.ownerCount;

// WoW labels
var mon=D.currentMonthLabel.split(' ')[0].slice(0,3);
document.getElementById('wow-lbl').textContent=D.currentMonthLabel+' — Last 3 Complete Weeks';
document.getElementById('wr1').textContent=mon+' 1–7';
document.getElementById('wr2').textContent=mon+' 8–14';
document.getElementById('wr3').textContent=mon+' 15–21';
document.getElementById('w1').textContent=fmt(D.w1Total);
document.getElementById('w2').textContent=fmt(D.w2Total);
document.getElementById('w3').textContent=fmt(D.w3Total);
document.getElementById('w1w2').innerHTML=wowHtml(D.w1w2Pct,D.w2Total-D.w1Total);
document.getElementById('w2w3').innerHTML=wowHtml(D.w2w3Pct,D.w3Total-D.w2Total);

// WoW chart
var oNames=Object.keys(D.wowByOwner);
new Chart(document.getElementById('wowChart'),{
  type:'bar',
  data:{
    labels:oNames,
    datasets:[
      {label:'Week 1',data:oNames.map(function(o){return D.wowByOwner[o][0];}),backgroundColor:oNames.map(function(o){return(OWNER_COLORS[o]||'#4299e1')+'66';})},
      {label:'Week 2',data:oNames.map(function(o){return D.wowByOwner[o][1];}),backgroundColor:oNames.map(function(o){return(OWNER_COLORS[o]||'#4299e1')+'aa';})},
      {label:'Week 3',data:oNames.map(function(o){return D.wowByOwner[o][2];}),backgroundColor:oNames.map(function(o){return OWNER_COLORS[o]||'#4299e1';})},
    ]
  },
  options:{
    responsive:true,
    plugins:{legend:{labels:{color:'#a0aec0',font:{size:11}}}},
    scales:{
      x:{ticks:{color:'#718096',font:{size:10}},grid:{color:'#1e2535'}},
      y:{ticks:{color:'#718096',callback:function(v){return '$'+fmtW(v);}},grid:{color:'#1e2535'}}
    }
  }
});

// Top movers
document.getElementById('movers').innerHTML=D.topMovers.map(function(m){
  var oc=OWNER_COLORS[m.owner]||'#718096',rc=ROLE_COLORS[m.role]||'#718096';
  var ob=m.owner?'<span class="obadge" style="background:'+oc+'22;color:'+oc+'">'+m.owner+'</span><span class="rbadge" style="background:'+rc+'33;color:'+rc+'">'+m.role+'</span>':'<span style="color:#4a5568">—</span>';
  return '<tr><td class="pname">'+m.name+'</td><td>'+ob+'</td><td class="cost">$'+fmt(m.w1)+'</td><td class="cost">$'+fmt(m.w2)+'</td><td class="cost">$'+fmt(m.w3)+'</td><td>'+wowHtml(m.wow_pct,m.w3-m.w2)+'</td></tr>';
}).join('');

// Table month headers
var m2=D.months[D.months.length-2]||'',m1=D.months[D.months.length-3]||'',m0=D.months[D.months.length-4]||'';
['sm2','om2','pm2'].forEach(function(id){document.getElementById(id).textContent=m2;});
['sm1','om1','pm1'].forEach(function(id){document.getElementById(id).textContent=m1;});
['sm0','om0','pm0'].forEach(function(id){document.getElementById(id).textContent=m0;});
document.getElementById('ptl').textContent=m2;

// SKU Donut
var top8=D.skus.slice(0,8);
new Chart(document.getElementById('skuDonut'),{
  type:'doughnut',
  data:{labels:top8.map(function(s){return s.sku;}),datasets:[{data:top8.map(function(s){return s.total;}),backgroundColor:SKU_PAL.slice(0,8)}]},
  options:{plugins:{legend:{position:'bottom',labels:{color:'#a0aec0',font:{size:10},boxWidth:12}}}}
});

// SKU Hbar
new Chart(document.getElementById('skuHbar'),{
  type:'bar',
  data:{labels:top8.map(function(s){return s.sku;}),datasets:[{label:'MTD Cost',data:top8.map(function(s){return s.total;}),backgroundColor:SKU_PAL.slice(0,8)}]},
  options:{
    indexAxis:'y',
    plugins:{legend:{display:false}},
    scales:{
      x:{ticks:{color:'#718096',callback:function(v){return '$'+fmtW(v);}},grid:{color:'#1e2535'}},
      y:{ticks:{color:'#718096',font:{size:10}},grid:{display:false}}
    }
  }
});

// SKU Line
var top5s=D.skus.slice(0,5).map(function(s){return s.sku;});
new Chart(document.getElementById('skuLine'),{
  type:'line',
  data:{
    labels:D.months,
    datasets:top5s.map(function(sku,i){return{label:sku,data:D.skuMonthly[sku]||[],borderColor:SKU_PAL[i],backgroundColor:'transparent',tension:0.3,pointRadius:4};})
  },
  options:{
    plugins:{legend:{labels:{color:'#a0aec0',font:{size:10},boxWidth:12}}},
    scales:{
      x:{ticks:{color:'#718096'},grid:{color:'#1e2535'}},
      y:{ticks:{color:'#718096',callback:function(v){return '$'+fmtW(v);}},grid:{color:'#1e2535'}}
    }
  }
});

// SKU table
var skuTot=D.skus.reduce(function(s,r){return s+r.total;},0);
document.getElementById('skutbl').innerHTML=D.skus.map(function(s,i){
  var mon=D.skuMonthly[s.sku]||[],pct=skuTot>0?(s.total/skuTot*100).toFixed(1):'0.0';
  var dot='<span style="display:inline-block;width:10px;height:10px;background:'+SKU_PAL[i%SKU_PAL.length]+';border-radius:2px;margin-right:6px"></span>';
  return '<tr><td>'+dot+s.sku+'</td><td class="cost">$'+fmt(s.total)+'</td>'+
    '<td class="cost dim">'+(mon[2]!==undefined?'$'+fmt(mon[2]):'&mdash;')+'</td>'+
    '<td class="cost dim">'+(mon[1]!==undefined?'$'+fmt(mon[1]):'&mdash;')+'</td>'+
    '<td class="cost dim">'+(mon[0]!==undefined?'$'+fmt(mon[0]):'&mdash;')+'</td>'+
    '<td style="color:#a0aec0">'+pct+'%</td><td style="color:#718096">'+s.projects+'</td></tr>';
}).join('');

// Owner Hbar
var top15o=D.ownerSummary.slice(0,15);
new Chart(document.getElementById('ownerHbar'),{
  type:'bar',
  data:{
    labels:top15o.map(function(o){return o.owner||'(Unidentified)';}),
    datasets:[{label:'MTD BigQuery Cost',data:top15o.map(function(o){return o.current;}),backgroundColor:top15o.map(function(o){return OWNER_COLORS[o.owner]||'#4299e1';})}]
  },
  options:{
    indexAxis:'y',
    plugins:{legend:{display:false}},
    scales:{
      x:{ticks:{color:'#718096',callback:function(v){return '$'+fmtW(v);}},grid:{color:'#1e2535'}},
      y:{ticks:{color:'#718096',font:{size:10}},grid:{display:false}}
    }
  }
});

// Owner table
var owTot=D.ownerSummary.reduce(function(s,o){return s+o.current;},0);
document.getElementById('ownertbl').innerHTML=D.ownerSummary.map(function(o,i){
  var oc=OWNER_COLORS[o.owner]||PALETTE[i%PALETTE.length],rc=ROLE_COLORS[o.role]||'#718096';
  var ob=o.owner&&o.owner!=='(Unidentified)'
    ?'<span class="obadge" style="background:'+oc+'22;color:'+oc+'">'+o.owner+'</span><span class="rbadge" style="background:'+rc+'33;color:'+rc+'">'+o.role+'</span>'
    :'<span style="color:#4a5568">'+(o.owner||'—')+'</span>';
  var pct=owTot>0?(o.current/owTot*100).toFixed(1):'0.0';
  var tr=o.mom_pct===null?'<span style="color:#4a5568">—</span>':'<span class="trend '+(o.mom_pct>0?'up':'down')+'">'+(o.mom_pct>0?'▲':'▼')+' '+Math.abs(o.mom_pct)+'%</span>';
  return '<tr><td>'+ob+'</td><td class="cost">$'+fmt(o.current)+'</td>'+
    '<td class="cost dim">$'+fmt(o.monthly[2]||0)+'</td>'+
    '<td class="cost dim">$'+fmt(o.monthly[1]||0)+'</td>'+
    '<td class="cost dim">$'+fmt(o.monthly[0]||0)+'</td>'+
    '<td style="color:#a0aec0">'+pct+'%</td><td>'+tr+'</td><td style="color:#718096">'+o.projects+'</td></tr>';
}).join('');

// Project table
var maxC=D.projects[0]?D.projects[0].current:1;
document.getElementById('projtbl').innerHTML=D.projects.map(function(p,i){
  var bp=(p.current/maxC*100).toFixed(1);
  var oc=OWNER_COLORS[p.owner]||'#718096',rc=ROLE_COLORS[p.role]||'#718096';
  var tr=p.mom_pct===null?'<span style="color:#4a5568">—</span>':'<span class="trend '+(p.mom_pct>0?'up':'down')+'">'+(p.mom_pct>0?'▲':'▼')+' '+Math.abs(p.mom_pct)+'%</span>';
  var oh=p.owner?'<div><span class="obadge" style="background:'+oc+'22;color:'+oc+'">'+p.owner+'</span><span class="rbadge" style="background:'+rc+'33;color:'+rc+'">'+p.role+'</span></div>':'<span style="color:#4a5568">—</span>';
  var sh=p.app_service?'<span style="font-family:monospace;font-size:11px;color:#a0aec0">'+p.app_service+'</span>':'<span style="color:#4a5568">—</span>';
  var eh=p.team_email?'<a href="mailto:'+p.team_email+'" style="color:#4299e1;text-decoration:none;font-size:11px">'+p.team_email+'</a>':'<span style="color:#4a5568">—</span>';
  var hasSku=p.skus&&p.skus.length>0;
  var sb=hasSku?'<button class="xbtn" onclick="toggleSku(this,\\''+p.id+'\\')">▶ '+p.skus.length+' SKUs</button>':'<span class="cost dim">—</span>';
  var main='<tr class="prow" data-name="'+p.name.toLowerCase()+'" data-id="'+p.id+'">'+
    '<td style="color:#4a5568">'+(i+1)+'</td>'+
    '<td><div class="pname">'+p.name+'</div><div class="cbar" style="width:'+bp+'%"></div></td>'+
    '<td class="cost">$'+fmt(p.current)+'</td>'+
    '<td class="cost dim">$'+fmt(p.monthly[2]||0)+'</td>'+
    '<td class="cost dim">$'+fmt(p.monthly[1]||0)+'</td>'+
    '<td class="cost dim">$'+fmt(p.monthly[0]||0)+'</td>'+
    '<td>'+tr+'</td><td>'+sh+'</td><td>'+oh+'</td><td>'+eh+'</td><td>'+sb+'</td></tr>';
  var detail=hasSku?'<tr id="sku-'+p.id+'" class="svcrow"><td colspan="11"><div class="svc-inner"><table>'+
    '<tr><th>BigQuery SKU</th><th>Cost (MTD)</th></tr>'+
    p.skus.map(function(s){return '<tr><td style="color:#a0aec0">'+s.sku+'</td><td class="cost">$'+fmt(s.cost)+'</td></tr>';}).join('')+
    '</table></div></td></tr>':'';
  return main+detail;
}).join('');


</script>
</body>
</html>'''

import os, shutil

html = HEAD + D_JSON + TAIL

# Write root dashboard (always latest)
with open(OUTPUT, 'w') as f:
    f.write(html)

# Write dated snapshot to reports/YYYY-MM-DD/dashboard.html
REPORTS_DIR = os.path.join(os.path.dirname(OUTPUT), 'reports', TODAY.strftime('%Y-%m-%d'))
os.makedirs(REPORTS_DIR, exist_ok=True)
REPORT_PATH = os.path.join(REPORTS_DIR, 'dashboard.html')
shutil.copy2(OUTPUT, REPORT_PATH)

print('Dashboard written to', OUTPUT)
print('Report snapshot:', REPORT_PATH)
print('Projects:', len(D['projects']))
print('MTD Total: ${:,.2f}'.format(D['mtdTotal']))
print('Projected: ${:,.2f}'.format(D['projectedTotal']))
print('Distinct owners:', D['ownerCount'])
print('SKUs:', len(D['skus']))
