from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app.notifications import add_notifications
from src.business.item_master_service import ItemMasterService
from src.domain.item_master import (
    clean_item_text,
    detect_item_changes,
    display_item_label,
    editable_item_columns,
    ensure_editable_item_columns,
    inline_validation_warnings,
    item_key_from_row,
    row_action_change,
)
from src.infra.master_data_repository import MasterDataRepository
from src.utils import normalize_text


def widget_key(section: str, name: str, suffix: str = "") -> str:
    parts = [section, name]
    if suffix:
        parts.append(str(suffix))
    return "__".join(
        str(part).strip().replace(" ", "_").replace("/", "_").lower()
        for part in parts
        if part is not None and str(part).strip() != ""
    )


def _item_master_service() -> ItemMasterService:
    return ItemMasterService(MasterDataRepository())


def render_report_stale_banner() -> None:
    if st.session_state.get("report_stale"):
        st.warning("Item master data changed. Run analysis again to refresh PO recommendations.")


def _save_changes_and_refresh_session(
    store_id: str,
    section_prefix: str,
    changes,
) -> None:
    service = _item_master_service()
    result = service.save_item_changes(store_id, changes)
    if result.changed:
        report = st.session_state.get("report")
        if isinstance(report, dict):
            store_name = str(st.session_state.get("active_store_name", ""))
            st.session_state["report"] = service.apply_changes_to_report(report, store_id, store_name, changes)
        st.session_state["report_stale"] = True
        add_notifications(result.notification_messages(), context=section_prefix)


def _render_inline_item_validation_warnings(df: pd.DataFrame) -> None:
    warnings = inline_validation_warnings(df, report_stale=bool(st.session_state.get("report_stale")))
    if warnings:
        with st.expander("Inline item data checks", expanded=False):
            for warning in warnings:
                st.warning(warning)


def render_editable_item_list(
    df: pd.DataFrame,
    section_prefix: str,
    store_id: str,
    show_po_columns: bool = True,
    allow_category_edit: bool = True,
    allow_supplier_edit: bool = True,
    allow_discontinued_edit: bool = True,
) -> pd.DataFrame:
    render_report_stale_banner()
    editable_source = ensure_editable_item_columns(df)
    if editable_source.empty:
        st.info("No items to display.")
        return editable_source

    service = _item_master_service()
    category_options = service.category_options_for_items(editable_source)
    supplier_options = service.supplier_options_for_items(editable_source)
    if category_options.inactive_current:
        st.warning("Some items are assigned to inactive categories.")
    if supplier_options.inactive_current:
        st.warning("Some items are assigned to inactive suppliers.")

    display_cols = editable_item_columns(editable_source, show_po_columns)
    original = editable_source[display_cols].copy()
    column_config = {
        "Category Name": st.column_config.SelectboxColumn("Category", options=category_options.options, required=True),
        "Assigned Supplier Name": st.column_config.SelectboxColumn("Supplier", options=supplier_options.options, required=True),
        "Is Discontinued": st.column_config.CheckboxColumn("Discontinued"),
        "Discontinued Reason": st.column_config.TextColumn("Discontinued Reason"),
    }
    editable_cols: set[str] = set()
    if allow_category_edit:
        editable_cols.add("Category Name")
    if allow_supplier_edit:
        editable_cols.add("Assigned Supplier Name")
    if allow_discontinued_edit:
        editable_cols.update({"Is Discontinued", "Discontinued Reason"})
    disabled_cols = [col for col in original.columns if col not in editable_cols]

    editor_key = widget_key(section_prefix, "editable_table")
    edited = st.data_editor(
        original,
        key=editor_key,
        hide_index=True,
        width="stretch",
        disabled=disabled_cols,
        column_config={key: value for key, value in column_config.items() if key in original.columns},
        num_rows="fixed",
    )
    edited = ensure_editable_item_columns(edited)
    changes = detect_item_changes(original, edited, allow_category_edit, allow_supplier_edit, allow_discontinued_edit)
    _render_inline_item_validation_warnings(edited)

    auto_save = st.toggle("Auto-save inline changes", value=False, key=widget_key(section_prefix, "auto_save_inline_changes"))
    col_a, col_b = st.columns([1, 1])
    save_clicked = col_a.button(
        "Save All Item Changes",
        type="primary",
        disabled=not bool(changes),
        key=widget_key(section_prefix, "save_all_item_changes"),
    )
    reset_clicked = col_b.button("Reset Unsaved Changes", key=widget_key(section_prefix, "reset_unsaved_changes"))

    if reset_clicked:
        st.session_state.pop(editor_key, None)
        st.rerun()
    if changes and (save_clicked or auto_save):
        _save_changes_and_refresh_session(store_id, section_prefix, changes)
        st.session_state.pop(editor_key, None)
        st.rerun()
    return edited


def render_item_row_actions(
    df: pd.DataFrame,
    section_prefix: str,
    store_id: str,
) -> None:
    view = ensure_editable_item_columns(df)
    if view.empty:
        return

    st.subheader("Row Actions")
    service = _item_master_service()
    category_options = service.category_options_for_items(view).options
    supplier_options = service.supplier_options_for_items(view).options
    label_to_key: dict[str, str] = {}
    for idx, row in view.head(1000).iterrows():
        label = display_item_label(row, idx)
        if label in label_to_key:
            label = f"{label} | {row.get('Item Key', idx)}"
        label_to_key[label] = item_key_from_row(row)

    selected_label = st.selectbox(
        "Select Item",
        list(label_to_key.keys()),
        key=widget_key(section_prefix, "row_action_item"),
    )
    selected_key = label_to_key[selected_label]
    selected_rows = view[view["Item Key"].map(normalize_text).eq(selected_key)]
    if selected_rows.empty:
        st.warning("Selected item was not found.")
        return
    row = selected_rows.iloc[0]

    current_category = clean_item_text(row.get("Category Name", ""), "Uncategorized")
    current_supplier = clean_item_text(row.get("Assigned Supplier Name", ""), "Unknown Supplier")
    col_a, col_b, col_c = st.columns([1, 1, 1])
    category_choice = col_a.selectbox(
        "Quick Category",
        category_options,
        index=category_options.index(current_category) if current_category in category_options else 0,
        key=widget_key(section_prefix, "row_action_category"),
    )
    supplier_choice = col_b.selectbox(
        "Quick Supplier",
        supplier_options,
        index=supplier_options.index(current_supplier) if current_supplier in supplier_options else 0,
        key=widget_key(section_prefix, "row_action_supplier"),
    )
    reason = col_c.text_input(
        "Discontinued Reason",
        value=clean_item_text(row.get("Discontinued Reason", "")),
        key=widget_key(section_prefix, "row_action_discontinued_reason"),
    )

    action_cols = st.columns(5)
    if action_cols[0].button("Save Category", key=widget_key(section_prefix, "row_action_save_category")):
        change = row_action_change(row)
        change.category_name = category_choice
        change.category_changed = True
        _save_changes_and_refresh_session(store_id, section_prefix, [change])
        st.session_state.pop(widget_key(section_prefix, "editable_table"), None)
        st.rerun()
    if action_cols[1].button("Save Supplier", key=widget_key(section_prefix, "row_action_save_supplier")):
        change = row_action_change(row)
        change.supplier_name = supplier_choice
        change.supplier_changed = True
        _save_changes_and_refresh_session(store_id, section_prefix, [change])
        st.session_state.pop(widget_key(section_prefix, "editable_table"), None)
        st.rerun()
    if action_cols[2].button("Mark Discontinued", key=widget_key(section_prefix, "row_action_mark_discontinued")):
        change = row_action_change(row)
        change.is_discontinued = True
        change.discontinued_reason = reason
        change.discontinued_changed = True
        _save_changes_and_refresh_session(store_id, section_prefix, [change])
        st.session_state.pop(widget_key(section_prefix, "editable_table"), None)
        st.rerun()
    if action_cols[3].button("Remove Discontinued", key=widget_key(section_prefix, "row_action_remove_discontinued")):
        change = row_action_change(row)
        change.is_discontinued = False
        change.discontinued_reason = ""
        change.discontinued_changed = True
        _save_changes_and_refresh_session(store_id, section_prefix, [change])
        st.session_state.pop(widget_key(section_prefix, "editable_table"), None)
        st.rerun()
    if action_cols[4].button("View Item Details", key=widget_key(section_prefix, "row_action_view_item")):
        st.session_state[widget_key(section_prefix, "row_action_view_item_key")] = selected_key
        st.session_state[widget_key(section_prefix, "row_action_show_item")] = True
