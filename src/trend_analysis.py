from __future__ import annotations

import numpy as np
import pandas as pd


def analyze_trends(monthly: pd.DataFrame, mode: str = "Manual recent months", manual_recent_months: int = 6) -> pd.DataFrame:
    if monthly.empty:
        return pd.DataFrame()
    observed_months = sorted(monthly["Sales Month"].dropna().unique())
    if observed_months:
        month_periods = pd.period_range(pd.Timestamp(min(observed_months)).to_period("M"), pd.Timestamp(max(observed_months)).to_period("M"), freq="M")
        months = [period.to_timestamp() for period in month_periods]
    else:
        months = []
    if not months:
        return pd.DataFrame()
    if mode == "Manual recent months":
        recent_months = months[-max(1, manual_recent_months):]
        older_months = months[:-max(1, manual_recent_months)]
    else:
        midpoint = max(1, len(months) // 2)
        older_months = months[:midpoint]
        recent_months = months[midpoint:] or months[-1:]

    all_items = monthly[["Item Code / SKU"]].drop_duplicates()

    def avg_for(selected_months, label):
        if not selected_months:
            return all_items.assign(**{label: 0.0})
        temp = monthly[monthly["Sales Month"].isin(selected_months)].groupby("Item Code / SKU")["Sales Quantity"].sum().reset_index()
        temp[label] = temp["Sales Quantity"] / len(selected_months)
        return all_items.merge(temp[["Item Code / SKU", label]], on="Item Code / SKU", how="left").fillna({label: 0.0})

    older = avg_for(older_months, "Older Avg Monthly Sales Qty")
    recent = avg_for(recent_months, "Recent Avg Monthly Sales Qty")
    result = older.merge(recent, on="Item Code / SKU", how="outer").fillna(0)

    older_avg = result["Older Avg Monthly Sales Qty"]
    recent_avg = result["Recent Avg Monthly Sales Qty"]
    result["Trend Change %"] = np.where(older_avg > 0, ((recent_avg - older_avg) / older_avg) * 100, np.nan)
    conditions = [
        (older_avg.eq(0) & recent_avg.gt(0)),
        (older_avg.eq(0) & recent_avg.eq(0)),
        (older_avg.gt(0) & recent_avg.eq(0)),
        (result["Trend Change %"].gt(50)),
        (result["Trend Change %"].gt(20) & result["Trend Change %"].le(50)),
        (result["Trend Change %"].lt(-50)),
        (result["Trend Change %"].lt(-20) & result["Trend Change %"].ge(-50)),
    ]
    choices = ["New Moving Item", "No Sales", "Dormant Item", "Strong Upward Trend", "Upward Trend", "Strong Downward Trend", "Downward Trend"]
    result["Sales Trend"] = np.select(conditions, choices, default="Stable Trend")
    result["Older Average Monthly Sales Qty"] = result["Older Avg Monthly Sales Qty"]
    result["Recent Average Monthly Sales Qty"] = result["Recent Avg Monthly Sales Qty"]
    return result
