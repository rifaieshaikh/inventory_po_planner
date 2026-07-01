from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import pandas as pd

from src.domain.item_master import ItemChange, ItemUpdateResult, clean_item_text
from src.utils import normalize_text


class MasterDataRepositoryProtocol(Protocol):
    def ensure_uncategorized_category_exists(self) -> dict: ...
    def load_categories(self, active_only: bool = False) -> pd.DataFrame: ...
    def load_suppliers(self, active_only: bool = False) -> pd.DataFrame: ...
    def load_item_categories(self, store_id: str) -> pd.DataFrame: ...
    def load_item_suppliers(self, store_id: str) -> pd.DataFrame: ...
    def set_item_category(self, store_id: str, item_key: str, item_code: str, item_name: str, category_id: str, category_name: str) -> None: ...
    def set_item_supplier(self, store_id: str, item_key: str, item_code: str, item_name: str, supplier_id: str, supplier_name: str) -> None: ...
    def set_discontinued_item(self, store_id: str, item_key: str, item_code: str, item_name: str, discontinued: bool, reason: str = "") -> None: ...


@dataclass
class MasterOptions:
    options: list[str]
    lookup: dict[str, dict[str, object]]
    inactive_current: list[str]


def _append_unique(values: list[str], value: object, fallback: str = "") -> None:
    text = clean_item_text(value, fallback)
    if text and text not in values:
        values.append(text)


def _safe_number(value: object) -> float:
    try:
        number = pd.to_numeric(value, errors="coerce")
        if pd.isna(number):
            return 0.0
        return float(number)
    except (TypeError, ValueError):
        return 0.0


def _add_store_context(df: pd.DataFrame, store_id: str, store_name: str) -> pd.DataFrame:
    result = df.copy()
    if "Store Name" not in result.columns:
        result.insert(0, "Store Name", store_name)
    else:
        result["Store Name"] = result["Store Name"].replace("", store_name).fillna(store_name)
    if "Store ID" not in result.columns:
        result.insert(0, "Store ID", store_id)
    else:
        result["Store ID"] = result["Store ID"].replace("", store_id).fillna(store_id)
    return result


class ItemMasterService:
    def __init__(self, repository: MasterDataRepositoryProtocol):
        self.repository = repository

    def category_options_for_items(self, df: pd.DataFrame) -> MasterOptions:
        uncategorized = self.repository.ensure_uncategorized_category_exists()
        categories = self.repository.load_categories(active_only=False)
        lookup: dict[str, dict[str, object]] = {"UNCATEGORIZED": uncategorized}
        options = ["Uncategorized"]
        active_names: set[str] = {"UNCATEGORIZED"}

        if not categories.empty:
            for _, row in categories.iterrows():
                name = clean_item_text(row.get("Category Name", ""), "Uncategorized")
                lookup.setdefault(normalize_text(name), row.to_dict())
                if str(row.get("Active", "Yes")).strip().upper() == "YES":
                    active_names.add(normalize_text(name))
                    _append_unique(options, name)

        inactive_current: list[str] = []
        if "Category Name" in df.columns:
            for value in df["Category Name"].fillna("Uncategorized").astype(str):
                name = clean_item_text(value, "Uncategorized")
                if normalize_text(name) not in active_names and normalize_text(name) != "UNCATEGORIZED":
                    _append_unique(inactive_current, name)
                _append_unique(options, name, "Uncategorized")
        return MasterOptions(options=options, lookup=lookup, inactive_current=inactive_current)

    def supplier_options_for_items(self, df: pd.DataFrame) -> MasterOptions:
        suppliers = self.repository.load_suppliers(active_only=False)
        lookup: dict[str, dict[str, object]] = {"UNKNOWN SUPPLIER": {"Supplier ID": "", "Supplier Name": "Unknown Supplier"}}
        options = ["Unknown Supplier"]
        active_names: set[str] = {"UNKNOWN SUPPLIER"}

        if not suppliers.empty:
            for _, row in suppliers.iterrows():
                name = clean_item_text(row.get("Supplier Name", ""), "Unknown Supplier")
                lookup.setdefault(normalize_text(name), row.to_dict())
                if str(row.get("Active", "Yes")).strip().upper() == "YES":
                    active_names.add(normalize_text(name))
                    _append_unique(options, name)

        inactive_current: list[str] = []
        if "Assigned Supplier Name" in df.columns:
            for value in df["Assigned Supplier Name"].fillna("Unknown Supplier").astype(str):
                name = clean_item_text(value, "Unknown Supplier")
                if normalize_text(name) not in active_names and normalize_text(name) != "UNKNOWN SUPPLIER":
                    _append_unique(inactive_current, name)
                _append_unique(options, name, "Unknown Supplier")
        return MasterOptions(options=options, lookup=lookup, inactive_current=inactive_current)

    def save_item_changes(self, store_id: str, changes: list[ItemChange]) -> ItemUpdateResult:
        category_lookup = self.category_options_for_items(pd.DataFrame()).lookup
        supplier_lookup = self.supplier_options_for_items(pd.DataFrame()).lookup
        result = ItemUpdateResult()

        for change in changes:
            row_changed = False
            if change.category_changed:
                category_name = clean_item_text(change.category_name, "Uncategorized")
                category_row = category_lookup.get(normalize_text(category_name), category_lookup.get("UNCATEGORIZED", {}))
                change.category_name = clean_item_text(category_row.get("Category Name", ""), "Uncategorized")
                change.category_id = clean_item_text(category_row.get("Category ID", ""))
                change.category_box_qty = _safe_number(category_row.get("Box Qty", 0))
                self.repository.set_item_category(
                    store_id,
                    change.item_key,
                    change.item_code,
                    change.item_name,
                    change.category_id,
                    change.category_name,
                )
                result.category += 1
                row_changed = True

            if change.supplier_changed:
                supplier_name = clean_item_text(change.supplier_name, "Unknown Supplier")
                supplier_row = supplier_lookup.get(normalize_text(supplier_name), supplier_lookup["UNKNOWN SUPPLIER"])
                change.supplier_name = clean_item_text(supplier_row.get("Supplier Name", ""), "Unknown Supplier")
                change.supplier_id = clean_item_text(supplier_row.get("Supplier ID", ""))
                if normalize_text(change.supplier_name) == "UNKNOWN SUPPLIER":
                    change.supplier_id = ""
                    change.supplier_name = "Unknown Supplier"
                self.repository.set_item_supplier(
                    store_id,
                    change.item_key,
                    change.item_code,
                    change.item_name,
                    change.supplier_id,
                    change.supplier_name,
                )
                result.supplier += 1
                row_changed = True

            if change.discontinued_changed:
                reason = clean_item_text(change.discontinued_reason, "") if change.is_discontinued else ""
                if change.is_discontinued and not reason:
                    result.missing_reasons += 1
                change.discontinued_reason = reason
                self.repository.set_discontinued_item(
                    store_id,
                    change.item_key,
                    change.item_code,
                    change.item_name,
                    change.is_discontinued,
                    reason,
                )
                result.discontinued += 1
                row_changed = True

            if row_changed:
                result.rows += 1
        return result

    def apply_changes_to_report(
        self,
        report: dict,
        store_id: str,
        store_name: str,
        changes: list[ItemChange],
    ) -> dict:
        if not isinstance(report, dict) or not changes:
            return report

        updated_report = dict(report)
        change_by_key = {change.item_key: change for change in changes}
        discontinued_keys = {
            change.item_key
            for change in changes
            if change.discontinued_changed and change.is_discontinued
        }

        for sheet_name, frame in list(updated_report.items()):
            if not isinstance(frame, pd.DataFrame) or "Item Key" not in frame.columns:
                continue
            updated = frame.copy()
            normalized_keys = updated["Item Key"].map(normalize_text)
            for item_key, change in change_by_key.items():
                mask = normalized_keys.eq(item_key)
                if not mask.any():
                    continue
                if change.category_changed:
                    for col, value in {
                        "Category ID": change.category_id,
                        "Category Name": change.category_name,
                        "Category / Size / Type": change.category_name,
                        "Category Source": "Item Category Mapping",
                    }.items():
                        if col in updated.columns:
                            updated.loc[mask, col] = value
                    if "Category Box Qty" in updated.columns:
                        updated.loc[mask, "Category Box Qty"] = change.category_box_qty
                if change.supplier_changed:
                    for col, value in {
                        "Assigned Supplier ID": change.supplier_id,
                        "Assigned Supplier Name": change.supplier_name,
                        "Supplier Name": change.supplier_name,
                        "Supplier Source": "Item Supplier Mapping",
                    }.items():
                        if col in updated.columns:
                            updated.loc[mask, col] = value
                if change.discontinued_changed:
                    reason = change.discontinued_reason if change.is_discontinued else ""
                    for col, value in {
                        "Is Discontinued": "Yes" if change.is_discontinued else "No",
                        "Discontinued Reason": reason,
                        "Discontinued Date": datetime.now().strftime("%Y-%m-%d") if change.is_discontinued else "",
                    }.items():
                        if col in updated.columns:
                            updated.loc[mask, col] = value
                    if change.is_discontinued:
                        for col in [
                            "Final PO Quantity",
                            "Final PO Boxes",
                            "Estimated Purchase Value",
                            "Budget Approved PO Quantity",
                            "Budget Approved PO Value",
                            "Required Stock Qty",
                            "Rounded PO Qty",
                        ]:
                            if col in updated.columns:
                                updated.loc[mask, col] = 0
                        if "Purchase Priority" in updated.columns:
                            updated.loc[mask, "Purchase Priority"] = "No Purchase"
                        if "PO Optimization Decision" in updated.columns:
                            updated.loc[mask, "PO Optimization Decision"] = "Discontinued Item - Do Not Purchase"

            if sheet_name in {"Optimized PO", "Final PO", "Supplier Ready PO", "Supplier Ready PO Edited"} and discontinued_keys:
                updated = updated[~updated["Item Key"].map(normalize_text).isin(discontinued_keys)].copy()
            updated_report[sheet_name] = updated

        detail = updated_report.get("Detailed Item Analysis")
        if isinstance(detail, pd.DataFrame) and "Is Discontinued" in detail.columns:
            updated_report["Discontinued Items"] = detail[detail["Is Discontinued"].astype(str).str.upper().eq("YES")].copy()

        updated_report["Item Supplier Mapping"] = _add_store_context(
            self.repository.load_item_suppliers(store_id),
            store_id,
            store_name,
        )
        updated_report["Item Category Mapping"] = _add_store_context(
            self.repository.load_item_categories(store_id),
            store_id,
            store_name,
        )
        return updated_report
