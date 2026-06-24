# GCP Cost Dashboards

Self-contained HTML dashboards for GCP cost visibility at Groupon. No server needed — open in any browser.

**Billing source:** `prj-grpn-seed-terraform-66e7.grpn_cloudability_billing.gcp_billing_export_resource_v1_01F2E1_BA7EDD_9C9EB7`

**Ownership lookup:** `Service Portal info.csv` — active services only (Decommed/Sunset excluded), columns: Service, Product Owner, Service Owner, Tech Lead, Team Email.

---

## Dashboards

### 1. DnD Team Cost Dashboard

**Scope:** GCP projects under folder `499446588003` (DnD team only), all GCP services.

**Live dashboard:** `dashboard.html` (root)

**Regenerate:** Run `/dnd-cost` in Claude Code.

#### Sections
- **KPI Cards** — MTD spend, projected full month, last month, prior month, MoM trend, project count, owner count
- **GCP Services Breakdown** — donut + bar charts, monthly trend line, full SKU table
- **Project Table** — all projects with MTD, prior months, trend, service owner, team email, expandable GCP services per project

#### Owner Filter
Only projects whose effective owner (Service Owner → Tech Lead → Product Owner) is a DnD team member are shown.

---

### 2. BigQuery Cost Dashboard

**Scope:** All Groupon GCP projects (org-wide), BigQuery service only (`service.description = 'BigQuery'`).

**Live dashboard:** `bigquery-cost/dashboard.html`

**Regenerate:** Run `/bq-cost` in Claude Code.

#### Sections
- **KPI Cards** — MTD BigQuery spend, projected full month, last month, prior month, MoM trend, project count, owner count
- **Week-over-Week** — W1/W2/W3 totals, grouped bar chart by owner, top movers table
- **BigQuery SKU Breakdown** — donut + bar charts, monthly trend, full SKU table (Analysis, Active/Long Term Storage, etc.)
- **Cost by Service Owner** — bar chart + table with MTD, prior months, MoM trend, project count
- **Project Table** — all 144 projects, searchable, expandable SKU rows per project

---

## Dated Snapshots

Every dashboard regeneration auto-saves a dated copy:

```
reports/YYYY-MM-DD/dashboard.html          ← DnD dashboard snapshots
bigquery-cost/reports/YYYY-MM-DD/dashboard.html  ← BigQuery dashboard snapshots
```

---

## Ownership Resolution

For each GCP project:
1. Read the `service` label from the billing export
2. Match it to a row in `Service Portal info.csv`
3. Pick the first active owner in priority order: **Service Owner → Tech Lead → Product Owner**
4. Names containing `(Inactive)` or `(Unconfirmed)` are skipped

Services with `Lifecycle = Decommed` or `Sunset` are excluded from the CSV.

---

## Updating Service Portal CSV

Replace `Service Portal info.csv` with a fresh export from [services.groupondev.com](https://services.groupondev.com):
1. Export the full CSV from the Service Portal
2. Keep only active services (filter out `Lifecycle = Decommed` and `Sunset`)
3. Slim to columns: `Service, Product Owner, Service Owner, Tech Lead, Team Email`
4. Overwrite `Service Portal info.csv` at the repo root
5. Re-run the relevant dashboard skill to pick up the new ownership data
