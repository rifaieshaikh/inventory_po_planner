from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from . import store_manager
from .utils import MASTER_DIR, build_item_key, normalize_text


DISCONTINUED_COLUMNS = ["Item Key", "Item Code / SKU", "Item Name", "Discontinued", "Discontinued Date", "Reason", "Updated At"]
ITEM_SUPPLIER_COLUMNS = ["Item Key", "Item Code / SKU", "Item Name", "Supplier ID", "Supplier Name", "Updated At"]
CATEGORY_COLUMNS = ["Category ID", "Category Name", "Box Qty", "Active", "Created At", "Updated At"]
ITEM_CATEGORY_COLUMNS = ["Item Key", "Item Code / SKU", "Item Name", "Category ID", "Category Name", "Updated At"]
SUPPLIER_COLUMNS = [
    "Supplier ID",
    "Supplier Name",
    "Contact Person",
    "Phone",
    "Email",
    "Address",
    "Notes",
    "Active",
    "Created At",
    "Updated At",
]

DISCONTINUED_PATH = MASTER_DIR / "discontinued-items.csv"
ITEM_SUPPLIERS_PATH = MASTER_DIR / "item-suppliers.csv"
CATEGORIES_PATH = MASTER_DIR / "categories.csv"
ITEM_CATEGORIES_PATH = MASTER_DIR / "item-categories.csv"
SUPPLIERS_PATH = MASTER_DIR / "suppliers.csv"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_master_dirs() -> None:
    MASTER_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_csv(path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        pd.DataFrame(columns=columns).to_csv(path, index=False)


def ensure_master_files() -> None:
    ensure_category_files()
    _ensure_csv(SUPPLIERS_PATH, SUPPLIER_COLUMNS)


def ensure_category_files() -> None:
    _ensure_csv(CATEGORIES_PATH, CATEGORY_COLUMNS)
    ensure_uncategorized_category_exists()


def _store_master_dir(store_id: str) -> Path:
    return store_manager.get_store_folder(store_id) / "master"


def discontinued_path(store_id: str) -> Path:
    return _store_master_dir(store_id) / "discontinued-items.csv"


def item_suppliers_path(store_id: str) -> Path:
    return _store_master_dir(store_id) / "item-suppliers.csv"


def item_categories_path(store_id: str) -> Path:
    return _store_master_dir(store_id) / "item-categories.csv"


def ensure_store_master_files(store_id: str) -> None:
    _ensure_csv(discontinued_path(store_id), DISCONTINUED_COLUMNS)
    _ensure_csv(item_suppliers_path(store_id), ITEM_SUPPLIER_COLUMNS)
    _ensure_csv(item_categories_path(store_id), ITEM_CATEGORY_COLUMNS)


def _read_csv(path, columns: list[str]) -> pd.DataFrame:
    ensure_master_dirs()
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        df = pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns].copy()


def load_discontinued_items(store_id: str) -> pd.DataFrame:
    ensure_store_master_files(store_id)
    return _read_csv(discontinued_path(store_id), DISCONTINUED_COLUMNS)


def save_discontinued_items(store_id: str, df: pd.DataFrame) -> None:
    ensure_store_master_files(store_id)
    out = df.copy()
    for col in DISCONTINUED_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out[DISCONTINUED_COLUMNS].to_csv(discontinued_path(store_id), index=False)


def set_discontinued_item(store_id: str, item_key: str, item_code: str, item_name: str, discontinued: bool, reason: str = "") -> None:
    df = load_discontinued_items(store_id)
    item_key = normalize_text(item_key)
    mask = df["Item Key"].map(normalize_text).eq(item_key)
    row = {
        "Item Key": item_key,
        "Item Code / SKU": item_code or "",
        "Item Name": item_name or "",
        "Discontinued": "Yes" if discontinued else "No",
        "Discontinued Date": datetime.now().strftime("%Y-%m-%d") if discontinued else "",
        "Reason": reason or "",
        "Updated At": _now(),
    }
    if mask.any():
        for col, value in row.items():
            df.loc[mask, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_discontinued_items(store_id, df)


def load_item_suppliers(store_id: str) -> pd.DataFrame:
    ensure_store_master_files(store_id)
    return _read_csv(item_suppliers_path(store_id), ITEM_SUPPLIER_COLUMNS)


def save_item_suppliers(store_id: str, df: pd.DataFrame) -> None:
    ensure_store_master_files(store_id)
    out = df.copy()
    for col in ITEM_SUPPLIER_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out[ITEM_SUPPLIER_COLUMNS].to_csv(item_suppliers_path(store_id), index=False)


def set_item_supplier(store_id: str, item_key: str, item_code: str, item_name: str, supplier_id: str, supplier_name: str) -> None:
    df = load_item_suppliers(store_id)
    item_key = normalize_text(item_key)
    mask = df["Item Key"].map(normalize_text).eq(item_key)
    row = {
        "Item Key": item_key,
        "Item Code / SKU": item_code or "",
        "Item Name": item_name or "",
        "Supplier ID": supplier_id or "",
        "Supplier Name": supplier_name or "Unknown Supplier",
        "Updated At": _now(),
    }
    if mask.any():
        for col, value in row.items():
            df.loc[mask, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_item_suppliers(store_id, df)


def load_categories(active_only: bool = False) -> pd.DataFrame:
    df = _read_csv(CATEGORIES_PATH, CATEGORY_COLUMNS)
    if active_only and not df.empty:
        df = df[df["Active"].astype(str).str.upper().eq("YES")]
    return df.copy()


def save_categories(df: pd.DataFrame) -> None:
    ensure_master_dirs()
    out = df.copy()
    for col in CATEGORY_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out[CATEGORY_COLUMNS].to_csv(CATEGORIES_PATH, index=False)


def get_next_category_id() -> str:
    categories = load_categories()
    max_id = 0
    for value in categories["Category ID"].astype(str):
        if value.upper().startswith("CAT-"):
            try:
                max_id = max(max_id, int(value.split("-", 1)[1]))
            except (IndexError, ValueError):
                continue
    return f"CAT-{max_id + 1:04d}"


def _category_name_exists(df: pd.DataFrame, category_name: str, exclude_id: str = "") -> bool:
    name = normalize_text(category_name)
    mask = df["Category Name"].map(normalize_text).eq(name)
    if exclude_id:
        mask &= ~df["Category ID"].astype(str).eq(exclude_id)
    return bool(mask.any())


def ensure_uncategorized_category_exists() -> dict:
    categories = load_categories(active_only=False)
    mask = categories["Category Name"].map(normalize_text).eq("UNCATEGORIZED")
    now = _now()
    if mask.any():
        idx = categories[mask].index[0]
        changed = False
        if str(categories.loc[idx, "Active"]).strip().upper() != "YES":
            categories.loc[idx, "Active"] = "Yes"
            changed = True
        if not str(categories.loc[idx, "Box Qty"]).strip():
            categories.loc[idx, "Box Qty"] = 0
            changed = True
        if changed:
            categories.loc[idx, "Updated At"] = now
            save_categories(categories)
        row = categories.loc[idx].to_dict()
        return row
    category_id = get_next_category_id()
    row = {
        "Category ID": category_id,
        "Category Name": "Uncategorized",
        "Box Qty": 0,
        "Active": "Yes",
        "Created At": now,
        "Updated At": now,
    }
    save_categories(pd.concat([categories, pd.DataFrame([row])], ignore_index=True))
    return row


def add_category(category_name: str, box_qty: float = 0) -> str:
    category_name = category_name.strip()
    if not category_name:
        raise ValueError("Category Name is required.")
    df = load_categories()
    if _category_name_exists(df, category_name):
        raise ValueError("Category Name must be unique.")
    category_id = get_next_category_id()
    now = _now()
    row = {
        "Category ID": category_id,
        "Category Name": category_name,
        "Box Qty": float(box_qty or 0),
        "Active": "Yes",
        "Created At": now,
        "Updated At": now,
    }
    save_categories(pd.concat([df, pd.DataFrame([row])], ignore_index=True))
    return category_id


def update_category(category_id: str, category_name: str, box_qty: float = 0, active: bool = True) -> None:
    df = load_categories()
    category_id = str(category_id).strip()
    category_name = category_name.strip()
    if not category_id:
        raise ValueError("Category ID is required.")
    if not category_name:
        raise ValueError("Category Name is required.")
    if _category_name_exists(df, category_name, exclude_id=category_id):
        raise ValueError("Category Name must be unique.")
    mask = df["Category ID"].astype(str).eq(category_id)
    if not mask.any():
        raise ValueError("Category not found.")
    updates = {
        "Category Name": category_name,
        "Box Qty": float(box_qty or 0),
        "Active": "Yes" if active else "No",
        "Updated At": _now(),
    }
    for col, value in updates.items():
        df.loc[mask, col] = value
    save_categories(df)


def deactivate_category(category_id: str) -> None:
    df = load_categories()
    mask = df["Category ID"].astype(str).eq(str(category_id))
    df.loc[mask, ["Active", "Updated At"]] = ["No", _now()]
    save_categories(df)


def reactivate_category(category_id: str) -> None:
    df = load_categories()
    mask = df["Category ID"].astype(str).eq(str(category_id))
    df.loc[mask, ["Active", "Updated At"]] = ["Yes", _now()]
    save_categories(df)


def load_item_categories(store_id: str) -> pd.DataFrame:
    ensure_store_master_files(store_id)
    return _read_csv(item_categories_path(store_id), ITEM_CATEGORY_COLUMNS)


def save_item_categories(store_id: str, df: pd.DataFrame) -> None:
    ensure_store_master_files(store_id)
    out = df.copy()
    for col in ITEM_CATEGORY_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out[ITEM_CATEGORY_COLUMNS].to_csv(item_categories_path(store_id), index=False)


def set_item_category(store_id: str, item_key: str, item_code: str, item_name: str, category_id: str, category_name: str) -> None:
    df = load_item_categories(store_id)
    item_key = normalize_text(item_key)
    mask = df["Item Key"].map(normalize_text).eq(item_key)
    row = {
        "Item Key": item_key,
        "Item Code / SKU": item_code or "",
        "Item Name": item_name or "",
        "Category ID": category_id or "",
        "Category Name": category_name or "Uncategorized",
        "Updated At": _now(),
    }
    if mask.any():
        for col, value in row.items():
            df.loc[mask, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_item_categories(store_id, df)


def clear_item_category(store_id: str, item_key: str) -> None:
    df = load_item_categories(store_id)
    item_key = normalize_text(item_key)
    df = df[~df["Item Key"].map(normalize_text).eq(item_key)].copy()
    save_item_categories(store_id, df)


def load_suppliers(active_only: bool = False) -> pd.DataFrame:
    df = _read_csv(SUPPLIERS_PATH, SUPPLIER_COLUMNS)
    if active_only:
        df = df[df["Active"].astype(str).str.upper().eq("YES")]
    return df.copy()


def save_suppliers(df: pd.DataFrame) -> None:
    ensure_master_dirs()
    out = df.copy()
    for col in SUPPLIER_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out[SUPPLIER_COLUMNS].to_csv(SUPPLIERS_PATH, index=False)


def get_next_supplier_id() -> str:
    suppliers = load_suppliers()
    max_id = 0
    for value in suppliers["Supplier ID"].astype(str):
        if value.upper().startswith("SUP-"):
            try:
                max_id = max(max_id, int(value.split("-", 1)[1]))
            except (IndexError, ValueError):
                continue
    return f"SUP-{max_id + 1:04d}"


def _supplier_name_exists(df: pd.DataFrame, supplier_name: str, exclude_id: str = "") -> bool:
    name = normalize_text(supplier_name)
    mask = df["Supplier Name"].map(normalize_text).eq(name)
    if exclude_id:
        mask &= ~df["Supplier ID"].astype(str).eq(exclude_id)
    return bool(mask.any())


def add_supplier(supplier_name: str, contact_person: str = "", phone: str = "", email: str = "", address: str = "", notes: str = "") -> str:
    supplier_name = supplier_name.strip()
    if not supplier_name:
        raise ValueError("Supplier Name is required.")
    df = load_suppliers()
    if _supplier_name_exists(df, supplier_name):
        raise ValueError("Supplier Name must be unique.")
    supplier_id = get_next_supplier_id()
    now = _now()
    row = {
        "Supplier ID": supplier_id,
        "Supplier Name": supplier_name,
        "Contact Person": contact_person,
        "Phone": phone,
        "Email": email,
        "Address": address,
        "Notes": notes,
        "Active": "Yes",
        "Created At": now,
        "Updated At": now,
    }
    save_suppliers(pd.concat([df, pd.DataFrame([row])], ignore_index=True))
    return supplier_id


def update_supplier(
    supplier_id: str,
    supplier_name: str,
    contact_person: str = "",
    phone: str = "",
    email: str = "",
    address: str = "",
    notes: str = "",
    active: bool = True,
) -> None:
    df = load_suppliers()
    supplier_name = supplier_name.strip()
    if not supplier_id:
        raise ValueError("Supplier ID is required.")
    if not supplier_name:
        raise ValueError("Supplier Name is required.")
    if _supplier_name_exists(df, supplier_name, exclude_id=supplier_id):
        raise ValueError("Supplier Name must be unique.")
    mask = df["Supplier ID"].astype(str).eq(supplier_id)
    if not mask.any():
        raise ValueError("Supplier not found.")
    updates = {
        "Supplier Name": supplier_name,
        "Contact Person": contact_person,
        "Phone": phone,
        "Email": email,
        "Address": address,
        "Notes": notes,
        "Active": "Yes" if active else "No",
        "Updated At": _now(),
    }
    for col, value in updates.items():
        df.loc[mask, col] = value
    save_suppliers(df)


def deactivate_supplier(supplier_id: str) -> None:
    df = load_suppliers()
    df.loc[df["Supplier ID"].astype(str).eq(supplier_id), ["Active", "Updated At"]] = ["No", _now()]
    save_suppliers(df)


def reactivate_supplier(supplier_id: str) -> None:
    df = load_suppliers()
    df.loc[df["Supplier ID"].astype(str).eq(supplier_id), ["Active", "Updated At"]] = ["Yes", _now()]
    save_suppliers(df)


def enrich_with_master_data(detail: pd.DataFrame, store_id: str) -> pd.DataFrame:
    ensure_store_master_files(store_id)
    result = detail.copy()
    if "Item Key" not in result.columns:
        result["Item Key"] = result.apply(build_item_key, axis=1)
    else:
        blank_key = result["Item Key"].fillna("").astype(str).str.strip().eq("")
        if blank_key.any():
            result.loc[blank_key, "Item Key"] = result.loc[blank_key].apply(build_item_key, axis=1)
    result["Item Key"] = result["Item Key"].map(normalize_text)

    categories = load_categories(active_only=False)
    ensure_uncategorized_category_exists()
    categories = load_categories(active_only=False)
    if not categories.empty:
        categories["Category Name Norm"] = categories["Category Name"].map(normalize_text)
    active_categories = categories[categories["Active"].astype(str).str.upper().eq("YES")].copy() if not categories.empty else pd.DataFrame()
    active_category_map = active_categories.set_index("Category Name Norm")[["Category ID", "Category Name", "Box Qty"]].to_dict("index") if not active_categories.empty else {}
    all_category_map = categories.set_index("Category Name Norm")[["Category ID", "Category Name", "Box Qty", "Active"]].to_dict("index") if not categories.empty else {}

    def _box_qty(value) -> float:
        qty = pd.to_numeric(value, errors="coerce")
        return float(qty) if pd.notna(qty) else 0.0

    item_categories = load_item_categories(store_id)
    if not item_categories.empty:
        item_categories["Item Key"] = item_categories["Item Key"].map(normalize_text)
        item_categories = item_categories.drop_duplicates("Item Key", keep="last")
    else:
        item_categories = pd.DataFrame(columns=ITEM_CATEGORY_COLUMNS)
    item_category_map = item_categories.set_index("Item Key").to_dict("index") if not item_categories.empty else {}

    resolved_category_rows = []
    uncategorized_updates = []
    for _, row in result.iterrows():
        item_key = str(row.get("Item Key", "")).strip()
        item_code = str(row.get("Item Code / SKU", "")).strip()
        item_name = str(row.get("Item Name", "")).strip()
        source_category = str(row.get("Category / Size / Type", "")).strip()
        source_norm = normalize_text(source_category)
        mapping = item_category_map.get(item_key)
        category_id = ""
        category_name = ""
        category_box_qty = 0.0
        category_source = "Uncategorized"
        box_source = "Not Available"
        if mapping:
            category_id = str(mapping.get("Category ID", "")).strip()
            category_name = str(mapping.get("Category Name", "")).strip() or "Uncategorized"
            lookup = all_category_map.get(normalize_text(category_name))
            if lookup:
                category_box_qty = _box_qty(lookup.get("Box Qty", 0))
                box_source = "Category" if category_box_qty > 0 else "Not Available"
            category_source = "Item Category Mapping"
        elif source_norm and source_norm in active_category_map:
            lookup = active_category_map[source_norm]
            category_id = str(lookup.get("Category ID", "")).strip()
            category_name = str(lookup.get("Category Name", "")).strip() or source_category
            category_box_qty = _box_qty(lookup.get("Box Qty", 0))
            category_source = "Source Data"
            box_source = "Category" if category_box_qty > 0 else "Not Available"
        else:
            unc = ensure_uncategorized_category_exists()
            category_id = str(unc.get("Category ID", "")).strip()
            category_name = "Uncategorized"
            category_box_qty = _box_qty(unc.get("Box Qty", 0))
            category_source = "Uncategorized"
            box_source = "Category" if category_box_qty > 0 else "Not Available"
            uncategorized_updates.append((item_key, item_code, item_name))
        resolved_category_rows.append(
            {
                "Category ID": category_id,
                "Category Name": category_name or "Uncategorized",
                "Category Box Qty": category_box_qty if pd.notna(category_box_qty) else 0,
                "Category Source": category_source,
                "Box Qty Source": box_source,
            }
        )

    if uncategorized_updates:
        existing = load_item_categories(store_id)
        for item_key, item_code, item_name in uncategorized_updates:
            if not existing.empty and existing["Item Key"].map(normalize_text).eq(normalize_text(item_key)).any():
                continue
            existing = pd.concat(
                [
                    existing,
                    pd.DataFrame(
                        [
                            {
                                "Item Key": normalize_text(item_key),
                                "Item Code / SKU": item_code,
                                "Item Name": item_name,
                                "Category ID": ensure_uncategorized_category_exists().get("Category ID", ""),
                                "Category Name": "Uncategorized",
                                "Updated At": _now(),
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        save_item_categories(store_id, existing)

    category_df = pd.DataFrame(resolved_category_rows).reset_index(drop=True)
    result = result.reset_index(drop=True)
    for col in category_df.columns:
        result[col] = category_df[col].values
    result["Category Name"] = result["Category Name"].fillna("Uncategorized").replace("", "Uncategorized")
    result["Category / Size / Type"] = result["Category Name"]
    result["Category Box Qty"] = pd.to_numeric(result["Category Box Qty"], errors="coerce").fillna(0)
    result["Category Source"] = result["Category Source"].fillna("Uncategorized")
    result["Box Qty Source"] = result["Box Qty Source"].fillna("Not Available")

    discontinued = load_discontinued_items(store_id)
    disc_active = discontinued[discontinued["Discontinued"].astype(str).str.upper().eq("YES")].copy()
    disc_active["Item Key"] = disc_active["Item Key"].map(normalize_text)
    disc_cols = disc_active[["Item Key", "Discontinued Date", "Reason"]].rename(columns={"Reason": "Discontinued Reason"})
    result = result.drop(columns=["Discontinued Date", "Discontinued Reason"], errors="ignore").merge(disc_cols, on="Item Key", how="left")
    result["Is Discontinued"] = result["Discontinued Date"].fillna("").ne("").map(lambda x: "Yes" if x else "No")
    result["Discontinued Date"] = result["Discontinued Date"].fillna("")
    result["Discontinued Reason"] = result["Discontinued Reason"].fillna("")

    mappings = load_item_suppliers(store_id)
    mappings["Item Key"] = mappings["Item Key"].map(normalize_text)
    mappings = mappings.drop_duplicates("Item Key", keep="last")
    map_cols = mappings[["Item Key", "Supplier ID", "Supplier Name"]].rename(
        columns={"Supplier ID": "Mapped Supplier ID", "Supplier Name": "Mapped Supplier Name"}
    )
    result = result.merge(map_cols, on="Item Key", how="left")
    stock_supplier = result.get("Supplier Name", pd.Series("Unknown Supplier", index=result.index)).fillna("Unknown Supplier").astype(str).str.strip()
    stock_supplier = stock_supplier.replace(["", "nan", "None", "NaN"], "Unknown Supplier")
    mapped_supplier = result["Mapped Supplier Name"].fillna("").astype(str).str.strip()
    mapped_id = result["Mapped Supplier ID"].fillna("").astype(str).str.strip()
    has_mapping = mapped_supplier.ne("")
    result["Assigned Supplier ID"] = mapped_id.where(has_mapping, "")
    result["Assigned Supplier Name"] = mapped_supplier.where(has_mapping, stock_supplier)
    result["Assigned Supplier Name"] = result["Assigned Supplier Name"].replace(["", "nan", "None", "NaN"], "Unknown Supplier")
    result["Supplier Source"] = "Unknown Supplier"
    result.loc[stock_supplier.ne("Unknown Supplier") & ~has_mapping, "Supplier Source"] = "Stock File"
    result.loc[has_mapping, "Supplier Source"] = "Item Supplier Mapping"
    result["Supplier Name"] = result["Assigned Supplier Name"]
    return result.drop(columns=["Mapped Supplier ID", "Mapped Supplier Name"], errors="ignore")


def master_validation_warnings(detail: pd.DataFrame, final_po: pd.DataFrame, store_id: str) -> pd.DataFrame:
    ensure_store_master_files(store_id)
    issues = []
    suppliers = load_suppliers()
    mappings = load_item_suppliers(store_id)
    categories = load_categories()
    item_categories = load_item_categories(store_id)
    supplier_active = suppliers.set_index("Supplier ID")["Active"].to_dict() if not suppliers.empty else {}
    category_active = categories.set_index("Category ID")["Active"].to_dict() if not categories.empty and "Category ID" in categories.columns else {}
    current_keys = set(detail.get("Item Key", pd.Series(dtype=str)).map(normalize_text))

    no_supplier = detail["Assigned Supplier Name"].fillna("Unknown Supplier").astype(str).str.strip().isin(["", "Unknown Supplier"]).sum() if "Assigned Supplier Name" in detail else 0
    if no_supplier:
        issues.append(["Items without assigned supplier", "Warning", "", "", f"{int(no_supplier)} item(s) use Unknown Supplier."])

    if "Assigned Supplier ID" in detail:
        inactive = detail[detail["Assigned Supplier ID"].astype(str).map(lambda x: bool(x) and supplier_active.get(x, "Yes") != "Yes")]
        for _, row in inactive.iterrows():
            issues.append(["Item assigned to inactive supplier", "Warning", row.get("Item Code / SKU", ""), row.get("Item Name", ""), row.get("Assigned Supplier Name", "")])

    discontinued = detail[detail.get("Is Discontinued", pd.Series("No", index=detail.index)).astype(str).str.upper().eq("YES")]
    for _, row in discontinued[discontinued["Current Stock Qty"].fillna(0).gt(0)].iterrows():
        issues.append(["Discontinued item with stock available", "Warning", row.get("Item Code / SKU", ""), row.get("Item Name", ""), "Existing stock available. Consider discount/liquidation. Do not reorder."])
    for _, row in discontinued[discontinued["Final PO Quantity"].fillna(0).gt(0)].iterrows():
        issues.append(["Discontinued item was found in PO and removed", "Error", row.get("Item Code / SKU", ""), row.get("Item Name", ""), "Final PO quantity forced to 0."])

    if not mappings.empty:
        dupes = mappings[mappings["Item Key"].map(normalize_text).duplicated(keep=False)]
        for _, row in dupes.drop_duplicates("Item Key").iterrows():
            issues.append(["Duplicate item supplier mapping", "Warning", row.get("Item Code / SKU", ""), row.get("Item Name", ""), row.get("Item Key", "")])
        for _, row in mappings.iterrows():
            if normalize_text(row.get("Item Key", "")) not in current_keys:
                issues.append(["Supplier mapping item not found", "Warning", row.get("Item Code / SKU", ""), row.get("Item Name", ""), row.get("Item Key", "")])

    if not suppliers.empty:
        dup_names = suppliers[suppliers["Supplier Name"].map(normalize_text).duplicated(keep=False)]
        for _, row in dup_names.drop_duplicates("Supplier Name").iterrows():
            issues.append(["Duplicate supplier name", "Warning", "", row.get("Supplier Name", ""), "Supplier names should be unique."])

    if not categories.empty:
        dup_categories = categories[categories["Category Name"].map(normalize_text).duplicated(keep=False)]
        for _, row in dup_categories.drop_duplicates("Category Name").iterrows():
            issues.append(["Duplicate category name", "Warning", "", row.get("Category Name", ""), "Category names should be unique."])
        missing_box = categories[pd.to_numeric(categories.get("Box Qty", 0), errors="coerce").fillna(0).le(0)]
        if not missing_box.empty:
            issues.append([
                "Categories with missing Box Qty",
                "Warning",
                "",
                "",
                f"{len(missing_box)} category(s) have Box Qty missing or 0.",
            ])

    if not item_categories.empty and "Item Key" in item_categories.columns:
        mapped_keys = set(item_categories["Item Key"].map(normalize_text))
        missing_mappings = current_keys.difference(mapped_keys)
        if missing_mappings:
            issues.append([
                "Items with Uncategorized category",
                "Warning",
                "",
                "",
                f"{len(missing_mappings)} item(s) are not mapped and will use Uncategorized.",
            ])

        inactive_rows = item_categories[item_categories["Category ID"].astype(str).map(lambda x: bool(x) and category_active.get(x, "Yes") != "Yes")]
        for _, row in inactive_rows.iterrows():
            issues.append([
                "Item assigned to inactive category",
                "Warning",
                row.get("Item Code / SKU", ""),
                row.get("Item Name", ""),
                row.get("Category Name", ""),
            ])

    if not final_po.empty and "Is Discontinued" in final_po.columns and final_po["Is Discontinued"].astype(str).str.upper().eq("YES").any():
        issues.append(["Final PO contains discontinued item", "Error", "", "", "Discontinued items were removed from final PO."])

    return pd.DataFrame(issues, columns=["Issue Type", "Severity", "Item Code / SKU", "Item Name", "Details"])
