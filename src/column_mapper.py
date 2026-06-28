from __future__ import annotations

import re


FIELD_ALIASES = {
    "item_code": ["item code", "sku", "code", "product code", "item no", "item id"],
    "item_name": ["item", "item name", "product", "product name", "description", "particulars"],
    "category": ["category", "size", "type", "group", "brand"],
    "sales_qty": ["qty", "quantity", "sales qty", "sale qty", "sold qty", "net qty", "billed qty", "meter", "mtr", "meters"],
    "sales_date": ["date", "invoice date", "bill date", "month", "sales month"],
    "sales_amount": ["amount", "sales amount", "value", "net amount", "total"],
    "stock_qty": ["stock", "closing stock", "current stock", "balance qty", "available qty", "qty"],
    "purchase_price": ["purchase price", "p.price", "cost", "rate", "buy price", "landing cost"],
    "supplier": ["supplier", "supplier name", "vendor"],
    "pack_size": ["box size", "moq", "pack size", "packing", "box qty"],
}

BAD_QUANTITY_TERMS = ["amount", "value", "total amount", "gross", "taxable", "rate", "price", "cost", "inr", "rs", "₹"]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def is_bad_quantity_column(column_name: str | None) -> bool:
    norm = _norm(column_name or "")
    return any(term in norm for term in BAD_QUANTITY_TERMS)


def validate_sales_quantity_column(column_name: str | None) -> str | None:
    if column_name and is_bad_quantity_column(column_name):
        return "Sales quantity column appears to be an amount/value column. Please remap quantity."
    return None


def quantity_candidate_columns(columns) -> list[str]:
    candidates = []
    for col in columns:
        norm = _norm(col)
        if is_bad_quantity_column(col):
            continue
        if norm in {"qty", "qty 1"} or "qty" in norm or norm in {"quantity", "meter", "meters", "mtr"}:
            candidates.append(col)
    return candidates


def detect_columns(columns, data_type: str) -> dict[str, str | None]:
    normalized = {_norm(col): col for col in columns}
    fields = (
        ["item_code", "item_name", "category", "sales_qty", "sales_date", "sales_amount"]
        if data_type == "sales"
        else ["item_code", "item_name", "category", "stock_qty", "purchase_price", "supplier", "pack_size"]
    )
    mapping: dict[str, str | None] = {}
    for field in fields:
        match = None
        for alias in FIELD_ALIASES[field]:
            alias_norm = _norm(alias)
            if alias_norm in normalized:
                match = normalized[alias_norm]
                break
        if match is None:
            for norm_col, original in normalized.items():
                if any(_norm(alias) in norm_col for alias in FIELD_ALIASES[field]):
                    match = original
                    break
        mapping[field] = match
    return mapping


def missing_required(mapping: dict[str, str | None], data_type: str) -> list[str]:
    required = ["item_name", "sales_qty"] if data_type == "sales" else ["item_name", "stock_qty", "purchase_price"]
    return [field for field in required if not mapping.get(field)]
