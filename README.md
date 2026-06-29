# Inventory PO Planner

Inventory PO Planner is a Streamlit application for multi-store, quantity-based inventory planning. It reads each store's stock and item-wise sales CSV files, analyzes sales velocity and stock coverage, applies master-data rules for suppliers, categories, box quantities, discontinued items, and item mappings, then produces store-specific optimized purchase orders and supplier-ready reports.

The app is built for purchase planning where reorder decisions should be driven primarily by sold quantity and stock cover, not by sales amount.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the Streamlit URL shown in the terminal.

## Main Workflow

1. Select or create a store from the sidebar.
2. Upload or place the store stock file at `data/stock/{FY}/{STORE_ID}/stock.csv`.
3. Upload or place store sales files at `data/itemwisesales/{FY}/{STORE_ID}/itemwisesales.csv`.
4. Review or adjust column mappings on the Run Analysis page.
5. Maintain global categories/suppliers and store-specific item mappings/discontinued flags.
6. Run analysis for the selected store.
7. Review that store's dashboard, detailed item analysis, optimized PO, and supplier-ready PO.
8. Export the store-specific Excel workbook or CSV result files.

## Documentation

- [Project Overview](docs/PROJECT_OVERVIEW.md) explains the architecture, runtime flow, navigation model, and major components.
- [User Guide](docs/USER_GUIDE.md) explains how to operate the app day to day.
- [Data And Outputs](docs/DATA_AND_OUTPUTS.md) documents input files, master files, result files, normalized schemas, and output contracts.
- [Analysis Logic](docs/ANALYSIS_LOGIC.md) documents the formulas and decision rules used for velocity, trends, stock risk, PO calculation, rounding, budget optimization, and validation.
- [Developer Guide](docs/DEVELOPER_GUIDE.md) maps the codebase for future development and debugging.

## Repository Layout

```text
inventory_po_planner/
  app.py                         Streamlit UI and orchestration
  requirements.txt               Python dependencies
  README.md                      Project entry point
  docs/                          Project documentation
  scripts/
    debug_item_velocity.py       CLI debug helper for one item
  src/
    column_mapper.py             Input column auto-detection
    cleaner.py                   Sales and stock normalization
    data_loader.py               CSV loading and cleaning
    file_manager.py              Data folder and upload persistence
    store_manager.py             Store master and store folder lifecycle
    sales_analysis.py            Velocity and consistency analysis
    trend_analysis.py            Recent-vs-older trend analysis
    stock_analysis.py            Stock and sales merge
    master_data_manager.py       Suppliers, categories, discontinued items
    po_calculator.py             Purchase-order calculation
    recommendations.py           Summaries and business recommendations
    result_store.py              Result history and latest run persistence
    excel_exporter.py            Excel workbook export
    validator.py                 Data and velocity validation
    debug_tools.py               Per-item debugging tables
    item_lookup.py               Item search and monthly history helpers
    edge_band_rules.py           Edge-band size and box quantity detection
    utils.py                     Shared constants and helpers
  data/
    master/
      stores.csv
      suppliers.csv
      categories.csv
    itemwisesales/
      26-27/
        STORE-0001/
          itemwisesales.csv
    stock/
      26-27/
        STORE-0001/
          stock.csv
    stores/
      STORE-0001/
        store.json
        master/
        results/
    exports/
```

## Important Paths

- Store master: `data/master/stores.csv`
- Global suppliers/categories: `data/master/suppliers.csv`, `data/master/categories.csv`
- Store stock input: `data/stock/{FY}/{STORE_ID}/stock.csv`
- Store sales input: `data/itemwisesales/{FY}/{STORE_ID}/itemwisesales.csv`
- Store-specific item mappings: `data/stores/{STORE_ID}/master/*.csv`
- Latest saved result: `data/stores/{STORE_ID}/results/latest/`
- Historical result runs: `data/stores/{STORE_ID}/results/history/RUN-YYYYMMDD-HHMMSS/`
- Excel export: `data/stores/{STORE_ID}/results/latest/inventory_report.xlsx` and each saved run's `inventory_report.xlsx`

## Requirements

The project depends on:

- Streamlit
- pandas
- openpyxl
- xlsxwriter
- plotly

Install them with:

```bash
pip install -r requirements.txt
```

## Notes

- Purchase planning is quantity-first. Sales amount is used mainly for estimated purchase value and budget controls.
- Dormant, dead-stock, and discontinued items are not reordered by default.
- Box rounding uses category box quantity first, then stock pack size, then detected edge-band rules.
- Every analysis run is saved to the selected store's history and copied to that store's `results/latest/`.
- Existing single-store files are copied into `STORE-0001 / Main Store` on first run so older data remains usable.
