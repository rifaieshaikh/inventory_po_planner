from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import ceil_to_multiple, join_reasons


MAX_COVER_AFTER_PO = {
    "Very Fast Moving": 4.5,
    "Fast Moving": 4.5,
    "Medium Moving": 4.0,
    "Slow Moving": 2.5,
    "Dormant": 0.0,
    "Dead Stock / No Sales": 0.0,
}


def _suggested_target_cover(row, settings: dict) -> float:
    velocity = row.get("Velocity Class", row.get("Movement Category", "Dead Stock / No Sales"))
    trend = row.get("Sales Trend", "No Sales")
    consistency = row.get("Consistency Class", "Irregular")

    if velocity in {"Dormant", "Dead Stock / No Sales"} or trend in {"Dormant Item", "No Sales"}:
        return 0.0

    very_fast_upward = settings.get("very_fast_upward_months", 3.5)
    fast_stable = settings.get("fast_stable_months", 2.5)
    medium_stable = settings.get("medium_stable_months", 2.0)
    slow_stable = settings.get("slow_stable_months", 1.0)

    if velocity == "Very Fast Moving":
        if trend in {"Strong Upward Trend", "Upward Trend", "New Moving Item"}:
            return very_fast_upward
        if trend == "Stable Trend":
            return 3.0
        if trend == "Downward Trend":
            return 2.5
        if trend == "Strong Downward Trend":
            return 2.0
    if velocity == "Fast Moving":
        if trend in {"Strong Upward Trend", "Upward Trend", "New Moving Item"}:
            return 3.0
        if trend == "Stable Trend":
            return fast_stable
        if trend == "Downward Trend":
            return 2.0
        if trend == "Strong Downward Trend":
            return 1.5
    if velocity == "Medium Moving":
        if trend in {"Strong Upward Trend", "Upward Trend", "New Moving Item"}:
            return 2.5
        if trend == "Stable Trend":
            return medium_stable
        if trend == "Downward Trend":
            return 1.5
        if trend == "Strong Downward Trend":
            return 1.0
    if velocity == "Slow Moving":
        if trend in {"Strong Upward Trend", "Upward Trend", "New Moving Item"}:
            return 2.0 if consistency in {"Consistent", "Moderate"} else 1.0
        if trend == "Stable Trend":
            return slow_stable if consistency != "Irregular" else min(slow_stable, 0.75)
        if trend == "Downward Trend":
            return 0.5
        if trend == "Strong Downward Trend":
            return 0.0
    return 0.0


def _relevant_velocity(row) -> float:
    trend = row.get("Sales Trend", "No Sales")
    recent = float(row.get("Recent Monthly Velocity Qty", row.get("Recent Average Monthly Sales Qty", 0)) or 0)
    weighted = float(row.get("Weighted Velocity Qty", row.get("Average Monthly Sales Qty", 0)) or 0)
    if trend in {"Strong Upward Trend", "Upward Trend", "New Moving Item"}:
        return max(recent, weighted)
    if trend == "Stable Trend":
        return weighted
    if trend in {"Downward Trend", "Strong Downward Trend"}:
        return recent
    return 0.0


def _resolve_box_qty(row) -> tuple[float, str]:
    category_qty = float(row.get("Category Box Qty", 0) or 0)
    if category_qty > 0:
        return category_qty, "Category"
    pack_qty = float(row.get("Box / Pack Quantity", 0) or 0)
    if pack_qty > 0:
        return pack_qty, "Item Pack Size"
    detected_qty = float(row.get("Detected Box Qty", 0) or 0)
    if detected_qty > 0:
        return detected_qty, "Edge Band Rule"
    return 0.0, "Not Available"


def _stock_risk(row) -> str:
    velocity = row["Velocity Class"]
    recent_velocity = row["Recent Monthly Velocity Qty"]
    recent_cover = row["Recent Stock Coverage Months"]
    cover = row["Stock Coverage Months"]
    target = row["Suggested Target Cover Months"]
    current_stock = row["Current Stock Qty"]

    if pd.notna(cover) and ((target > 0 and cover > target * 2) or (velocity in {"Slow Moving", "Medium Moving"} and cover > 6)):
        return "Overstock Risk"
    if velocity in {"Dormant", "Dead Stock / No Sales"} and current_stock > 0:
        return "Overstock Risk"
    if velocity in {"Very Fast Moving", "Fast Moving"} and recent_velocity > 0 and (pd.isna(recent_cover) or recent_cover < 0.5):
        return "Urgent Stock Risk"
    if velocity in {"Fast Moving", "Medium Moving", "Very Fast Moving"} and (pd.isna(recent_cover) or recent_cover < 1):
        return "High Stock Risk"
    active = velocity not in {"Dormant", "Dead Stock / No Sales"}
    active_cover = recent_cover if pd.notna(recent_cover) else cover
    if active and target > 0 and (pd.isna(active_cover) or active_cover < target):
        return "Medium Stock Risk"
    return "Low Stock Risk"


def _purchase_priority(row) -> str:
    if row["Final PO Quantity"] <= 0:
        return "No Purchase"
    velocity = row["Velocity Class"]
    risk = row["Stock Risk Level"]
    recent_cover = row["Recent Stock Coverage Months"]
    trend = row["Sales Trend"]
    if velocity in {"Dormant", "Dead Stock / No Sales"}:
        return "No Purchase"
    if velocity in {"Very Fast Moving", "Fast Moving"} and risk == "Urgent Stock Risk":
        return "Urgent"
    if velocity in {"Very Fast Moving", "Fast Moving"} and risk in {"High Stock Risk", "Medium Stock Risk"}:
        return "High"
    if velocity == "Medium Moving" and (pd.isna(recent_cover) or recent_cover < 1):
        return "High"
    if velocity == "Medium Moving":
        return "Medium"
    if velocity == "Slow Moving" and trend in {"Strong Upward Trend", "Upward Trend", "New Moving Item"}:
        return "Medium"
    if velocity == "Slow Moving":
        return "Low"
    return "No Purchase"


def _budget_score(row) -> float:
    priority_score = {"Urgent": 10000, "High": 8000, "Medium": 5000, "Low": 2000, "No Purchase": 0}.get(row["Purchase Priority"], 0)
    velocity_score = {"Very Fast Moving": 3000, "Fast Moving": 2000, "Medium Moving": 1000, "Slow Moving": 300}.get(row["Velocity Class"], 0)
    overstock_penalty = 1500 if row["Stock Risk Level"] == "Overstock Risk" else 0
    value_penalty = min(float(row["Estimated Purchase Value"] or 0) / 1000, 500)
    return priority_score + velocity_score + float(row["Recent Monthly Velocity Qty"] or 0) - overstock_penalty - value_penalty


def _apply_budget(result: pd.DataFrame, settings: dict) -> pd.DataFrame:
    result["Budget Priority Score"] = result.apply(_budget_score, axis=1)
    result["Included In Budget PO"] = "Yes"
    result["Deferred Reason"] = ""
    result["Budget Approved PO Quantity"] = result["Final PO Quantity"]
    result["Budget Approved PO Value"] = result["Estimated Purchase Value"]

    if not settings.get("enable_budget_optimization", False):
        return result

    budget = float(settings.get("purchase_budget_amount") or 0)
    if budget <= 0:
        mask = result["Final PO Quantity"].gt(0)
        result.loc[mask, "Included In Budget PO"] = "No"
        result.loc[mask, "Deferred Reason"] = "Deferred due to budget limit."
        result.loc[mask, ["Budget Approved PO Quantity", "Budget Approved PO Value"]] = 0
        return result

    eligible = result.get("Is Discontinued", pd.Series("No", index=result.index)).fillna("No").astype(str).str.upper().ne("YES")
    candidates = result[result["Final PO Quantity"].gt(0) & eligible].sort_values(
        ["Budget Priority Score", "Estimated Purchase Value"], ascending=[False, True]
    )
    running = 0.0
    included_indexes = []
    for idx, row in candidates.iterrows():
        value = float(row["Estimated Purchase Value"] or 0)
        if running + value <= budget:
            running += value
            included_indexes.append(idx)
    deferred = candidates.index.difference(included_indexes)
    result.loc[deferred, "Included In Budget PO"] = "No"
    result.loc[deferred, "Deferred Reason"] = "Deferred due to budget limit."
    result.loc[deferred, ["Budget Approved PO Quantity", "Budget Approved PO Value"]] = 0
    return result


def apply_discontinued_po_rules(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if "Is Discontinued" not in result.columns:
        result["Is Discontinued"] = "No"
    discontinued_mask = (
        result["Is Discontinued"].fillna("No").astype(str).str.strip().str.upper().isin(["YES", "TRUE", "1"])
    )
    result.loc[discontinued_mask, "Suggested Target Cover Months"] = 0
    result.loc[discontinued_mask, "Target Stock Cover"] = 0
    result.loc[discontinued_mask, "Required Stock Qty"] = 0
    result.loc[discontinued_mask, "Exact Purchase Requirement Qty"] = 0
    result.loc[discontinued_mask, "Rounded PO Qty"] = 0
    result.loc[discontinued_mask, "Final PO Quantity"] = 0
    result.loc[discontinued_mask, "Estimated Purchase Value"] = 0
    result.loc[discontinued_mask, "Purchase Priority"] = "No Purchase"
    result.loc[discontinued_mask, "PO Optimization Decision"] = "Discontinued Item - Do Not Purchase"
    result.loc[discontinued_mask, "Reason for Recommendation"] = (
        "Item is marked discontinued. Do not reorder. Sell down or liquidate existing stock."
    )
    result.loc[discontinued_mask, "Reason"] = result.loc[discontinued_mask, "Reason for Recommendation"]
    if "Budget Approved PO Quantity" in result.columns:
        result.loc[discontinued_mask, "Budget Approved PO Quantity"] = 0
    if "Budget Approved PO Value" in result.columns:
        result.loc[discontinued_mask, "Budget Approved PO Value"] = 0
    if "Included In Budget PO" in result.columns:
        result.loc[discontinued_mask, "Included In Budget PO"] = "No"
    if "Deferred Reason" in result.columns:
        result.loc[discontinued_mask, "Deferred Reason"] = "Discontinued item - not eligible for purchase"
    return result


def calculate_po(df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    result = df.copy()
    if settings.get("exclude_dormant_dead", settings.get("exclude_dead_stock", True)):
        result.loc[result["Velocity Class"].isin(["Dormant", "Dead Stock / No Sales"]), "Recent Monthly Velocity Qty"] = 0

    result["Suggested Target Cover Months"] = result.apply(lambda row: _suggested_target_cover(row, settings), axis=1)
    result["Target Stock Cover"] = result["Suggested Target Cover Months"]
    result["Relevant Velocity Qty"] = result.apply(_relevant_velocity, axis=1)
    result["Relevant Sales Velocity"] = result["Relevant Velocity Qty"]
    result["Required Stock Qty"] = result["Relevant Velocity Qty"] * result["Suggested Target Cover Months"]
    result["Exact Purchase Requirement Qty"] = (result["Required Stock Qty"] - result["Current Stock Qty"]).clip(lower=0)
    if "Category Box Qty" not in result.columns:
        result["Category Box Qty"] = 0
    result["Category Box Qty"] = pd.to_numeric(result["Category Box Qty"], errors="coerce").fillna(0)

    rounded_qty = []
    rounded_boxes = []
    decisions = []
    warnings = []
    box_sources = []
    required_boxes = []
    for _, row in result.iterrows():
        exact = float(row["Exact Purchase Requirement Qty"] or 0)
        velocity = row["Velocity Class"]
        box_qty, source = _resolve_box_qty(row)
        box_sources.append(source)
        required_boxes.append(exact / box_qty if box_qty > 0 else 0.0)
        if exact <= 0 or row["Suggested Target Cover Months"] <= 0 or row["Relevant Velocity Qty"] <= 0:
            rounded_qty.append(0.0)
            rounded_boxes.append(0.0)
            decisions.append("Enough Stock / No Purchase" if exact <= 0 else "Dormant / No Purchase")
            warnings.append("")
            continue
        pack = box_qty if settings.get("apply_box_rounding", True) else np.nan
        qty = ceil_to_multiple(exact, float(pack)) if pd.notna(pack) and float(pack) > 0 else float(np.ceil(exact))
        box_count = float(np.ceil(exact / float(pack))) if pd.notna(pack) and float(pack) > 0 else 0.0
        cover_after = (float(row["Current Stock Qty"] or 0) + qty) / float(row["Relevant Velocity Qty"])
        max_cover = MAX_COVER_AFTER_PO.get(velocity, 0)
        excess = max_cover > 0 and cover_after > max_cover
        warning = "Box rounding causes excess stock." if excess and pd.notna(pack) and float(pack) > 0 else ""
        decision = "Purchase Optimized"
        if velocity in {"Dormant", "Dead Stock / No Sales"}:
            qty = 0.0
            box_count = 0.0
            decision = "Dormant / Dead / No Purchase"
        elif excess and velocity in {"Very Fast Moving", "Fast Moving"} and not settings.get("allow_excess_rounding_fast", True):
            qty = 0.0
            box_count = 0.0
            decision = "Skipped: rounded PO creates overstock"
        elif excess and velocity == "Medium Moving" and cover_after > max_cover * 1.5:
            qty = 0.0
            box_count = 0.0
            decision = "Skipped: rounded PO creates overstock"
        elif excess and velocity == "Slow Moving" and (
            settings.get("skip_slow_excess_rounding", True) or not settings.get("allow_excess_rounding_slow", False)
        ):
            qty = 0.0
            box_count = 0.0
            decision = "Skipped slow item: rounded PO creates excess cover"
        rounded_qty.append(qty)
        rounded_boxes.append(box_count if qty > 0 else 0.0)
        decisions.append(decision)
        warnings.append(warning)

    result["Rounded PO Qty"] = rounded_qty
    result["Final PO Boxes"] = rounded_boxes
    result["Final PO Quantity"] = result["Rounded PO Qty"]
    result["Stock After PO Qty"] = result["Current Stock Qty"] + result["Final PO Quantity"]
    result["Stock Cover After PO Months"] = np.where(
        result["Relevant Velocity Qty"].gt(0),
        result["Stock After PO Qty"] / result["Relevant Velocity Qty"],
        np.nan,
    )
    result["Required Boxes"] = required_boxes
    result["Extra Stock Due To Rounding"] = (result["Rounded PO Qty"] - result["Exact Purchase Requirement Qty"]).clip(lower=0)
    result["Extra Qty Due To Box Rounding"] = result["Extra Stock Due To Rounding"]
    result["Rounding Extra Qty"] = result["Extra Stock Due To Rounding"]
    result["Box Qty Source"] = box_sources
    result["Overstock After PO Flag"] = np.where(
        result["Stock Cover After PO Months"].gt(result["Velocity Class"].map(MAX_COVER_AFTER_PO).fillna(0)),
        "Yes",
        "No",
    )
    result["PO Optimization Decision"] = decisions
    result["Rounding Warning"] = warnings
    result.loc[result["Final PO Quantity"].le(0) & result["PO Optimization Decision"].eq("Purchase Optimized"), "PO Optimization Decision"] = "Enough Stock / No Purchase"
    result["Estimated Purchase Value"] = result["Final PO Quantity"] * result["Purchase Price"]
    result["Stock Risk Level"] = result.apply(_stock_risk, axis=1)
    result["Purchase Priority"] = result.apply(_purchase_priority, axis=1)
    result.loc[result["PO Optimization Decision"].str.contains("Skipped|Dormant|Enough", case=False, na=False), "Purchase Priority"] = "No Purchase"
    result["Recommendation Status"] = np.where(result["Final PO Quantity"].gt(0), "Purchase Recommended", "No Purchase")

    def reason(row):
        parts = [
            row["Velocity Class"],
            row["Sales Trend"],
            row["Consistency Class"],
            row["Stock Risk Level"],
            row["PO Optimization Decision"],
        ]
        if row["Suggested Target Cover Months"] > 0:
            parts.append(f"dynamic cover {row['Suggested Target Cover Months']:.1f} months")
        if row["Rounding Warning"]:
            parts.append(row["Rounding Warning"])
        if row["Sales Trend"] in {"Downward Trend", "Strong Downward Trend"}:
            parts.append("recent velocity used because sales are declining")
        return join_reasons(parts)

    result["Reason for Recommendation"] = result.apply(reason, axis=1)
    result["Reason"] = result["Reason for Recommendation"]

    min_value = settings.get("min_purchase_value") or 0
    if min_value > 0:
        mask = result["Estimated Purchase Value"].lt(min_value) & result["Final PO Quantity"].gt(0)
        result.loc[mask, "PO Optimization Decision"] = "Below Minimum Purchase Value"
        result.loc[mask, "Purchase Priority"] = "No Purchase"
        result.loc[mask, ["Final PO Quantity", "Estimated Purchase Value"]] = 0

    return apply_discontinued_po_rules(_apply_budget(result, settings))
