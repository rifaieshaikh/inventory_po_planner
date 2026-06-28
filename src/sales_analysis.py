from __future__ import annotations

import numpy as np
import pandas as pd


def _classify_velocity(row) -> str:
    total = row["Total Sales Qty"]
    recent = row["Recent Monthly Velocity Qty"]
    weighted = row["Weighted Velocity Qty"]
    percentile = row["Velocity Percentile"]
    recent_freq = row["Recent Sales Frequency %"]
    if total <= 0:
        return "Dead Stock / No Sales"
    if recent <= 0:
        return "Dormant"
    if percentile >= 90 and recent_freq >= 50:
        return "Very Fast Moving"
    if percentile >= 75:
        return "Fast Moving"
    if percentile >= 40 and weighted > 0:
        return "Medium Moving"
    return "Slow Moving"


def _classify_consistency(row) -> str:
    if row["Recent Monthly Velocity Qty"] <= 0 and row["Total Sales Qty"] > 0:
        return "Dormant"
    if row["Months With Sales"] <= 1 and row["Total Sales Qty"] > 0:
        return "One-time Sale"
    if row["Sales CV"] <= 0.75 and row["Sales Frequency %"] >= 60:
        return "Consistent"
    if row["Sales CV"] <= 1.25:
        return "Moderate"
    return "Irregular"


def analyze_sales(sales: pd.DataFrame, recent_period_months: int = 6) -> tuple[pd.DataFrame, pd.DataFrame]:
    if sales.empty:
        return pd.DataFrame(), pd.DataFrame()
    monthly = (
        sales.groupby(["Item Code / SKU", "Item Name", "Normalized Item Name", "Category / Size / Type", "Sales Month"], dropna=False)
        .agg({"Sales Quantity": "sum", "Sales Amount": "sum"})
        .reset_index()
    )
    observed_months = sorted(monthly["Sales Month"].dropna().unique())
    if observed_months:
        month_periods = pd.period_range(pd.Timestamp(min(observed_months)).to_period("M"), pd.Timestamp(max(observed_months)).to_period("M"), freq="M")
        months = [period.to_timestamp() for period in month_periods]
    else:
        months = []
    months_total = max(1, len(months))
    recent_period_months = max(1, min(int(recent_period_months or 6), months_total))
    recent_months = months[-recent_period_months:]
    weekly_available = sales["Sales Date"].notna().any()
    days = max(1, (sales["Sales Date"].max() - sales["Sales Date"].min()).days) if weekly_available else 0
    weeks = max(1, days / 7) if weekly_available else 0

    item_cols = ["Item Code / SKU", "Item Name", "Normalized Item Name", "Category / Size / Type"]
    item_index = monthly[item_cols].drop_duplicates()
    month_index = pd.DataFrame({"Sales Month": months})
    full_monthly = item_index.merge(month_index, how="cross").merge(monthly, on=item_cols + ["Sales Month"], how="left")
    full_monthly["Sales Quantity"] = full_monthly["Sales Quantity"].fillna(0)
    full_monthly["Sales Amount"] = full_monthly["Sales Amount"].fillna(0)

    grouped = full_monthly.groupby(item_cols, dropna=False)
    result = grouped.agg(
        **{
            "Total Sales Qty": ("Sales Quantity", "sum"),
            "Months With Sales": ("Sales Quantity", lambda x: int((x > 0).sum())),
            "Last Sale Month": ("Sales Month", "max"),
            "Monthly Sales Std Dev": ("Sales Quantity", "std"),
        }
    ).reset_index()
    result["Number of Sales Months"] = months_total
    result["Average Monthly Sales Qty"] = result["Total Sales Qty"] / months_total
    result["Overall Monthly Velocity Qty"] = result["Average Monthly Sales Qty"]
    result["Average Weekly Sales Qty"] = result["Total Sales Qty"] / weeks if weekly_available else 0
    result["Sales Consistency %"] = (result["Months With Sales"] / months_total * 100).round(2)
    result["Sales Frequency %"] = result["Sales Consistency %"]
    result["Monthly Sales Std Dev"] = result["Monthly Sales Std Dev"].fillna(0)
    result["Sales CV"] = np.where(result["Average Monthly Sales Qty"].gt(0), result["Monthly Sales Std Dev"] / result["Average Monthly Sales Qty"], 0)

    recent = full_monthly[full_monthly["Sales Month"].isin(recent_months)]
    recent_summary = recent.groupby("Item Code / SKU").agg(
        **{
            "Recent Period Sales Qty": ("Sales Quantity", "sum"),
            "Recent Months With Sales": ("Sales Quantity", lambda x: int((x > 0).sum())),
        }
    ).reset_index()
    result = result.merge(recent_summary, on="Item Code / SKU", how="left").fillna({"Recent Period Sales Qty": 0, "Recent Months With Sales": 0})
    result["Recent Period Months"] = recent_period_months
    result["Recent Monthly Velocity Qty"] = result["Recent Period Sales Qty"] / recent_period_months
    result["Recent Sales Frequency %"] = result["Recent Months With Sales"] / recent_period_months * 100
    result["Weighted Velocity Qty"] = (result["Recent Monthly Velocity Qty"] * 0.7) + (result["Overall Monthly Velocity Qty"] * 0.3)
    result["Velocity Percentile"] = 0.0
    active_mask = result["Weighted Velocity Qty"].gt(0)
    result.loc[active_mask, "Velocity Percentile"] = result.loc[active_mask, "Weighted Velocity Qty"].rank(pct=True) * 100
    result["Velocity Class"] = result.apply(_classify_velocity, axis=1)
    result["Movement Category"] = result["Velocity Class"]
    result["Consistency Class"] = result.apply(_classify_consistency, axis=1)
    return result, full_monthly
