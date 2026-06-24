# Cost Dashboards

Self-contained HTML dashboards for GCP and AWS cost visibility at Groupon. No server needed — open in any browser or via GitHub Pages.

**Live index:** `https://demahato-01.github.io/data-tribe-cost/`

---

## Dashboards

### 1. AWS Cost Monitor

**Accounts:** `grpn-dnd-prod` (458721635755) · `grpn-teradata-prod` (851725417994)

**Live dashboard:** `aws-cost/dashboard.html`

**Regenerate:**
```bash
python3 aws-cost/build_dashboard.py
```
Requires AWS profiles `dnd-prod` and `teradata-prod` (authenticated via `saml2aws`).

#### Sections
- **Header strip** — combined MTD, projected, MoM vs last month, W2→W3 delta
- **Account cards** — per-account MTD, projected, last/prior month, WoW W1/W2/W3 mini trend
- **Week-over-Week** — summary table (both accounts + combined), grouped bar chart, biggest cost movers per account
- **Per-account service breakdown** — sortable table: Service | MTD | W1 | W2 | W3 | W2→W3 Δ
- **Monthly trends** — grouped bar chart (both accounts), top services MTD comparison

#### Auth setup (one-time)
```bash
brew install awscli saml2aws
# saml2aws config already at ~/.saml2aws (Okta)
saml2aws login --role arn:aws:iam::458721635755:role/grpn-all-billing-ro --profile dnd-prod
saml2aws login --role arn:aws:iam::851725417994:role/grpn-all-billing-ro --profile teradata-prod
```
Credentials expire every hour — re-run `saml2aws login` before regenerating.

---

### 2. BigQuery Cost Dashboard

**Scope:** All Groupon GCP projects (org-wide), BigQuery service only.

**Billing source:** `prj-grpn-seed-terraform-66e7.grpn_cloudability_billing.gcp_billing_export_resource_v1_01F2E1_BA7EDD_9C9EB7`

**Live dashboard:** `bigquery-cost/dashboard.html`

**Regenerate:** Run `/bq-cost` in Claude Code.

#### Sections
- **KPI Cards** — MTD BigQuery spend, projected, last month, MoM trend, project count, owner count
- **Week-over-Week** — W1/W2/W3 totals, grouped bar chart by owner, top movers table
- **BigQuery SKU Breakdown** — donut + bar charts, monthly trend, full SKU table
- **Cost by Service Owner** — bar chart + table with MTD, prior months, MoM trend
- **Project Table** — all projects, searchable, expandable SKU rows per project

---

### 3. DnD GCP Cost Dashboard

**Scope:** GCP projects under folder `499446588003` (DnD team only).

**Live dashboard:** `dashboard.html` (root)

**Regenerate:** Run `/dnd-cost` in Claude Code.

#### Sections
- **KPI Cards** — MTD spend, projected, last month, MoM trend, project count, owner count
- **GCP Services Breakdown** — donut + bar charts, monthly trend
- **Project Table** — all DnD projects with MTD, prior months, trend, service owner, team email

---

## Dated Snapshots

Every regeneration saves a dated copy automatically:

```
reports/YYYY-MM-DD/dashboard.html
bigquery-cost/reports/YYYY-MM-DD/dashboard.html
aws-cost/reports/YYYY-MM-DD/dashboard.html
```

---

## Ownership Resolution (GCP dashboards)

For each GCP project:
1. Read the `service` label from the billing export
2. Match to a row in `Service Portal info.csv`
3. Pick the first active owner: **Service Owner → Tech Lead → Product Owner**
4. Names with `(Inactive)` or `(Unconfirmed)` are skipped
5. Services with `Lifecycle = Decommed` or `Sunset` are excluded

---

## GitHub Pages

Dashboards are served statically via GitHub Pages from the `main` branch.  
Enable once: **repo Settings → Pages → Source: Deploy from branch → main → / (root)**.
