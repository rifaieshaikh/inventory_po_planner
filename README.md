# Inventory PO Planner

Inventory PO Planner is a small Streamlit app for quantity-based inventory planning, sales trend analysis, stock coverage review, and supplier-ready purchase order generation.

## Folder Structure

```text
inventory_po_planner/
  app.py
  requirements.txt
  README.md
  data/
    item-wise-sales/{FY}/item-wise-sales.csv
    stock/stock.csv
    exports/inventory_report.xlsx
  src/
```

## Upload Stock File

Use the sidebar **Upload Stock File** section to upload one CSV. Click **Save / Replace Stock File**. The app always stores it as:

```text
data/stock/stock.csv
```

Uploading a new stock file replaces the existing file.

## Upload Item-wise Sales File By FY

Use the sidebar **Upload Item-wise Sales File** section, choose the financial year, upload one CSV, and click **Save / Replace Sales File for FY**.

Sales files are always stored as:

```text
data/item-wise-sales/{FY}/item-wise-sales.csv
```

For example:

```text
data/item-wise-sales/26-27/item-wise-sales.csv
```

Only one sales file exists per FY. Uploading a new file for the same FY replaces the previous file.

## Run Analysis

The app works from files already saved in the `data/` folder, even if nothing is uploaded in the current session.

1. Confirm `data/stock/stock.csv` is available.
2. Confirm at least one FY sales file is available.
3. Select the FYs to include.
4. Adjust planning settings in the sidebar.
5. Click **Run Analysis**.

The planning logic is based mainly on sales quantity, not sales amount. Dead-stock and no-recent-sales items are not reordered by default.

## Download Excel Report

After analysis, click **Download Excel Report**. The workbook is generated at:

```text
data/exports/inventory_report.xlsx
```

Workbook sheets include executive summary, validation issues, detailed item analysis, final PO, supplier-ready PO, category/size summary, business recommendations, and assumptions.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```
