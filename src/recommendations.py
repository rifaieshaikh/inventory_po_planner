from __future__ import annotations

import pandas as pd

from .utils import ensure_required_output_columns


def build_executive_summary(detail: pd.DataFrame) -> pd.DataFrame:
    detail = ensure_required_output_columns(detail)
    total_items = len(detail)
    very_fast = int(detail["Velocity Class"].eq("Very Fast Moving").sum())
    fast = int(detail["Velocity Class"].eq("Fast Moving").sum())
    medium = int(detail["Velocity Class"].eq("Medium Moving").sum())
    slow = int(detail["Velocity Class"].eq("Slow Moving").sum())
    dormant = int(detail["Velocity Class"].eq("Dormant").sum())
    dead = int(detail["Velocity Class"].eq("Dead Stock / No Sales").sum())
    purchase = int(detail["Final PO Quantity"].gt(0).sum())
    urgent = int(detail["Purchase Priority"].eq("Urgent").sum())
    high = int(detail["Purchase Priority"].eq("High").sum())
    value = float(detail["Estimated Purchase Value"].sum())
    overstock_value = float(detail.loc[detail["Stock Risk Level"].eq("Overstock Risk"), "Current Stock Qty"].mul(detail["Purchase Price"]).sum())
    skipped_overstock = int(detail["PO Optimization Decision"].astype(str).str.contains("overstock|excess", case=False, na=False).sum()) if "PO Optimization Decision" in detail else 0
    deferred_budget = int(detail["Included In Budget PO"].eq("No").sum()) if "Included In Budget PO" in detail else 0
    health = "Healthy"
    if urgent > 0:
        health = "Urgent replenishment needed for fast movers"
    elif skipped_overstock > 0:
        health = "Cash protected by skipping overstock lines"
    elif purchase / max(total_items, 1) > 0.35:
        health = "Broad replenishment required, review budget"
    risks = []
    if dead:
        risks.append(f"{dead} dead/no-sales items should not be reordered.")
    if urgent:
        risks.append(f"{urgent} urgent items have low recent coverage.")
    if high:
        risks.append(f"{high} high-priority items are below target coverage.")
    return pd.DataFrame(
        [
            ["Total items analyzed", total_items],
            ["Very Fast Moving items", very_fast],
            ["Fast Moving items", fast],
            ["Medium Moving items", medium],
            ["Slow Moving items", slow],
            ["Dormant items", dormant],
            ["Dead stock items", dead],
            ["Items recommended for purchase", purchase],
            ["Urgent PO items", urgent],
            ["High PO items", high],
            ["Total PO value", value],
            ["PO value by priority", detail.groupby("Purchase Priority")["Estimated Purchase Value"].sum().to_dict()],
            ["Potential overstock value", overstock_value],
            ["Items skipped due to overstock risk", skipped_overstock],
            ["Items deferred due to budget", deferred_budget],
            ["Overall stock health", health],
            ["Key risks", " ".join(risks) if risks else "No major risks detected."],
        ],
        columns=["Metric", "Value"],
    )


def supplier_ready_po(final_po: pd.DataFrame) -> pd.DataFrame:
    final_po = ensure_required_output_columns(final_po)
    if "Assigned Supplier Name" in final_po.columns:
        final_po["Supplier Name"] = final_po["Assigned Supplier Name"].fillna("Unknown Supplier")
    if "Is Discontinued" in final_po.columns:
        final_po = final_po[final_po["Is Discontinued"].astype(str).str.upper().ne("YES")]
    po_items = final_po[final_po["Final PO Quantity"] > 0].copy()
    columns = [
        "Supplier Name",
        "Sl No",
        "Item Code / SKU",
        "Item Name",
        "Category Name",
        "Category Box Qty",
        "Quantity",
        "Boxes",
        "Unit",
        "Purchase Price",
        "Total Amount",
    ]
    if po_items.empty:
        return pd.DataFrame(columns=columns)

    po_items["Supplier Name"] = po_items["Supplier Name"].fillna("Unknown Supplier").astype(str).str.strip()
    po_items["Supplier Name"] = po_items["Supplier Name"].replace(["", "nan", "None", "NaN"], "Unknown Supplier")
    po_items["Category Name"] = po_items.get("Category Name", po_items.get("Category / Size / Type", "Uncategorized")).fillna("Uncategorized")
    po_items["Category Box Qty"] = pd.to_numeric(po_items.get("Category Box Qty", 0), errors="coerce").fillna(0)

    rows = []
    for supplier, group in po_items.groupby("Supplier Name", dropna=False):
        supplier = supplier or "Unknown Supplier"
        group = group.reset_index(drop=True)
        for idx, row in group.iterrows():
            qty = float(row.get("Final PO Quantity", 0) or 0)
            box_qty = float(row.get("Category Box Qty", 0) or 0)
            rows.append(
                {
                    "Supplier Name": supplier,
                    "Sl No": idx + 1,
                    "Item Code / SKU": row.get("Item Code / SKU", ""),
                    "Item Name": row.get("Item Name", ""),
                    "Category Name": row.get("Category Name", row.get("Category / Size / Type", "Uncategorized")),
                    "Category Box Qty": box_qty,
                    "Quantity": qty,
                    "Boxes": float(np.ceil(qty / box_qty)) if box_qty > 0 and qty > 0 else 0,
                    "Unit": row.get("Unit", "Meters"),
                    "Purchase Price": row.get("Purchase Price", 0),
                    "Total Amount": qty * float(row.get("Purchase Price", 0) or 0),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def category_size_summary(detail: pd.DataFrame) -> pd.DataFrame:
    temp = detail.copy()
    temp["Category"] = temp["Category / Size / Type"].replace("", "Uncategorized")
    recent_col = "Recent Monthly Velocity Qty" if "Recent Monthly Velocity Qty" in temp.columns else "Recent Average Monthly Sales Qty"
    grouped = temp.groupby("Category", dropna=False).agg(
        **{
            "Total Sales Qty": ("Total Sales Qty", "sum"),
            "Recent Sales Qty": (recent_col, "sum"),
            "Current Stock Qty": ("Current Stock Qty", "sum"),
            "Final PO Quantity": ("Final PO Quantity", "sum"),
            "PO Value": ("Estimated Purchase Value", "sum"),
            "Trend direction": ("Sales Trend", lambda x: x.value_counts().idxmax() if len(x) else ""),
        }
    ).reset_index()
    grouped["Size"] = grouped["Category"]
    return grouped[["Category", "Size", "Total Sales Qty", "Recent Sales Qty", "Current Stock Qty", "Final PO Quantity", "PO Value", "Trend direction"]]


def business_recommendations(detail: pd.DataFrame, category_summary: pd.DataFrame) -> pd.DataFrame:
    detail = ensure_required_output_columns(detail)
    recs = []
    urgent = detail[detail["Purchase Priority"].eq("Urgent")].sort_values("Recent Monthly Velocity Qty", ascending=False).head(10)
    recs.append(("Order immediately", "These items have high sales velocity and less than 15 days of stock cover: " + (", ".join(urgent["Item Name"].tolist()) or "None.")))
    no_order = detail[detail["Velocity Class"].isin(["Dormant", "Dead Stock / No Sales"])].head(10)
    recs.append(("Do not order", "These items have no recent sales and current stock may already be blocked: " + (", ".join(no_order["Item Name"].tolist()) or "None.")))
    rising = detail[detail["Sales Trend"].isin(["Strong Upward Trend", "Upward Trend", "New Moving Item"])].head(10)
    recs.append(("Monitor", "These items are showing recent upward movement, but history may still be limited: " + (", ".join(rising["Item Name"].tolist()) or "None.")))
    declining = detail[detail["Sales Trend"].isin(["Downward Trend", "Strong Downward Trend"])].head(10)
    recs.append(("Reduce purchase", "These items are declining, so recent velocity is used instead of old average: " + (", ".join(declining["Item Name"].tolist()) or "None.")))
    rounding = detail[detail["Rounding Warning"].astype(str).ne("")].head(10) if "Rounding Warning" in detail.columns else detail.head(0)
    recs.append(("Box rounding warning", "MOQ creates extra stock. Purchase only if supplier does not allow smaller quantity: " + (", ".join(rounding["Item Name"].tolist()) or "None.")))
    overstock = detail[detail["Stock Risk Level"].eq("Overstock Risk")].head(10)
    recs.append(("Cash optimization", "PO is reduced by avoiding slow-moving items that would otherwise receive unnecessary 3-month stock: " + (", ".join(overstock["Item Name"].tolist()) or "None.")))
    deferred = detail[detail["Included In Budget PO"].eq("No")].head(10)
    recs.append(("Budget control", "These PO lines are deferred due to the purchase budget: " + (", ".join(deferred["Item Name"].tolist()) or "None.")))
    total_value = detail["Estimated Purchase Value"].sum()
    recs.append(("PO value health", f"Optimized PO value is {total_value:,.2f}; amount is used for budget control only, while planning remains quantity-based."))
    return pd.DataFrame(recs, columns=["Recommendation Area", "Recommendation"])
