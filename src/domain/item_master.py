from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.utils import normalize_text


@dataclass
class ItemChange:
    item_key: str
    item_code: str
    item_name: str
    category_name: str = "Uncategorized"
    supplier_name: str = "Unknown Supplier"
    is_discontinued: bool = False
    discontinued_reason: str = ""
    category_changed: bool = False
    supplier_changed: bool = False
    discontinued_changed: bool = False
    category_id: str = ""
    supplier_id: str = ""
    category_box_qty: float = 0.0

    @property
    def has_changes(self) -> bool:
        return self.category_changed or self.supplier_changed or self.discontinued_changed


@dataclass
class ItemUpdateResult:
    rows: int = 0
    category: int = 0
    supplier: int = 0
    discontinued: int = 0
    missing_reasons: int = 0

    @property
    def changed(self) -> bool:
        return self.rows > 0

    def notification_messages(self) -> list[tuple[str, str]]:
        messages: list[tuple[str, str]] = []
        if self.rows:
            messages.append(("success", f"Saved {self.rows} item update(s)."))
            messages.append(("warning", "Run analysis again to refresh PO quantities."))
        if self.category:
            messages.append(("warning", "Category changed. Run analysis again to recalculate box quantity and PO."))
        if self.supplier:
            messages.append(("warning", "Supplier changed. Run analysis again to rebuild supplier-ready PO."))
        if self.discontinued:
            messages.append(("warning", "Item discontinued status changed. It will not be included in PO after refresh when marked discontinued."))
        if self.missing_reasons:
            messages.append(("warning", "Some discontinued items have no reason."))
        return messages


def clean_item_text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else "").strip()
    if text.lower() in {"nan", "none"}:
        return fallback
    return text or fallback


def is_discontinued_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in {"YES", "TRUE", "1", "Y"}


def item_key_from_row(row: pd.Series) -> str:
    key = clean_item_text(row.get("Item Key", ""))
    if not key:
        key = clean_item_text(row.get("Item Code / SKU", ""))
    if not key:
        key = clean_item_text(row.get("Item Name", ""))
    return normalize_text(key)


def display_item_label(row: pd.Series, index: int = 0) -> str:
    code = clean_item_text(row.get("Item Code / SKU", ""))
    name = clean_item_text(row.get("Item Name", ""))
    if code and name and normalize_text(code) != normalize_text(name):
        return f"{code} - {name}"
    return name or code or item_key_from_row(row) or f"Item {index + 1}"


def ensure_editable_item_columns(df: pd.DataFrame | None) -> pd.DataFrame:
    result = df.copy() if df is not None else pd.DataFrame()
    for col in ["Item Code / SKU", "Item Name", "Item Key"]:
        if col not in result.columns:
            result[col] = ""
    blank_key = result["Item Key"].fillna("").astype(str).str.strip().eq("")
    if blank_key.any():
        result.loc[blank_key, "Item Key"] = result.loc[blank_key].apply(
            lambda row: clean_item_text(row.get("Item Code / SKU", "")) or normalize_text(row.get("Item Name", "")),
            axis=1,
        )
    result["Item Key"] = result["Item Key"].map(normalize_text)

    if "Category Name" not in result.columns:
        result["Category Name"] = result.get("Category / Size / Type", "Uncategorized")
    result["Category Name"] = result["Category Name"].fillna("Uncategorized").astype(str).replace(
        {"": "Uncategorized", "nan": "Uncategorized", "None": "Uncategorized"}
    )

    if "Assigned Supplier Name" not in result.columns:
        result["Assigned Supplier Name"] = result.get("Supplier Name", "Unknown Supplier")
    result["Assigned Supplier Name"] = result["Assigned Supplier Name"].fillna("Unknown Supplier").astype(str).replace(
        {"": "Unknown Supplier", "nan": "Unknown Supplier", "None": "Unknown Supplier"}
    )

    if "Is Discontinued" not in result.columns:
        result["Is Discontinued"] = False
    result["Is Discontinued"] = result["Is Discontinued"].map(is_discontinued_value)

    if "Discontinued Reason" not in result.columns:
        result["Discontinued Reason"] = result.get("Reason", "")
    result["Discontinued Reason"] = result["Discontinued Reason"].fillna("").astype(str)
    return result


def editable_item_columns(df: pd.DataFrame, show_po_columns: bool) -> list[str]:
    base_cols = [
        "Item Key",
        "Item Code / SKU",
        "Item Name",
        "Category Name",
        "Assigned Supplier Name",
        "Is Discontinued",
        "Discontinued Reason",
    ]
    support_cols = [
        "Current Stock Qty",
        "Velocity Class",
        "Sales Trend",
        "Recent Monthly Velocity Qty",
        "Stock Coverage Months",
        "Purchase Priority",
        "Stock Risk Level",
    ]
    po_cols = [
        "Category Box Qty",
        "Final PO Boxes",
        "Final PO Quantity",
        "Estimated Purchase Value",
        "Total Amount",
    ]
    ordered = base_cols + support_cols + (po_cols if show_po_columns else [])
    return [col for col in ordered if col in df.columns]


def detect_item_changes(
    original: pd.DataFrame,
    edited: pd.DataFrame,
    allow_category_edit: bool = True,
    allow_supplier_edit: bool = True,
    allow_discontinued_edit: bool = True,
) -> list[ItemChange]:
    if original.empty or edited.empty:
        return []
    original_by_key: dict[str, pd.Series] = {}
    for _, row in original.iterrows():
        key = item_key_from_row(row)
        if key and key not in original_by_key:
            original_by_key[key] = row

    changes: list[ItemChange] = []
    for _, row in edited.iterrows():
        item_key = item_key_from_row(row)
        if not item_key or item_key not in original_by_key:
            continue
        old = original_by_key[item_key]
        category_name = clean_item_text(row.get("Category Name", ""), "Uncategorized")
        old_category = clean_item_text(old.get("Category Name", ""), "Uncategorized")
        supplier_name = clean_item_text(row.get("Assigned Supplier Name", ""), "Unknown Supplier")
        old_supplier = clean_item_text(old.get("Assigned Supplier Name", ""), "Unknown Supplier")
        discontinued = is_discontinued_value(row.get("Is Discontinued", False))
        old_discontinued = is_discontinued_value(old.get("Is Discontinued", False))
        reason = clean_item_text(row.get("Discontinued Reason", ""))
        old_reason = clean_item_text(old.get("Discontinued Reason", ""))
        change = ItemChange(
            item_key=item_key,
            item_code=clean_item_text(row.get("Item Code / SKU", old.get("Item Code / SKU", ""))),
            item_name=clean_item_text(row.get("Item Name", old.get("Item Name", ""))),
            category_name=category_name,
            supplier_name=supplier_name,
            is_discontinued=discontinued,
            discontinued_reason=reason,
            category_changed=allow_category_edit and normalize_text(category_name) != normalize_text(old_category),
            supplier_changed=allow_supplier_edit and normalize_text(supplier_name) != normalize_text(old_supplier),
            discontinued_changed=allow_discontinued_edit and (discontinued != old_discontinued or reason != old_reason),
        )
        if change.has_changes:
            changes.append(change)
    return changes


def row_action_change(row: pd.Series) -> ItemChange:
    return ItemChange(
        item_key=item_key_from_row(row),
        item_code=clean_item_text(row.get("Item Code / SKU", "")),
        item_name=clean_item_text(row.get("Item Name", "")),
        category_name=clean_item_text(row.get("Category Name", ""), "Uncategorized"),
        supplier_name=clean_item_text(row.get("Assigned Supplier Name", ""), "Unknown Supplier"),
        is_discontinued=is_discontinued_value(row.get("Is Discontinued", False)),
        discontinued_reason=clean_item_text(row.get("Discontinued Reason", "")),
    )


def is_discontinued_series(series: pd.Series) -> pd.Series:
    return series.map(is_discontinued_value)


def inline_validation_warnings(df: pd.DataFrame, report_stale: bool = False) -> list[str]:
    if df.empty:
        return []
    warnings: list[str] = []
    if "Category Name" in df.columns:
        count = int(df["Category Name"].fillna("Uncategorized").astype(str).str.strip().eq("Uncategorized").sum())
        if count:
            warnings.append(f"{count} item(s) are still Uncategorized.")
    if "Assigned Supplier Name" in df.columns:
        supplier = df["Assigned Supplier Name"].fillna("Unknown Supplier").astype(str).str.strip()
        count = int(supplier.isin(["", "Unknown Supplier"]).sum())
        if count:
            warnings.append(f"{count} item(s) still use Unknown Supplier.")
    if {"Is Discontinued", "Final PO Quantity"}.issubset(df.columns):
        po_qty = pd.to_numeric(df["Final PO Quantity"], errors="coerce").fillna(0)
        count = int((is_discontinued_series(df["Is Discontinued"]) & po_qty.gt(0)).sum())
        if count:
            warnings.append(f"{count} discontinued item(s) still appear in this PO view.")
    if report_stale:
        warnings.append("Report stale due to item master changes.")
    return warnings
