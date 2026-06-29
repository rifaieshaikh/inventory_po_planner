# Developer Guide

This guide maps the codebase for maintainers.

## Entry Point

Run the app with:

```bash
streamlit run app.py
```

`app.py` owns:

- Streamlit page config.
- Directory initialization.
- Store initialization and default-store migration.
- Master-data initialization.
- Result-history initialization.
- Session-state report loading.
- Sidebar navigation.
- All page render functions.
- The `build_report` orchestration function.

## Module Map

| File | Key Functions | Notes |
| --- | --- | --- |
| `src/utils.py` | `normalize_text`, `build_item_key`, `safe_divide`, `ceil_to_multiple`, `ensure_required_output_columns` | Shared paths, sort orders, defaults |
| `src/store_manager.py` | `create_default_store_if_missing`, `add_store`, `update_store`, `deactivate_store`, `reactivate_store` | Store master, IDs, folders, `store.json` |
| `src/file_manager.py` | `ensure_store_dirs`, `save_sales_file`, `save_stock_file`, `list_available_sales_years`, `get_sales_file_paths`, `get_stock_file_path`, `migrate_single_store_data_to_default_store` | Store-aware filesystem contract for uploads and migration |
| `src/column_mapper.py` | `detect_columns`, `missing_required`, `validate_sales_quantity_column`, `quantity_candidate_columns` | Source CSV field detection |
| `src/cleaner.py` | `clean_sales`, `clean_stock`, `choose_sales_quantity_column` | Raw-to-normalized dataframe conversion |
| `src/data_loader.py` | `read_csv_flexible`, `load_sales_files`, `load_stock_file` | CSV reading with encoding fallback |
| `src/sales_analysis.py` | `analyze_sales` | Monthly grid, velocity, consistency |
| `src/trend_analysis.py` | `analyze_trends` | Older-vs-recent trend classification |
| `src/stock_analysis.py` | `merge_stock_sales` | Outer merge and stock coverage |
| `src/master_data_manager.py` | `ensure_master_files`, `enrich_with_master_data`, `master_validation_warnings`, supplier/category/discontinued setters | Master CSV lifecycle and enrichment |
| `src/po_calculator.py` | `calculate_po`, `apply_discontinued_po_rules` | PO engine |
| `src/recommendations.py` | `build_executive_summary`, `supplier_ready_po`, `category_size_summary`, `business_recommendations` | Business-facing outputs |
| `src/result_store.py` | `save_analysis_result`, `load_latest_result`, `load_result`, `list_result_runs`, `delete_result` | Result persistence |
| `src/excel_exporter.py` | `export_excel` | Workbook writer |
| `src/validator.py` | `validate_data`, `validate_velocity_calculations` | Data-quality checks |
| `src/debug_tools.py` | `item_debug_report`, `raw_sales_debug` | Per-item explainability |
| `src/item_lookup.py` | `search_items`, `monthly_history_for_item` | Item search and chart data |
| `src/edge_band_rules.py` | `detect_edge_band_size` | Edge-band size to box-quantity rules |

## Report Orchestration

`build_report` in `app.py` is the central flow:

```text
active store selection
store-specific load_stock_file
store-specific load_sales_files
validate_data
analyze_sales
analyze_trends
merge_stock_sales
ensure_required_output_columns
mdm.enrich_with_master_data
calculate_po
apply_discontinued_po_rules
validate_velocity_calculations
mdm.master_validation_warnings
build_executive_summary
supplier_ready_po
category_size_summary
business_recommendations
return report dict
```

The report dictionary is the contract between the analysis layer, UI pages, result storage, and Excel export.

## Session State

Important session keys:

| Key | Meaning |
| --- | --- |
| `report` | Active report dictionary |
| `report_store_id` | Store ID for the active report |
| `active_store_id` | Selected store ID |
| `active_store_name` | Selected store name |
| `active_run_id` | Active run ID |
| `active_result_source` | `latest`, `new_run`, or loaded history source |
| `active_manifest` | Manifest for active result |
| `active_result_path` | Filesystem path for active result |
| `export_path` | Excel workbook path |
| `nav_active_menu` | Active sidebar section |
| `nav_active_page` | Active page within section |
| `nav_expanded_menu` | Expanded sidebar section |
| `supplier_ready_po_edited_df` | Edited supplier PO table in memory |

Most widget keys are built through `widget_key(section, name, suffix)` to avoid collisions.

## Adding A New Input Field

1. Add aliases to `FIELD_ALIASES` in `src/column_mapper.py`.
2. Include the logical field in `detect_columns`.
3. Add any required-field behavior in `missing_required`.
4. Read and normalize the field in `clean_sales` or `clean_stock`.
5. Add defaults to `ensure_required_output_columns` if downstream outputs need the column.
6. Update docs in `docs/DATA_AND_OUTPUTS.md`.

## Adding A New Output Column

1. Calculate the column in the relevant analysis module.
2. Add a default in `ensure_required_output_columns` if it should be stable in outputs.
3. Add it to `DETAIL_COLUMNS` or `FINAL_PO_COLUMNS` in `app.py` if it should appear in those tables.
4. Update focused report slices in `build_report` if needed.
5. Update `docs/DATA_AND_OUTPUTS.md` and `docs/ANALYSIS_LOGIC.md`.

## Adding A New Result File

1. Add the report dataframe to the dictionary returned by `build_report`.
2. Add a mapping in `CSV_MAPPING` or `TEXT_MAPPING` in `src/result_store.py`.
3. Confirm `excel_exporter.export_excel` should include it. It will include any dataframe report key unless the key starts with `_`.
4. Add a UI page or download flow if users need to view it directly.
5. Update `docs/DATA_AND_OUTPUTS.md`.

## Adding A New Streamlit Page

1. Add a render function in `app.py`.
2. Add the page name under the relevant `NAV_ITEMS` section.
3. Add a branch in the final page router.
4. Use `report_or_warning()` or explicit checks when the page requires an active report.
5. Use `widget_key` for every widget key.

## Master Data Rules

Master files should be treated as persistent user-managed state. Global suppliers/categories/stores live under `data/master/`. Store-specific discontinued, item-supplier, and item-category mappings live under `data/stores/{STORE_ID}/master/`. Avoid replacing or regenerating them during analysis except for intentional behavior already present in `master_data_manager.py`, such as:

- Ensuring the `Uncategorized` category exists.
- Adding missing uncategorized item-category rows during enrichment.
- Updating selected items through UI actions.

When editing master-data behavior, preserve user changes and avoid destructive rewrites.

## Result Storage Rules

`save_analysis_result(store_id, ...)` writes a new run directory under `data/stores/{STORE_ID}/results/history/` and then copies that directory to that store's `results/latest/`.

Historical run IDs are validated before load/delete/copy:

- Must start with `RUN-`.
- Must not contain `/`, `\`, or `..`.

Deletion resolves paths under the selected store's history directory before removing them.

## Debugging

### Compile Check

Run:

```bash
python -m compileall app.py src scripts
```

### Debug One Item

Run:

```bash
python scripts/debug_item_velocity.py "ITEM NAME OR SKU"
```

The script prints:

- Selected source columns
- Matched raw sales rows
- Matched cleaned sales rows
- Total sales by FY
- Total sales by month
- Monthly aggregates
- Calculated velocity fields
- Matched stock rows

### Inspect Saved Runs

Saved run folders are under:

```text
data/stores/{STORE_ID}/results/history/
```

Each run has a `manifest.json`. The current active latest run is copied to:

```text
data/stores/{STORE_ID}/results/latest/
```

## Known Caveats

- There is no automated test suite in the repository at the time this guide was written.
- The UI and orchestration are concentrated in `app.py`, which is large. Keep new analysis logic in `src/` modules where possible.
- Some source CSVs may contain duplicate headers. Pandas can load them, but manual mapping should still be reviewed.
- Sales files without dates are assigned a fallback month based on FY, which limits trend accuracy.
- Missing item codes use normalized item names as keys. This is practical but can merge distinct items with identical names.
- Budget optimization is greedy, not a global optimization solver.

## Development Checklist

Before handing off changes:

1. Run `python -m compileall app.py src scripts`.
2. If analysis logic changed, run the Streamlit app and create a new analysis result from the UI.
3. Inspect Data Validation and Velocity Calculation Warnings.
4. Check `data/stores/{STORE_ID}/results/latest/manifest.json`.
5. Download or regenerate the Excel workbook from Reports / Excel Export.
6. Update documentation when behavior or file contracts change.
