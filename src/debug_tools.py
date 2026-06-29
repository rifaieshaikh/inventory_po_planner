from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .column_mapper import detect_columns, quantity_candidate_columns
from .cleaner import choose_sales_quantity_column
from .data_loader import read_csv_flexible
from .file_manager import get_sales_year_from_path
from .utils import normalize_text


def _match_item(series: pd.Series, query: str) -> pd.Series:
    q = normalize_text(query)
    compact_q = re.sub(r"[^A-Z0-9]+", "", q)
    values = series.fillna("").astype(str).map(normalize_text)
    compact_values = values.map(lambda x: re.sub(r"[^A-Z0-9]+", "", x))
    return values.str.contains(re.escape(q), na=False) | compact_values.str.contains(re.escape(compact_q), na=False)


def raw_sales_debug(paths: list[Path], query: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    maps = []
    for path in paths:
        fy = get_sales_year_from_path(path)
        raw = read_csv_flexible(path)
        mapping = detect_columns(raw.columns, "sales")
        selected_qty = choose_sales_quantity_column(raw, mapping)
        item_col = mapping.get("item_name")
        matched = raw[_match_item(raw[item_col], query)] if item_col else raw.head(0)
        maps.append(
            {
                "FY": fy,
                "File": str(path),
                "Selected Quantity Column": selected_qty,
                "Selected Amount Column": mapping.get("sales_amount"),
                "Quantity Candidates": ", ".join(quantity_candidate_columns(raw.columns)),
                "Matched Raw Rows": len(matched),
            }
        )
        if not matched.empty:
            temp = matched.copy()
            temp.insert(0, "FY", fy)
            temp.insert(1, "Source File", str(path))
            rows.append(temp)
    raw_rows = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return raw_rows, pd.DataFrame(maps)


def item_debug_report(
    query: str,
    sales_paths: list[Path],
    cleaned_sales: pd.DataFrame,
    monthly: pd.DataFrame,
    detail: pd.DataFrame,
    stock: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    raw_rows, mapping_rows = raw_sales_debug(sales_paths, query)
    clean_mask = _match_item(cleaned_sales["Item Name"], query) | _match_item(cleaned_sales["Item Code / SKU"], query)
    clean_rows = cleaned_sales[clean_mask].copy()
    keys = set(clean_rows["Item Code / SKU"].dropna().astype(str))
    monthly_rows = monthly[monthly["Item Code / SKU"].astype(str).isin(keys)].copy() if keys else monthly.head(0).copy()
    detail_rows = detail[detail["Item Code / SKU"].astype(str).isin(keys)].copy() if keys else detail.head(0).copy()
    stock_rows = stock[stock["Item Code / SKU"].astype(str).isin(keys)].copy() if keys else stock.head(0).copy()

    fy_totals = clean_rows.groupby("FY", dropna=False)["Sales Quantity"].sum().reset_index(name="Total Sales Qty") if not clean_rows.empty else pd.DataFrame(columns=["FY", "Total Sales Qty"])
    month_totals = clean_rows.groupby("Sales Month", dropna=False)["Sales Quantity"].sum().reset_index(name="Total Sales Qty") if not clean_rows.empty else pd.DataFrame(columns=["Sales Month", "Total Sales Qty"])

    debug_cols = [
        "Item Code / SKU",
        "Item Name",
        "Total Sales Qty",
        "Recent Period Sales Qty",
        "Overall Monthly Velocity Qty",
        "Recent Monthly Velocity Qty",
        "Weighted Velocity Qty",
        "Relevant Velocity Qty",
        "Older Avg Monthly Sales Qty",
        "Recent Avg Monthly Sales Qty",
        "Current Stock Qty",
        "Final PO Quantity",
    ]
    return {
        "Selected Columns": mapping_rows,
        "Matched Raw Sales Rows": raw_rows,
        "Matched Cleaned Sales Rows": clean_rows,
        "Total Sales Quantity By FY": fy_totals,
        "Total Sales Quantity By Month": month_totals,
        "Monthly Aggregates": monthly_rows,
        "Calculated Velocity": detail_rows[[c for c in debug_cols if c in detail_rows.columns]],
        "Matched Stock Rows": stock_rows,
    }
