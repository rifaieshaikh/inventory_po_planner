from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .utils import normalize_text


QUANTITY_VALUE_ERROR = "Quantity column appears to be an amount/value column. Please select a real quantity column."


SALES_FIELD_SPECS = [
    {"field": "Item Name", "required": True},
    {"field": "Sales Quantity", "required": True},
    {"field": "Item Code / SKU", "required": False},
    {"field": "Sales Date", "required": False},
    {"field": "Sales Month", "required": False},
    {"field": "Category / Size / Type", "required": False},
    {"field": "Selling Price", "required": False},
    {"field": "Sales Amount", "required": False},
    {"field": "Invoice Number", "required": False},
    {"field": "Customer Name", "required": False},
    {"field": "Unit", "required": False},
]

STOCK_FIELD_SPECS = [
    {"field": "Item Name", "required": True},
    {"field": "Current Stock Quantity", "required": True},
    {"field": "Item Code / SKU", "required": False},
    {"field": "Category / Size / Type", "required": False},
    {"field": "Purchase Price", "required": False},
    {"field": "Supplier Name", "required": False},
    {"field": "Unit", "required": False},
    {"field": "Box Size / Pack Size / MOQ", "required": False},
    {"field": "Stock Value", "required": False},
    {"field": "Location / Rack", "required": False},
]

FIELD_SPECS = {
    "sales": SALES_FIELD_SPECS,
    "item-wise sales": SALES_FIELD_SPECS,
    "item-wise-sales": SALES_FIELD_SPECS,
    "stock": STOCK_FIELD_SPECS,
}

COLUMN_ALIASES = {
    "Item Name": [
        "item",
        "item name",
        "product",
        "product name",
        "description",
        "particulars",
        "material",
        "item description",
    ],
    "Sales Quantity": [
        "qty",
        "quantity",
        "sales qty",
        "sale qty",
        "sold qty",
        "net qty",
        "billed qty",
        "meter",
        "meters",
        "mtr",
        "quantity sold",
    ],
    "Current Stock Quantity": [
        "stock",
        "current stock",
        "closing stock",
        "balance qty",
        "available qty",
        "quantity",
        "qty",
        "stock qty",
        "physical stock",
        "current stock qty",
        "current stock quantity",
    ],
    "Item Code / SKU": [
        "item code",
        "sku",
        "product code",
        "material code",
        "code",
        "barcode",
        "item no",
        "item id",
    ],
    "Sales Date": ["date", "invoice date", "bill date", "sales date", "voucher date"],
    "Sales Month": ["month", "sales month", "period"],
    "Category / Size / Type": ["category", "type", "size", "group", "item group", "product group", "brand"],
    "Selling Price": ["selling price", "sale price", "sales price", "mrp", "price"],
    "Sales Amount": ["amount", "sales amount", "value", "net amount", "total", "taxable amount"],
    "Invoice Number": ["invoice number", "invoice no", "bill number", "bill no", "voucher no", "voucher number"],
    "Customer Name": ["customer", "customer name", "party", "party name"],
    "Supplier Name": ["supplier", "supplier name", "vendor", "vendor name"],
    "Purchase Price": ["purchase price", "cost", "rate", "buy price", "landing cost", "unit cost"],
    "Box Size / Pack Size / MOQ": [
        "box size",
        "box qty",
        "pack size",
        "moq",
        "minimum order qty",
        "carton qty",
        "qty per box",
        "packing",
    ],
    "Stock Value": ["stock value", "inventory value", "value", "amount"],
    "Location / Rack": ["location", "rack", "rack no", "bin", "warehouse"],
    "Unit": ["unit", "uom", "units"],
}

BAD_QUANTITY_TERMS = [
    "amount",
    "value",
    "total",
    "net amount",
    "gross",
    "taxable",
    "rate",
    "price",
    "cost",
    "inr",
    "rs",
    "rupee",
    "\u20b9",
    "a 1 2",
]
TOTAL_ROW_LABELS = {
    "TOTAL",
    "GRANDTOTAL",
    "SUBTOTAL",
    "TOTALQTY",
    "TOTALQUANTITY",
    "TOTALSTOCK",
    "TOTALSALES",
}

OLD_FIELD_TO_LOGICAL = {
    "item_code": "Item Code / SKU",
    "item_name": "Item Name",
    "category": "Category / Size / Type",
    "sales_qty": "Sales Quantity",
    "sales_date": "Sales Date",
    "sales_amount": "Sales Amount",
    "stock_qty": "Current Stock Quantity",
    "purchase_price": "Purchase Price",
    "supplier": "Supplier Name",
    "pack_size": "Box Size / Pack Size / MOQ",
}
LOGICAL_TO_OLD_FIELD = {logical: old for old, logical in OLD_FIELD_TO_LOGICAL.items()}


def _file_type_key(file_type: str) -> str:
    normalized = str(file_type or "").strip().lower()
    if normalized in {"item-wise sales", "item-wise-sales", "sales"}:
        return "sales"
    if normalized == "stock":
        return "stock"
    raise ValueError(f"Unsupported file type: {file_type}")


def _norm(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()


def get_field_specs(file_type: str) -> list[dict[str, Any]]:
    return [dict(spec) for spec in FIELD_SPECS[_file_type_key(file_type)]]


def get_required_fields(file_type: str) -> list[str]:
    return [spec["field"] for spec in get_field_specs(file_type) if spec["required"]]


def get_optional_fields(file_type: str) -> list[str]:
    return [spec["field"] for spec in get_field_specs(file_type) if not spec["required"]]


def is_bad_quantity_column(column_name: str | None) -> bool:
    norm = _norm(column_name or "")
    return any(_norm(term) and _norm(term) in norm for term in BAD_QUANTITY_TERMS)


def is_total_row_label(value: object) -> bool:
    normalized = normalize_text(value)
    compact = re.sub(r"[^A-Z0-9]+", "", normalized)
    return compact in TOTAL_ROW_LABELS


def _is_quantity_field(field: str, file_type: str) -> bool:
    key = _file_type_key(file_type)
    return (key == "sales" and field == "Sales Quantity") or (
        key == "stock" and field == "Current Stock Quantity"
    )


def _column_lookup(columns: list[object]) -> dict[str, str]:
    return {_norm(col): str(col) for col in columns}


def _find_alias_match(columns: list[object], field: str, file_type: str) -> str | None:
    normalized = _column_lookup(columns)
    aliases = COLUMN_ALIASES.get(field, [])
    for alias in aliases:
        alias_norm = _norm(alias)
        candidate = normalized.get(alias_norm)
        if candidate and not (_is_quantity_field(field, file_type) and is_bad_quantity_column(candidate)):
            return candidate
    for norm_col, original in normalized.items():
        if _is_quantity_field(field, file_type) and is_bad_quantity_column(original):
            continue
        if any(_norm(alias) and _norm(alias) in norm_col for alias in aliases):
            return original
    return None


def detect_column_mapping(df: pd.DataFrame, file_type: str) -> dict[str, str | None]:
    mapping: dict[str, str | None] = {}
    columns = list(df.columns)
    for spec in get_field_specs(file_type):
        mapping[spec["field"]] = _find_alias_match(columns, spec["field"], file_type)
    return mapping


def _issue(severity: str, field: str, message: str, row_count: int = 0, examples: list[Any] | None = None) -> dict[str, Any]:
    return {
        "Severity": severity,
        "Field": field,
        "Message": message,
        "Row Count": int(row_count or 0),
        "Example Values": ", ".join([str(value) for value in (examples or [])[:5] if str(value) != ""]),
    }


def clean_text_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def to_number(series: pd.Series) -> pd.Series:
    cleaned = (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("\u20b9", "", regex=False)
        .str.replace("INR", "", case=False, regex=False)
        .str.replace("Rs.", "", case=False, regex=False)
        .str.replace("Rs", "", case=False, regex=False)
        .str.replace(" ", "", regex=False)
    )
    cleaned = cleaned.str.replace(r"[^0-9.\-()]", "", regex=True)
    cleaned = cleaned.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def _series_from_mapping(df: pd.DataFrame, mapping: dict[str, str | None], field: str) -> pd.Series:
    column = mapping.get(field)
    if column and column in df.columns:
        return df[column]
    return pd.Series([""] * len(df), index=df.index, dtype=object)


def _numeric_quality_issue(df: pd.DataFrame, mapping: dict[str, str | None], field: str) -> dict[str, Any] | None:
    column = mapping.get(field)
    if not column or column not in df.columns:
        return None
    raw = df[column]
    nonblank_mask = raw.fillna("").astype(str).str.strip().ne("")
    nonblank_count = int(nonblank_mask.sum())
    if nonblank_count == 0:
        return _issue("Error", field, f"{field} has no values.", 0, [])
    converted = to_number(raw)
    bad_mask = nonblank_mask & converted.isna()
    bad_count = int(bad_mask.sum())
    if bad_count > nonblank_count / 2:
        return _issue(
            "Error",
            field,
            f"{field} cannot be converted to numeric for most rows.",
            bad_count,
            raw[bad_mask].head(5).tolist(),
        )
    if bad_count:
        return _issue(
            "Warning",
            field,
            f"{field} has some values that could not be converted to numeric.",
            bad_count,
            raw[bad_mask].head(5).tolist(),
        )
    return None


def validate_mapping(df: pd.DataFrame, mapping: dict, file_type: str) -> list[dict]:
    key = _file_type_key(file_type)
    issues: list[dict[str, Any]] = []
    columns = set(map(str, df.columns))
    mapping = normalize_mapping(mapping, file_type)

    for field in get_required_fields(key):
        column = mapping.get(field)
        if not column or column == "Not Available":
            issues.append(_issue("Error", field, f"{field} not mapped."))
        elif column not in columns:
            issues.append(_issue("Error", field, f"Mapped column '{column}' is missing from the uploaded file."))

    for field, column in mapping.items():
        if column and column != "Not Available" and column not in columns:
            issues.append(_issue("Warning", field, f"Mapped column '{column}' is missing from the uploaded file."))

    qty_field = "Sales Quantity" if key == "sales" else "Current Stock Quantity"
    qty_column = mapping.get(qty_field)
    if qty_column and is_bad_quantity_column(qty_column):
        issues.append(_issue("Error", qty_field, QUANTITY_VALUE_ERROR))

    qty_quality = _numeric_quality_issue(df, mapping, qty_field)
    if qty_quality:
        issues.append(qty_quality)

    item_col = mapping.get("Item Name")
    if item_col in df.columns:
        item_blank = clean_text_series(df[item_col]).eq("")
        blank_count = int(item_blank.sum())
        if blank_count:
            issues.append(_issue("Warning", "Item Name", "Rows with blank Item Name will be dropped.", blank_count, []))
        total_mask = df[item_col].map(is_total_row_label)
        total_count = int(total_mask.sum())
        if total_count:
            issues.append(_issue("Info", "Item Name", "Rows marked TOTAL will be excluded.", total_count, df.loc[total_mask, item_col].head(5).tolist()))

    if key == "sales":
        if not mapping.get("Sales Date") and not mapping.get("Sales Month"):
            issues.append(
                _issue(
                    "Warning",
                    "Sales Period",
                    "Sales Date/Month is not mapped. FY-level period assumptions will be used.",
                )
            )
        qty_col = mapping.get("Sales Quantity")
        if qty_col in df.columns:
            qty = to_number(df[qty_col])
            blank_qty = int(qty.isna().sum())
            if blank_qty:
                issues.append(_issue("Warning", "Sales Quantity", "Rows with blank Sales Quantity will use 0.", blank_qty, []))
            neg_qty = qty.lt(0)
            if int(neg_qty.sum()):
                issues.append(_issue("Warning", "Sales Quantity", "Negative Sales Quantity found.", int(neg_qty.sum()), df.loc[neg_qty, qty_col].head(5).tolist()))
    else:
        stock_quality = _numeric_quality_issue(df, mapping, "Current Stock Quantity")
        if stock_quality and stock_quality not in issues:
            issues.append(stock_quality)
        if not mapping.get("Supplier Name"):
            issues.append(_issue("Info", "Supplier Name", "Supplier is not mapped. Unknown Supplier will be used."))
        if not mapping.get("Category / Size / Type"):
            issues.append(_issue("Info", "Category / Size / Type", "Category is not mapped. Existing item category mapping or Uncategorized will be used."))
        price_col = mapping.get("Purchase Price")
        if price_col in df.columns:
            price = to_number(df[price_col])
            blank_price = int(price.isna().sum())
            if blank_price:
                issues.append(_issue("Warning", "Purchase Price", "Blank Purchase Price will use 0.", blank_price, []))

    return issues


def has_blocking_errors(issues: list[dict]) -> bool:
    return any(str(issue.get("Severity", "")).lower() == "error" for issue in issues)


def _default_sales_month(fy: str | None) -> pd.Timestamp:
    fy_text = str(fy or "").strip()
    match = re.search(r"(\d{2})\s*[-/]\s*(\d{2})", fy_text)
    if match:
        return pd.Timestamp(year=2000 + int(match.group(2)), month=3, day=1)
    return pd.Timestamp.today().normalize().replace(day=1)


def _to_month(series: pd.Series, fy: str | None = None) -> pd.Series:
    text = clean_text_series(series)
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    month = parsed.dt.to_period("M").dt.to_timestamp()
    if month.isna().all():
        month = pd.Series([_default_sales_month(fy)] * len(series), index=series.index, dtype="datetime64[ns]")
    else:
        month = month.fillna(_default_sales_month(fy))
    return month


def _date_to_output(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
    return parsed.dt.strftime("%Y-%m-%d").fillna("")


def _mapping_value(mapping: dict[str, str | None], field: str) -> str | None:
    value = mapping.get(field)
    if not value or value == "Not Available":
        return None
    return str(value)


def normalize_mapping(mapping: dict | None, file_type: str) -> dict[str, str | None]:
    normalized: dict[str, str | None] = {spec["field"]: None for spec in get_field_specs(file_type)}
    if not mapping:
        return normalized
    for key, value in mapping.items():
        logical = OLD_FIELD_TO_LOGICAL.get(str(key), str(key))
        if logical in normalized:
            normalized[logical] = None if value in ("", "Not Available") else value
    return normalized


def _lookup_category(item_key: str, item_code: str, item_name: str, category_lookup: dict[str, str] | None) -> str:
    if not category_lookup:
        return "Uncategorized"
    for key in [item_key, normalize_text(item_code), normalize_text(item_name)]:
        if key and category_lookup.get(key):
            return category_lookup[key]
    return "Uncategorized"


def apply_mapping(
    df: pd.DataFrame,
    mapping: dict,
    file_type: str,
    context: dict,
) -> pd.DataFrame:
    key = _file_type_key(file_type)
    mapping = normalize_mapping(mapping, key)
    source = str(context.get("source_file_name", ""))
    store_id = str(context.get("store_id", ""))
    store_name = str(context.get("store_name", ""))
    source_row = pd.Series(df.index + 2, index=df.index)
    cleaned = df.copy()
    cleaned.columns = [str(col).strip().lstrip("\ufeff") for col in cleaned.columns]
    cleaned = cleaned.dropna(how="all")

    item = clean_text_series(_series_from_mapping(cleaned, mapping, "Item Name"))
    keep = item.ne("") & ~item.map(is_total_row_label)
    cleaned = cleaned.loc[keep].copy()
    item = item.loc[keep]
    source_row = source_row.loc[keep]
    item_code_raw = clean_text_series(_series_from_mapping(cleaned, mapping, "Item Code / SKU"))
    item_key = item_code_raw.map(normalize_text)
    fallback_key = item.map(normalize_text)
    item_key = item_key.where(item_key.ne(""), fallback_key)
    item_code = item_code_raw.where(item_code_raw.ne(""), item_key)
    category = clean_text_series(_series_from_mapping(cleaned, mapping, "Category / Size / Type"))

    if key == "sales":
        fy = str(context.get("fy", ""))
        qty = to_number(_series_from_mapping(cleaned, mapping, "Sales Quantity")).fillna(0)
        selling_price = to_number(_series_from_mapping(cleaned, mapping, "Selling Price")).fillna(0)
        amount = to_number(_series_from_mapping(cleaned, mapping, "Sales Amount")).fillna(0)
        date_column = _mapping_value(mapping, "Sales Date")
        month_column = _mapping_value(mapping, "Sales Month")
        if date_column and date_column in cleaned.columns:
            sales_date = _date_to_output(cleaned[date_column])
            sales_month = _to_month(cleaned[date_column], fy)
        elif month_column and month_column in cleaned.columns:
            sales_date = pd.Series([""] * len(cleaned), index=cleaned.index)
            sales_month = _to_month(cleaned[month_column], fy)
        else:
            sales_date = pd.Series([""] * len(cleaned), index=cleaned.index)
            sales_month = pd.Series([_default_sales_month(fy)] * len(cleaned), index=cleaned.index, dtype="datetime64[ns]")
        result = pd.DataFrame(
            {
                "Store ID": store_id,
                "Store Name": store_name,
                "FY": fy,
                "Item Key": item_key,
                "Item Code / SKU": item_code,
                "Item Name": item,
                "Category / Size / Type": category,
                "Sales Date": sales_date,
                "Sales Month": sales_month.dt.strftime("%Y-%m"),
                "Sales Quantity": qty,
                "Selling Price": selling_price,
                "Sales Amount": amount,
                "Invoice Number": clean_text_series(_series_from_mapping(cleaned, mapping, "Invoice Number")),
                "Customer Name": clean_text_series(_series_from_mapping(cleaned, mapping, "Customer Name")),
                "Unit": clean_text_series(_series_from_mapping(cleaned, mapping, "Unit")),
                "Source Row Number": source_row,
                "Source File Name": source,
            }
        )
        return result.reset_index(drop=True)

    category_lookup = context.get("category_lookup") or {}
    category = [
        value if str(value).strip() else _lookup_category(item_key.iloc[pos], item_code.iloc[pos], item.iloc[pos], category_lookup)
        for pos, value in enumerate(category.tolist())
    ]
    supplier = clean_text_series(_series_from_mapping(cleaned, mapping, "Supplier Name"))
    supplier = supplier.where(~supplier.str.lower().isin(["", "nan", "none"]), "Unknown Supplier")
    result = pd.DataFrame(
        {
            "Store ID": store_id,
            "Store Name": store_name,
            "Item Key": item_key,
            "Item Code / SKU": item_code,
            "Item Name": item,
            "Category / Size / Type": category,
            "Current Stock Quantity": to_number(_series_from_mapping(cleaned, mapping, "Current Stock Quantity")).fillna(0),
            "Purchase Price": to_number(_series_from_mapping(cleaned, mapping, "Purchase Price")).fillna(0),
            "Supplier Name": supplier,
            "Unit": clean_text_series(_series_from_mapping(cleaned, mapping, "Unit")),
            "Box Size / Pack Size / MOQ": to_number(_series_from_mapping(cleaned, mapping, "Box Size / Pack Size / MOQ")),
            "Stock Value": to_number(_series_from_mapping(cleaned, mapping, "Stock Value")).fillna(0),
            "Location / Rack": clean_text_series(_series_from_mapping(cleaned, mapping, "Location / Rack")),
            "Source Row Number": source_row,
            "Source File Name": source,
        }
    )
    return result.reset_index(drop=True)


def load_mapping(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_mapping(path: Path, mapping: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2), encoding="utf-8")


def quantity_candidate_columns(columns) -> list[str]:
    candidates = []
    for col in columns:
        norm = _norm(col)
        if is_bad_quantity_column(str(col)):
            continue
        if norm in {"qty", "qty 1", "quantity", "meter", "meters", "mtr"} or "qty" in norm:
            candidates.append(col)
    return candidates


def validate_sales_quantity_column(column_name: str | None) -> str | None:
    if column_name and is_bad_quantity_column(column_name):
        return QUANTITY_VALUE_ERROR
    return None


def detect_columns(columns, data_type: str) -> dict[str, str | None]:
    empty = pd.DataFrame(columns=list(columns))
    logical = detect_column_mapping(empty, data_type)
    result: dict[str, str | None] = {}
    for old_field, logical_field in OLD_FIELD_TO_LOGICAL.items():
        if data_type == "sales" and old_field not in {"stock_qty", "purchase_price", "supplier", "pack_size"}:
            result[old_field] = logical.get(logical_field)
        elif data_type == "stock" and old_field not in {"sales_qty", "sales_date", "sales_amount"}:
            result[old_field] = logical.get(logical_field)
    return result


def missing_required(mapping: dict[str, str | None], data_type: str) -> list[str]:
    if data_type == "sales":
        required = ["item_name", "sales_qty"]
    else:
        required = ["item_name", "stock_qty"]
    return [field for field in required if not mapping.get(field)]
