from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from .utils import MASTER_DIR, STORES_DIR, normalize_text


DEFAULT_STORE_ID = "STORE-0001"
DEFAULT_STORE_NAME = "Main Store"
STORES_PATH = MASTER_DIR / "stores.csv"
STORE_COLUMNS = [
    "Store ID",
    "Store Name",
    "Location",
    "Contact Person",
    "Phone",
    "Notes",
    "Active",
    "Created At",
    "Updated At",
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_store_master_file() -> None:
    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    STORES_DIR.mkdir(parents=True, exist_ok=True)
    if not STORES_PATH.exists() or STORES_PATH.stat().st_size == 0:
        pd.DataFrame(columns=STORE_COLUMNS).to_csv(STORES_PATH, index=False)


def _write_store_json(row: dict[str, object]) -> None:
    store_id = str(row.get("Store ID", "")).strip()
    if not store_id:
        return
    folder = get_store_folder(store_id)
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "store_id": store_id,
        "store_name": str(row.get("Store Name", "")).strip(),
        "location": str(row.get("Location", "")).strip(),
        "active": str(row.get("Active", "Yes")).strip().upper() == "YES",
        "created_at": str(row.get("Created At", "")).strip(),
        "updated_at": str(row.get("Updated At", "")).strip(),
    }
    (folder / "store.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_stores(active_only: bool = False) -> pd.DataFrame:
    ensure_store_master_file()
    try:
        df = pd.read_csv(STORES_PATH, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        df = pd.DataFrame(columns=STORE_COLUMNS)
    for col in STORE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[STORE_COLUMNS].copy()
    if active_only:
        df = df[df["Active"].astype(str).str.upper().eq("YES")].copy()
    return df


def save_stores(df: pd.DataFrame) -> None:
    ensure_store_master_file()
    out = df.copy()
    for col in STORE_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out[STORE_COLUMNS].to_csv(STORES_PATH, index=False)
    for _, row in out.iterrows():
        _write_store_json(row.to_dict())


def get_next_store_id() -> str:
    stores = load_stores(active_only=False)
    max_id = 0
    for value in stores["Store ID"].astype(str):
        if value.upper().startswith("STORE-"):
            try:
                max_id = max(max_id, int(value.split("-", 1)[1]))
            except (IndexError, ValueError):
                continue
    return f"STORE-{max_id + 1:04d}"


def _store_name_exists(df: pd.DataFrame, store_name: str, exclude_id: str = "") -> bool:
    name = normalize_text(store_name)
    mask = df["Store Name"].map(normalize_text).eq(name)
    if exclude_id:
        mask &= ~df["Store ID"].astype(str).eq(exclude_id)
    return bool(mask.any())


def get_store_folder(store_id: str) -> Path:
    store_id = str(store_id or DEFAULT_STORE_ID).strip() or DEFAULT_STORE_ID
    return STORES_DIR / store_id


def get_store_by_id(store_id: str) -> dict | None:
    stores = load_stores(active_only=False)
    rows = stores[stores["Store ID"].astype(str).eq(str(store_id))]
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()


def create_default_store_if_missing() -> str:
    stores = load_stores(active_only=False)
    now = _now()
    if stores.empty:
        row = {
            "Store ID": DEFAULT_STORE_ID,
            "Store Name": DEFAULT_STORE_NAME,
            "Location": "",
            "Contact Person": "",
            "Phone": "",
            "Notes": "",
            "Active": "Yes",
            "Created At": now,
            "Updated At": now,
        }
        save_stores(pd.DataFrame([row], columns=STORE_COLUMNS))
        return DEFAULT_STORE_ID

    if not stores["Store ID"].astype(str).eq(DEFAULT_STORE_ID).any():
        row = {
            "Store ID": DEFAULT_STORE_ID,
            "Store Name": DEFAULT_STORE_NAME if not _store_name_exists(stores, DEFAULT_STORE_NAME) else f"{DEFAULT_STORE_NAME} {DEFAULT_STORE_ID}",
            "Location": "",
            "Contact Person": "",
            "Phone": "",
            "Notes": "",
            "Active": "Yes",
            "Created At": now,
            "Updated At": now,
        }
        save_stores(pd.concat([stores, pd.DataFrame([row])], ignore_index=True))
        return DEFAULT_STORE_ID

    row = stores[stores["Store ID"].astype(str).eq(DEFAULT_STORE_ID)].iloc[0].to_dict()
    _write_store_json(row)
    return DEFAULT_STORE_ID


def add_store(
    store_name: str,
    location: str = "",
    contact_person: str = "",
    phone: str = "",
    notes: str = "",
) -> str:
    store_name = store_name.strip()
    if not store_name:
        raise ValueError("Store Name is required.")
    stores = load_stores(active_only=False)
    if _store_name_exists(stores, store_name):
        raise ValueError("Store Name must be unique.")
    store_id = get_next_store_id()
    now = _now()
    row = {
        "Store ID": store_id,
        "Store Name": store_name,
        "Location": location,
        "Contact Person": contact_person,
        "Phone": phone,
        "Notes": notes,
        "Active": "Yes",
        "Created At": now,
        "Updated At": now,
    }
    save_stores(pd.concat([stores, pd.DataFrame([row])], ignore_index=True))
    return store_id


def update_store(
    store_id: str,
    store_name: str,
    location: str = "",
    contact_person: str = "",
    phone: str = "",
    notes: str = "",
    active: bool = True,
) -> None:
    stores = load_stores(active_only=False)
    store_id = str(store_id).strip()
    store_name = store_name.strip()
    if not store_id:
        raise ValueError("Store ID is required.")
    if not store_name:
        raise ValueError("Store Name is required.")
    if _store_name_exists(stores, store_name, exclude_id=store_id):
        raise ValueError("Store Name must be unique.")
    mask = stores["Store ID"].astype(str).eq(store_id)
    if not mask.any():
        raise ValueError("Store not found.")
    updates = {
        "Store Name": store_name,
        "Location": location,
        "Contact Person": contact_person,
        "Phone": phone,
        "Notes": notes,
        "Active": "Yes" if active else "No",
        "Updated At": _now(),
    }
    for col, value in updates.items():
        stores.loc[mask, col] = value
    save_stores(stores)


def deactivate_store(store_id: str) -> None:
    stores = load_stores(active_only=False)
    mask = stores["Store ID"].astype(str).eq(str(store_id))
    stores.loc[mask, ["Active", "Updated At"]] = ["No", _now()]
    save_stores(stores)


def reactivate_store(store_id: str) -> None:
    stores = load_stores(active_only=False)
    mask = stores["Store ID"].astype(str).eq(str(store_id))
    stores.loc[mask, ["Active", "Updated At"]] = ["Yes", _now()]
    save_stores(stores)
