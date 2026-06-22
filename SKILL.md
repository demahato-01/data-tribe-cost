---
name: dnd-cost
description: >
  Generate or refresh the DnD GCP Cost Dashboard for all projects under GCP folder 499446588003.
  Queries BigQuery billing data, builds a self-contained HTML dashboard, and opens it in the browser.
  Use this skill whenever the user says "refresh the cost dashboard", "update dnd-cost",
  "show GCP costs", "regenerate the cost dashboard", "run dnd-cost", or any variation of
  viewing or refreshing GCP spend for the DnD infrastructure folder.
---

# DnD GCP Cost Dashboard

Generates a self-contained HTML cost dashboard at:
`/Users/demahato/CoS/projects/work/dnd-cost/dashboard.html`

**Billing source:**
`prj-grpn-seed-terraform-66e7.grpn_cloudability_billing.gcp_billing_export_resource_v1_01F2E1_BA7EDD_9C9EB7`

**GCP Folder:** `499446588003`

**Service Portal:** `/Users/demahato/CoS/projects/work/dnd-cost/Service Portal info.csv`
Columns: Service, Product Owner, Service Owner, Tech Lead, Team Email

---

## Concept: Two Types of "Service"

These are different and must NOT be conflated in the dashboard:

| Type | Source | Examples | Used for |
|---|---|---|---|
| **GCP Service** | `service.description` in billing export | Compute Engine, Cloud Storage, BigQuery | Infrastructure cost breakdown |
| **App Service** | `service` label on GCP project → matched to Service Portal CSV | janus, gcp-hadoop-infra, bigquery | Ownership — who is responsible for the project |

Always label GCP infrastructure as "GCP Service" and portal-matched services as "Service Name" or "App Service".

---

## Owner Filter

The dashboard is scoped to projects owned by these 5 team members only:

| Name | Color |
|---|---|
| Aaditya Raj | `#9f7aea` |
| Pratyush Raizada | `#4299e1` |
| Ravikumar Padala | `#48bb78` |
| Audrius Sadauskas | `#ed8936` |
| Ahmad Abdul Wakeel | `#fc8181` |
| Josef Pokorny | `#38b2ac` |
| Saurabh Santhosh | `#f687b3` |
| Deepak Mahato | `#d69e2e` |

**Effective owner priority:** Service Owner → Tech Lead → Product Owner. Entries marked `(Inactive)` or `(Unconfirmed)` are **skipped entirely** — the next active person in the chain is used instead. Also store only active values for `service_owner`, `tech_lead`, `product_owner` fields on the info dict (set to `''` if inactive).

**Note:** Audrius Sadauskas, Ahmad Abdul Wakeel, and Saurabh Santhosh currently have no projects under folder 499446588003 (Saurabh appears as TL in services where Josef Pokorny is SO). The dashboard footer must state this.

---

## Step 1 — Query BigQuery (run all queries in parallel)

Use:
```
bq query --use_legacy_sql=false --project_id=prj-grpn-seed-terraform-66e7 --format=json --max_rows=5000 2>/dev/null
```

Save each to a temp file. Strip the bq status prefix before parsing: find the first `[` in the file.

### Query A — Current month cost by project
```sql
SELECT
  project.id AS project_id,
  project.name AS project_name,
  ROUND(SUM(cost), 2) AS current_month_cost,
  currency
FROM `prj-grpn-seed-terraform-66e7.grpn_cloudability_billing.gcp_billing_export_resource_v1_01F2E1_BA7EDD_9C9EB7`
WHERE
  project.ancestry_numbers LIKE "%499446588003%"
  AND DATE(usage_start_time) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
GROUP BY project_id, project_name, currency
ORDER BY current_month_cost DESC
```
Save to `/tmp/dnd_current.json`

### Query B — Monthly totals (last 4 months) by project
```sql
SELECT
  project.id AS project_id,
  project.name AS project_name,
  FORMAT_DATE("%Y-%m", DATE(usage_start_time)) AS month,
  ROUND(SUM(cost), 2) AS monthly_cost
FROM `prj-grpn-seed-terraform-66e7.grpn_cloudability_billing.gcp_billing_export_resource_v1_01F2E1_BA7EDD_9C9EB7`
WHERE
  project.ancestry_numbers LIKE "%499446588003%"
  AND DATE(usage_start_time) >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 3 MONTH)
GROUP BY project_id, project_name, month
ORDER BY project_id, month
```
Save to `/tmp/dnd_monthly.json`

### Query C — GCP service breakdown per project (current month, cost ≥ $0.50)
```sql
SELECT
  project.id AS project_id,
  project.name AS project_name,
  service.description AS service,
  ROUND(SUM(cost), 2) AS service_cost
FROM `prj-grpn-seed-terraform-66e7.grpn_cloudability_billing.gcp_billing_export_resource_v1_01F2E1_BA7EDD_9C9EB7`
WHERE
  project.ancestry_numbers LIKE "%499446588003%"
  AND DATE(usage_start_time) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
  AND cost > 0
GROUP BY project_id, project_name, service
HAVING service_cost >= 0.5
ORDER BY project_id, service_cost DESC
```
Save to `/tmp/dnd_services.json`

### Query D — Total cost by GCP service across all projects (current month)
```sql
SELECT
  service.description AS service,
  ROUND(SUM(cost), 2) AS total_cost,
  COUNT(DISTINCT project.id) AS project_count
FROM `prj-grpn-seed-terraform-66e7.grpn_cloudability_billing.gcp_billing_export_resource_v1_01F2E1_BA7EDD_9C9EB7`
WHERE
  project.ancestry_numbers LIKE "%499446588003%"
  AND DATE(usage_start_time) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
  AND cost > 0
GROUP BY service
HAVING total_cost >= 0.5
ORDER BY total_cost DESC
```
Save to `/tmp/dnd_by_service.json`

### Query E — Monthly totals by GCP service (last 4 months)
```sql
SELECT
  service.description AS service,
  FORMAT_DATE("%Y-%m", DATE(usage_start_time)) AS month,
  ROUND(SUM(cost), 2) AS total_cost
FROM `prj-grpn-seed-terraform-66e7.grpn_cloudability_billing.gcp_billing_export_resource_v1_01F2E1_BA7EDD_9C9EB7`
WHERE
  project.ancestry_numbers LIKE "%499446588003%"
  AND DATE(usage_start_time) >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 3 MONTH)
  AND cost > 0
GROUP BY service, month
HAVING total_cost >= 1
ORDER BY service, month
```
Save to `/tmp/dnd_service_monthly.json`

### Query F — Project service labels (App Service per project)
```sql
SELECT DISTINCT
  project.id AS project_id,
  project.name AS project_name,
  label.value AS service_label
FROM `prj-grpn-seed-terraform-66e7.grpn_cloudability_billing.gcp_billing_export_resource_v1_01F2E1_BA7EDD_9C9EB7`,
UNNEST(project.labels) AS label
WHERE
  project.ancestry_numbers LIKE "%499446588003%"
  AND DATE(usage_start_time) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
  AND label.key = "service"
ORDER BY project_id
```
Save to `/tmp/dnd_project_labels.json`

### Query G — Weekly cost by project (current month, last 3 complete weeks)
```sql
SELECT
  project.id AS project_id,
  project.name AS project_name,
  CASE
    WHEN EXTRACT(DAY FROM DATE(usage_start_time)) BETWEEN 1 AND 7  THEN 1
    WHEN EXTRACT(DAY FROM DATE(usage_start_time)) BETWEEN 8 AND 14 THEN 2
    WHEN EXTRACT(DAY FROM DATE(usage_start_time)) BETWEEN 15 AND 21 THEN 3
  END AS week_num,
  ROUND(SUM(cost), 2) AS week_cost
FROM `prj-grpn-seed-terraform-66e7.grpn_cloudability_billing.gcp_billing_export_resource_v1_01F2E1_BA7EDD_9C9EB7`
WHERE
  project.ancestry_numbers LIKE "%499446588003%"
  AND DATE(usage_start_time) BETWEEN DATE_TRUNC(CURRENT_DATE(), MONTH)
    AND DATE_SUB(DATE_ADD(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 21 DAY), INTERVAL 1 DAY)
  AND cost > 0
GROUP BY project_id, project_name, week_num
HAVING week_cost > 0
ORDER BY project_id, week_num
```
Save to `/tmp/dnd_weekly.json`

Week definitions (always fixed calendar slices within the current month):
- **Week 1** = day 1–7
- **Week 2** = day 8–14
- **Week 3** = day 15–21

---

## Step 2 — Build the OWNER_MAP and filter to team projects

Use Python to join project service labels with `Service Portal info.csv`, compute the effective owner, and keep only projects owned by the 5 target team members:

```python
import csv, json, re

TARGET_OWNERS = {
    'Aaditya Raj', 'Pratyush Raizada', 'Ravikumar Padala',
    'Audrius Sadauskas', 'Ahmad Abdul Wakeel',
    'Josef Pokorny', 'Saurabh Santhosh',
    'Deepak Mahato',
}

with open('/Users/demahato/CoS/projects/work/dnd-cost/Service Portal info.csv') as f:
    svc_rows = list(csv.DictReader(f))
svc_lookup = {r['Service'].lower().strip(): r for r in svc_rows}

def clean(name):
    return re.sub(r'\s*\(Inactive\)|\s*\(Unconfirmed\)', '', name or '').strip()

def is_active(name):
    """Returns True only if the name is non-empty AND not marked Inactive/Unconfirmed."""
    return bool(name) and '(Inactive)' not in name and '(Unconfirmed)' not in name

def effective_owner(row):
    """Returns (owner_name, role) using SO → TL → PO priority.
    Inactive/Unconfirmed entries are skipped entirely — falls through to next active person."""
    so = row.get('Service Owner', '')
    tl = row.get('Tech Lead', '')
    po = row.get('Product Owner', '')
    if is_active(so): return clean(so), 'SO'
    if is_active(tl): return clean(tl), 'TL'
    if is_active(po): return clean(po), 'PO'
    return '', ''

# Additional manual resolutions for labels that differ slightly from portal names
EXTRA_MAP = {
    'decision-science': 'revmgmt-decision-science',
    'gcp-data-catalog':  'data-catalog',
}

labels = json.load(open('/tmp/dnd_project_labels.json'))

owner_map = {}
team_project_ids = set()

for r in labels:
    pid   = r['project_id']
    pname = r['project_name']
    label = r['service_label'].lower().strip()
    key   = label if label in svc_lookup else EXTRA_MAP.get(label)
    if key and key in svc_lookup:
        row = svc_lookup[key]
        owner, role = effective_owner(row)
        info = {
            'service':        row['Service'],
            'product_owner':  clean(row['Product Owner']),
            'service_owner':  clean(row['Service Owner']),
            'tech_lead':      clean(row['Tech Lead']),
            'team_email':     row['Team Email'],
            'owner':          owner,
            'role':           role,
        }
    else:
        info = {'service': label, 'product_owner': '', 'service_owner': '',
                'tech_lead': '', 'team_email': '', 'owner': '', 'role': ''}
    owner_map[pid]   = info   # keyed by project_id  (e.g. prj-grp-datalake-prod-8a19)
    owner_map[pname] = info   # keyed by project_name (e.g. prj-grp-datalake-prod)
    if info['owner'] in TARGET_OWNERS:
        team_project_ids.add(pid)
```

Key both `project_id` and `project_name` — the JS uses both as fallback: `OWNER_MAP[p.name] || OWNER_MAP[p.id]`.

After building `team_project_ids`, filter all parsed data (current, monthly, services) to only include those project IDs before building the project list.

---

## Step 3 — Parse remaining data

Use Python to:
1. Parse all JSON files (strip bq status prefix — find first `[`)
2. Build project list filtered to `team_project_ids`, sorted by current month cost
3. For each project, embed `app_service`, `service_owner`, `tech_lead`, `product_owner`, `team_email`, `owner`, `role` from `owner_map`
4. Build GCP service totals and monthly trends (filtered to team projects only)
5. Compute: MTD total, projected full-month (`mtd × days_in_month / today.day`), MoM change
6. Build weekly lookup per project from `/tmp/dnd_weekly.json` (filter to `team_project_ids`):
   - `weekly_by_proj[pid] = {1: w1_cost, 2: w2_cost, 3: w3_cost}`
   - Compute week totals: `w1_total`, `w2_total`, `w3_total`
   - Compute WoW %: `w1w2_pct = (w2-w1)/w1*100`, `w2w3_pct = (w3-w2)/w2*100`
   - Aggregate by owner: `wow_by_owner[owner] = [w1, w2, w3]`
   - Build top movers list: projects with W2 cost > $100, sorted by `abs(w3-w2)` desc, top 15
   - Per project: store `weekly: [w1, w2, w3]` and `wow_pct` (W2→W3 %) on the project dict

---

## Step 4 — Generate the HTML dashboard

Write to `/Users/demahato/CoS/projects/work/dnd-cost/dashboard.html`.

### Layout overview

```
Header (title, folder, owner names, date, MTD note)
KPI Cards ×5 (MTD/proj, last month/prev, MoM, project count, active owner count)
Week-over-Week section (current month, last 3 complete weeks)
  ├── WoW KPI cards ×3 (W1 / W2 / W3 totals with % change vs prior week)
  ├── Grouped bar chart (weekly spend by owner — W1/W2/W3 grouped bars)
  └── Top movers table (top 15 projects by |W3-W2| change)
GCP Infrastructure Services section
  ├── Donut chart (share by GCP service)
  ├── Horizontal bar chart (top 8 GCP services)
  ├── Line chart (monthly trend top 5 GCP services)
  └── Full GCP service table
Cost by Service Name section
  ├── Horizontal bar chart (top 12 App Services by MTD)
  └── Table (all App Services with owner badge, MTD, prior months, trend, project count)
Project search filter
Project table (team projects only)
Footer (data source, MTD note, WoW note, owner note)
```

---

### Section 1 — Header + KPI Cards

Title: **"DnD Team GCP Cost Dashboard"**

Header subtitle lists all 5 target owners, project count, generation date, MTD days.

KPI Cards:
1. MTD spend + projected full month
2. Last full month + month prior
3. MoM trend % (projected vs last full month, green/yellow)
4. Project count (number in filtered list)
5. Owners with Projects (count of target owners who have ≥1 project in folder)

---

### Section 2 — Week-over-Week (current month, last 3 complete weeks)

Section header: **"Week-over-Week"** with a blue label chip: **"[current month] — Last 3 Complete Weeks"**

Week definitions (fixed calendar slices, always within the current month):
- **Week 1** = day 1–7
- **Week 2** = day 8–14
- **Week 3** = day 15–21

**WoW KPI cards (3-col grid):**
- W1 card: total cost, label "Week 1 / [Mon day1]–[day7]", sub "baseline"
- W2 card: total cost, label "Week 2 / [Mon day8]–[day14]", sub = WoW % change with ▲/▼ + absolute delta vs W1
- W3 card: total cost, label "Week 3 / [Mon day15]–[day21]", sub = WoW % change with ▲/▼ + absolute delta vs W2
- Up = red (`#fc8181`), down = green (`#68d391`) — same convention as MoM trend

**2-col grid below the KPI cards:**

Left — **Grouped bar chart** ("Weekly Spend by Owner"):
- X-axis: owner names (sorted by total descending)
- 3 datasets: W1 (owner color at 60% opacity), W2 (80% opacity), W3 (full color)
- Tooltip shows `$` amount per week per owner

Right — **Top Movers table** ("Top Movers — Week 3 vs Week 2"):
- Columns: Project | Owner | W1 (Jun 1–7) | W2 (Jun 8–14) | W3 (Jun 15–21) | W2→W3
- Filter: only projects with W2 cost > $100; sort by `abs(w3 - w2)` desc; show top 15
- W2→W3 cell: `▲/▼ ±pct%` (colored) + dimmed absolute delta e.g. `+$1,200`
- Owner shown as color-coded badge + role badge

**JS data bindings:**
```javascript
D.wowByOwner   // {ownerName: [w1, w2, w3], ...} — only TARGET_OWNERS with data
D.topMovers    // [{name, owner, role, app_service, w1, w2, w3, wow_pct}, ...]
D.w1Total      // number
D.w2Total      // number
D.w3Total      // number
D.w1w2Pct     // number (%)
D.w2w3Pct     // number (%)
```

---

### Section 3 — GCP Infrastructure Services

Label everything in this section as **GCP Service** (not just "Service").
Filter to team projects only (same `team_project_ids` filter).

**Three charts (3-col grid):**
- Donut — GCP Service Share of Spend (top 8)
- Horizontal bar — Top GCP Services MTD
- Line — GCP Service Monthly Trend (top 5, Jan–current)

**GCP service table columns:** GCP Service | MTD | Mar | Feb | Jan | % of Total | Projects

---

### Section 4 — Cost by Service Name

2-column grid: horizontal bar chart (left, top 12 App Services) + summary table (right).

**JS aggregation pattern:**
```javascript
const svcNameAgg = {};
D.projects.forEach(p => {
  const key = p.app_service || '(unlabeled)';
  if (!svcNameAgg[key]) {
    svcNameAgg[key] = {service: key, owner: p.owner, team_email: p.team_email,
                       current: 0, monthly: [0,0,0,0], projects: 0};
  }
  svcNameAgg[key].current += p.current;
  p.monthly.forEach((v, i) => { svcNameAgg[key].monthly[i] += v; });
  svcNameAgg[key].projects++;
});
const svcNameList = Object.values(svcNameAgg).sort((a,b) => b.current - a.current);
```

**Table columns:** Service Name (monospace) | Owner badge | MTD | Mar | Feb | Jan | Trend vs Mar | Projects

---

### Section 5 — Project Table

**Search input** filters by project name.

**Project table columns:**

| Column | Content |
|---|---|
| # | Row number |
| Project | Project name + proportional cost bar |
| MTD | Current month-to-date cost |
| Mar / Feb / Jan | Monthly totals |
| Trend vs Mar | ▲/▼ % projected vs last full month |
| **Service Name** | App Service label from project tag (monospace) |
| **Service Owner** | Color-coded owner badge + role badge (SO/TL/PO) |
| **Team Email** | Clickable mailto link |
| **GCP Services** | App Service badge (small monospace tag) + `▶ N GCP services` expandable button |

**Color constants:**
```javascript
const OWNER_COLORS = {
  "Aaditya Raj":       "#9f7aea",
  "Pratyush Raizada":  "#4299e1",
  "Ravikumar Padala":  "#48bb78",
  "Audrius Sadauskas": "#ed8936",
  "Ahmad Abdul Wakeel":"#fc8181",
  "Josef Pokorny":     "#38b2ac",
  "Saurabh Santhosh":  "#f687b3",
  "Deepak Mahato":     "#d69e2e"
};
const ROLE_COLORS = {"SO": "#48bb78", "TL": "#ecc94b", "PO": "#4299e1"};
```

**Row generation pattern (JavaScript):**
```javascript
const barPct      = (p.current / maxCost * 100).toFixed(1);
const hasSvc      = p.services && p.services.length > 0;
const trendHtml   = p.mom_pct === null ? '<span style="color:#4a5568">—</span>'
  : `<span class="trend ${p.mom_pct > 0 ? 'up' : 'down'}">${p.mom_pct > 0 ? '▲' : '▼'} ${Math.abs(p.mom_pct)}%</span>`;
const ownerColor  = OWNER_COLORS[p.owner] || '#718096';
const roleColor   = ROLE_COLORS[p.role]   || '#718096';
const svcNameHtml = p.app_service
  ? `<span style="font-family:monospace;font-size:11px;color:#a0aec0">${p.app_service}</span>`
  : '<span style="color:#4a5568">—</span>';
const ownerHtml   = p.owner
  ? `<div><span class="owner-badge" style="background:${ownerColor}22;color:${ownerColor}">${p.owner}</span><span class="role-badge" style="background:${roleColor}33;color:${roleColor}">${p.role}</span></div>`
  : '<span style="color:#4a5568">—</span>';
const emailHtml   = p.team_email
  ? `<a href="mailto:${p.team_email}" style="color:#4299e1;text-decoration:none;font-size:11px">${p.team_email}</a>`
  : '<span style="color:#4a5568">—</span>';
const appBadge    = p.app_service
  ? `<div class="app-badge">${p.app_service}</div>`
  : '';
const gcpBtn      = hasSvc
  ? `<button class="expand-btn" onclick="toggleSvc(this,'${p.id}')">▶ ${p.services.length} GCP services</button>`
  : '<span class="cost dim">—</span>';
```

Cells in order: `#` | `project name + bar` | `MTD` | `Mar` | `Feb` | `Jan` | `trendHtml` | `svcNameHtml` | `ownerHtml` | `emailHtml` | `appBadge + gcpBtn`

**Expandable GCP service row** header: `GCP Service | Cost (MTD)`

---

### Footer

Data source table, MTD explanation, WoW note, owner priority note, generation timestamp.

WoW note: "Week 1 = [Mon] day 1–7, Week 2 = day 8–14, Week 3 = day 15–21. All complete calendar weeks only."

Explicitly state which owners have no projects under this folder (from the computed `no_project_owners` set).

**Style:** Dark theme (`#0f1117` bg, `#1a1f2e` cards, `#2d3748` borders), blue accents (`#4299e1`), monospace costs. Chart.js CDN only.

---

## Step 5 — Push report to GitHub

Repo: `git@github.com:demahato-01/data-tribe-cost.git`
Local clone: `/tmp/data-tribe-cost`
**Live URL:** `https://demahato-01.github.io/data-tribe-cost/` (GitHub Pages, public)

```bash
# Clone if not present, otherwise pull latest
if [ -d /tmp/data-tribe-cost/.git ]; then
  git -C /tmp/data-tribe-cost pull origin main
else
  git clone git@github.com:demahato-01/data-tribe-cost.git /tmp/data-tribe-cost
fi

# Create dated folder and copy report
REPORT_DATE=$(date +%Y-%m-%d)
mkdir -p /tmp/data-tribe-cost/reports/$REPORT_DATE
cp /Users/demahato/CoS/projects/work/dnd-cost/dashboard.html /tmp/data-tribe-cost/reports/$REPORT_DATE/dashboard.html
cp /Users/demahato/CoS/projects/work/dnd-cost/dashboard.html /tmp/data-tribe-cost/dashboard.html

# Keep SKILL.md in sync
cp /Users/demahato/.claude/skills/dnd-cost/SKILL.md /tmp/data-tribe-cost/SKILL.md

# Commit and push
cd /tmp/data-tribe-cost
git add reports/$REPORT_DATE/dashboard.html dashboard.html SKILL.md
git -c user.name="Deepak Mahato" -c user.email="demahato@groupon.com" \
  commit -m "Add cost report $REPORT_DATE"
git push origin main
```

**Folder structure in repo:**
```
reports/
  2026-06-22/dashboard.html   ← historical snapshot
  2026-06-29/dashboard.html   ← next run adds a new folder
dashboard.html                ← always the latest run (root URL redirects here)
index.html                    ← auto-redirect to dashboard.html
Service Portal info.csv
SKILL.md
README.md
```

**Shareable URLs (GitHub Pages):**
- Latest dashboard: `https://demahato-01.github.io/data-tribe-cost/dashboard.html`
- Dated snapshot: `https://demahato-01.github.io/data-tribe-cost/reports/YYYY-MM-DD/dashboard.html`
- Root (auto-redirects to latest): `https://demahato-01.github.io/data-tribe-cost/`

Each run creates `reports/YYYY-MM-DD/dashboard.html` (the dated snapshot) and overwrites the root `dashboard.html` (the "latest" link). If the same date is run twice, the second run overwrites that date's folder — this is intentional.

---

## Step 6 — Open the dashboard

```bash
open /Users/demahato/CoS/projects/work/dnd-cost/dashboard.html
```

---

## Step 7 — Report back

- Generation timestamp
- Total MTD spend + projected
- Last full month total + MoM trend
- Week-over-week totals: W1, W2, W3 with % change (W1→W2, W2→W3)
- Number of team projects shown
- Projects matched to Service Portal vs total projects in folder
- Active owners (owners with ≥1 project in the folder)
- File path

---

## IMPORTANT — Formatting rules

**Costs with commas:** Always use `toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})` for costs with cents, and `{minimumFractionDigits:0, maximumFractionDigits:0}` for whole-dollar summaries. Never use bare `toFixed(2)`.

**Python f-string + JS template literals:** Dollar signs in JS template literals inside a Python f-string must be written as `$$` to produce a single `$` in output (e.g. `$${s.cost.toLocaleString(...)}`). Double-check all currency cells.

**OWNER_MAP lookup must use both keys:** Always key owner_map by both `project_id` AND `project_name`. The JS lookup is `OWNER_MAP[p.name] || OWNER_MAP[p.id] || {}` — if only one key is stored, half the projects will show `—`.

**Never inject OWNER_MAP cells via Python f-string substitution** — build the row innerHTML directly in plain JavaScript within the HTML `<script>` block. Mixing Python f-strings with JS template literal `${}` syntax causes escaping bugs that silently break the lookup.

**Owner badge uses semi-transparent background:** `background:${ownerColor}22` (hex with 22 alpha = ~13% opacity) for the badge background, full color for text. Same pattern for role badge with `33` alpha.
