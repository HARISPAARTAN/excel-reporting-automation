# Data model

All names and figures are invented. The master data and the metrics live in [report.yaml](../report.yaml); the parameters that shape the invented demo data live in `src/buildreport/fixtures.py`, because they describe a simulation, not the client's configuration.

## Branches

| Code | Branch | Format |
|---|---|---|
| CL-01 | Alderbrook | Flagship |
| CL-02 | Brackenford | High street |
| CL-03 | Corravale | High street |
| CL-04 | Dunmarren | Neighbourhood |
| CL-05 | Elmshaw | Neighbourhood |
| CL-06 | Fernhollow | Neighbourhood |
| CL-07 | Glenvarra | Transit kiosk |
| CL-08 | Hollinmoor | Neighbourhood |
| CL-09 | Kilbrecan | High street |
| CL-10 | Lisnaferry | Retail park |
| CL-11 | Mosswick | Neighbourhood |
| CL-12 | Rowanmere | Transit kiosk |

`report.yaml` accepts 1 to 14 branches with unique codes; the sheets follow the list.

## Product groups and roles

| Product group | Unit price EUR (demo) | Waste rate (demo) |
|---|---|---|
| Bread | 3.40 | 7.5 % |
| Viennoiserie | 2.60 | 8.5 % |
| Cakes and Pastries | 3.90 | 5.0 % |
| Savoury and Sandwiches | 5.80 | 6.5 % |
| Hot Drinks | 3.50 | 0.4 % |
| Cold Drinks and Grocery | 2.40 | 0.6 % |

| Role | Employer cost per hour EUR (demo) | Share of labour cost (demo) |
|---|---|---|
| Bakery | 21.40 | 40 % |
| Counter | 17.80 | 48 % |
| Supervisor | 25.60 | 12 % |

## Demo generator parameters

The generator (`build-report generate-fixtures`, `src/buildreport/fixtures.py`) draws every file from its own `random.Random(f"cedarline:{seed}:{code}:{week}")` with seed 2207, so any week regenerates on its own and the committed set is reproducible.

| Code | Base net sales EUR per week | Average basket EUR | Labour % target | Waste factor |
|---|---|---|---|---|
| CL-01 | 41,500 | 8.90 | 27.0 | 0.90 |
| CL-02 | 33,000 | 8.20 | 28.0 | 1.00 |
| CL-03 | 30,500 | 8.30 | 28.5 | 1.12 |
| CL-04 | 24,000 | 7.60 | 30.0 | 0.95 |
| CL-05 | 22,500 | 7.50 | 30.5 | 1.25 |
| CL-06 | 21,000 | 7.70 | 29.5 | 0.85 |
| CL-07 | 15,500 | 5.80 | 31.0 | 0.80 |
| CL-08 | 23,500 | 7.40 | 30.0 | 1.05 |
| CL-09 | 29,000 | 8.10 | 28.0 | 0.92 |
| CL-10 | 26,500 | 9.40 | 26.5 | 1.18 |
| CL-11 | 19,500 | 7.30 | 32.5 | 1.00 |
| CL-12 | 14,000 | 5.60 | 31.5 | 0.88 |

Net sales follow a seasonal factor by ISO week and a growth of 3 % a year, split by the format's product mix; waste, units, transactions and labour are derived with bounded noise. Labour is semi-fixed, so the labour share rises in slow weeks. The seasonal factor is a table by ISO week (from 0.86 in week 1 to 1.24 in week 51), the growth compounds from the Monday of 2025-W01, and the product mix depends on the branch format, with more hot drinks in winter and more cold drinks in summer. Labour cost is the branch's labour target (a share of sales) times its base weekly sales, the growth and `0.7 + 0.3 × season`. The tables and the formulas are in `src/buildreport/fixtures.py`.

## Incoming workbook (template version 3)

One workbook per branch and ISO week (Monday to Sunday), weekly totals only. File name `CL-NN_YYYY-Www.xlsx`, for example `CL-03_2025-W38.xlsx`; a suffix after a space, `_` or `-` is allowed (`CL-10_2025-W37_resend.xlsx`). The pattern is `input.file_pattern` in `report.yaml`.

| Sheet | Layout | Fields |
|---|---|---|
| `Cover` | labels in column A (rows 1 to 30, matched without regard to case), values in column B | Branch code (`CL-NN`, must exist in `report.yaml`), Branch name, ISO week (`YYYY-Www`, `YYYYWww` accepted), Transactions (whole number ≥ 0), Submitted at (date and time), Submitted by (role mailbox such as `alderbrook.manager@cedarline.example`), Template version (3) |
| `Sales` | header row 1, one row per product group; column order free; headers matched after case folding and collapsing whitespace; blank rows and a row keyed `Total` ignored | Product group (one of six), Net sales EUR (money ≥ 0, excluding VAT), Units sold (whole number ≥ 0), Waste units (whole number ≥ 0), Waste EUR (discarded goods at net selling price) |
| `Labour` | as `Sales`, one row per role | Role (one of three), Hours (≥ 0), Cost EUR (employer cost) |

Sheets are found by name or by the aliases in `report.yaml` (`Sales*`, `Sales data`, `Labour*`, `Labor*`, `Cover*`). Text in a numeric cell, a negative number or a blank required value is a finding; numbers are never parsed from text. The reader opens files with cached values only, and the template contains no formulas.

## Deviations in the demo set

The `demo` profile is defined relative to the end week E. The committed set (E = 2025-W38, weeks 2025-W31 to 2025-W38) and every weekly CI run use it, so the demo report always carries exactly these six warnings:

| Deviation | Where | Handling | Finding |
|---|---|---|---|
| Renamed sheet | CL-03, week E: `Sales` is named `Sales wk38` | matched by the alias `Sales*` | `SHEET_RENAMED` |
| Extra column | CL-05, week E: a `Notes` column between Units sold and Waste units | ignored; columns are matched by header | `EXTRA_COLUMN` |
| Missing week | CL-08, week E: the cover cell ISO week is blank | week from the file name | `WEEK_MISSING` |
| Wrong week in the file name | CL-11, week E: named with week E−10 (`CL-11_2025-W28.xlsx`), the cover says E | the cover wins | `WEEK_NAME_MISMATCH` |
| Duplicate file | CL-10, week E−1: `CL-10_2025-W37.xlsx` (submitted Monday 08:40) and `CL-10_2025-W37_resend.xlsx` (14:12, Bread net sales corrected by +3.5 %) | the later Submitted at is used | `DUPLICATE_REPLACED` |
| Missing branch file | CL-12, week E−2: no file | the branch is blank that week; the trend counts 11 branches | `MISSING_BRANCH` |

All finding codes are listed in [usage](usage.md#findings).

## The long table `tblWeekly`

The sheet Data holds the combined records as the Excel table `tblWeekly`, one row per branch, week, category and measure, so that branch measures and product-group measures never share a row. The metrics engine reads the same records.

| Column | Type | Content |
|---|---|---|
| `week` | text | ISO week, `2025-W38` |
| `week_start` | date | Monday of the week |
| `branch_code` | text | `CL-03` |
| `branch_name` | text | `Corravale` |
| `category` | text | the product group for the four sales measures, the role for the two labour measures, empty for transactions |
| `measure` | text | one of the seven measures below |
| `value` | number | the value as reported |
| `source_file` | text | the workbook the value came from |

| Measure | Category | Unit |
|---|---|---|
| `net_sales_eur` | product group | EUR |
| `units_sold` | product group | count |
| `waste_units` | product group | count |
| `waste_eur` | product group | EUR |
| `labour_hours` | role | hours |
| `labour_cost_eur` | role | EUR |
| `transactions` | empty | count |

A branch-week has 31 rows (6 × 4 + 3 × 2 + 1); the 2025-W38 demo report holds 2,945 rows for 95 branch-weeks. The table is sorted by week, branch code, measure order and category order.

## Metrics

| Key | Label | Expression | Format | Change | Better |
|---|---|---|---|---|---|
| `revenue` | Revenue | `sum(net_sales_eur)` | eur | relative | higher |
| `transactions` | Transactions | `sum(transactions)` | count | relative | higher |
| `avg_basket` | Average basket | `revenue / transactions` | eur2 | relative | higher |
| `units_sold` | Units sold | `sum(units_sold)` | count | relative | higher |
| `waste_eur` | Waste EUR | `sum(waste_eur)` | eur | relative | lower |
| `waste_pct` | Waste % | `waste_eur / revenue` | pct1 | points | lower |
| `labour_hours` | Labour hours | `sum(labour_hours)` | hours | relative | neutral |
| `labour_cost` | Labour cost | `sum(labour_cost_eur)` | eur | relative | lower |
| `labour_pct` | Labour % of revenue | `labour_cost / revenue` | pct1 | points | lower |
| `revenue_per_labour_hour` | Revenue per labour hour | `revenue / labour_hours` | eur2 | relative | higher |

The Summary shows seven of them (`summary_kpis`): revenue, transactions, average basket, waste %, labour % of revenue, revenue per labour hour and labour hours. Thresholds: waste % above 6 % is shown red, labour % of revenue above 32 % amber.

## Rules

- Scopes: branch-week (one branch's records in a week), product-group-week (one category across the reporting branches) and chain-week (all reporting branches).
- `sum(m)` adds `value` over the scope's records with measure `m` (`math.fsum`; nothing to add gives 0). A bare name refers to a metric defined earlier in `report.yaml`. Numbers, `+ - * /`, unary minus and parentheses complete the grammar; anything else is a configuration error.
- Division by zero or a blank operand gives blank. Money is rounded only by number formats, never in computation.
- Week-on-week change of period P against P−1: relative = (current − previous) / previous, blank when previous is blank or 0; points = (current − previous) × 100, shown as pp.
- Chain figures include every branch that reported in each week (as reported, not like-for-like); when the branch counts differ, the Summary says so in its data notes.
- Ranking: branches with a valid return in P by revenue, descending; ties by branch code; ranks 1 to n without gaps; rank change = rank in P−1 minus rank in P (`+2` is up two places), blank when unranked in P−1.
- Share of revenue = group revenue / chain revenue; branch mix = branch-group revenue / branch revenue.
- A threshold compares a value with its operator (`>`, `>=`, `<`, `<=`) and applies its style (`bad` red, `warn` amber).
- The ten metric keys are required, because the sheet layout of v0.1.0 uses them; further metrics appear in the manifest only.
