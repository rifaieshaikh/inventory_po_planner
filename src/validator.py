from __future__ import annotations

import pandas as pd


def _issue(issue_type: str, severity: str, item_code: str, item_name: str, details: str) -> dict[str, str]:
    return {
        "Issue Type": issue_type,
        "Severity": severity,
        "Item Code / SKU": item_code,
        "Item Name": item_name,
        "Details": details,
    }


def validate_data(sales: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    issues: list[dict[str, str]] = []
    if not sales.empty:
        missing_codes = sales[sales["Item Code / SKU"].eq(sales["Normalized Item Name"])]
        for _, row in missing_codes.drop_duplicates("Item Code / SKU").iterrows():
            issues.append(_issue("Missing item code", "Medium", row["Item Code / SKU"], row["Item Name"], "Using normalized item name as SKU."))
        zero_sales = sales[sales["Sales Quantity"].fillna(0).le(0)]
        for _, row in zero_sales.head(200).iterrows():
            issues.append(_issue("Zero or blank sales quantity", "Low", row["Item Code / SKU"], row["Item Name"], "Sales quantity is zero or blank."))

    if not stock.empty:
        missing_codes = stock[stock["Item Code / SKU"].eq(stock["Normalized Item Name"])]
        for _, row in missing_codes.drop_duplicates("Item Code / SKU").iterrows():
            issues.append(_issue("Missing item code", "Medium", row["Item Code / SKU"], row["Item Name"], "Using normalized item name as SKU."))
        dupes = stock[stock["Item Code / SKU"].duplicated(keep=False)]
        for _, row in dupes.drop_duplicates("Item Code / SKU").iterrows():
            issues.append(_issue("Duplicate item code", "High", row["Item Code / SKU"], row["Item Name"], "Duplicate SKU found in stock data."))
        for _, row in stock[stock["Purchase Price"].fillna(0).le(0)].iterrows():
            issues.append(_issue("Missing purchase price", "High", row["Item Code / SKU"], row["Item Name"], "Purchase price is missing or zero."))
        supplier = stock["Supplier Name"] if "Supplier Name" in stock.columns else pd.Series("Unknown Supplier", index=stock.index)
        missing_supplier_mask = supplier.fillna("Unknown Supplier").astype(str).str.strip().isin(["", "nan", "None", "NaN", "Unknown Supplier"])
        missing_supplier_count = int(missing_supplier_mask.sum())
        if missing_supplier_count:
            issues.append(
                _issue(
                    "Missing Supplier Name",
                    "Warning",
                    "",
                    "",
                    f"Yes / {missing_supplier_count} item(s) missing supplier. Items are grouped under Unknown Supplier.",
                )
            )
        for _, row in stock[stock["Box / Pack Quantity"].isna()].iterrows():
            issues.append(_issue("Missing box size / MOQ / pack size", "Low", row["Item Code / SKU"], row["Item Name"], "No pack size and no edge-band rule detected."))
        for _, row in stock[stock["Current Stock Qty"].fillna(0).lt(0)].iterrows():
            issues.append(_issue("Negative stock value", "High", row["Item Code / SKU"], row["Item Name"], "Current stock quantity is negative."))

    sales_keys = set(sales["Item Code / SKU"].dropna().unique()) if not sales.empty else set()
    stock_keys = set(stock["Item Code / SKU"].dropna().unique()) if not stock.empty else set()
    stock_lookup = stock.drop_duplicates("Item Code / SKU").set_index("Item Code / SKU")["Item Name"].to_dict() if not stock.empty else {}
    sales_lookup = sales.drop_duplicates("Item Code / SKU").set_index("Item Code / SKU")["Item Name"].to_dict() if not sales.empty else {}
    for sku in sorted(sales_keys - stock_keys):
        issues.append(_issue("Sales item missing in stock data", "High", sku, sales_lookup.get(sku, ""), "Item sold but not found in stock file."))
    for sku in sorted(stock_keys - sales_keys):
        issues.append(_issue("Stock item missing in sales data", "Low", sku, stock_lookup.get(sku, ""), "Item exists in stock but has no sales in selected years."))

    if not sales.empty and not stock.empty:
        sales_names = sales.drop_duplicates("Item Code / SKU").set_index("Item Code / SKU")["Normalized Item Name"]
        stock_names = stock.drop_duplicates("Item Code / SKU").set_index("Item Code / SKU")["Normalized Item Name"]
        for sku in sorted(sales_keys & stock_keys):
            if sales_names.get(sku) and stock_names.get(sku) and sales_names.get(sku) != stock_names.get(sku):
                issues.append(_issue("Item name mismatch", "Medium", sku, stock_lookup.get(sku, ""), "Sales and stock item names differ for the same SKU."))

    return pd.DataFrame(issues)


def validate_velocity_calculations(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if detail.empty:
        return pd.DataFrame(
            columns=[
                "Item Code / SKU",
                "Item Name",
                "Total Sales Qty",
                "Current Stock Qty",
                "Overall Monthly Velocity Qty",
                "Recent Sales Qty",
                "Recent Monthly Velocity Qty",
                "Weighted Velocity Qty",
                "Relevant Velocity Qty",
                "Warning Reason",
            ]
        )

    for _, row in detail.iterrows():
        reasons = []
        total = float(row.get("Total Sales Qty", 0) or 0)
        recent_sales = float(row.get("Recent Period Sales Qty", 0) or 0)
        overall = float(row.get("Overall Monthly Velocity Qty", 0) or 0)
        recent = float(row.get("Recent Monthly Velocity Qty", 0) or 0)
        weighted = float(row.get("Weighted Velocity Qty", 0) or 0)
        relevant = float(row.get("Relevant Velocity Qty", 0) or 0)
        stock = float(row.get("Current Stock Qty", 0) or 0)
        if overall > total and total > 0:
            reasons.append("Average monthly velocity is greater than total sales quantity.")
        if recent > recent_sales and recent_sales > 0:
            reasons.append("Recent monthly velocity is greater than recent sales quantity.")
        if relevant > total and total > 0:
            reasons.append("Relevant velocity is greater than total sales quantity.")
        if stock > 0 and relevant > stock * 5:
            reasons.append("Relevant velocity is more than 5x current stock.")
        if relevant > 100000 and total < relevant:
            reasons.append("Relevant velocity exceeds 100,000/month without supporting total sales.")
        if weighted > total and total > 0:
            reasons.append("Weighted velocity is greater than total sales quantity.")
        if reasons:
            rows.append(
                {
                    "Item Code / SKU": row.get("Item Code / SKU", ""),
                    "Item Name": row.get("Item Name", ""),
                    "Total Sales Qty": total,
                    "Current Stock Qty": stock,
                    "Overall Monthly Velocity Qty": overall,
                    "Recent Sales Qty": recent_sales,
                    "Recent Monthly Velocity Qty": recent,
                    "Weighted Velocity Qty": weighted,
                    "Relevant Velocity Qty": relevant,
                    "Warning Reason": " ".join(reasons),
                }
            )
    return pd.DataFrame(rows)
