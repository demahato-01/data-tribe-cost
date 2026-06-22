# DnD Team GCP Cost Dashboard

Filtered cost dashboard for GCP projects under folder `499446588003` owned by the DnD team.

## Output

`dashboard.html` — open in any browser, no server needed.

## Data Source

| Field | Value |
|---|---|
| Project | `prj-grpn-seed-terraform-66e7` |
| Dataset | `grpn_cloudability_billing` |
| Table | `gcp_billing_export_resource_v1_01F2E1_BA7EDD_9C9EB7` |
| Folder filter | `project.ancestry_numbers LIKE "%499446588003%"` |

## Owner Filter

Dashboard shows only projects whose effective owner (Service Owner → Tech Lead → Product Owner) is one of:

| Owner | Color |
|---|---|
| Aaditya Raj | purple |
| Pratyush Raizada | blue |
| Ravikumar Padala | green |
| Audrius Sadauskas | orange |
| Ahmad Abdul Wakeel | red |
| Josef Pokorny | teal |
| Saurabh Santhosh | pink |
| Deepak Mahato | gold |

**Note:** Audrius Sadauskas, Ahmad Abdul Wakeel, and Saurabh Santhosh currently have no projects under this folder.

## Dashboard Sections

### KPI Cards
- Current MTD spend + projected full-month estimate
- Last full month + month prior
- MoM trend (projected vs last full month)
- Team project count
- Owners with active projects

### GCP Services Breakdown
- Donut chart — share of spend by GCP service (top 8)
- Horizontal bar chart — top 8 GCP services by MTD cost
- Line chart — monthly trend Jan–current for top 5 GCP services
- Full GCP service table — all services with MTD, prior months, % of total, project count

### Project Table
Columns: # | Project | MTD | Mar | Feb | Jan | Trend vs Mar | Service Name | Service Owner | Team Email | GCP Services

- **Service Name** — App Service label from GCP project tag (e.g. `janus`, `megatron-gcp`) matched to Service Portal
- **Service Owner** — Color-coded owner badge (matching owner's color) + role badge (SO/TL/PO)
- **Team Email** — Clickable mailto link
- **GCP Services** — App Service badge + expandable `▶ N GCP services` button showing per-project infrastructure breakdown
- Filter by project name

> Note: "Service Name" (App Service / portal label) and "GCP Service" (infrastructure like Compute Engine) are different concepts and are kept separate throughout the dashboard.

## Regenerating

Run `/dnd-cost` in Claude Code to refresh with the latest billing data.

The skill runs 6 BigQuery queries in parallel, filters to team-owned projects, processes the data with Python, and rewrites `dashboard.html`.
