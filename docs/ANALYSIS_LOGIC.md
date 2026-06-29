# Analysis Logic

This document explains how the app calculates sales velocity, trends, stock risk, purchase quantities, and outputs.

## Pipeline Order

`app.py` builds a report in this order:

1. Load and clean stock.
2. Load and clean selected sales files.
3. Validate source sales and stock data.
4. Analyze sales velocity and consistency.
5. Analyze trends from older and recent monthly sales.
6. Merge stock, sales, and trend results.
7. Enrich with master data.
8. Calculate PO quantities, risk, priority, rounding, and budget fields.
9. Apply discontinued rules.
10. Build focused report tables.
11. Save result files and Excel workbook.

## Sales Analysis

Implemented in `src/sales_analysis.py`.

### Monthly Aggregation

Sales rows are grouped by:

- Item Code / SKU
- Item Name
- Normalized Item Name
- Category / Size / Type
- Sales Month

For each item-month, sales quantity and sales amount are summed.

The app builds a complete monthly grid from the first observed sales month to the last observed sales month. Missing item-month combinations are filled with zero quantity and zero amount.

### Core Metrics

| Metric | Formula |
| --- | --- |
| Total Sales Qty | Sum of monthly sales quantity |
| Months With Sales | Count of months where sales quantity is greater than 0 |
| Number of Sales Months | Number of months in the full observed date range |
| Average Monthly Sales Qty | Total Sales Qty / Number of Sales Months |
| Overall Monthly Velocity Qty | Same as Average Monthly Sales Qty |
| Recent Period Sales Qty | Sales quantity in the latest N months |
| Recent Monthly Velocity Qty | Recent Period Sales Qty / Recent Period Months |
| Sales Frequency % | Months With Sales / Number of Sales Months * 100 |
| Recent Sales Frequency % | Recent Months With Sales / Recent Period Months * 100 |
| Weighted Velocity Qty | Recent Monthly Velocity Qty * 0.7 + Overall Monthly Velocity Qty * 0.3 |
| Velocity Percentile | Percentile rank of positive Weighted Velocity Qty |
| Sales CV | Monthly Sales Std Dev / Average Monthly Sales Qty |

### Velocity Class

| Condition | Velocity Class |
| --- | --- |
| Total Sales Qty <= 0 | Dead Stock / No Sales |
| Recent Monthly Velocity Qty <= 0 | Dormant |
| Velocity Percentile >= 90 and Recent Sales Frequency % >= 50 | Very Fast Moving |
| Velocity Percentile >= 75 | Fast Moving |
| Velocity Percentile >= 40 and Weighted Velocity Qty > 0 | Medium Moving |
| Otherwise | Slow Moving |

`Movement Category` is set to the same value as `Velocity Class`.

### Consistency Class

| Condition | Consistency Class |
| --- | --- |
| Recent velocity <= 0 and total sales > 0 | Dormant |
| Months With Sales <= 1 and total sales > 0 | One-time Sale |
| Sales CV <= 0.75 and Sales Frequency % >= 60 | Consistent |
| Sales CV <= 1.25 | Moderate |
| Otherwise | Irregular |

## Trend Analysis

Implemented in `src/trend_analysis.py`.

The app compares older monthly average sales to recent monthly average sales.

### Period Selection

| Mode | Older Period | Recent Period |
| --- | --- | --- |
| Manual recent months | All months before the latest N months | Latest N months |
| Auto split period in half | First half of observed months | Second half of observed months |

### Trend Change

```text
Trend Change % = (Recent Avg Monthly Sales Qty - Older Avg Monthly Sales Qty) / Older Avg Monthly Sales Qty * 100
```

When older average is zero, trend change percent is not meaningful and trend class is determined by older/recent zero checks.

### Sales Trend

| Condition | Sales Trend |
| --- | --- |
| Older avg = 0 and recent avg > 0 | New Moving Item |
| Older avg = 0 and recent avg = 0 | No Sales |
| Older avg > 0 and recent avg = 0 | Dormant Item |
| Trend Change % > 50 | Strong Upward Trend |
| Trend Change % > 20 and <= 50 | Upward Trend |
| Trend Change % < -50 | Strong Downward Trend |
| Trend Change % < -20 and >= -50 | Downward Trend |
| Otherwise | Stable Trend |

## Stock Merge

Implemented in `src/stock_analysis.py`.

Stock is outer-merged with sales summary by `Item Code / SKU`, then trend fields are merged. This preserves:

- Stock items with no sales.
- Sales items missing from stock.

Missing numeric values are filled with zero where appropriate. Missing suppliers become `Unknown Supplier`.

Coverage metrics:

```text
Stock Coverage Months = Current Stock Qty / Overall Monthly Velocity Qty
Recent Stock Coverage Months = Current Stock Qty / Recent Monthly Velocity Qty
```

If velocity is zero, coverage is `NaN` rather than infinite.

## Master Data Enrichment

Implemented in `src/master_data_manager.py`.

### Category Resolution

The app resolves category in this order:

1. Item Category Mapping by Item Key.
2. Active category from source data, if source category name matches an active category.
3. Uncategorized.

The resolved category provides:

- Category ID
- Category Name
- Category Box Qty
- Category Source
- Box Qty Source

### Supplier Resolution

The app resolves supplier in this order:

1. Item Supplier Mapping by Item Key.
2. Supplier from stock file.
3. Unknown Supplier.

The resolved supplier provides:

- Assigned Supplier ID
- Assigned Supplier Name
- Supplier Source

### Discontinued Resolution

Any item with an active discontinued row gets:

- Is Discontinued = Yes
- Discontinued Date
- Discontinued Reason

Discontinued items are later forced to zero PO quantity.

## Purchase Order Calculation

Implemented in `src/po_calculator.py`.

### Target Cover

Target cover is dynamic. Dormant, dead-stock, dormant-trend, and no-sales items get zero target cover.

Default stable target settings:

| Movement | Default Stable Cover |
| --- | --- |
| Very Fast Moving | 3.0 months |
| Fast Moving | 2.5 months |
| Medium Moving | 2.0 months |
| Slow Moving | 1.0 month |

Upward trends generally increase target cover. Downward trends reduce it. Strong downward trends reduce it further. Slow irregular items can be capped lower.

### Relevant Velocity

Relevant velocity is trend-aware:

| Trend | Relevant Velocity |
| --- | --- |
| Strong Upward Trend, Upward Trend, New Moving Item | max(recent velocity, weighted velocity) |
| Stable Trend | weighted velocity |
| Downward Trend, Strong Downward Trend | recent velocity |
| Other | 0 |

### Required Quantity

```text
Required Stock Qty = Relevant Velocity Qty * Suggested Target Cover Months
Exact Purchase Requirement Qty = max(Required Stock Qty - Current Stock Qty, 0)
```

### Box Quantity Source

The box quantity used for rounding is resolved in this order:

1. Category Box Qty
2. Box / Pack Quantity from stock
3. Detected edge-band box quantity
4. Not available

### Rounding

If box rounding is enabled and a valid box quantity exists:

```text
Rounded PO Qty = ceil(Exact Purchase Requirement Qty / Box Qty) * Box Qty
Final PO Boxes = ceil(Exact Purchase Requirement Qty / Box Qty)
```

If no valid box quantity exists, the app rounds up to the next whole quantity.

### Maximum Cover After PO

The app uses these maximum cover thresholds to prevent overstock after rounding:

| Velocity Class | Max Cover After PO |
| --- | --- |
| Very Fast Moving | 4.5 months |
| Fast Moving | 4.5 months |
| Medium Moving | 4.0 months |
| Slow Moving | 2.5 months |
| Dormant | 0 months |
| Dead Stock / No Sales | 0 months |

If rounding creates too much cover, the app may skip the PO line depending on velocity class and settings.

### Stock Risk

`Stock Risk Level` is assigned after PO fields are calculated.

Rules include:

- Overstock Risk when cover is much higher than target or dormant/dead items have stock.
- Urgent Stock Risk for very fast or fast items with less than 0.5 months recent cover.
- High Stock Risk for active fast/medium/very fast items with less than 1 month recent cover.
- Medium Stock Risk when active cover is below target.
- Low Stock Risk otherwise.

### Purchase Priority

Priority is based on final PO quantity, velocity, stock risk, recent cover, and trend:

- Zero final PO quantity means No Purchase.
- Very fast or fast items with urgent risk become Urgent.
- Very fast or fast items with high or medium risk become High.
- Medium moving items below 1 month recent cover become High.
- Other medium moving items become Medium.
- Slow moving upward/new items become Medium.
- Other slow moving items become Low.

Rows skipped for overstock, dormant/dead status, or enough stock are forced back to No Purchase.

### Estimated Value

```text
Estimated Purchase Value = Final PO Quantity * Purchase Price
```

`Total Amount` is kept in sync with estimated purchase value for export and supplier PO views.

## Budget Optimization

Budget optimization is optional.

When enabled, candidate PO lines are sorted by:

1. Budget Priority Score descending.
2. Estimated Purchase Value ascending.

The app includes lines greedily until the configured budget is reached. Remaining candidate lines are marked:

- Included In Budget PO = No
- Deferred Reason = Deferred due to budget limit.
- Budget Approved PO Quantity = 0
- Budget Approved PO Value = 0

Discontinued items are never eligible.

## Discontinued Rules

Implemented in `apply_discontinued_po_rules`.

Discontinued items are forced to:

- Suggested Target Cover Months = 0
- Required Stock Qty = 0
- Exact Purchase Requirement Qty = 0
- Rounded PO Qty = 0
- Final PO Quantity = 0
- Estimated Purchase Value = 0
- Purchase Priority = No Purchase
- PO Optimization Decision = Discontinued Item - Do Not Purchase

The reason is set to:

```text
Item is marked discontinued. Do not reorder. Sell down or liquidate existing stock.
```

## Minimum Purchase Value

If `min_purchase_value` is greater than zero, PO lines below that value are removed:

- PO Optimization Decision = Below Minimum Purchase Value
- Purchase Priority = No Purchase
- Final PO Quantity = 0
- Estimated Purchase Value = 0

## Validation

Implemented in `src/validator.py` and `master_validation_warnings`.

### Source Data Validation

The app flags:

- Missing item code
- Zero or blank sales quantity
- Duplicate item code in stock
- Missing purchase price
- Missing supplier
- Missing box size, MOQ, or pack size
- Negative stock
- Sales item missing in stock
- Stock item missing in sales
- Item name mismatch between stock and sales for same SKU

### Velocity Calculation Warnings

The app flags suspicious velocity rows such as:

- Average monthly velocity greater than total sales quantity.
- Recent monthly velocity greater than recent sales quantity.
- Relevant velocity greater than total sales quantity.
- Relevant velocity more than 5x current stock.
- Relevant velocity exceeding 100,000 per month without supporting total sales.
- Weighted velocity greater than total sales quantity.

### Master Data Warnings

The app flags:

- Items without assigned supplier.
- Items assigned to inactive suppliers.
- Discontinued items with stock available.
- Discontinued items found in PO and removed.
- Duplicate item supplier mappings.
- Supplier mappings for items not in the current result.
- Duplicate supplier names.
- Duplicate category names.
- Categories with missing box quantity.
- Items without category mapping.
- Items assigned to inactive categories.

## Report Tables

After calculation, `build_report` creates:

- Executive Summary
- Data Validation
- Velocity Calculation Warnings
- Velocity Analysis
- Trend Analysis
- Stock Risk
- Detailed Item Analysis
- Optimized PO
- Supplier Ready PO
- Category Size Summary
- Overstock Dead Stock
- Discontinued Items
- Supplier Master
- Item Supplier Mapping
- Categories
- Item Category Mapping
- Business Recommendations
- Assumptions

Internal debug inputs are stored under `_Debug Inputs` in session state and are not exported to Excel.
