from __future__ import annotations

import math
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from src import file_manager
from src.column_mapper import detect_columns, missing_required, validate_sales_quantity_column
from src.data_loader import load_sales_files, load_stock_file, read_csv_flexible
from src.debug_tools import item_debug_report
from src.excel_exporter import export_excel
from src.item_lookup import monthly_history_for_item, search_items
from src import master_data_manager as mdm
from src.po_calculator import calculate_po
from src.po_calculator import apply_discontinued_po_rules
from src.recommendations import build_executive_summary, business_recommendations, category_size_summary, supplier_ready_po
from src import result_store
from src.sales_analysis import analyze_sales
from src.stock_analysis import merge_stock_sales
from src.trend_analysis import analyze_trends
from src.utils import MOVEMENT_ORDER, PRIORITY_ORDER, REPORT_PATH, RISK_ORDER, ensure_required_output_columns, normalize_text
from src.validator import validate_data, validate_velocity_calculations


st.set_page_config(page_title="Inventory PO Planner", layout="wide")
file_manager.ensure_data_dirs()
mdm.ensure_master_files()
result_store.ensure_result_dirs()


DETAIL_COLUMNS = [
    "Item Code / SKU",
    "Item Key",
    "Supplier Name",
    "Assigned Supplier ID",
    "Assigned Supplier Name",
    "Supplier Source",
    "Is Discontinued",
    "Discontinued Date",
    "Discontinued Reason",
    "Item Name",
    "Category ID",
    "Category Name",
    "Category / Size / Type",
    "Category Box Qty",
    "Category Source",
    "Box Qty Source",
    "Total Sales Qty",
    "Overall Monthly Velocity Qty",
    "Recent Period Sales Qty",
    "Recent Monthly Velocity Qty",
    "Weighted Velocity Qty",
    "Velocity Percentile",
    "Velocity Class",
    "Sales Frequency %",
    "Recent Sales Frequency %",
    "Older Avg Monthly Sales Qty",
    "Recent Avg Monthly Sales Qty",
    "Trend Change %",
    "Sales Trend",
    "Monthly Sales Std Dev",
    "Sales CV",
    "Consistency Class",
    "Current Stock Qty",
    "Stock Coverage Months",
    "Recent Stock Coverage Months",
    "Relevant Velocity Qty",
    "Suggested Target Cover Months",
    "Required Stock Qty",
    "Required Boxes",
    "Exact Purchase Requirement Qty",
    "Box / Pack Quantity",
    "Rounded PO Qty",
    "Final PO Boxes",
    "Final PO Quantity",
    "Stock After PO Qty",
    "Stock Cover After PO Months",
    "Extra Stock Due To Rounding",
    "Extra Qty Due To Box Rounding",
    "Overstock After PO Flag",
    "Purchase Price",
    "Estimated Purchase Value",
    "Purchase Priority",
    "Stock Risk Level",
    "PO Optimization Decision",
    "Budget Priority Score",
    "Included In Budget PO",
    "Deferred Reason",
    "Budget Approved PO Quantity",
    "Budget Approved PO Value",
    "Reason for Recommendation",
]

FINAL_PO_COLUMNS = [
    "Supplier Name",
    "Assigned Supplier ID",
    "Assigned Supplier Name",
    "Item Code / SKU",
    "Item Key",
    "Item Name",
    "Category ID",
    "Category Name",
    "Category / Size / Type",
    "Category Box Qty",
    "Final PO Boxes",
    "Velocity Class",
    "Sales Trend",
    "Consistency Class",
    "Current Stock Qty",
    "Relevant Velocity Qty",
    "Suggested Target Cover Months",
    "Final PO Quantity",
    "Stock After PO Qty",
    "Stock Cover After PO Months",
    "Purchase Price",
    "Total Amount",
    "Purchase Priority",
    "Stock Risk Level",
    "Reason",
]


def modified_text(path: Path | None) -> str:
    if not path or not path.exists():
        return "Not available"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))


def widget_key(section: str, name: str, suffix: str = "") -> str:
    parts = [section, name]
    if suffix:
        parts.append(str(suffix))
    return "__".join(
        str(part).strip().replace(" ", "_").replace("/", "_").lower()
        for part in parts
        if part is not None and str(part).strip() != ""
    )


def mapping_editor(path: Path, data_type: str, key_prefix: str) -> dict[str, str | None]:
    raw = read_csv_flexible(path)
    detected = detect_columns(raw.columns, data_type)
    missing = missing_required(detected, data_type)
    if not missing:
        return detected
    with st.expander(f"Column mapping needed for {path.name}", expanded=True):
        st.warning(f"Could not auto-detect: {', '.join(missing)}")
        options = [""] + list(raw.columns)
        mapping = {}
        for field, current in detected.items():
            index = options.index(current) if current in options else 0
            choice = st.selectbox(field.replace("_", " ").title(), options, index=index, key=widget_key(key_prefix, field))
            mapping[field] = choice or None
        if data_type == "sales":
            qty_error = validate_sales_quantity_column(mapping.get("sales_qty"))
            if qty_error:
                st.error(qty_error)
        return mapping


def refresh_report() -> None:
    if stock_path and sales_paths:
        report = build_report(stock_path, sales_paths, settings, sales_mappings, stock_mapping)
        st.session_state["report"] = report
        run_id = result_store.save_analysis_result(
            report,
            settings,
            [path.parent.name for path in sales_paths],
            stock_path,
            sales_paths,
        )
        st.session_state["active_run_id"] = run_id
        st.session_state["active_result_source"] = "new_run"
        loaded = result_store.load_latest_result()
        if loaded:
            st.session_state["active_manifest"] = loaded["manifest"]
            st.session_state["active_result_path"] = str(loaded["path"])
            st.session_state["export_path"] = loaded["excel_path"]


def render_item_performance(row: pd.Series, monthly: pd.DataFrame, section_prefix: str = "item_popup") -> None:
    item_key = row.get("Item Key", "")
    item_name = row.get("Item Name", "")
    st.subheader(f"Item Performance: {item_name}")
    if str(row.get("Is Discontinued", "No")).upper() == "YES":
        st.warning("This item is discontinued. It will not be added to Final PO even if sales velocity exists.")
    if str(row.get("Category Name", "Uncategorized")).strip() == "Uncategorized":
        st.warning("This item is Uncategorized. Assign a category to enable proper box calculation.")

    sections = {
        "Basic Info": [
            "Item Code / SKU",
            "Item Name",
            "Item Key",
            "Category ID",
            "Category Name",
            "Category / Size / Type",
            "Category Box Qty",
            "Category Source",
            "Box Qty Source",
            "Assigned Supplier Name",
            "Supplier Source",
            "Is Discontinued",
            "Discontinued Reason",
        ],
        "Stock Info": ["Current Stock Qty", "Stock Coverage Months", "Recent Stock Coverage Months", "Stock Risk Level", "Overstock After PO Flag"],
        "Sales Velocity": [
            "Total Sales Qty",
            "Overall Monthly Velocity Qty",
            "Recent Monthly Velocity Qty",
            "Weighted Velocity Qty",
            "Relevant Velocity Qty",
            "Velocity Class",
            "Velocity Percentile",
            "Sales Frequency %",
            "Recent Sales Frequency %",
        ],
        "Trend": [
            "Older Avg Monthly Sales Qty",
            "Recent Avg Monthly Sales Qty",
            "Trend Change %",
            "Sales Trend",
            "Monthly Sales Std Dev",
            "Sales CV",
            "Consistency Class",
        ],
        "Purchase Recommendation": [
            "Suggested Target Cover Months",
            "Required Stock Qty",
            "Exact Purchase Requirement Qty",
            "Rounded PO Qty",
            "Final PO Quantity",
            "Purchase Priority",
            "PO Optimization Decision",
            "Reason for Recommendation",
        ],
    }
    for title, cols in sections.items():
        st.markdown(f"**{title}**")
        values = pd.DataFrame([[col, row.get(col, "")] for col in cols], columns=["Field", "Value"])
        values["Value"] = values["Value"].astype(str)
        st.dataframe(values, hide_index=True, use_container_width=True)

    history = monthly_history_for_item(monthly, item_key)
    st.markdown("**Monthly Sales History**")
    st.dataframe(history, hide_index=True, use_container_width=True)
    if not history.empty:
        st.line_chart(history.set_index("Month")["Sales Qty"])

    st.markdown("**Actions**")
    with st.form(widget_key(section_prefix, "item_settings_form", item_key)):
        cat_options, cat_lookup = category_option_labels(include_inactive=True)
        current_cat = current_category_label(row)
        category_choice = st.selectbox(
            "Category",
            cat_options,
            index=cat_options.index(current_cat) if current_cat in cat_options else 0,
            key=widget_key(section_prefix, "category_select", item_key),
        )
        discontinued = st.checkbox(
            "Discontinued Item",
            value=str(row.get("Is Discontinued", "No")).upper() == "YES",
            key=widget_key(section_prefix, "discontinued_checkbox", item_key),
        )
        reason = st.text_input(
            "Discontinued Reason",
            value=str(row.get("Discontinued Reason", "")),
            key=widget_key(section_prefix, "discontinued_reason", item_key),
        )
        suppliers = mdm.load_suppliers(active_only=True)
        supplier_options = ["Unknown Supplier"] + [
            f"{r['Supplier ID']} | {r['Supplier Name']}" for _, r in suppliers.iterrows()
        ]
        current_supplier = str(row.get("Assigned Supplier Name", "Unknown Supplier"))
        current_option = "Unknown Supplier"
        if not suppliers.empty:
            match = suppliers[suppliers["Supplier Name"].astype(str).eq(current_supplier)]
            if not match.empty:
                first = match.iloc[0]
                current_option = f"{first['Supplier ID']} | {first['Supplier Name']}"
        supplier_choice = st.selectbox(
            "Assigned Supplier",
            supplier_options,
            index=supplier_options.index(current_option) if current_option in supplier_options else 0,
            key=widget_key(section_prefix, "supplier_select", item_key),
        )
        submitted = st.form_submit_button("Save Item Settings", key=widget_key(section_prefix, "save_item_settings", item_key))
        if submitted:
            category_row = cat_lookup.get(category_choice, cat_lookup.get("Uncategorized", {}))
            category_name = str(category_row.get("Category Name", "Uncategorized")).strip() or "Uncategorized"
            category_id = str(category_row.get("Category ID", "")).strip()
            mdm.set_discontinued_item(
                item_key=item_key,
                item_code=str(row.get("Item Code / SKU", "")),
                item_name=item_name,
                discontinued=discontinued,
                reason=reason,
            )
            if supplier_choice == "Unknown Supplier":
                supplier_id, supplier_name = "", "Unknown Supplier"
            else:
                supplier_id, supplier_name = supplier_choice.split(" | ", 1)
            mdm.set_item_supplier(item_key, str(row.get("Item Code / SKU", "")), item_name, supplier_id, supplier_name)
            mdm.set_item_category(item_key, str(row.get("Item Code / SKU", "")), item_name, category_id, category_name)
            refresh_report()
            st.success("Item settings saved.")
            st.rerun()


def render_supplier_management(detail: pd.DataFrame | None = None, section_prefix: str = "supplier_management") -> None:
    suppliers = mdm.load_suppliers(active_only=False)
    st.subheader("View Suppliers")
    supplier_search = st.text_input("Search suppliers", key=widget_key(section_prefix, "supplier_search"))
    supplier_view = suppliers.copy()
    if supplier_search.strip() and not supplier_view.empty:
        q = supplier_search.strip().upper()
        supplier_view = supplier_view[supplier_view.apply(lambda r: q in " ".join(r.astype(str)).upper(), axis=1)]
    st.dataframe(supplier_view[["Supplier ID", "Supplier Name", "Contact Person", "Phone", "Email", "Active", "Updated At"]], hide_index=True, use_container_width=True)

    st.subheader("Add Supplier")
    with st.form(widget_key(section_prefix, "add_supplier_form")):
        name = st.text_input("Supplier Name", key=widget_key(section_prefix, "add_supplier_name"))
        contact = st.text_input("Contact Person", key=widget_key(section_prefix, "add_supplier_contact"))
        phone = st.text_input("Phone", key=widget_key(section_prefix, "add_supplier_phone"))
        email = st.text_input("Email", key=widget_key(section_prefix, "add_supplier_email"))
        address = st.text_area("Address", key=widget_key(section_prefix, "add_supplier_address"))
        notes = st.text_area("Notes", key=widget_key(section_prefix, "add_supplier_notes"))
        if st.form_submit_button("Add Supplier", key=widget_key(section_prefix, "add_supplier_submit")):
            try:
                supplier_id = mdm.add_supplier(name, contact, phone, email, address, notes)
                st.success(f"Added supplier {supplier_id}.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    if not suppliers.empty:
        st.subheader("Edit / Activate Supplier")
        labels = [f"{r['Supplier ID']} | {r['Supplier Name']}" for _, r in suppliers.iterrows()]
        selected = st.selectbox("Select supplier", labels, key=widget_key(section_prefix, "edit_supplier_select"))
        supplier_id = selected.split(" | ", 1)[0]
        current = suppliers[suppliers["Supplier ID"].eq(supplier_id)].iloc[0]
        with st.form(widget_key(section_prefix, "edit_supplier_form", supplier_id)):
            edit_name = st.text_input("Supplier Name", value=str(current["Supplier Name"]), key=widget_key(section_prefix, "edit_supplier_name", supplier_id))
            edit_contact = st.text_input("Contact Person", value=str(current["Contact Person"]), key=widget_key(section_prefix, "edit_contact", supplier_id))
            edit_phone = st.text_input("Phone", value=str(current["Phone"]), key=widget_key(section_prefix, "edit_phone", supplier_id))
            edit_email = st.text_input("Email", value=str(current["Email"]), key=widget_key(section_prefix, "edit_email", supplier_id))
            edit_address = st.text_area("Address", value=str(current["Address"]), key=widget_key(section_prefix, "edit_address", supplier_id))
            edit_notes = st.text_area("Notes", value=str(current["Notes"]), key=widget_key(section_prefix, "edit_notes", supplier_id))
            active = st.checkbox("Active", value=str(current["Active"]).upper() == "YES", key=widget_key(section_prefix, "edit_active", supplier_id))
            if st.form_submit_button("Update Supplier", key=widget_key(section_prefix, "update_supplier_submit", supplier_id)):
                try:
                    mdm.update_supplier(supplier_id, edit_name, edit_contact, edit_phone, edit_email, edit_address, edit_notes, active)
                    st.success("Supplier updated.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        col_a, col_b = st.columns(2)
        if col_a.button("Deactivate Supplier", key=widget_key(section_prefix, "deactivate_supplier", supplier_id)):
            mdm.deactivate_supplier(supplier_id)
            st.success("Supplier deactivated.")
            st.rerun()
        if col_b.button("Reactivate Supplier", key=widget_key(section_prefix, "reactivate_supplier", supplier_id)):
            mdm.reactivate_supplier(supplier_id)
            st.success("Supplier reactivated.")
            st.rerun()

        if detail is not None and not detail.empty:
            st.subheader("Supplier Item Mapping View")
            mapped = detail[detail.get("Assigned Supplier ID", pd.Series("", index=detail.index)).astype(str).eq(supplier_id)].copy()
            cols = ["Item Code / SKU", "Item Name", "Current Stock Qty", "Velocity Class", "Final PO Quantity", "Is Discontinued"]
            st.dataframe(mapped[[c for c in cols if c in mapped.columns]], hide_index=True, use_container_width=True)


def render_discontinued_items(detail: pd.DataFrame, section_prefix: str = "discontinued_items") -> None:
    discontinued_master = mdm.load_discontinued_items()
    current = detail[detail.get("Is Discontinued", pd.Series("No", index=detail.index)).astype(str).str.upper().eq("YES")].copy() if detail is not None and not detail.empty else pd.DataFrame()
    st.subheader("Discontinued Items")
    search = st.text_input("Search discontinued items", key=widget_key(section_prefix, "search"))
    view = current.copy()
    if search.strip() and not view.empty:
        q = search.strip().upper()
        view = view[view.apply(lambda r: q in " ".join(r.astype(str)).upper(), axis=1)]
    cols = ["Item Code / SKU", "Item Name", "Current Stock Qty", "Recent Monthly Velocity Qty", "Assigned Supplier Name", "Discontinued Date", "Discontinued Reason"]
    st.dataframe(view[[c for c in cols if c in view.columns]], hide_index=True, use_container_width=True)
    st.download_button(
        "Export discontinued list as CSV",
        data=discontinued_master.to_csv(index=False),
        file_name="discontinued-items.csv",
        mime="text/csv",
        key=widget_key(section_prefix, "download_discontinued_csv"),
    )
    if not view.empty:
        options = [f"{r['Item Key']} | {r['Item Name']}" for _, r in view.iterrows()]
        selected = st.selectbox("Remove discontinued status", options, key=widget_key(section_prefix, "remove_status_select"))
        selected_key = selected.split(" | ", 1)[0]
        if st.button("Remove Discontinued Status", key=widget_key(section_prefix, "remove_status", selected_key)):
            row = view[view["Item Key"].astype(str).eq(selected_key)].iloc[0]
            mdm.set_discontinued_item(selected_key, str(row.get("Item Code / SKU", "")), str(row.get("Item Name", "")), False, "")
            refresh_report()
            st.success("Discontinued status removed.")
            st.rerun()
    stock_items = current[current.get("Current Stock Qty", pd.Series(0, index=current.index)).fillna(0).gt(0)] if not current.empty else pd.DataFrame()
    if not stock_items.empty:
        st.warning("Existing stock available. Consider discount/liquidation. Do not reorder.")


def render_categories_view_page(report: dict | None) -> None:
    st.title("View Categories")
    categories = mdm.load_categories(active_only=False)
    if categories.empty:
        st.info("No categories found.")
        return
    search = st.text_input("Search category", key=widget_key("categories_view", "search"))
    active_only = st.checkbox("Show active only", value=False, key=widget_key("categories_view", "active_only"))
    view = categories.copy()
    if active_only:
        view = view[view["Active"].astype(str).str.upper().eq("YES")]
    if search.strip():
        q = search.strip().upper()
        view = view[view.apply(lambda r: q in " ".join(r.astype(str)).upper(), axis=1)]
    st.dataframe(view[visible_columns(view, ["Category ID", "Category Name", "Box Qty", "Active", "Created At", "Updated At"])], hide_index=True, use_container_width=True)
    if not view.empty:
        labels = [f"{r['Category ID']} | {r['Category Name']}" for _, r in view.iterrows()]
        selected = st.selectbox("Select category", labels, key=widget_key("categories_view", "selected_category"))
        category_id = selected.split(" | ", 1)[0]
        current = categories[categories["Category ID"].astype(str).eq(category_id)].iloc[0]
        current_box = pd.to_numeric(current.get("Box Qty", 0), errors="coerce")
        current_box = float(current_box) if pd.notna(current_box) else 0.0
        with st.form(widget_key("categories_view", "edit_form", category_id)):
            edit_name = st.text_input("Category Name", value=str(current["Category Name"]), key=widget_key("categories_view", "edit_name", category_id))
            edit_box = st.number_input("Box Qty", min_value=0.0, value=current_box, step=1.0, key=widget_key("categories_view", "edit_box", category_id))
            edit_active = st.checkbox("Active", value=str(current["Active"]).upper() == "YES", key=widget_key("categories_view", "edit_active", category_id))
            col_a, col_b = st.columns(2)
            if col_a.form_submit_button("Save Changes", key=widget_key("categories_view", "save", category_id)):
                try:
                    mdm.update_category(category_id, edit_name, edit_box, edit_active)
                    st.success("Category updated.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if col_b.form_submit_button("Cancel", key=widget_key("categories_view", "cancel", category_id)):
                st.rerun()
        col_c, col_d = st.columns(2)
        if col_c.button("Deactivate Category", key=widget_key("categories_view", "deactivate", category_id)):
            mdm.deactivate_category(category_id)
            st.success("Category deactivated.")
            st.rerun()
        if col_d.button("Reactivate Category", key=widget_key("categories_view", "reactivate", category_id)):
            mdm.reactivate_category(category_id)
            st.success("Category reactivated.")
            st.rerun()


def render_add_category_page() -> None:
    st.title("Add Category")
    with st.form(widget_key("categories_add", "form")):
        name = st.text_input("Category Name", key=widget_key("categories_add", "name"))
        box_qty = st.number_input("Box Qty", min_value=0.0, value=0.0, step=1.0, key=widget_key("categories_add", "box_qty"))
        if st.form_submit_button("Add Category", key=widget_key("categories_add", "save")):
            try:
                category_id = mdm.add_category(name, box_qty)
                st.success(f"Added category {category_id}.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def _category_detail_df(report: dict | None) -> pd.DataFrame:
    if report is not None and "Detailed Item Analysis" in report and not report["Detailed Item Analysis"].empty:
        return report["Detailed Item Analysis"].copy()
    path = file_manager.get_stock_file_path()
    if not path:
        return pd.DataFrame()
    stock, _ = load_stock_file(path, {})
    return mdm.enrich_with_master_data(ensure_required_output_columns(stock))


def render_item_category_mapping_page(report: dict | None) -> None:
    st.title("Item Category Mapping")
    detail = _category_detail_df(report)
    if detail.empty:
        st.warning("Run analysis first or upload stock data.")
        return
    view = filter_detail(detail, "item_category_mapping")
    if "Category Name" in view.columns:
        uncategorized_only = st.checkbox("Show Uncategorized only", key=widget_key("item_category_mapping", "uncategorized_only"))
        if uncategorized_only:
            view = view[view["Category Name"].astype(str).eq("Uncategorized")]
    cols = [
        "Item Key",
        "Item Code / SKU",
        "Item Name",
        "Current Stock Qty",
        "Category Name",
        "Category Box Qty",
        "Assigned Supplier Name",
        "Is Discontinued",
        "Velocity Class",
        "Final PO Quantity",
    ]
    st.dataframe(view[visible_columns(view, cols)], hide_index=True, use_container_width=True)
    if view.empty:
        return
    labels = [f"{r['Item Key']} | {r['Item Name']}" for _, r in view.head(500).iterrows()]
    selected = st.selectbox("Select item", labels, key=widget_key("item_category_mapping", "selected_item"))
    selected_key = selected.split(" | ", 1)[0]
    row = view[view["Item Key"].astype(str).eq(selected_key)].iloc[0]
    cat_options, cat_lookup = category_option_labels(include_inactive=True)
    current_label = current_category_label(row)
    chosen = st.selectbox(
        "Change category",
        cat_options,
        index=cat_options.index(current_label) if current_label in cat_options else 0,
        key=widget_key("item_category_mapping", "category_select", selected_key),
    )
    if st.button("Save Category", key=widget_key("item_category_mapping", "save", selected_key)):
        cat_row = cat_lookup.get(chosen, cat_lookup.get("Uncategorized", {}))
        mdm.set_item_category(
            selected_key,
            str(row.get("Item Code / SKU", "")),
            str(row.get("Item Name", "")),
            str(cat_row.get("Category ID", "")),
            str(cat_row.get("Category Name", "Uncategorized")),
        )
        refresh_report()
        st.success("Category saved.")
        st.rerun()


def render_bulk_category_assignment_page(report: dict | None) -> None:
    st.title("Bulk Category Assignment")
    detail = _category_detail_df(report)
    if detail.empty:
        st.warning("Run analysis first or upload stock data.")
        return
    view = filter_detail(detail, "bulk_category")
    if "Category Name" in view.columns:
        uncategorized_only = st.checkbox("Show Uncategorized only", value=False, key=widget_key("bulk_category", "uncategorized_only"))
        if uncategorized_only:
            view = view[view["Category Name"].astype(str).eq("Uncategorized")]
    cols = [
        "Item Key",
        "Item Code / SKU",
        "Item Name",
        "Category Name",
        "Current Stock Qty",
        "Assigned Supplier Name",
        "Is Discontinued",
        "Velocity Class",
        "Final PO Quantity",
    ]
    bulk = view[visible_columns(view, cols)].copy()
    bulk.insert(0, "Select", False)
    edited = st.data_editor(bulk, key=widget_key("bulk_category", "item_selector"), hide_index=True, use_container_width=True)
    cat_options, cat_lookup = category_option_labels(include_inactive=False)
    chosen = st.selectbox("Assign category", cat_options, key=widget_key("bulk_category", "category_select"))
    selected = edited[edited["Select"] == True]
    if st.button("Assign Category to Selected Items", key=widget_key("bulk_category", "assign")):
        cat_row = cat_lookup.get(chosen, cat_lookup.get("Uncategorized", {}))
        for _, row in selected.iterrows():
            mdm.set_item_category(
                str(row.get("Item Key", "")),
                str(row.get("Item Code / SKU", "")),
                str(row.get("Item Name", "")),
                str(cat_row.get("Category ID", "")),
                str(cat_row.get("Category Name", "Uncategorized")),
            )
        refresh_report()
        st.success(f"Updated {len(selected)} item(s).")
        st.rerun()
    if st.button("Clear Category for Selected Items", key=widget_key("bulk_category", "clear")):
        unc = mdm.ensure_uncategorized_category_exists()
        for _, row in selected.iterrows():
            mdm.set_item_category(
                str(row.get("Item Key", "")),
                str(row.get("Item Code / SKU", "")),
                str(row.get("Item Name", "")),
                str(unc.get("Category ID", "")),
                "Uncategorized",
            )
        refresh_report()
        st.success(f"Updated {len(selected)} item(s).")
        st.rerun()


def build_report(stock_path: Path, sales_paths: list[Path], settings: dict, sales_mappings: dict, stock_mapping: dict) -> dict[str, pd.DataFrame]:
    stock, _ = load_stock_file(stock_path, stock_mapping)
    sales, _ = load_sales_files(sales_paths, sales_mappings)
    validation = validate_data(sales, stock)
    sales_summary, monthly = analyze_sales(sales, settings["recent_period_months"])
    trend = analyze_trends(monthly, settings["recent_period_mode"], settings["recent_period_months"])
    merged = merge_stock_sales(sales_summary, trend, stock)
    detail = ensure_required_output_columns(merged)
    detail = mdm.enrich_with_master_data(detail)
    detail = calculate_po(detail, settings)
    detail = apply_discontinued_po_rules(detail)
    if settings["exclude_dormant_dead"]:
        dormant_mask = detail["Velocity Class"].isin(["Dormant", "Dead Stock / No Sales"])
        detail.loc[dormant_mask, ["Final PO Quantity", "Estimated Purchase Value", "Budget Approved PO Quantity", "Budget Approved PO Value"]] = 0
        detail.loc[dormant_mask, "Purchase Priority"] = "No Purchase"
    detail = ensure_required_output_columns(detail)
    detail = apply_discontinued_po_rules(detail)
    velocity_warnings = validate_velocity_calculations(detail)
    detail = detail[[col for col in DETAIL_COLUMNS if col in detail.columns]].copy()
    detail = apply_discontinued_po_rules(detail)

    final_po = detail[
        detail["Final PO Quantity"].gt(0)
        & detail.get("Is Discontinued", pd.Series("No", index=detail.index)).astype(str).str.upper().ne("YES")
    ].copy()
    final_po = ensure_required_output_columns(final_po)
    if not final_po.empty:
        final_po["Supplier Name"] = final_po["Assigned Supplier Name"].fillna("Unknown Supplier")
        final_po["Total Amount"] = final_po["Estimated Purchase Value"]
        final_po["priority_sort"] = final_po["Purchase Priority"].map(PRIORITY_ORDER).fillna(9)
        final_po["velocity_sort"] = final_po["Velocity Class"].map(MOVEMENT_ORDER).fillna(99)
        final_po["risk_sort"] = final_po["Stock Risk Level"].map(RISK_ORDER).fillna(99)
        sort_cols = ["priority_sort", "velocity_sort", "risk_sort", "Recent Monthly Velocity Qty", "Estimated Purchase Value"]
        for col in sort_cols:
            if col not in final_po.columns:
                final_po[col] = 0
        final_po = final_po.sort_values(sort_cols, ascending=[True, True, True, False, False])
        final_po = final_po.drop(columns=["priority_sort", "velocity_sort", "risk_sort"], errors="ignore")
        final_po = final_po[[col for col in FINAL_PO_COLUMNS if col in final_po.columns]]
    else:
        final_po = pd.DataFrame(columns=FINAL_PO_COLUMNS)

    master_warnings = mdm.master_validation_warnings(detail, final_po)
    if not master_warnings.empty:
        validation = pd.concat([validation, master_warnings], ignore_index=True)
    summary = build_executive_summary(detail)
    supplier_po = supplier_ready_po(final_po)
    cat_summary = category_size_summary(detail)
    recs = business_recommendations(detail, cat_summary)
    velocity_analysis = detail[
        [
            "Item Code / SKU",
            "Item Key",
            "Item Name",
            "Overall Monthly Velocity Qty",
            "Recent Monthly Velocity Qty",
            "Weighted Velocity Qty",
            "Velocity Percentile",
            "Velocity Class",
            "Sales Frequency %",
            "Recent Sales Frequency %",
            "Consistency Class",
        ]
    ].copy()
    trend_analysis = detail[
        [
            "Item Code / SKU",
            "Item Name",
            "Older Avg Monthly Sales Qty",
            "Recent Avg Monthly Sales Qty",
            "Trend Change %",
            "Sales Trend",
            "Monthly Sales Std Dev",
            "Sales CV",
            "Consistency Class",
        ]
    ].copy()
    stock_risk = detail[
        [
            "Item Code / SKU",
            "Item Name",
            "Velocity Class",
            "Current Stock Qty",
            "Recent Stock Coverage Months",
            "Suggested Target Cover Months",
            "Stock Risk Level",
            "Overstock After PO Flag",
            "PO Optimization Decision",
        ]
    ].copy()
    overstock_dead = detail[
        detail["Stock Risk Level"].eq("Overstock Risk")
        | detail["Velocity Class"].isin(["Dormant", "Dead Stock / No Sales"])
        | detail["Is Discontinued"].astype(str).str.upper().eq("YES")
    ].copy()
    discontinued_items = detail[detail["Is Discontinued"].astype(str).str.upper().eq("YES")].copy()
    assumptions = pd.DataFrame(
        [
            ["Planning metric", "Purchase planning is based on quantity, not sales amount."],
            ["Missing item code", "Normalized item name is used as SKU when item code is unavailable."],
            ["Missing stock", "Missing stock is treated as 0."],
            ["Missing purchase price", "Missing purchase price is treated as 0 and flagged."],
            ["Missing supplier", "Missing supplier is treated as Unknown Supplier."],
            ["Box rounding", "Final PO quantity is rounded up to box/MOQ where available and enabled."],
            ["Dynamic cover", "Very fast/fast items get higher cover; medium and slow items get lower cover."],
            ["Dormant and dead stock", "Dormant/dead items are not reordered when exclusion is enabled."],
            ["Budget optimization", "Budget approval columns are added when budget optimization is enabled."],
        ],
        columns=["Assumption", "Detail"],
    )
    return {
        "Executive Summary": summary,
        "Data Validation": validation,
        "Velocity Calculation Warnings": velocity_warnings,
        "Velocity Analysis": velocity_analysis,
        "Trend Analysis": trend_analysis,
        "Stock Risk": stock_risk,
        "Detailed Item Analysis": detail,
        "Optimized PO": final_po,
        "Final PO": final_po,
        "Supplier Ready PO": supplier_po,
        "Category Size Summary": cat_summary,
        "Overstock Dead Stock": overstock_dead,
        "Discontinued Items": discontinued_items,
        "Supplier Master": mdm.load_suppliers(active_only=False),
        "Item Supplier Mapping": mdm.load_item_suppliers(),
        "Categories": mdm.load_categories(active_only=False),
        "Item Category Mapping": mdm.load_item_categories(),
        "Business Recommendations": recs,
        "Assumptions": assumptions,
        "_Debug Inputs": {
            "stock": stock,
            "sales": sales,
            "monthly": monthly,
            "sales_paths": sales_paths,
        },
    }


DEFAULT_SETTINGS = {
    "recent_period_months": 6,
    "very_fast_upward_months": 3.5,
    "fast_stable_months": 2.5,
    "medium_stable_months": 2.0,
    "slow_stable_months": 1.0,
    "recent_period_mode": "Manual recent months",
    "manual_recent_months": 6,
    "enable_budget_optimization": False,
    "purchase_budget_amount": 0.0,
    "allow_excess_rounding_fast": True,
    "allow_excess_rounding_slow": False,
    "skip_slow_excess_rounding": True,
    "exclude_dormant_dead": True,
    "exclude_dead_stock": True,
    "apply_box_rounding": True,
    "min_purchase_value": 0.0,
}


def setting_value(name: str):
    return st.session_state.get(widget_key("analysis_settings", name), DEFAULT_SETTINGS[name])


def current_settings() -> dict:
    values = {name: setting_value(name) for name in DEFAULT_SETTINGS}
    values["recent_period_months"] = int(values["recent_period_months"])
    values["manual_recent_months"] = int(values["recent_period_months"])
    values["exclude_dead_stock"] = bool(values["exclude_dormant_dead"])
    return values


def current_sales_paths() -> list[Path]:
    years = file_manager.list_available_sales_years()
    selected = st.session_state.get(widget_key("sidebar", "selected_years"), years)
    return file_manager.get_sales_file_paths(selected)


def get_active_report() -> dict | None:
    if "report" in st.session_state and st.session_state["report"]:
        return st.session_state["report"]
    loaded = result_store.load_latest_result()
    if loaded:
        st.session_state["report"] = loaded["report"]
        st.session_state["active_run_id"] = loaded["manifest"].get("run_id", "")
        st.session_state["active_result_source"] = "latest"
        st.session_state["active_manifest"] = loaded["manifest"]
        st.session_state["active_result_path"] = str(loaded["path"])
        st.session_state["export_path"] = loaded["excel_path"]
        return loaded["report"]
    return None


def get_report() -> dict | None:
    return get_active_report()


def report_or_warning() -> dict | None:
    report = get_report()
    if report is None:
        st.warning("Run analysis first to view this page.")
    return report


def run_analysis(selected_paths: list[Path], show_mapping: bool = False) -> None:
    global stock_path, sales_paths, settings, sales_mappings, stock_mapping
    stock_path = file_manager.get_stock_file_path()
    sales_paths = selected_paths
    settings = current_settings()
    sales_mappings = {}
    stock_mapping = {}
    if show_mapping:
        for path in sales_paths:
            sales_mappings[path.parent.name] = mapping_editor(path, "sales", f"analysis_sales_{path.parent.name}")
        stock_mapping = mapping_editor(stock_path, "stock", "analysis_stock") if stock_path else {}
        for fy_key, mapping in sales_mappings.items():
            qty_error = validate_sales_quantity_column(mapping.get("sales_qty"))
            if qty_error:
                st.error(f"{qty_error} FY: {fy_key}")
                st.stop()
    with st.spinner("Analyzing inventory, sales trends, and purchase requirements..."):
        report = build_report(stock_path, sales_paths, settings, sales_mappings, stock_mapping)
        st.session_state["report"] = report
        run_id = result_store.save_analysis_result(
            report,
            settings,
            [path.parent.name for path in sales_paths],
            stock_path,
            sales_paths,
        )
        st.session_state["active_run_id"] = run_id
        st.session_state["active_result_source"] = "new_run"
        loaded = result_store.load_latest_result()
        if loaded:
            st.session_state["active_manifest"] = loaded["manifest"]
            st.session_state["active_result_path"] = str(loaded["path"])
            st.session_state["export_path"] = loaded["excel_path"]


def visible_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    return [col for col in columns if col in df.columns]


def find_item_detail_row(analysis_df: pd.DataFrame, selected_row: pd.Series) -> pd.Series | None:
    if analysis_df is None or analysis_df.empty:
        return None

    if "Item Key" in selected_row and "Item Key" in analysis_df.columns:
        item_key = str(selected_row.get("Item Key", "")).strip()
        if item_key:
            match = analysis_df[analysis_df["Item Key"].astype(str).str.strip().eq(item_key)]
            if not match.empty:
                return match.iloc[0]

    if "Item Code / SKU" in selected_row and "Item Code / SKU" in analysis_df.columns:
        sku = str(selected_row.get("Item Code / SKU", "")).strip()
        if sku:
            match = analysis_df[analysis_df["Item Code / SKU"].astype(str).str.strip().eq(sku)]
            if not match.empty:
                return match.iloc[0]

    if "Item Name" in selected_row and "Item Name" in analysis_df.columns:
        name = normalize_text(selected_row.get("Item Name", ""))
        if name:
            names = analysis_df["Item Name"].astype(str).map(normalize_text)
            match = analysis_df[names.eq(name)]
            if not match.empty:
                return match.iloc[0]

    return None


def filter_detail(detail: pd.DataFrame, section_prefix: str) -> pd.DataFrame:
    view = detail.copy()
    search = st.text_input("Search item", key=widget_key(section_prefix, "search"))
    if search.strip() and not view.empty:
        view = search_items(view, search)
    category_col = "Category Name" if "Category Name" in view.columns else "Category / Size / Type"
    if category_col in view.columns:
        categories = sorted([x for x in view[category_col].dropna().astype(str).unique() if x])
        chosen = st.multiselect("Category", categories, key=widget_key(section_prefix, "category_filter"))
        if chosen:
            view = view[view[category_col].astype(str).isin(chosen)]
    if "Assigned Supplier Name" in view.columns:
        suppliers = sorted([x for x in view["Assigned Supplier Name"].fillna("Unknown Supplier").astype(str).unique() if x])
        chosen = st.multiselect("Supplier", suppliers, key=widget_key(section_prefix, "supplier_filter"))
        if chosen:
            view = view[view["Assigned Supplier Name"].fillna("Unknown Supplier").astype(str).isin(chosen)]
    if "Velocity Class" in view.columns:
        classes = sorted([x for x in view["Velocity Class"].dropna().astype(str).unique() if x])
        chosen = st.multiselect("Velocity Class", classes, key=widget_key(section_prefix, "velocity_filter"))
        if chosen:
            view = view[view["Velocity Class"].astype(str).isin(chosen)]
    return view


def render_item_popup(detail: pd.DataFrame, item_key: str, report: dict, section_prefix: str) -> None:
    selected = detail[detail["Item Key"].astype(str).eq(str(item_key))]
    if selected.empty:
        st.warning("Selected item was not found in the current analysis.")
        return
    row = selected.iloc[0]
    monthly = report.get("_Debug Inputs", {}).get("monthly", pd.DataFrame())
    if hasattr(st, "dialog"):
        @st.dialog(f"Item Performance: {row.get('Item Name', '')}")
        def item_dialog():
            render_item_performance(row, monthly, section_prefix=widget_key(section_prefix, "dialog"))

        item_dialog()
    else:
        with st.expander("Item Performance", expanded=True):
            render_item_performance(row, monthly, section_prefix=widget_key(section_prefix, "expander"))


def render_add_supplier_modal() -> None:
    def body() -> None:
        with st.form(widget_key("supplier_add_modal", "form")):
            name = st.text_input("Supplier Name", key=widget_key("supplier_add_modal", "supplier_name"))
            contact = st.text_input("Contact Person", key=widget_key("supplier_add_modal", "contact_person"))
            phone = st.text_input("Phone", key=widget_key("supplier_add_modal", "phone"))
            email = st.text_input("Email", key=widget_key("supplier_add_modal", "email"))
            address = st.text_area("Address", key=widget_key("supplier_add_modal", "address"))
            notes = st.text_area("Notes", key=widget_key("supplier_add_modal", "notes"))
            col_a, col_b = st.columns(2)
            save = col_a.form_submit_button("Save Supplier", key=widget_key("supplier_add_modal", "save"))
            cancel = col_b.form_submit_button("Cancel", key=widget_key("supplier_add_modal", "cancel"))
            if cancel:
                st.session_state["show_add_supplier_modal"] = False
                st.rerun()
            if save:
                try:
                    supplier_id = mdm.add_supplier(name, contact, phone, email, address, notes)
                    st.session_state["show_add_supplier_modal"] = False
                    st.success(f"Added supplier {supplier_id}.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

    if hasattr(st, "dialog"):
        @st.dialog("Add Supplier")
        def add_dialog():
            body()

        add_dialog()
    else:
        with st.expander("Add Supplier", expanded=True):
            body()


def render_edit_supplier_modal(supplier_id: str, detail: pd.DataFrame | None = None) -> None:
    suppliers = mdm.load_suppliers(active_only=False)
    rows = suppliers[suppliers["Supplier ID"].astype(str).eq(str(supplier_id))]
    if rows.empty:
        st.session_state["edit_supplier_id"] = ""
        st.warning("Supplier not found.")
        return
    current = rows.iloc[0]

    def body() -> None:
        assigned_count = 0
        if detail is not None and not detail.empty and "Assigned Supplier ID" in detail.columns:
            assigned_count = int(detail["Assigned Supplier ID"].astype(str).eq(str(supplier_id)).sum())
        if assigned_count:
            st.warning("This supplier is assigned to items. Deactivation will not remove item mappings.")
        st.text_input("Supplier ID", value=str(current["Supplier ID"]), disabled=True, key=widget_key("supplier_edit_modal", "supplier_id", supplier_id))
        with st.form(widget_key("supplier_edit_modal", "form", supplier_id)):
            name = st.text_input("Supplier Name", value=str(current["Supplier Name"]), key=widget_key("supplier_edit_modal", "supplier_name", supplier_id))
            contact = st.text_input("Contact Person", value=str(current["Contact Person"]), key=widget_key("supplier_edit_modal", "contact_person", supplier_id))
            phone = st.text_input("Phone", value=str(current["Phone"]), key=widget_key("supplier_edit_modal", "phone", supplier_id))
            email = st.text_input("Email", value=str(current["Email"]), key=widget_key("supplier_edit_modal", "email", supplier_id))
            address = st.text_area("Address", value=str(current["Address"]), key=widget_key("supplier_edit_modal", "address", supplier_id))
            notes = st.text_area("Notes", value=str(current["Notes"]), key=widget_key("supplier_edit_modal", "notes", supplier_id))
            active = st.checkbox("Active", value=str(current["Active"]).upper() == "YES", key=widget_key("supplier_edit_modal", "active", supplier_id))
            col_a, col_b = st.columns(2)
            save = col_a.form_submit_button("Save Changes", key=widget_key("supplier_edit_modal", "save", supplier_id))
            cancel = col_b.form_submit_button("Cancel", key=widget_key("supplier_edit_modal", "cancel", supplier_id))
            if cancel:
                st.session_state["edit_supplier_id"] = ""
                st.rerun()
            if save:
                try:
                    mdm.update_supplier(supplier_id, name, contact, phone, email, address, notes, active)
                    st.session_state["edit_supplier_id"] = ""
                    st.success("Supplier updated.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        col_c, col_d = st.columns(2)
        if col_c.button("Deactivate Supplier", key=widget_key("supplier_edit_modal", "deactivate", supplier_id)):
            mdm.deactivate_supplier(supplier_id)
            st.session_state["edit_supplier_id"] = ""
            st.rerun()
        if col_d.button("Reactivate Supplier", key=widget_key("supplier_edit_modal", "reactivate", supplier_id)):
            mdm.reactivate_supplier(supplier_id)
            st.session_state["edit_supplier_id"] = ""
            st.rerun()

    if hasattr(st, "dialog"):
        @st.dialog(f"Edit Supplier: {current['Supplier Name']}")
        def edit_dialog():
            body()

        edit_dialog()
    else:
        with st.expander("Edit Supplier", expanded=True):
            body()


def render_page_header(title: str, subtitle: str = "") -> None:
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def render_kpi_card(label: str, value: object) -> None:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_summary(report: dict | None) -> None:
    render_page_header("Inventory PO Planner", "Purchase Manager Dashboard")
    if report is None:
        st.info("Run analysis from Purchase Planning -> Run Analysis.")
        render_data_file_status_page()
        return
    summary = report["Executive Summary"].copy()
    summary["Value"] = summary["Value"].astype(str)
    summary_map = dict(summary.values.tolist())
    kpis = st.columns(3)
    with kpis[0]:
        render_kpi_card("Items", summary_map.get("Total items analyzed", 0))
    with kpis[1]:
        render_kpi_card("Very Fast", summary_map.get("Very Fast Moving items", 0))
    with kpis[2]:
        render_kpi_card("Dormant / Dead", int(summary_map.get("Dormant items", 0)) + int(summary_map.get("Dead stock items", 0)))
    kpis = st.columns(3)
    with kpis[0]:
        render_kpi_card("PO Items", summary_map.get("Items recommended for purchase", 0))
    with kpis[1]:
        render_kpi_card("Urgent", summary_map.get("Urgent PO items", 0))
    with kpis[2]:
        render_kpi_card("PO Value", f"{float(summary_map.get('Total PO value', 0)):,.2f}")
    st.divider()
    st.dataframe(summary, use_container_width=True, hide_index=True)


def render_business_recommendations_page(report: dict | None) -> None:
    st.title("Business Recommendations")
    if report is None:
        st.warning("Run analysis first.")
        return
    for _, row in report["Business Recommendations"].iterrows():
        st.subheader(row["Recommendation Area"])
        st.write(row["Recommendation"])


def render_sales_upload_page() -> None:
    st.title("Upload Item-wise Sales")
    fy = st.selectbox("Financial Year", ["22-23", "23-24", "24-25", "25-26", "26-27"], index=4, key=widget_key("sales_upload", "financial_year"))
    target = file_manager.SALES_DIR / fy / "item-wise-sales.csv"
    if target.exists():
        st.warning(f"Existing file for {fy} will be replaced.")
    upload = st.file_uploader("Item-wise sales CSV", type=["csv"], key=widget_key("sales_upload", "file"))
    if st.button("Save / Replace Sales File", type="primary", key=widget_key("sales_upload", "save")):
        if upload is None:
            st.error("Choose a sales CSV before saving.")
        else:
            saved = file_manager.save_sales_file(upload, fy)
            st.success(f"Saved to {saved}")
            st.rerun()
    st.subheader("Available FY Files")
    rows = [{"FY": y, "Path": str((file_manager.SALES_DIR / y / "item-wise-sales.csv")), "Last Modified": modified_text(file_manager.SALES_DIR / y / "item-wise-sales.csv")} for y in file_manager.list_available_sales_years()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_sales_view_page() -> None:
    st.title("View Item-wise Sales")
    years = file_manager.list_available_sales_years()
    if not years:
        st.warning("No item-wise sales files found.")
        return
    selected = st.multiselect("FY", years, default=years, key=widget_key("sales_view", "fy_filter"))
    paths = file_manager.get_sales_file_paths(selected)
    sales, _ = load_sales_files(paths, {})
    if sales.empty:
        st.warning("No sales rows found.")
        return
    view = sales.copy()
    months = sorted(view["Sales Month"].dropna().dt.strftime("%Y-%m").unique()) if "Sales Month" in view.columns else []
    chosen_months = st.multiselect("Month", months, key=widget_key("sales_view", "month_filter"))
    if chosen_months:
        view = view[view["Sales Month"].dt.strftime("%Y-%m").isin(chosen_months)]
    search = st.text_input("Search item", key=widget_key("sales_view", "item_search"))
    if search.strip():
        q = search.strip().upper()
        view = view[view.apply(lambda r: q in " ".join(r.astype(str)).upper(), axis=1)]
    if "Category / Size / Type" in view.columns:
        categories = sorted([x for x in view["Category / Size / Type"].dropna().astype(str).unique() if x])
        selected_categories = st.multiselect("Category / Size / Type", categories, key=widget_key("sales_view", "category_filter"))
        if selected_categories:
            view = view[view["Category / Size / Type"].astype(str).isin(selected_categories)]
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Sales Qty", f"{view['Sales Quantity'].sum():,.2f}")
    c2.metric("Items Sold", view["Item Code / SKU"].nunique())
    c3.metric("Rows", len(view))
    st.subheader("Top Items by Quantity")
    top = view.groupby(["Item Code / SKU", "Item Name"], dropna=False)["Sales Quantity"].sum().reset_index().sort_values("Sales Quantity", ascending=False).head(20)
    st.dataframe(top, hide_index=True, use_container_width=True)
    st.subheader("Item-wise Sales")
    display = view.copy()
    if "Sales Month" in display.columns:
        display["Month"] = display["Sales Month"].dt.strftime("%Y-%m")
    cols = ["FY", "Month", "Item Code / SKU", "Item Name", "Category / Size / Type", "Sales Quantity", "Sales Amount"]
    st.dataframe(display[visible_columns(display, cols)], hide_index=True, use_container_width=True)


def render_stock_upload_page() -> None:
    st.title("Upload Stock")
    path = file_manager.get_stock_file_path()
    if path:
        st.warning("Existing stock.csv will be replaced.")
        st.caption(f"Current file last modified: {modified_text(path)}")
    upload = st.file_uploader("Stock CSV", type=["csv"], key=widget_key("stock_upload", "file"))
    if st.button("Save / Replace Stock File", type="primary", key=widget_key("stock_upload", "save")):
        if upload is None:
            st.error("Choose a stock CSV before saving.")
        else:
            saved = file_manager.save_stock_file(upload)
            st.success(f"Saved to {saved}")
            st.rerun()


def render_stock_view_page(report: dict | None) -> None:
    st.title("View Stock")
    if report is not None:
        detail = report["Detailed Item Analysis"].copy()
    else:
        path = file_manager.get_stock_file_path()
        if not path:
            st.warning("Stock file is missing.")
            return
        stock, _ = load_stock_file(path, {})
        detail = mdm.enrich_with_master_data(ensure_required_output_columns(stock))
    view = filter_detail(detail, "stock_view")
    if "Category Name" in view.columns:
        uncategorized_only = st.checkbox("Show Uncategorized only", key=widget_key("stock_view", "uncategorized_only"))
        if uncategorized_only:
            view = view[view["Category Name"].astype(str).eq("Uncategorized")]
    if "Stock Risk Level" in view.columns:
        risks = sorted([x for x in view["Stock Risk Level"].dropna().astype(str).unique() if x])
        chosen = st.multiselect("Stock Risk Level", risks, key=widget_key("stock_view", "risk_filter"))
        if chosen:
            view = view[view["Stock Risk Level"].astype(str).isin(chosen)]
    cols = [
        "Item Code / SKU",
        "Item Name",
        "Category Name",
        "Category Box Qty",
        "Current Stock Qty",
        "Purchase Price",
        "Assigned Supplier Name",
        "Is Discontinued",
        "Velocity Class",
        "Stock Coverage Months",
        "Final PO Quantity",
    ]
    st.dataframe(view[visible_columns(view, cols)], hide_index=True, use_container_width=True)
    if not view.empty:
        labels = [f"{r['Item Key']} | {r['Item Name']}" for _, r in view.head(500).iterrows()]
        selected = st.selectbox("Select item to view/edit", labels, key=widget_key("stock_view", "selected_item"))
        if st.button("View / Edit Item", key=widget_key("stock_view", "view_item")):
            st.session_state["stock_view_selected_item"] = selected.split(" | ", 1)[0]
    if st.session_state.get("stock_view_selected_item"):
        popup_report = report if report is not None else {"_Debug Inputs": {"monthly": pd.DataFrame()}}
        render_item_popup(detail, st.session_state["stock_view_selected_item"], popup_report, "stock_view_item_popup")


def supplier_options(active_only: bool = True) -> list[str]:
    suppliers = mdm.load_suppliers(active_only=active_only)
    return ["Unknown Supplier"] + [f"{r['Supplier ID']} | {r['Supplier Name']}" for _, r in suppliers.iterrows()]


def selected_supplier_parts(choice: str) -> tuple[str, str]:
    if not choice or choice == "Unknown Supplier":
        return "", "Unknown Supplier"
    return choice.split(" | ", 1)


def category_option_labels(include_inactive: bool = True) -> tuple[list[str], dict[str, dict[str, object]]]:
    categories = mdm.load_categories(active_only=False)
    options: list[str] = []
    lookup: dict[str, dict[str, object]] = {}
    if categories.empty:
        options = ["Uncategorized"]
        lookup["Uncategorized"] = {"Category ID": "", "Category Name": "Uncategorized", "Active": "Yes", "Box Qty": 0}
        return options, lookup
    for _, row in categories.iterrows():
        name = str(row.get("Category Name", "")).strip() or "Uncategorized"
        active = str(row.get("Active", "Yes")).strip().upper() == "YES"
        label = name if active or include_inactive else None
        if not active and include_inactive:
            label = f"{name} (Inactive)"
        if label and label not in lookup:
            options.append(label)
            lookup[label] = row.to_dict()
    if "Uncategorized" not in lookup:
        unc = mdm.ensure_uncategorized_category_exists()
        options.insert(0, "Uncategorized")
        lookup["Uncategorized"] = unc
    return options, lookup


def current_category_label(row: pd.Series) -> str:
    current = str(row.get("Category Name", "")).strip() or str(row.get("Category / Size / Type", "")).strip() or "Uncategorized"
    options, lookup = category_option_labels(include_inactive=True)
    for label, data in lookup.items():
        if normalize_text(data.get("Category Name", "")) == normalize_text(current):
            return label
    return current if current in options else "Uncategorized"


def render_bulk_supplier_assignment_page(report: dict | None) -> None:
    st.title("Bulk Supplier Assignment")
    if report is None:
        st.warning("Run analysis first.")
        return
    detail = filter_detail(report["Detailed Item Analysis"], "bulk_supplier")
    no_supplier_only = st.checkbox("Show only items without supplier", key=widget_key("bulk_supplier", "without_supplier"))
    active_only = st.checkbox("Show only active/non-discontinued", value=True, key=widget_key("bulk_supplier", "active_only"))
    if no_supplier_only and "Assigned Supplier Name" in detail.columns:
        detail = detail[detail["Assigned Supplier Name"].fillna("Unknown Supplier").astype(str).isin(["", "Unknown Supplier"])]
    if active_only and "Is Discontinued" in detail.columns:
        detail = detail[detail["Is Discontinued"].astype(str).str.upper().ne("YES")]
    cols = ["Item Key", "Item Code / SKU", "Item Name", "Category / Size / Type", "Current Stock Qty", "Velocity Class", "Assigned Supplier Name", "Is Discontinued"]
    bulk = detail[visible_columns(detail, cols)].copy()
    bulk.insert(0, "Select", False)
    edited = st.data_editor(bulk, key=widget_key("bulk_supplier", "item_selector"), hide_index=True, use_container_width=True)
    choice = st.selectbox("Assigned Supplier", supplier_options(True), key=widget_key("bulk_supplier", "supplier_select"))
    selected = edited[edited["Select"] == True]
    col_a, col_b = st.columns(2)
    if col_a.button("Assign Supplier to Selected Items", key=widget_key("bulk_supplier", "assign")):
        supplier_id, supplier_name = selected_supplier_parts(choice)
        for _, row in selected.iterrows():
            mdm.set_item_supplier(str(row.get("Item Key", "")), str(row.get("Item Code / SKU", "")), str(row.get("Item Name", "")), supplier_id, supplier_name)
        refresh_report()
        st.success(f"Updated {len(selected)} item(s).")
        st.rerun()
    if col_b.button("Clear Supplier for Selected Items", key=widget_key("bulk_supplier", "clear")):
        for _, row in selected.iterrows():
            mdm.set_item_supplier(str(row.get("Item Key", "")), str(row.get("Item Code / SKU", "")), str(row.get("Item Name", "")), "", "Unknown Supplier")
        refresh_report()
        st.success(f"Cleared supplier for {len(selected)} item(s).")
        st.rerun()


def render_bulk_mark_discontinued_page(report: dict | None) -> None:
    st.title("Bulk Mark Discontinued")
    if report is None:
        st.warning("Run analysis first.")
        return
    detail = filter_detail(report["Detailed Item Analysis"], "bulk_discontinued")
    active_only = st.checkbox("Show only active/non-discontinued", value=True, key=widget_key("bulk_discontinued", "active_only"))
    if active_only and "Is Discontinued" in detail.columns:
        detail = detail[detail["Is Discontinued"].astype(str).str.upper().ne("YES")]
    cols = ["Item Key", "Item Code / SKU", "Item Name", "Category / Size / Type", "Current Stock Qty", "Velocity Class", "Recent Monthly Velocity Qty", "Final PO Quantity", "Is Discontinued", "Assigned Supplier Name"]
    bulk = detail[visible_columns(detail, cols)].copy()
    bulk.insert(0, "Select", False)
    edited = st.data_editor(bulk, key=widget_key("bulk_discontinued", "item_selector"), hide_index=True, use_container_width=True)
    selected = edited[edited["Select"] == True]
    reason = st.text_input("Discontinued Reason", key=widget_key("bulk_discontinued", "reason"))
    col_a, col_b = st.columns(2)
    if col_a.button("Mark Selected as Discontinued", key=widget_key("bulk_discontinued", "mark")):
        for _, row in selected.iterrows():
            mdm.set_discontinued_item(str(row.get("Item Key", "")), str(row.get("Item Code / SKU", "")), str(row.get("Item Name", "")), True, reason)
        refresh_report()
        st.success(f"Marked {len(selected)} item(s) discontinued.")
        st.rerun()
    if col_b.button("Remove Discontinued Status for Selected", key=widget_key("bulk_discontinued", "remove")):
        for _, row in selected.iterrows():
            mdm.set_discontinued_item(str(row.get("Item Key", "")), str(row.get("Item Code / SKU", "")), str(row.get("Item Name", "")), False, "")
        refresh_report()
        st.success(f"Updated {len(selected)} item(s).")
        st.rerun()


def render_suppliers_view_page(report: dict | None) -> None:
    st.title("Suppliers")
    suppliers = mdm.load_suppliers(active_only=False)
    search = st.text_input("Search suppliers", key=widget_key("suppliers_view", "search"))
    view = suppliers.copy()
    if search.strip() and not view.empty:
        q = search.strip().upper()
        view = view[view.apply(lambda r: q in " ".join(r.astype(str)).upper(), axis=1)]
    st.dataframe(view[visible_columns(view, ["Supplier ID", "Supplier Name", "Contact Person", "Phone", "Email", "Active", "Updated At"])], hide_index=True, use_container_width=True)
    col_a, col_b = st.columns(2)
    if col_a.button("Add Supplier", key=widget_key("suppliers_view", "add_supplier")):
        st.session_state["show_add_supplier_modal"] = True
    if not suppliers.empty:
        labels = [f"{r['Supplier ID']} | {r['Supplier Name']}" for _, r in suppliers.iterrows()]
        selected = st.selectbox("Select supplier to edit", labels, key=widget_key("suppliers_view", "edit_supplier_select"))
        if col_b.button("Edit Selected Supplier", key=widget_key("suppliers_view", "edit_supplier")):
            st.session_state["edit_supplier_id"] = selected.split(" | ", 1)[0]
    if st.session_state.get("show_add_supplier_modal"):
        render_add_supplier_modal()
    if st.session_state.get("edit_supplier_id"):
        detail = report["Detailed Item Analysis"] if report is not None else None
        render_edit_supplier_modal(st.session_state["edit_supplier_id"], detail)


def render_supplier_item_mapping_page(report: dict | None) -> None:
    st.title("Supplier Item Mapping")
    mappings = mdm.load_item_suppliers()
    st.dataframe(mappings, hide_index=True, use_container_width=True)
    if report is not None:
        st.subheader("Current Item Assignments")
        cols = ["Item Code / SKU", "Item Name", "Assigned Supplier ID", "Assigned Supplier Name", "Supplier Source", "Current Stock Qty", "Velocity Class", "Final PO Quantity", "Is Discontinued"]
        st.dataframe(report["Detailed Item Analysis"][visible_columns(report["Detailed Item Analysis"], cols)], hide_index=True, use_container_width=True)


def render_purchase_run_analysis_page() -> None:
    global stock_path, sales_paths, settings, sales_mappings, stock_mapping
    st.title("Run Analysis")
    stock = file_manager.get_stock_file_path()
    years = file_manager.list_available_sales_years()
    selected = st.multiselect("Include FYs", years, default=st.session_state.get(widget_key("sidebar", "selected_years"), years), key=widget_key("sidebar", "selected_years"))
    paths = file_manager.get_sales_file_paths(selected)
    c1, c2, c3 = st.columns(3)
    c1.metric("Stock File", "Available" if stock else "Missing")
    c2.metric("Sales Years", len(paths))
    c3.metric("Export Path", str(REPORT_PATH.relative_to(Path(__file__).resolve().parent)))
    if stock:
        st.info(f"Stock file available. Last modified: {modified_text(stock)}")
    else:
        st.warning("Stock file is missing. Upload stock.csv.")
    if paths:
        st.info("Saved sales years: " + ", ".join(path.parent.name for path in paths))
    else:
        st.warning("No item-wise sales files found. Upload at least one FY sales file.")
    st.subheader("Column Mapping")
    if stock and paths:
        stock_path = stock
        sales_paths = paths
        settings = current_settings()
        sales_mappings = {}
        for path in sales_paths:
            sales_mappings[path.parent.name] = mapping_editor(path, "sales", f"analysis_sales_{path.parent.name}")
        stock_mapping = mapping_editor(stock_path, "stock", "analysis_stock")
        for fy_key, mapping in sales_mappings.items():
            qty_error = validate_sales_quantity_column(mapping.get("sales_qty"))
            if qty_error:
                st.error(f"{qty_error} FY: {fy_key}")
                st.stop()
        if st.button("Run Analysis", type="primary", key=widget_key("purchase_run", "run_analysis")):
            with st.spinner("Analyzing inventory, sales trends, and purchase requirements..."):
                report = build_report(stock_path, sales_paths, settings, sales_mappings, stock_mapping)
                st.session_state["report"] = report
                run_id = result_store.save_analysis_result(
                    report,
                    settings,
                    [path.parent.name for path in sales_paths],
                    stock_path,
                    sales_paths,
                )
                loaded = result_store.load_latest_result()
                st.session_state["active_run_id"] = run_id
                st.session_state["active_result_source"] = "new_run"
                if loaded:
                    st.session_state["active_manifest"] = loaded["manifest"]
                    st.session_state["active_result_path"] = str(loaded["path"])
                    st.session_state["export_path"] = loaded["excel_path"]
            st.success(f"Analysis completed and saved as {run_id}.")
            st.rerun()
    else:
        st.button("Run Analysis", disabled=True, key=widget_key("purchase_run", "run_analysis_disabled"))


def render_table_page(title: str, report: dict | None, sheet: str, section_prefix: str, columns: list[str] | None = None) -> None:
    st.title(title)
    if report is None:
        st.warning("Run analysis first.")
        return
    df = report.get(sheet, pd.DataFrame()).copy()
    if columns:
        df = df[visible_columns(df, columns)]
    st.dataframe(df, hide_index=True, use_container_width=True)


def render_detailed_item_analysis_page(report: dict | None) -> None:
    st.title("Detailed Item Analysis")
    if report is None:
        st.warning("Run analysis first.")
        return
    view = filter_detail(report["Detailed Item Analysis"], "detail_page")
    st.dataframe(view[visible_columns(view, DETAIL_COLUMNS)], hide_index=True, use_container_width=True)


def render_optimized_po_page(report: dict | None) -> None:
    st.title("Optimized PO")
    if report is None:
        st.warning("Run analysis first.")
        return
    po_source = report.get("Optimized PO")
    if po_source is None:
        po_source = report.get("Final PO")
    if po_source is None:
        st.warning("Optimized PO is not available. Run analysis first.")
        return
    analysis_df = report.get("Detailed Item Analysis")
    if analysis_df is None or analysis_df.empty:
        st.warning("Detailed Item Analysis is not available. Run analysis first.")
        return

    po = po_source.copy()
    if not po.empty:
        priority = sorted(po["Purchase Priority"].dropna().astype(str).unique()) if "Purchase Priority" in po.columns else []
        selected_priority = st.multiselect("Purchase Priority", priority, key=widget_key("optimized_po", "priority_filter"))
        if selected_priority:
            po = po[po["Purchase Priority"].astype(str).isin(selected_priority)]
        supplier = sorted(po["Assigned Supplier Name"].fillna("Unknown Supplier").astype(str).unique()) if "Assigned Supplier Name" in po.columns else []
        selected_supplier = st.multiselect("Supplier", supplier, key=widget_key("optimized_po", "supplier_filter"))
        if selected_supplier:
            po = po[po["Assigned Supplier Name"].fillna("Unknown Supplier").astype(str).isin(selected_supplier)]
    st.dataframe(po, hide_index=True, use_container_width=True)
    if po.empty:
        st.info("No items in Optimized PO.")
        return

    st.subheader("Inspect PO Item")
    label_to_index = {}
    label_options = []
    for idx, row in po.reset_index(drop=True).iterrows():
        code = str(row.get("Item Code / SKU", "")).strip()
        name = str(row.get("Item Name", "")).strip()
        item_label = f"{code} - {name}" if code and code != name else name or code or f"Item {idx + 1}"
        label = (
            f"{item_label} | PO Qty: {row.get('Final PO Quantity', 0)} "
            f"| Priority: {row.get('Purchase Priority', '')}"
        )
        if label in label_to_index:
            label = f"{label} | Row: {idx + 1}"
        label_to_index[label] = idx
        label_options.append(label)

    selected_label = st.selectbox(
        "Select PO item to inspect",
        label_options,
        key=widget_key("optimized_po", "selected_item_to_view"),
    )
    if st.button("View Selected Item", key=widget_key("optimized_po", "view_selected_item")):
        selected_row = po.reset_index(drop=True).iloc[label_to_index[selected_label]]
        detail_row = find_item_detail_row(analysis_df, selected_row)
        if detail_row is None:
            st.session_state["optimized_po_selected_item_key"] = ""
            st.error("Could not find full item details for the selected PO item.")
        else:
            st.session_state["optimized_po_selected_item_key"] = str(detail_row.get("Item Key", "")).strip()
            st.session_state["show_optimized_po_item_popup"] = True

    selected_key = st.session_state.get("optimized_po_selected_item_key", "")
    if st.session_state.get("show_optimized_po_item_popup") and selected_key:
        render_item_popup(analysis_df, selected_key, report, "optimized_po_item_popup")


def render_supplier_ready_po_page(report: dict | None) -> None:
    st.title("Supplier Ready PO")
    if report is None:
        st.warning("Run analysis first.")
        return
    recommended = report.get("Supplier Ready PO", pd.DataFrame()).copy()
    if recommended.empty:
        st.info("No supplier-ready PO rows found.")
        return

    active_run_id = str(st.session_state.get("active_run_id", "") or "")
    if st.session_state.get("supplier_ready_po_last_run_id") != active_run_id:
        st.session_state["supplier_ready_po_last_run_id"] = active_run_id
        st.session_state.pop("supplier_ready_po_edited_df", None)

    edited = st.session_state.get("supplier_ready_po_edited_df")
    if (edited is None or edited.empty) and isinstance(report.get("Supplier Ready PO Edited"), pd.DataFrame) and not report["Supplier Ready PO Edited"].empty:
        edited = report["Supplier Ready PO Edited"].copy()
        st.session_state["supplier_ready_po_edited_df"] = edited.copy()
    if edited is not None and not edited.empty:
        editable_df = edited.copy()
        st.caption("Showing edited supplier-ready PO for this run.")
    else:
        editable_df = recommended.copy()

    rename_map = {
        "Assigned Supplier Name": "Supplier Name",
        "Estimated Purchase Value": "Total Amount",
    }
    for old, new in rename_map.items():
        if old in editable_df.columns and new not in editable_df.columns:
            editable_df = editable_df.rename(columns={old: new})
    if "Quantity" not in editable_df.columns and "Final PO Quantity" in editable_df.columns:
        editable_df["Quantity"] = editable_df["Final PO Quantity"]
    if "Boxes" not in editable_df.columns:
        editable_df["Boxes"] = 0
    if "Category Name" not in editable_df.columns:
        editable_df["Category Name"] = editable_df.get("Category / Size / Type", "Uncategorized")
    if "Category Box Qty" not in editable_df.columns:
        editable_df["Category Box Qty"] = 0
    if "Purchase Price" not in editable_df.columns:
        editable_df["Purchase Price"] = 0
    if "Total Amount" not in editable_df.columns:
        editable_df["Total Amount"] = pd.to_numeric(editable_df.get("Quantity", 0), errors="coerce").fillna(0) * pd.to_numeric(
            editable_df.get("Purchase Price", 0), errors="coerce"
        ).fillna(0)

    editable_df["Quantity"] = pd.to_numeric(editable_df["Quantity"], errors="coerce").fillna(0)
    editable_df["Category Box Qty"] = pd.to_numeric(editable_df["Category Box Qty"], errors="coerce").fillna(0)
    editable_df["Purchase Price"] = pd.to_numeric(editable_df["Purchase Price"], errors="coerce").fillna(0)
    editable_df["Boxes"] = editable_df.apply(
        lambda r: math.ceil(float(r["Quantity"]) / float(r["Category Box Qty"])) if float(r["Category Box Qty"]) > 0 and float(r["Quantity"]) > 0 else 0,
        axis=1,
    )
    editable_df["Total Amount"] = editable_df["Quantity"] * editable_df["Purchase Price"]

    disabled_cols = [col for col in editable_df.columns if col not in {"Quantity"}]
    edited_df = st.data_editor(
        editable_df,
        key=widget_key("supplier_ready_po", "editable_po_table", active_run_id),
        hide_index=True,
        use_container_width=True,
        disabled=disabled_cols,
        column_config={
            "Quantity": st.column_config.NumberColumn("Quantity", min_value=0, step=1),
            "Category Box Qty": st.column_config.NumberColumn("Category Box Qty", disabled=True),
            "Boxes": st.column_config.NumberColumn("Boxes", disabled=True),
            "Purchase Price": st.column_config.NumberColumn("Purchase Price", disabled=True),
            "Total Amount": st.column_config.NumberColumn("Total Amount", disabled=True),
        },
    )

    edited_df["Quantity"] = pd.to_numeric(edited_df["Quantity"], errors="coerce").fillna(0)
    edited_df["Category Box Qty"] = pd.to_numeric(edited_df["Category Box Qty"], errors="coerce").fillna(0)
    edited_df["Purchase Price"] = pd.to_numeric(edited_df["Purchase Price"], errors="coerce").fillna(0)
    edited_df["Boxes"] = edited_df.apply(
        lambda r: math.ceil(float(r["Quantity"]) / float(r["Category Box Qty"])) if float(r["Category Box Qty"]) > 0 and float(r["Quantity"]) > 0 else 0,
        axis=1,
    )
    edited_df["Total Amount"] = edited_df["Quantity"] * edited_df["Purchase Price"]
    st.session_state["supplier_ready_po_edited_df"] = edited_df.copy()

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total Edited Quantity", f"{edited_df['Quantity'].sum():,.0f}")
    col_b.metric("Total Boxes", f"{edited_df['Boxes'].sum():,.0f}")
    col_c.metric("Total Amount", f"{edited_df['Total Amount'].sum():,.2f}")

    result_dir = Path(st.session_state.get("active_result_path", result_store.LATEST_DIR))
    if st.button("Save Edited Supplier PO for this run", key=widget_key("supplier_ready_po", "save_edited", active_run_id)):
        result_dir.mkdir(parents=True, exist_ok=True)
        save_path = result_dir / "supplier_ready_po_edited.csv"
        edited_df.to_csv(save_path, index=False)
        st.session_state["supplier_ready_po_edited_df"] = edited_df.copy()
        if isinstance(st.session_state.get("report"), dict):
            st.session_state["report"]["Supplier Ready PO Edited"] = edited_df.copy()
        st.success(f"Saved edited supplier PO to {save_path}")
    st.download_button(
        "Download Edited Supplier PO CSV",
        data=edited_df.to_csv(index=False),
        file_name="supplier_ready_po_edited.csv",
        mime="text/csv",
        key=widget_key("supplier_ready_po", "download_edited", active_run_id),
    )


def render_overstock_dead_stock_page(report: dict | None) -> None:
    render_table_page("Overstock / Dead Stock", report, "Overstock Dead Stock", "overstock_dead")


def render_discontinued_view_page(report: dict | None) -> None:
    detail = report["Detailed Item Analysis"] if report is not None else pd.DataFrame()
    render_discontinued_items(detail, section_prefix="discontinued_view")


def render_excel_export_page(report: dict | None) -> None:
    st.title("Excel Export")
    if report is None:
        st.warning("No analysis result available. Run analysis first or load from Result History.")
        return
    manifest = st.session_state.get("active_manifest", {})
    if manifest:
        st.caption(f"Active Run ID: {manifest.get('run_id', '')}")
        st.caption(f"Report Created At: {manifest.get('created_at_display', manifest.get('created_at', ''))}")
    active_path = Path(st.session_state.get("active_result_path", result_store.LATEST_DIR))
    export_path = Path(st.session_state.get("export_path", active_path / "inventory_report.xlsx"))
    if not export_path.exists():
        export_path = export_excel(report, active_path / "inventory_report.xlsx")
    st.session_state["export_path"] = export_path
    st.info(f"Report path: {export_path}")
    with open(export_path, "rb") as file:
        st.download_button(
            "Download Excel Report",
            data=file,
            file_name="inventory_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=widget_key("excel_export", "download"),
        )


def render_result_history_page(report: dict | None) -> None:
    st.title("Result History")
    runs = result_store.list_result_runs()
    if runs.empty:
        st.info("No saved analysis results found. Run analysis to generate one.")
        return
    display = runs[["Run ID", "Created At", "Sales Years", "Total Items", "PO Items", "Urgent Items", "High Items", "Total PO Value"]].copy()
    st.dataframe(display, hide_index=True, use_container_width=True)
    run_options = runs["Run ID"].astype(str).tolist()
    current = st.session_state.get("selected_result_run_id", run_options[0])
    index = run_options.index(current) if current in run_options else 0
    selected_run = st.selectbox("Select result run", run_options, index=index, key=widget_key("result_history", "selected_run"))
    st.session_state["selected_result_run_id"] = selected_run

    col_a, col_b = st.columns(2)
    if col_a.button("Load Selected Result", key=widget_key("result_history", "load_selected")):
        loaded = result_store.load_result(selected_run)
        if loaded:
            st.session_state["report"] = loaded["report"]
            st.session_state["active_run_id"] = loaded["manifest"].get("run_id", selected_run)
            st.session_state["active_result_source"] = "history"
            st.session_state["active_manifest"] = loaded["manifest"]
            st.session_state["active_result_path"] = str(loaded["path"])
            st.session_state["export_path"] = loaded["excel_path"]
            st.success(f"Loaded {selected_run} for this session.")
            st.rerun()
        else:
            st.error("Could not load selected result.")
    if col_b.button("Make Selected Result Latest", key=widget_key("result_history", "make_latest")):
        if result_store.copy_result_to_latest(selected_run):
            loaded = result_store.load_latest_result()
            if loaded:
                st.session_state["report"] = loaded["report"]
                st.session_state["active_run_id"] = loaded["manifest"].get("run_id", selected_run)
                st.session_state["active_result_source"] = "latest"
                st.session_state["active_manifest"] = loaded["manifest"]
                st.session_state["active_result_path"] = str(loaded["path"])
                st.session_state["export_path"] = loaded["excel_path"]
            st.success(f"{selected_run} is now the latest result.")
            st.rerun()
        else:
            st.error("Could not make selected result latest.")

    st.subheader("Delete Results")
    confirm = st.checkbox("I understand this will delete the selected result.", key=widget_key("result_history", "confirm_delete"))
    if st.button("Delete Selected Result", disabled=not confirm, key=widget_key("result_history", "delete_selected")):
        active_run = st.session_state.get("active_run_id", "")
        if result_store.delete_result(selected_run):
            if selected_run == active_run:
                st.session_state.pop("report", None)
                loaded = result_store.load_latest_result()
                if loaded:
                    st.session_state["report"] = loaded["report"]
                    st.session_state["active_run_id"] = loaded["manifest"].get("run_id", "")
                    st.session_state["active_result_source"] = "latest"
                    st.session_state["active_manifest"] = loaded["manifest"]
                    st.session_state["active_result_path"] = str(loaded["path"])
                    st.session_state["export_path"] = loaded["excel_path"]
            st.success(f"Deleted {selected_run}.")
            st.rerun()
        else:
            st.error("Could not delete selected result.")
    if st.button("Delete Old Results Except Latest", key=widget_key("result_history", "delete_old_except_latest")):
        deleted = result_store.delete_all_results_except_latest()
        st.success(f"Deleted {deleted} old result folder(s).")
        st.rerun()


def render_data_validation_page(report: dict | None) -> None:
    st.title("Data Validation")
    if report is None:
        st.warning("Run analysis first.")
        return
    st.dataframe(report["Data Validation"], use_container_width=True, hide_index=True)
    warnings = report.get("Velocity Calculation Warnings", pd.DataFrame())
    if not warnings.empty:
        st.subheader("Velocity Calculation Warnings")
        st.dataframe(warnings, use_container_width=True, hide_index=True)


def render_analysis_settings_page() -> None:
    st.title("Analysis Settings")
    st.number_input("Recent period months", min_value=1, value=int(setting_value("recent_period_months")), step=1, key=widget_key("analysis_settings", "recent_period_months"))
    st.number_input("Very fast upward target cover", min_value=0.0, value=float(setting_value("very_fast_upward_months")), step=0.5, key=widget_key("analysis_settings", "very_fast_upward_months"))
    st.number_input("Fast stable target cover", min_value=0.0, value=float(setting_value("fast_stable_months")), step=0.5, key=widget_key("analysis_settings", "fast_stable_months"))
    st.number_input("Medium stable target cover", min_value=0.0, value=float(setting_value("medium_stable_months")), step=0.5, key=widget_key("analysis_settings", "medium_stable_months"))
    st.number_input("Slow stable target cover", min_value=0.0, value=float(setting_value("slow_stable_months")), step=0.5, key=widget_key("analysis_settings", "slow_stable_months"))
    st.radio("Recent period mode", ["Auto split period in half", "Manual recent months"], index=1 if setting_value("recent_period_mode") == "Manual recent months" else 0, key=widget_key("analysis_settings", "recent_period_mode"))
    st.toggle("Enable budget optimization", value=bool(setting_value("enable_budget_optimization")), key=widget_key("analysis_settings", "enable_budget_optimization"))
    st.number_input("Purchase budget amount", min_value=0.0, value=float(setting_value("purchase_budget_amount")), step=1000.0, key=widget_key("analysis_settings", "purchase_budget_amount"))
    st.toggle("Allow excess box rounding for fast items", value=bool(setting_value("allow_excess_rounding_fast")), key=widget_key("analysis_settings", "allow_excess_rounding_fast"))
    st.toggle("Allow excess box rounding for slow items", value=bool(setting_value("allow_excess_rounding_slow")), key=widget_key("analysis_settings", "allow_excess_rounding_slow"))
    st.toggle("Skip slow items if rounded PO creates excess cover", value=bool(setting_value("skip_slow_excess_rounding")), key=widget_key("analysis_settings", "skip_slow_excess_rounding"))
    st.toggle("Exclude dormant/dead items", value=bool(setting_value("exclude_dormant_dead")), key=widget_key("analysis_settings", "exclude_dormant_dead"))
    st.toggle("Apply edge band box rounding", value=bool(setting_value("apply_box_rounding")), key=widget_key("analysis_settings", "apply_box_rounding"))
    st.number_input("Minimum purchase value filter", min_value=0.0, value=float(setting_value("min_purchase_value")), step=100.0, key=widget_key("analysis_settings", "min_purchase_value"))
    st.text_input("Debug Item Name / SKU", value=st.session_state.get(widget_key("analysis_settings", "debug_item_query"), ""), key=widget_key("analysis_settings", "debug_item_query"))


def render_data_file_status_page() -> None:
    st.title("Data File Status")
    stock = file_manager.get_stock_file_path()
    sales_rows = []
    for fy in file_manager.list_available_sales_years():
        path = file_manager.SALES_DIR / fy / "item-wise-sales.csv"
        sales_rows.append({"FY": fy, "Available": path.exists(), "Last Modified": modified_text(path), "Path": str(path)})
    master_rows = []
    for name, path in {
        "discontinued-items.csv": mdm.DISCONTINUED_PATH,
        "item-suppliers.csv": mdm.ITEM_SUPPLIERS_PATH,
        "suppliers.csv": mdm.SUPPLIERS_PATH,
        "categories.csv": mdm.CATEGORIES_PATH,
        "item-categories.csv": mdm.ITEM_CATEGORIES_PATH,
    }.items():
        master_rows.append({"File": name, "Available": path.exists(), "Last Modified": modified_text(path), "Path": str(path)})
    st.subheader("Stock")
    st.dataframe(pd.DataFrame([{"Available": bool(stock), "Last Modified": modified_text(stock), "Path": str(stock) if stock else str(file_manager.STOCK_DIR / "stock.csv")}]), hide_index=True, use_container_width=True)
    st.subheader("Sales Files")
    st.dataframe(pd.DataFrame(sales_rows), hide_index=True, use_container_width=True)
    st.subheader("Master Files")
    st.dataframe(pd.DataFrame(master_rows), hide_index=True, use_container_width=True)


def render_debug_item_velocity_page(report: dict | None) -> None:
    query = st.session_state.get(widget_key("analysis_settings", "debug_item_query"), "")
    if report is None or not query.strip():
        return
    st.header("Debug Item Velocity")
    debug_inputs = report.get("_Debug Inputs", {})
    debug_report = item_debug_report(
        query.strip(),
        debug_inputs.get("sales_paths", sales_paths),
        debug_inputs.get("sales", pd.DataFrame()),
        debug_inputs.get("monthly", pd.DataFrame()),
        report["Detailed Item Analysis"],
        debug_inputs.get("stock", pd.DataFrame()),
    )
    for title, df in debug_report.items():
        st.subheader(title)
        st.dataframe(df, use_container_width=True, hide_index=True)


stock_path = file_manager.get_stock_file_path()
sales_paths = current_sales_paths()
settings = current_settings()
sales_mappings = {}
stock_mapping = {}
report = get_active_report()

NAV_ITEMS = {
    "Dashboard": {
        "icon": "📊",
        "pages": ["Executive Summary", "Business Recommendations"],
    },
    "Item-wise Sales": {
        "icon": "🧾",
        "pages": ["View Sales", "Upload Sales"],
    },
    "Stock": {
        "icon": "📦",
        "pages": ["View Stock", "Upload Stock", "Bulk Item Update"],
    },
    "Categories": {
        "icon": "🏷️",
        "pages": ["View Categories", "Add Category", "Item Category Mapping", "Bulk Category Assignment"],
    },
    "Purchase Planning": {
        "icon": "🛒",
        "pages": [
            "Run Analysis",
            "Detailed Item Analysis",
            "Optimized PO",
            "Supplier Ready PO",
            "Overstock / Dead Stock",
        ],
    },
    "Suppliers": {
        "icon": "🏭",
        "pages": ["View Suppliers", "Supplier Item Mapping", "Bulk Supplier Assignment"],
    },
    "Discontinued Items": {
        "icon": "🚫",
        "pages": ["View Discontinued", "Bulk Mark Discontinued"],
    },
    "Result History": {
        "icon": "🕘",
        "pages": ["View Runs", "Load Run", "Delete Runs"],
    },
    "Reports": {
        "icon": "📈",
        "pages": ["Excel Export", "Data Validation", "Velocity Analysis", "Trend Analysis", "Stock Risk"],
    },
    "Settings": {
        "icon": "⚙️",
        "pages": ["Analysis Settings", "Data File Status"],
    },
}


def inject_ui_css() -> None:
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] {
            background: #f8fafc;
            border-right: 1px solid #e2e8f0;
        }
        section[data-testid="stSidebar"] hr {
            margin-top: 0.8rem;
            margin-bottom: 0.8rem;
            border-color: #e2e8f0;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
            width: 100%;
            min-height: 2.35rem;
            border-radius: 0.6rem;
            border: 1px solid #e2e8f0;
            background: #ffffff;
            color: #0f172a !important;
            font-weight: 650;
            text-align: left;
            justify-content: flex-start;
            box-shadow: none;
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {
            color: #0f172a !important;
            font-weight: 650;
            line-height: 1.25;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
            background: #eff6ff !important;
            border-color: #bfdbfe !important;
            color: #0f172a !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover p {
            color: #0f172a !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button:focus {
            background: #dbeafe !important;
            border-color: #93c5fd !important;
            color: #0f172a !important;
            outline: none;
            box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button:focus p {
            color: #0f172a !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button:active {
            background: #dbeafe !important;
            color: #0f172a !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button:active p {
            color: #0f172a !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button:disabled {
            background: #f1f5f9 !important;
            color: #94a3b8 !important;
            border-color: #e2e8f0 !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button:disabled p {
            color: #94a3b8 !important;
        }
        .sidebar-title {
            font-size: 1.15rem;
            font-weight: 800;
            color: #0f172a;
            margin-bottom: 0.15rem;
        }
        .sidebar-subtitle {
            font-size: 0.82rem;
            color: #64748b;
            margin-bottom: 0.85rem;
        }
        .sidebar-status-card {
            padding: 0.8rem;
            border-radius: 0.75rem;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            color: #0f172a;
            font-size: 0.82rem;
            line-height: 1.55;
            margin-bottom: 0.9rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        .sidebar-section-label {
            font-size: 0.72rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #64748b;
            margin-top: 0.75rem;
            margin-bottom: 0.25rem;
        }
        .sidebar-help-text {
            font-size: 0.75rem;
            color: #64748b;
            margin-top: 0.5rem;
        }
        .active-route-pill {
            padding: 0.55rem 0.7rem;
            border-radius: 0.7rem;
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            color: #1d4ed8;
            font-size: 0.78rem;
            font-weight: 700;
            margin-top: 0.6rem;
            margin-bottom: 0.6rem;
        }
        .kpi-card {
            padding: 1rem;
            border-radius: 0.9rem;
            background: #ffffff;
            border: 1px solid #e5e7eb;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
            margin-bottom: 0.75rem;
        }
        .kpi-label {
            font-size: 0.78rem;
            color: #64748b;
            margin-bottom: 0.25rem;
        }
        .kpi-value {
            font-size: 1.65rem;
            font-weight: 700;
            color: #0f172a;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_page_options(main_section: str) -> list[str]:
    return NAV_ITEMS.get(main_section, NAV_ITEMS["Dashboard"])["pages"]


def set_active_route(menu_name: str, page_name: str | None = None) -> None:
    pages = get_page_options(menu_name)
    if page_name is None or page_name not in pages:
        page_name = pages[0]
    st.session_state["nav_active_menu"] = menu_name
    st.session_state["nav_active_page"] = page_name
    st.session_state["nav_expanded_menu"] = menu_name


def load_latest_result_into_state() -> bool:
    loaded = result_store.load_latest_result()
    if not loaded:
        return False
    st.session_state["report"] = loaded["report"]
    st.session_state["active_run_id"] = loaded["manifest"].get("run_id", "")
    st.session_state["active_result_source"] = "latest"
    st.session_state["active_manifest"] = loaded["manifest"]
    st.session_state["active_result_path"] = str(loaded["path"])
    st.session_state["export_path"] = loaded["excel_path"]
    return True


def render_sidebar_status_card(active_manifest: dict | None) -> None:
    stock_status = "Available" if stock_path else "Missing"
    sales_count = len(file_manager.list_available_sales_years())
    run_id = active_manifest.get("run_id", "No result") if active_manifest else "No result"
    latest_time = active_manifest.get("created_at_display", "-") if active_manifest else "-"
    st.sidebar.markdown(
        f"""
        <div class="sidebar-status-card">
            <div><b>Stock:</b> {stock_status}</div>
            <div><b>Sales FYs:</b> {sales_count}</div>
            <div><b>Active Result:</b><br>{run_id}</div>
            <div><b>Latest Run:</b> {latest_time}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> tuple[str, str]:
    inject_ui_css()
    if "nav_expanded_menu" not in st.session_state:
        st.session_state["nav_expanded_menu"] = "Dashboard"
    if "nav_active_menu" not in st.session_state:
        st.session_state["nav_active_menu"] = "Dashboard"
    if "nav_active_page" not in st.session_state:
        st.session_state["nav_active_page"] = "Executive Summary"

    st.sidebar.markdown('<div class="sidebar-title">Inventory PO Planner</div>', unsafe_allow_html=True)
    st.sidebar.markdown('<div class="sidebar-subtitle">Purchase Manager Dashboard</div>', unsafe_allow_html=True)
    render_sidebar_status_card(st.session_state.get("active_manifest", {}))

    st.sidebar.markdown('<div class="sidebar-section-label">Quick Actions</div>', unsafe_allow_html=True)
    if st.sidebar.button("▶ Run Analysis", key=widget_key("sidebar_quick", "run_analysis"), use_container_width=True):
        set_active_route("Purchase Planning", "Run Analysis")
        st.rerun()
    if st.sidebar.button("↻ Load Latest", key=widget_key("sidebar_quick", "load_latest"), use_container_width=True):
        if load_latest_result_into_state():
            st.rerun()
        st.sidebar.warning("No saved result found.")

    st.sidebar.divider()
    st.sidebar.markdown('<div class="sidebar-section-label">Navigation</div>', unsafe_allow_html=True)
    active_menu = st.session_state.get("nav_active_menu", "Dashboard")
    active_page = st.session_state.get("nav_active_page", "Executive Summary")
    expanded_menu = st.session_state.get("nav_expanded_menu")
    st.sidebar.markdown(
        f'<div class="active-route-pill">{active_menu} / {active_page}</div>',
        unsafe_allow_html=True,
    )

    for menu_name, config in NAV_ITEMS.items():
        pages = config["pages"]
        expanded = expanded_menu == menu_name
        is_active_menu = active_menu == menu_name
        header_marker = "▾" if expanded else "▸"
        active_marker = "●" if is_active_menu else " "
        header_label = f"{config['icon']} {active_marker} {menu_name} {header_marker}"
        if st.sidebar.button(header_label, key=widget_key("nav_menu", menu_name), use_container_width=True):
            if st.session_state.get("nav_expanded_menu") == menu_name:
                st.session_state["nav_expanded_menu"] = None
            else:
                st.session_state["nav_expanded_menu"] = menu_name
            st.session_state["nav_active_menu"] = menu_name
            if st.session_state.get("nav_active_page") not in pages:
                st.session_state["nav_active_page"] = pages[0]
            st.rerun()

        if expanded:
            for page_name in pages:
                is_active_page = st.session_state.get("nav_active_menu") == menu_name and st.session_state.get("nav_active_page") == page_name
                page_marker = "●" if is_active_page else "○"
                page_label = f"   {page_marker} {page_name}"
                if st.sidebar.button(page_label, key=widget_key("nav_page", menu_name, page_name), use_container_width=True):
                    set_active_route(menu_name, page_name)
                    st.rerun()

    return st.session_state.get("nav_active_menu", "Dashboard"), st.session_state.get("nav_active_page", "Executive Summary")


main_section, page = render_sidebar()

if report is not None:
    validation = report.get("Data Validation", pd.DataFrame())
    if not validation.empty and validation["Issue Type"].eq("Missing Supplier Name").any():
        st.warning("Supplier name missing. Items are grouped under Unknown Supplier.")

if main_section == "Dashboard" and page == "Executive Summary":
    render_dashboard_summary(report)
elif main_section == "Dashboard" and page == "Business Recommendations":
    render_business_recommendations_page(report)
elif main_section == "Item-wise Sales" and page == "View Sales":
    render_sales_view_page()
elif main_section == "Item-wise Sales" and page == "Upload Sales":
    render_sales_upload_page()
elif main_section == "Stock" and page == "View Stock":
    render_stock_view_page(report)
elif main_section == "Stock" and page == "Upload Stock":
    render_stock_upload_page()
elif main_section == "Stock" and page == "Bulk Item Update":
    render_bulk_mark_discontinued_page(report)
elif main_section == "Categories" and page == "View Categories":
    render_categories_view_page(report)
elif main_section == "Categories" and page == "Add Category":
    render_add_category_page()
elif main_section == "Categories" and page == "Item Category Mapping":
    render_item_category_mapping_page(report)
elif main_section == "Categories" and page == "Bulk Category Assignment":
    render_bulk_category_assignment_page(report)
elif main_section == "Purchase Planning" and page == "Run Analysis":
    render_purchase_run_analysis_page()
elif main_section == "Purchase Planning" and page == "Detailed Item Analysis":
    render_detailed_item_analysis_page(report)
elif main_section == "Purchase Planning" and page == "Optimized PO":
    render_optimized_po_page(report)
elif main_section == "Purchase Planning" and page == "Supplier Ready PO":
    render_supplier_ready_po_page(report)
elif main_section == "Purchase Planning" and page == "Overstock / Dead Stock":
    render_overstock_dead_stock_page(report)
elif main_section == "Suppliers" and page == "View Suppliers":
    render_suppliers_view_page(report)
elif main_section == "Suppliers" and page == "Supplier Item Mapping":
    render_supplier_item_mapping_page(report)
elif main_section == "Suppliers" and page == "Bulk Supplier Assignment":
    render_bulk_supplier_assignment_page(report)
elif main_section == "Discontinued Items" and page == "View Discontinued":
    render_discontinued_view_page(report)
elif main_section == "Discontinued Items" and page == "Bulk Mark Discontinued":
    render_bulk_mark_discontinued_page(report)
elif main_section == "Result History" and page in {"View Runs", "Load Run", "Delete Runs"}:
    render_result_history_page(report)
elif main_section == "Reports" and page == "Excel Export":
    render_excel_export_page(report)
elif main_section == "Reports" and page == "Data Validation":
    render_data_validation_page(report)
elif main_section == "Reports" and page == "Velocity Analysis":
    render_table_page("Velocity Analysis", report, "Velocity Analysis", "velocity_analysis")
elif main_section == "Reports" and page == "Trend Analysis":
    render_table_page("Trend Analysis", report, "Trend Analysis", "trend_analysis")
elif main_section == "Reports" and page == "Stock Risk":
    render_table_page("Stock Risk", report, "Stock Risk", "stock_risk")
elif main_section == "Settings" and page == "Analysis Settings":
    render_analysis_settings_page()
elif main_section == "Settings" and page == "Data File Status":
    render_data_file_status_page()

render_debug_item_velocity_page(report)
