# Data And Outputs

This document describes the file contracts used by Inventory PO Planner.

## Directory Contract

```text
data/
  master/
    stores.csv
    suppliers.csv
    categories.csv
  stores/
    STORE-0001/
      store.json
      master/
        discontinued-items.csv
        item-suppliers.csv
        item-categories.csv
      results/
        latest/
        history/
          RUN-YYYYMMDD-HHMMSS/
  itemwisesales/
    {FY}/
      {STORE_ID}/
        itemwisesales.csv
  stock/
    {FY}/
      {STORE_ID}/
        stock.csv
```

## Input Files

### Stock CSV

Expected path:

```text
data/stock/{FY}/{STORE_ID}/stock.csv
```

Required logical fields:

- Item name
- Current stock quantity
- Purchase price

Optional logical fields:

- Item code or SKU
- Category, size, type, group, or brand
- Supplier or vendor
- Box size, MOQ, pack size, packing, or box quantity

Current checked-in stock header:

```text
SlNo,Item Name,P.Price,Retail,COST,Qty,Amount
```

### Item-wise Sales CSV

Expected path:

```text
data/itemwisesales/{FY}/{STORE_ID}/itemwisesales.csv
```

Required logical fields:

- Item name
- Sales quantity

Optional logical fields:

- Item code or SKU
- Category, size, type, group, or brand
- Sales date
- Sales amount

Current checked-in sales FYs:

```text
22-23
23-24
24-25
26-27
```

The `24-25` file currently has duplicate `Qty` headers. Pandas can load duplicate headers by suffixing later copies, but manual mapping should be reviewed when duplicate or ambiguous source columns exist.

## Column Detection

`src/column_mapper.py` detects logical fields from source headers.

| Logical Field | Common Header Aliases |
| --- | --- |
| item_code | item code, sku, code, product code, item no, item id |
| item_name | item, item name, product, product name, description, particulars |
| category | category, size, type, group, brand |
| sales_qty | qty, quantity, sales qty, sale qty, sold qty, net qty, billed qty, meter, mtr, meters |
| sales_date | date, invoice date, bill date, month, sales month |
| sales_amount | amount, sales amount, value, net amount, total |
| stock_qty | stock, closing stock, current stock, balance qty, available qty, qty |
| purchase_price | purchase price, p.price, cost, rate, buy price, landing cost |
| supplier | supplier, supplier name, vendor |
| pack_size | box size, moq, pack size, packing, box qty |

Sales quantity detection rejects likely amount/value columns with terms such as amount, value, gross, taxable, rate, price, cost, INR, and Rs.

## Cleaned Sales Schema

`clean_sales` returns these columns:

| Column | Meaning |
| --- | --- |
| FY | Financial year from the parent folder name |
| Item Name | Cleaned source item name |
| Normalized Item Name | Uppercase normalized item name |
| Item Code / SKU | Source item code, or normalized item name when missing |
| Category / Size / Type | Source category-like value when available |
| Sales Quantity | Numeric sales quantity |
| Sales Amount | Numeric sales amount, or 0 when unavailable |
| Sales Date | Parsed date, day-first |
| Sales Month | Month timestamp derived from Sales Date |
| Detected Size | Edge-band size detected from item name |
| Detected Box Qty | Edge-band box quantity detected from item name |

When no usable sales date exists, missing months are assigned to March of the selected FY.

## Cleaned Stock Schema

`clean_stock` returns these columns:

| Column | Meaning |
| --- | --- |
| Item Name | Cleaned source item name |
| Normalized Item Name | Uppercase normalized item name |
| Item Code / SKU | Source item code, or normalized item name when missing |
| Category / Size / Type | Source category-like value when available |
| Current Stock Qty | Numeric stock quantity |
| Purchase Price | Numeric purchase price |
| Supplier Name | Source supplier, or Unknown Supplier |
| Box / Pack Quantity | Numeric pack size, or detected edge-band box quantity |
| Detected Size | Edge-band size detected from item name |
| Detected Box Qty | Edge-band box quantity detected from item name |
| Unit | `Meters` for detected edge-band items, otherwise `Qty` |

## Master Files

Master files are created automatically if missing or empty. Stores, suppliers, and categories are global. Item mappings and discontinued flags are store-specific.

### stores.csv

Path:

```text
data/master/stores.csv
```

Columns:

```text
Store ID,Store Name,Location,Contact Person,Phone,Notes,Active,Created At,Updated At
```

Store IDs are generated as `STORE-0001`, `STORE-0002`, and so on. If no stores exist, the app creates `STORE-0001 / Main Store`.

### suppliers.csv

Columns:

```text
Supplier ID,Supplier Name,Contact Person,Phone,Email,Address,Notes,Active,Created At,Updated At
```

Supplier IDs are generated as `SUP-0001`, `SUP-0002`, and so on.

### item-suppliers.csv

Path:

```text
data/stores/{STORE_ID}/master/item-suppliers.csv
```

Columns:

```text
Item Key,Item Code / SKU,Item Name,Supplier ID,Supplier Name,Updated At
```

These mappings override supplier names from the stock file.

### categories.csv

Columns:

```text
Category ID,Category Name,Box Qty,Active,Created At,Updated At
```

Category IDs are generated as `CAT-0001`, `CAT-0002`, and so on. The app ensures an active `Uncategorized` category exists.

### item-categories.csv

Path:

```text
data/stores/{STORE_ID}/master/item-categories.csv
```

Columns:

```text
Item Key,Item Code / SKU,Item Name,Category ID,Category Name,Updated At
```

These mappings override the category from source data.

### discontinued-items.csv

Path:

```text
data/stores/{STORE_ID}/master/discontinued-items.csv
```

Columns:

```text
Item Key,Item Code / SKU,Item Name,Discontinued,Discontinued Date,Reason,Updated At
```

Rows marked `Discontinued = Yes` force PO quantity and purchase value to zero.

## Result Files

Each saved run writes CSV and text files to:

```text
data/stores/{STORE_ID}/results/history/{RUN_ID}/
```

The latest run is copied to:

```text
data/stores/{STORE_ID}/results/latest/
```

### CSV Outputs

| Report Key | File |
| --- | --- |
| Store Summary | `store_summary.csv` |
| Executive Summary | `executive_summary.csv` |
| Data Validation | `data_validation.csv` |
| Velocity Calculation Warnings | `velocity_calculation_warnings.csv` |
| Velocity Analysis | `velocity_analysis.csv` |
| Trend Analysis | `trend_analysis.csv` |
| Stock Risk | `stock_risk.csv` |
| Detailed Item Analysis | `detailed_item_analysis.csv` |
| Optimized PO | `optimized_po.csv` |
| Supplier Ready PO | `supplier_ready_po.csv` |
| Supplier Ready PO Edited | `supplier_ready_po_edited.csv` |
| Overstock Dead Stock | `overstock_dead_stock.csv` |
| Discontinued Items | `discontinued_items.csv` |
| Supplier Master | `supplier_master.csv` |
| Item Supplier Mapping | `item_supplier_mapping.csv` |
| Categories | `categories.csv` |
| Item Category Mapping | `item_categories.csv` |
| Category Size Summary | `category_size_summary.csv` |

### Text Outputs

| Report Key | File |
| --- | --- |
| Business Recommendations | `business_recommendations.txt` |
| Assumptions | `assumptions.txt` |

These are stored as tab-separated text when they originate from dataframes.

## Detailed Item Analysis

`detailed_item_analysis.csv` is the main per-item output. It includes:

- Store ID and Store Name
- Item identifiers and item key
- Supplier assignment fields
- Discontinued fields
- Category assignment fields
- Sales totals and velocity fields
- Trend fields
- Consistency fields
- Stock quantity and stock coverage fields
- Relevant velocity and target cover
- Required stock and exact purchase requirement
- Box quantity and rounding fields
- Final PO quantity and estimated value
- Purchase priority and stock risk
- Budget approval fields
- Recommendation reason

The current checked-in latest result has 270 detailed rows.

## Optimized PO

`optimized_po.csv` includes only non-discontinued items with `Final PO Quantity > 0`.

Important columns:

- Store ID
- Store Name
- Supplier Name
- Item Code / SKU
- Item Name
- Category Name
- Category Box Qty
- Final PO Boxes
- Velocity Class
- Sales Trend
- Current Stock Qty
- Relevant Velocity Qty
- Suggested Target Cover Months
- Final PO Quantity
- Purchase Price
- Total Amount
- Purchase Priority
- Stock Risk Level
- Reason

The current checked-in latest result has 10 optimized PO rows.

## Supplier Ready PO

`supplier_ready_po.csv` is formatted for supplier-facing purchase rows.

Columns:

```text
Store ID,Store Name,Supplier Name,Sl No,Item Code / SKU,Item Name,Category Name,Category Box Qty,Quantity,Boxes,Unit,Purchase Price,Total Amount
```

The Streamlit UI lets users edit `Quantity`; boxes and total amount are recalculated from quantity, category box quantity, and purchase price.

## Excel Export

The workbook is generated by `src/excel_exporter.py`. It writes every dataframe in the report dictionary except internal keys beginning with `_`.

Formatting includes:

- Bold colored headers
- Auto column widths
- Freeze panes
- Autofilters
- Number formats for amount/value/price and quantity/stock columns
- Conditional formatting for urgent, high, dormant/dead, and overstock rows

## Manifest

Every saved run includes `manifest.json`.

Important fields:

| Field | Meaning |
| --- | --- |
| run_id | Generated run ID |
| store_id | Store used for the run |
| store_name | Store name used for the run |
| created_at | ISO timestamp |
| created_at_display | Human readable timestamp |
| stock_file | Stock file used |
| stock_file_modified_at | Stock file modified time |
| sales_years | Selected FYs |
| sales_files | Paths and modified times for selected FY files |
| settings | Compact settings summary |
| summary | Key executive metrics |
| category_summary | Category counts and unmapped category health |
| files | Main output filenames |

Example latest run ID in the current repository snapshot:

```text
RUN-20260629-085058
```
