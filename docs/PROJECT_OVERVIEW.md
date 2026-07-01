# Project Overview

Inventory PO Planner is a local Streamlit app for purchase managers. It turns each store's stock and item-wise sales CSV files into a store-specific purchase recommendation package: dashboard metrics, detailed item analysis, optimized PO lines, supplier-ready PO rows, validation warnings, and an Excel workbook.

## What The App Solves

The app answers:

- Which items need replenishment?
- Which items should not be reordered because they are dormant, dead, discontinued, or overstocked?
- How much should be ordered after applying velocity, trend, stock cover, box rounding, and budget settings?
- Which supplier should each PO line go to?
- Which data issues need attention before trusting the purchase plan?

## High-Level Flow

```text
CSV inputs
  -> active store selection
  -> file_manager
  -> data_loader
  -> cleaner and column_mapper
  -> validator
  -> sales_analysis
  -> trend_analysis
  -> stock_analysis
  -> master_data_manager enrichment
  -> po_calculator
  -> recommendations
  -> result_store and excel_exporter
  -> Streamlit pages, CSV outputs, Excel workbook
```

## Runtime Startup

`app.py` is the application entry point. At import/startup it:

- Sets Streamlit page config.
- Ensures `data/`, `data/master/`, `data/item-wise-sales/`, `data/stock/`, `data/runs/`, and `data/stores/` exist.
- Ensures `data/master/stores.csv` exists and creates `STORE-0001 / Main Store` when no store exists.
- Copies old single-store sales and stock files into the default FY/store input folders on first run.
- Ensures global supplier/category CSVs exist under `data/master/`.
- Ensures store-specific master files under `data/stores/{STORE_ID}/` and run directories under `data/runs/{STORE_ID}/`.
- Loads the selected store's latest saved result into session state if available.
- Builds the sidebar navigation and renders the selected page.

## Application Layers

| Layer | Files | Responsibility |
| --- | --- | --- |
| Streamlit UI | `app.py` | Page rendering, sidebar navigation, data editors, session state, user actions |
| Store master | `src/store_manager.py` | Store creation, editing, activation, store folders, `store.json` |
| File persistence | `src/file_manager.py` | Save uploads, locate store stock/sales files, ensure data folders, migrate old data |
| Input mapping | `src/column_mapper.py` | Detect likely source columns and required fields |
| Input cleaning | `src/cleaner.py`, `src/data_loader.py` | Normalize raw CSV files into consistent sales and stock tables |
| Analysis | `src/sales_analysis.py`, `src/trend_analysis.py`, `src/stock_analysis.py` | Velocity, consistency, trend, and stock coverage |
| Master data | `src/master_data_manager.py` | Suppliers, categories, item mappings, discontinued items, enrichment, master warnings |
| PO engine | `src/po_calculator.py` | Target cover, relevant velocity, PO requirement, box rounding, stock risk, priority, budget controls |
| Reporting | `src/recommendations.py`, `src/excel_exporter.py` | Executive summary, recommendations, supplier PO, category summary, Excel workbook |
| Results | `src/result_store.py` | Save every analysis run, maintain `latest`, load/delete/copy historical runs |
| Debugging | `src/debug_tools.py`, `src/item_lookup.py`, `scripts/debug_item_velocity.py` | Search and explain item-level velocity calculations |

## Streamlit Navigation

The sidebar defines these sections:

| Section | Pages |
| --- | --- |
| Dashboard | Executive Summary, Business Recommendations |
| Stores | Manage Stores, Store Data Status |
| Item-wise Sales | View Sales, Upload Sales |
| Stock | View Stock, Upload Stock, Bulk Item Update |
| Categories | View Categories, Add Category, Item Category Mapping, Bulk Category Assignment |
| Purchase Planning | Run Analysis, Detailed Item Analysis, Optimized PO, Supplier Ready PO, Overstock / Dead Stock |
| Suppliers | View Suppliers, Supplier Item Mapping, Bulk Supplier Assignment |
| Discontinued Items | View Discontinued, Bulk Mark Discontinued |
| Result History | View Runs, Load Run, Delete Runs |
| Reports | Excel Export, Data Validation, Velocity Analysis, Trend Analysis, Stock Risk |
| Settings | Analysis Settings, Data File Status |

## Important Concepts

### Item Key

Most joins and mappings are keyed by `Item Key`.

`Item Key` is built from `Item Code / SKU` when available. If item code is missing, the normalized item name is used as the fallback key. Text normalization trims whitespace, uppercases values, and collapses repeated spaces.

### Quantity-First Planning

The planning engine uses sales quantity as the primary metric. Sales amount is retained for reporting and purchase-value calculations, but it does not drive velocity or reorder quantity.

### Master Data Overrides

Global master files under `data/master/` define stores, suppliers, and categories. Store-specific master files under `data/stores/{STORE_ID}/master/` override or enrich raw input data for that store:

- Item-to-category mappings determine category name and category box quantity.
- Item-to-supplier mappings determine assigned supplier.
- Discontinued item flags force purchase quantity to zero.
- Category box quantity can override item pack size and edge-band detection for rounding.

### Result Runs

Every analysis run gets a generated ID like `RUN-20260629-085058`. The run is saved under:

```text
data/runs/{STORE_ID}/{RUN_ID}/
```

Each run keeps its input snapshots and output files:

```text
data/runs/{STORE_ID}/{RUN_ID}/item-wise-sales/{FY}/item-wise-sales.csv
data/runs/{STORE_ID}/{RUN_ID}/stock/stock.csv
data/runs/{STORE_ID}/{RUN_ID}/result/
```

The app can load the selected store's latest result automatically from `data/runs/{STORE_ID}/latest/result/` and can load or delete historical runs for that store from the Result History pages.

## Current Data Snapshot

At the time this documentation was written, the repository contained:

- 1 stock file with 247 rows.
- 4 sales FY files: `22-23`, `23-24`, `24-25`, and `26-27`.
- 25 category rows.
- 1 supplier row.
- 254 item-supplier mappings.
- 8 item-category mappings.
- 4 discontinued-item rows.
- A latest result run, `RUN-20260629-085058`, with 270 analyzed items and 10 optimized PO rows.

These values describe the checked-in data snapshot only. They will change as new files are uploaded and new runs are saved.
