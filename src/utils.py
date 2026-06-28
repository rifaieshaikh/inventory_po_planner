from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
SALES_DIR = DATA_DIR / "item-wise-sales"
STOCK_DIR = DATA_DIR / "stock"
EXPORTS_DIR = DATA_DIR / "exports"
MASTER_DIR = DATA_DIR / "master"
REPORT_PATH = EXPORTS_DIR / "inventory_report.xlsx"

PRIORITY_ORDER = {"Urgent": 1, "High": 2, "Medium": 3, "Low": 4, "No Purchase": 5}
MOVEMENT_ORDER = {
    "Very Fast Moving": 1,
    "Fast Moving": 2,
    "Medium Moving": 3,
    "Slow Moving": 4,
    "Dormant": 5,
    "Dead Stock / No Sales": 6,
    "Unknown": 7,
}
RISK_ORDER = {"Urgent Stock Risk": 1, "High Stock Risk": 2, "Medium Stock Risk": 3, "Low Stock Risk": 4, "Overstock Risk": 5}


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    text = re.sub(r"\s+", " ", text)
    return text


def build_item_key(row) -> str:
    code = normalize_text(row.get("Item Code / SKU", "") if hasattr(row, "get") else "")
    name = normalize_text(row.get("Normalized Item Name", row.get("Item Name", "")) if hasattr(row, "get") else "")
    return code or name


def safe_divide(numerator: float, denominator: float) -> float:
    if denominator in (0, None) or math.isclose(float(denominator), 0.0):
        return 0.0
    return float(numerator) / float(denominator)


def ceil_to_multiple(value: float, multiple: float) -> float:
    if value <= 0:
        return 0.0
    if multiple <= 0:
        return float(math.ceil(value))
    return float(math.ceil(value / multiple) * multiple)


def fmt_months(value: float | None) -> str:
    if value is None or math.isinf(value) or math.isnan(value):
        return "No Sales / NA"
    return f"{value:.2f}"


def join_reasons(parts: Iterable[str]) -> str:
    return "; ".join([part for part in parts if part])


def ensure_required_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if "Estimated Purchase Value" not in result.columns and "Total Amount" in result.columns:
        result["Estimated Purchase Value"] = result["Total Amount"]
    if "Total Amount" not in result.columns and "Estimated Purchase Value" in result.columns:
        result["Total Amount"] = result["Estimated Purchase Value"]

    defaults = {
        "Supplier Name": "Unknown Supplier",
        "Item Key": "",
        "Category ID": "",
        "Category Name": "Uncategorized",
        "Category / Size / Type": "Uncategorized",
        "Category Box Qty": 0,
        "Category Source": "Uncategorized",
        "Box Qty Source": "Not Available",
        "Is Discontinued": "No",
        "Discontinued Date": "",
        "Discontinued Reason": "",
        "Assigned Supplier ID": "",
        "Assigned Supplier Name": "Unknown Supplier",
        "Supplier Source": "Unknown Supplier",
        "Purchase Price": 0,
        "Recent Average Monthly Sales Qty": 0,
        "Movement Category": "Unknown",
        "Velocity Class": "Unknown",
        "Purchase Priority": "No Purchase",
        "Sales Trend": "No Sales",
        "Consistency Class": "Irregular",
        "Stock Risk Level": "Low Stock Risk",
        "PO Optimization Decision": "Enough Stock / No Purchase",
        "Rounding Warning": "",
        "Final PO Quantity": 0,
        "Rounded PO Qty": 0,
        "Estimated Purchase Value": 0,
        "Total Amount": 0,
        "Unit": "Meters",
        "Current Stock Qty": 0,
        "Stock After PO Qty": 0,
        "Stock Cover After PO Months": 0,
        "Recent Monthly Velocity Qty": 0,
        "Overall Monthly Velocity Qty": 0,
        "Weighted Velocity Qty": 0,
        "Relevant Velocity Qty": 0,
        "Suggested Target Cover Months": 0,
        "Exact Purchase Requirement Qty": 0,
        "Required Stock Qty": 0,
        "Required Boxes": 0,
        "Final PO Boxes": 0,
        "Extra Stock Due To Rounding": 0,
        "Extra Qty Due To Box Rounding": 0,
        "Overstock After PO Flag": "No",
        "Budget Approved PO Quantity": 0,
        "Budget Approved PO Value": 0,
        "Included In Budget PO": "Yes",
        "Deferred Reason": "",
    }

    for col, default_value in defaults.items():
        if col not in result.columns:
            result[col] = default_value
        else:
            result[col] = result[col].fillna(default_value)
            if isinstance(default_value, str):
                result[col] = result[col].astype(str).str.strip()
                result[col] = result[col].replace(["", "nan", "None", "NaN"], default_value)
    return result
