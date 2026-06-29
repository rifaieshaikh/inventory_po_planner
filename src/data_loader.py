from __future__ import annotations

from pathlib import Path

import pandas as pd

from .cleaner import clean_sales, clean_stock
from .column_mapper import detect_columns, to_number
from .file_manager import get_sales_year_from_path
from .utils import normalize_text


def read_csv_flexible(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "latin1"]
    last_error = None
    attempts: list[pd.DataFrame] = []
    for encoding in encodings:
        try:
            attempts.append(pd.read_csv(path, encoding=encoding))
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
        try:
            attempts.append(pd.read_csv(path, encoding=encoding, sep="\t"))
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
        try:
            attempts.append(pd.read_csv(path, encoding=encoding, sep=None, engine="python"))
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
    if attempts:
        return max(attempts, key=lambda frame: len(frame.columns))
    raise last_error


def _default_sales_month(fy: str) -> pd.Timestamp:
    try:
        end_year = int(str(fy).split("-")[-1])
        return pd.Timestamp(year=2000 + end_year, month=3, day=1)
    except (TypeError, ValueError):
        return pd.Timestamp.today().normalize().replace(day=1)


def _looks_standardized_sales(df: pd.DataFrame) -> bool:
    required = {"Item Name", "Sales Quantity"}
    return required.issubset(set(df.columns)) and ("Item Key" in df.columns or "Item Code / SKU" in df.columns)


def _looks_standardized_stock(df: pd.DataFrame) -> bool:
    stock_col_exists = "Current Stock Quantity" in df.columns or "Current Stock Qty" in df.columns
    return {"Item Name"}.issubset(set(df.columns)) and stock_col_exists and ("Item Key" in df.columns or "Item Code / SKU" in df.columns)


def _prepare_standardized_sales(df: pd.DataFrame, fy: str) -> pd.DataFrame:
    result = df.copy()
    result.columns = [str(col).strip().lstrip("\ufeff") for col in result.columns]
    result = result.dropna(how="all")
    result["Item Name"] = result.get("Item Name", "").fillna("").astype(str).str.strip()
    result = result[result["Item Name"].ne("")].copy()
    result["Normalized Item Name"] = result["Item Name"].map(normalize_text)
    if "Item Key" not in result.columns:
        result["Item Key"] = ""
    if "Item Code / SKU" not in result.columns:
        result["Item Code / SKU"] = ""
    result["Item Key"] = result["Item Key"].fillna("").astype(str).str.strip().map(normalize_text)
    result["Item Code / SKU"] = result["Item Code / SKU"].fillna("").astype(str).str.strip()
    blank_key = result["Item Key"].eq("")
    result.loc[blank_key, "Item Key"] = result.loc[blank_key, "Item Code / SKU"].map(normalize_text)
    blank_key = result["Item Key"].eq("")
    result.loc[blank_key, "Item Key"] = result.loc[blank_key, "Normalized Item Name"]
    result["Item Code / SKU"] = result["Item Code / SKU"].where(result["Item Code / SKU"].ne(""), result["Item Key"])
    if "Category / Size / Type" not in result.columns:
        result["Category / Size / Type"] = ""
    result["Category / Size / Type"] = result["Category / Size / Type"].fillna("").astype(str).str.strip()
    result["Sales Quantity"] = to_number(result.get("Sales Quantity", pd.Series(0, index=result.index))).fillna(0)
    result["Sales Amount"] = to_number(result.get("Sales Amount", pd.Series(0, index=result.index))).fillna(0)
    if "Sales Date" not in result.columns:
        result["Sales Date"] = pd.NaT
    else:
        result["Sales Date"] = pd.to_datetime(result["Sales Date"], errors="coerce", dayfirst=True)
    if "Sales Month" in result.columns:
        month = pd.to_datetime(result["Sales Month"].astype(str) + "-01", errors="coerce")
        fallback = pd.to_datetime(result["Sales Month"], errors="coerce", dayfirst=True)
        result["Sales Month"] = month.fillna(fallback).dt.to_period("M").dt.to_timestamp()
    else:
        result["Sales Month"] = result["Sales Date"].dt.to_period("M").dt.to_timestamp()
    result["Sales Month"] = result["Sales Month"].fillna(_default_sales_month(fy))
    result["FY"] = result.get("FY", fy)
    return result


def _prepare_standardized_stock(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result.columns = [str(col).strip().lstrip("\ufeff") for col in result.columns]
    result = result.dropna(how="all")
    result["Item Name"] = result.get("Item Name", "").fillna("").astype(str).str.strip()
    result = result[result["Item Name"].ne("")].copy()
    result["Normalized Item Name"] = result["Item Name"].map(normalize_text)
    if "Item Key" not in result.columns:
        result["Item Key"] = ""
    if "Item Code / SKU" not in result.columns:
        result["Item Code / SKU"] = ""
    result["Item Key"] = result["Item Key"].fillna("").astype(str).str.strip().map(normalize_text)
    result["Item Code / SKU"] = result["Item Code / SKU"].fillna("").astype(str).str.strip()
    blank_key = result["Item Key"].eq("")
    result.loc[blank_key, "Item Key"] = result.loc[blank_key, "Item Code / SKU"].map(normalize_text)
    blank_key = result["Item Key"].eq("")
    result.loc[blank_key, "Item Key"] = result.loc[blank_key, "Normalized Item Name"]
    result["Item Code / SKU"] = result["Item Code / SKU"].where(result["Item Code / SKU"].ne(""), result["Item Key"])
    if "Current Stock Qty" not in result.columns:
        result["Current Stock Qty"] = result.get("Current Stock Quantity", 0)
    result["Current Stock Qty"] = to_number(result["Current Stock Qty"]).fillna(0)
    result["Purchase Price"] = to_number(result.get("Purchase Price", pd.Series(0, index=result.index))).fillna(0)
    if "Box / Pack Quantity" not in result.columns:
        result["Box / Pack Quantity"] = result.get("Box Size / Pack Size / MOQ", pd.NA)
    result["Box / Pack Quantity"] = to_number(result["Box / Pack Quantity"])
    if "Supplier Name" not in result.columns:
        result["Supplier Name"] = "Unknown Supplier"
    result["Supplier Name"] = result["Supplier Name"].fillna("Unknown Supplier").astype(str).str.strip()
    result.loc[result["Supplier Name"].isin(["", "nan", "None", "NaN"]), "Supplier Name"] = "Unknown Supplier"
    if "Category / Size / Type" not in result.columns:
        result["Category / Size / Type"] = "Uncategorized"
    result["Category / Size / Type"] = result["Category / Size / Type"].fillna("Uncategorized").astype(str).str.strip()
    result.loc[result["Category / Size / Type"].isin(["", "nan", "None", "NaN"]), "Category / Size / Type"] = "Uncategorized"
    if "Unit" not in result.columns:
        result["Unit"] = "Qty"
    return result


def load_sales_files(paths: list[Path], mappings: dict[str, dict[str, str | None]] | None = None) -> tuple[pd.DataFrame, dict[str, dict[str, str | None]]]:
    frames = []
    used_mappings = {}
    for path in paths:
        fy = get_sales_year_from_path(path)
        raw = read_csv_flexible(path)
        if _looks_standardized_sales(raw):
            frames.append(_prepare_standardized_sales(raw, fy))
            used_mappings[fy] = mappings.get(fy, {}) if mappings else {}
            continue
        mapping = mappings.get(fy) if mappings else detect_columns(raw.columns, "sales")
        used_mappings[fy] = mapping
        frames.append(clean_sales(raw, mapping, fy))
    if not frames:
        return pd.DataFrame(), used_mappings
    return pd.concat(frames, ignore_index=True), used_mappings


def load_stock_file(path: Path, mapping: dict[str, str | None] | None = None) -> tuple[pd.DataFrame, dict[str, str | None]]:
    raw = read_csv_flexible(path)
    if _looks_standardized_stock(raw):
        return _prepare_standardized_stock(raw), mapping or {}
    mapping = mapping or detect_columns(raw.columns, "stock")
    return clean_stock(raw, mapping), mapping
