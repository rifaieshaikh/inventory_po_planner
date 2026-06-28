from __future__ import annotations

import pandas as pd

from .column_mapper import quantity_candidate_columns, validate_sales_quantity_column
from .edge_band_rules import detect_edge_band_size
from .utils import normalize_text


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.replace(" ", "", regex=False),
        errors="coerce",
    )


def _find_column(columns, names: list[str]) -> str | None:
    lookup = {str(col).strip().lower(): col for col in columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def choose_sales_quantity_column(df: pd.DataFrame, mapping: dict[str, str | None]) -> str | None:
    selected = mapping.get("sales_qty")
    error = validate_sales_quantity_column(selected)
    if error:
        raise ValueError(error)

    candidates = quantity_candidate_columns(df.columns)
    if selected and selected not in candidates:
        candidates.insert(0, selected)
    if not candidates:
        return selected

    amount_col = mapping.get("sales_amount") or _find_column(df.columns, ["Amount", "Net Amount", "Total Amount"])
    rate_col = _find_column(df.columns, ["Rate", "Selling Price", "Price"])
    invoice_col = _find_column(df.columns, ["Invoice No", "Invoice Number", "Bill No"])
    amount = _to_number(df[amount_col]) if amount_col else None
    rate = _to_number(df[rate_col]) if rate_col else None
    invoice = _to_number(df[invoice_col]) if invoice_col else None

    best_col = selected or candidates[0]
    best_score = -10**9
    for col in candidates:
        qty = _to_number(df[col])
        nonzero = qty[qty.gt(0)]
        if nonzero.empty:
            score = -1000
        else:
            score = 0.0
            score += min(len(nonzero), 500) / 10
            score -= float(nonzero.median()) / 100000
            if str(col) == str(selected):
                score += 5
            if amount is not None and rate is not None:
                denom = (rate * qty).replace(0, pd.NA)
                ratio = (amount / denom).replace([float("inf"), -float("inf")], pd.NA).dropna()
                if not ratio.empty:
                    close_taxed = ratio.between(1.15, 1.21).mean()
                    close_plain = ratio.between(0.95, 1.05).mean()
                    score += max(close_taxed, close_plain) * 100
            if invoice is not None and qty.equals(invoice):
                score -= 200
            elif invoice is not None and qty.corr(invoice) == 1:
                score -= 75
            if nonzero.nunique() <= 2 and len(nonzero) > 20:
                score -= 25
        if score > best_score:
            best_score = score
            best_col = col
    mapping["sales_qty"] = best_col
    return best_col


def clean_sales(df: pd.DataFrame, mapping: dict[str, str | None], fy: str) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(col).strip().lstrip("\ufeff") for col in df.columns]
    df = df.dropna(how="all")
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()

    item_col = mapping.get("item_name")
    qty_col = choose_sales_quantity_column(df, mapping)
    code_col = mapping.get("item_code")
    date_col = mapping.get("sales_date")
    amount_col = mapping.get("sales_amount")
    category_col = mapping.get("category")

    result = pd.DataFrame(index=df.index)
    result["FY"] = fy
    result["Item Name"] = df[item_col].fillna("").astype(str).str.strip() if item_col else ""
    result["Normalized Item Name"] = result["Item Name"].map(normalize_text)
    result["Item Code / SKU"] = df[code_col].fillna("").astype(str).str.strip() if code_col else ""
    result["Item Code / SKU"] = result["Item Code / SKU"].where(result["Item Code / SKU"].ne(""), result["Normalized Item Name"])
    result["Category / Size / Type"] = df[category_col].fillna("").astype(str).str.strip() if category_col else ""
    result["Sales Quantity"] = _to_number(df[qty_col]).fillna(0) if qty_col else 0
    result["Sales Amount"] = _to_number(df[amount_col]).fillna(0) if amount_col else 0
    if date_col:
        result["Sales Date"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
    else:
        result["Sales Date"] = pd.NaT
    result["Sales Month"] = result["Sales Date"].dt.to_period("M").dt.to_timestamp()
    if not date_col or result["Sales Date"].notna().sum() == 0:
        missing_month = result["Sales Month"].isna()
        result.loc[missing_month, "Sales Month"] = pd.to_datetime("20" + fy[-2:] + "-03-01", errors="coerce")
    detected = result["Item Name"].map(detect_edge_band_size)
    result["Detected Size"] = detected.map(lambda x: x[0])
    result["Detected Box Qty"] = detected.map(lambda x: x[1])
    return result


def clean_stock(df: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(col).strip().lstrip("\ufeff") for col in df.columns]
    df = df.dropna(how="all")
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()

    item_col = mapping.get("item_name")
    code_col = mapping.get("item_code")
    stock_col = mapping.get("stock_qty")
    price_col = mapping.get("purchase_price")
    supplier_col = mapping.get("supplier")
    pack_col = mapping.get("pack_size")
    category_col = mapping.get("category")

    result = pd.DataFrame()
    result["Item Name"] = df[item_col].fillna("").astype(str).str.strip() if item_col else ""
    result["Normalized Item Name"] = result["Item Name"].map(normalize_text)
    result["Item Code / SKU"] = df[code_col].fillna("").astype(str).str.strip() if code_col else ""
    result["Item Code / SKU"] = result["Item Code / SKU"].where(result["Item Code / SKU"].ne(""), result["Normalized Item Name"])
    result["Category / Size / Type"] = df[category_col].fillna("").astype(str).str.strip() if category_col else ""
    result["Current Stock Qty"] = _to_number(df[stock_col]).fillna(0) if stock_col else 0
    result["Purchase Price"] = _to_number(df[price_col]).fillna(0) if price_col else 0
    if supplier_col:
        result["Supplier Name"] = df[supplier_col].fillna("Unknown Supplier").astype(str).str.strip()
        result.loc[result["Supplier Name"].isin(["", "nan", "None", "NaN"]), "Supplier Name"] = "Unknown Supplier"
    else:
        result["Supplier Name"] = "Unknown Supplier"
    result["Box / Pack Quantity"] = _to_number(df[pack_col]) if pack_col else pd.NA
    detected = result["Item Name"].map(detect_edge_band_size)
    result["Detected Size"] = detected.map(lambda x: x[0])
    result["Detected Box Qty"] = detected.map(lambda x: x[1])
    result["Box / Pack Quantity"] = result["Box / Pack Quantity"].fillna(result["Detected Box Qty"])
    result["Unit"] = "Qty"
    result.loc[result["Detected Box Qty"].notna(), "Unit"] = "Meters"
    return result
