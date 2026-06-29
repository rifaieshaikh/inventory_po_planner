# User Guide

This guide explains how to operate Inventory PO Planner from the Streamlit UI.

## Start The App

Install dependencies:

```bash
pip install -r requirements.txt
```

Run Streamlit:

```bash
streamlit run app.py
```

Use the URL printed by Streamlit.

## Prepare Input Files

The app can work from files already saved in the selected FY/store input folders, even if nothing is uploaded during the current session. A default `STORE-0001 / Main Store` is created automatically if no stores exist.

### Store Selection

Use the sidebar store selector to choose the active store. Store-specific pages only read and write files for the selected store. Use Stores / View Stores to edit, deactivate, reactivate, or switch stores, and Stores / Add Store to create another branch.

### Stock File

Use the Stock / Upload Stock page to upload one stock CSV. The app always saves it as:

```text
data/stock/{FY}/{STORE_ID}/stock.csv
```

Uploading a new stock file replaces the existing file for the selected store only.

### Sales Files

Use Item-wise Sales / Upload Sales to upload one CSV per financial year. The app saves each file as:

```text
data/itemwisesales/{FY}/{STORE_ID}/itemwisesales.csv
```

Example:

```text
data/itemwisesales/26-27/STORE-0001/itemwisesales.csv
```

Uploading a new file for the same store and FY replaces that store/FY's previous file.

## First Analysis Run

1. Select the store from the sidebar.
2. Open Stores / Store Data Status or Settings / Data File Status and confirm stock and sales files exist for that store.
3. Open Categories / View Categories and check global category box quantities.
4. Open Suppliers / View Suppliers and add or edit global supplier records if needed.
5. Use Supplier Item Mapping or Bulk Supplier Assignment to assign suppliers for the selected store.
6. Use Item Category Mapping or Bulk Category Assignment to assign categories for the selected store.
7. Use Discontinued Items / Bulk Mark Discontinued to block selected-store items that should not be reordered.
8. Open Purchase Planning / Run Analysis.
9. Select the FYs to include.
10. Review the column mappings shown for stock and sales files.
11. Click Run Analysis.

After the run finishes, the app saves a historical result and refreshes the active report.

## Column Mapping

On Run Analysis, the app shows detected mappings for each input file. Review these carefully, especially:

- Sales quantity: should point to a quantity column, not amount or value.
- Item name: required for both sales and stock.
- Stock quantity: required for stock.
- Purchase price: required for stock.

If a source CSV contains duplicate or ambiguous headers, verify the mapping before running analysis.

## Analysis Settings

Settings live under Settings / Analysis Settings.

| Setting | What It Controls |
| --- | --- |
| Recent period months | Number of latest months used for recent velocity |
| Very fast upward target cover | Target cover for very fast items with upward movement |
| Fast stable target cover | Target cover for fast stable items |
| Medium stable target cover | Target cover for medium stable items |
| Slow stable target cover | Target cover for slow stable items |
| Recent period mode | Manual recent months or auto split period in half |
| Enable budget optimization | Whether PO lines are approved/deferred against a budget |
| Purchase budget amount | Maximum total PO value when budget optimization is enabled |
| Allow excess box rounding for fast items | Whether rounded fast-item PO can create extra cover |
| Allow excess box rounding for slow items | Whether rounded slow-item PO can create extra cover |
| Skip slow items if rounded PO creates excess cover | Avoid slow-item purchases that become excessive after rounding |
| Exclude dormant/dead items | Force dormant and no-sales items to no purchase |
| Apply edge band box rounding | Round PO quantities to category, pack, or edge-band box quantities |
| Minimum purchase value filter | Remove PO lines below the minimum purchase value |
| Debug Item Name / SKU | Item query used by the debug velocity page |

## Main Pages

### Dashboard

Executive Summary shows key metrics from the active result. Business Recommendations turns the analysis into purchase-manager guidance such as order immediately, do not order, monitor, reduce purchase, and budget control.

### Item-wise Sales

View Sales lets you inspect cleaned sales rows, filter by FY, month, item text, and category, and see top items by quantity. Upload Sales saves or replaces a source sales CSV for a selected FY.

### Stock

View Stock shows current stock enriched with category, supplier, discontinued, velocity, risk, and PO fields when a report exists. Upload Stock replaces `data/stock/{FY}/{STORE_ID}/stock.csv` for the selected store and FY. Bulk Item Update routes to the discontinued bulk workflow.

### Categories

Use this section to manage category records and item-to-category mappings. Category box quantity is important because it is the first source used for PO box rounding.

### Purchase Planning

Run Analysis is the main orchestration page. Detailed Item Analysis contains the full per-item calculation output. Optimized PO contains purchase lines with final PO quantity greater than zero. Supplier Ready PO groups PO rows by supplier and lets you edit quantity before downloading a supplier-facing CSV. Overstock / Dead Stock highlights items to avoid or review.

### Suppliers

View Suppliers manages the supplier master. Supplier Item Mapping shows current item assignments. Bulk Supplier Assignment applies supplier mappings to selected items.

### Discontinued Items

Use Bulk Mark Discontinued to mark selected items as discontinued or remove discontinued status. Discontinued items are forced to zero PO quantity during analysis.

### Result History

Use this section to inspect past runs, load an old run as the active result, or delete saved runs. The app also supports keeping the latest result while deleting older historical runs.

### Reports

Excel Export creates or downloads the workbook for the active result. Data Validation lists input and master-data warnings. Velocity Analysis, Trend Analysis, and Stock Risk expose focused analysis tables.

### Settings

Analysis Settings controls the algorithm settings. Data File Status lists the stock, sales, and master-data files and their last modified times.

## Everyday Workflows

### Replace Stock

1. Open Stock / Upload Stock.
2. Upload a CSV.
3. Click Save / Replace Stock File.
4. Run analysis again.

### Replace One FY Sales File

1. Open Item-wise Sales / Upload Sales.
2. Select the FY.
3. Upload the CSV.
4. Click Save / Replace Sales File.
5. Run analysis again.

### Assign Categories In Bulk

1. Run or load an analysis result.
2. Open Categories / Bulk Category Assignment.
3. Filter or search the item list.
4. Select rows.
5. Choose a category.
6. Click Assign Category to Selected Items.
7. Run analysis again if you want the PO to use the updated mappings.

### Assign Suppliers In Bulk

1. Run or load an analysis result.
2. Open Suppliers / Bulk Supplier Assignment.
3. Filter to items without suppliers if desired.
4. Select rows.
5. Choose a supplier.
6. Click Assign Supplier to Selected Items.
7. Run analysis again if you want the PO to use the updated mappings.

### Mark Discontinued Items

1. Run or load an analysis result.
2. Open Discontinued Items / Bulk Mark Discontinued.
3. Select rows.
4. Enter a reason if needed.
5. Click Mark Selected as Discontinued.
6. Run analysis again to force those items out of the PO.

### Review And Export PO

1. Open Purchase Planning / Optimized PO.
2. Filter by priority or supplier.
3. Inspect individual PO items if needed.
4. Open Purchase Planning / Supplier Ready PO.
5. Edit quantities if needed.
6. Save or download the edited supplier PO.
7. Open Reports / Excel Export to download the full workbook.

## Debug One Item

In Settings / Analysis Settings, enter an item name or SKU into Debug Item Name / SKU. After a report is active, the app shows debug tables at the bottom of the page. These include selected source columns, matched raw rows, cleaned rows, FY totals, monthly totals, velocity fields, and stock rows.

You can also run the CLI helper:

```bash
python scripts/debug_item_velocity.py "ITEM NAME OR SKU"
```

## Troubleshooting

| Symptom | What To Check |
| --- | --- |
| Run Analysis is disabled | Confirm stock and at least one sales FY file exist |
| Quantity looks too high or too low | Review sales quantity column mapping |
| Items grouped under Unknown Supplier | Add suppliers and item-supplier mappings |
| Too many Uncategorized items | Add category mappings and category box quantities |
| PO lines look too large | Check box rounding, category box quantity, and max cover behavior |
| Dormant items still appear in analysis | They remain in detailed analysis, but final PO should be zero |
| Discontinued item appears in stock | Existing stock can appear, but final PO is forced to zero |
| Excel file is missing | Open Reports / Excel Export; the app regenerates it for the active result |
