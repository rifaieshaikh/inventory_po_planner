from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import safe_divide


def merge_stock_sales(sales_summary: pd.DataFrame, trend: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    keys = ["Item Code / SKU"]
    base = stock.merge(sales_summary, on=keys, how="outer", suffixes=("_stock", "_sales"))
    if not trend.empty:
        base = base.merge(trend, on="Item Code / SKU", how="left")

    for col in ["Item Name", "Normalized Item Name", "Category / Size / Type"]:
        stock_col = f"{col}_stock"
        sales_col = f"{col}_sales"
        if stock_col in base.columns or sales_col in base.columns:
            base[col] = base.get(stock_col, pd.Series(index=base.index, dtype=object)).fillna(base.get(sales_col, ""))

    defaults = {
        "Current Stock Qty": 0,
        "Purchase Price": 0,
        "Supplier Name": "Unknown Supplier",
        "Box / Pack Quantity": np.nan,
        "Unit": "Qty",
        "Total Sales Qty": 0,
        "Average Monthly Sales Qty": 0,
        "Overall Monthly Velocity Qty": 0,
        "Recent Monthly Velocity Qty": 0,
        "Weighted Velocity Qty": 0,
        "Sales Frequency %": 0,
        "Recent Sales Frequency %": 0,
        "Velocity Percentile": 0,
        "Velocity Class": "Dead Stock / No Sales",
        "Monthly Sales Std Dev": 0,
        "Sales CV": 0,
        "Consistency Class": "Irregular",
        "Average Weekly Sales Qty": 0,
        "Months With Sales": 0,
        "Sales Consistency %": 0,
        "Older Avg Monthly Sales Qty": 0,
        "Recent Avg Monthly Sales Qty": 0,
        "Older Average Monthly Sales Qty": 0,
        "Recent Average Monthly Sales Qty": 0,
        "Trend Change %": 0,
        "Sales Trend": "No Sales",
    }
    for col, default in defaults.items():
        if col not in base.columns:
            base[col] = default
        base[col] = base[col].fillna(default)

    base["Stock Coverage Months"] = [
        safe_divide(stock_qty, avg_qty) if avg_qty > 0 else np.nan
        for stock_qty, avg_qty in zip(base["Current Stock Qty"], base["Overall Monthly Velocity Qty"])
    ]
    base["Recent Stock Coverage Months"] = [
        safe_divide(stock_qty, avg_qty) if avg_qty > 0 else np.nan
        for stock_qty, avg_qty in zip(base["Current Stock Qty"], base["Recent Monthly Velocity Qty"])
    ]
    base["Movement Category"] = base["Velocity Class"]
    return base
