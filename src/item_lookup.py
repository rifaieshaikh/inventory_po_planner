from __future__ import annotations

import re

import pandas as pd

from .utils import normalize_text


def search_items(detail: pd.DataFrame, query: str) -> pd.DataFrame:
    if detail.empty or not query.strip():
        return detail.head(0).copy()
    q = normalize_text(query)
    compact = re.sub(r"[^A-Z0-9]+", "", q)
    mask = pd.Series(False, index=detail.index)
    for col in ["Item Code / SKU", "Item Name", "Item Key"]:
        if col in detail.columns:
            values = detail[col].fillna("").astype(str).map(normalize_text)
            compact_values = values.map(lambda x: re.sub(r"[^A-Z0-9]+", "", x))
            mask |= values.str.contains(re.escape(q), na=False) | compact_values.str.contains(re.escape(compact), na=False)
    return detail[mask].copy()


def monthly_history_for_item(monthly: pd.DataFrame, item_key: str) -> pd.DataFrame:
    if monthly.empty or "Item Code / SKU" not in monthly.columns:
        return pd.DataFrame(columns=["Month", "Sales Qty"])
    key = normalize_text(item_key)
    rows = monthly[monthly["Item Code / SKU"].map(normalize_text).eq(key)].copy()
    if rows.empty and "Item Key" in monthly.columns:
        rows = monthly[monthly["Item Key"].map(normalize_text).eq(key)].copy()
    if rows.empty:
        return pd.DataFrame(columns=["Month", "Sales Qty"])
    out = rows.groupby("Sales Month", dropna=False)["Sales Quantity"].sum().reset_index()
    out = out.rename(columns={"Sales Month": "Month", "Sales Quantity": "Sales Qty"})
    return out
