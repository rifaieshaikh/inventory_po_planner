from __future__ import annotations

import streamlit as st

from src import file_manager, store_manager
from src.app.notifications import add_notification
from src.business.mapping_config_service import MappingConfigService
from src.column_mapper import get_field_specs
from src.domain.mapping_config import MappingConfig
from src.infra.mapping_config_repository import MappingConfigRepository


def _service() -> MappingConfigService:
    return MappingConfigService(MappingConfigRepository())


def _repository_from_service(service: MappingConfigService) -> MappingConfigRepository:
    repository = getattr(service, "repository", None)
    return repository if isinstance(repository, MappingConfigRepository) else MappingConfigRepository()


def _get_config(service: MappingConfigService, config_id: str) -> MappingConfig | None:
    getter = getattr(service, "get_config", None)
    if callable(getter):
        return getter(config_id)
    return _repository_from_service(service).get_config(config_id)


def _save_template(
    service: MappingConfigService,
    file_type: str,
    template_name: str,
    mapping: dict,
    previous_template_name: str = "",
) -> str:
    saver = getattr(service, "save_template", None)
    if callable(saver):
        return saver(file_type, template_name, mapping, previous_template_name)
    return _repository_from_service(service).save_template(file_type, template_name, mapping, previous_template_name)


def _save_store_mapping(service: MappingConfigService, file_type: str, store_id: str, mapping: dict, fy: str = "") -> None:
    saver = getattr(service, "save_store_mapping", None)
    if callable(saver):
        saver(file_type, store_id, mapping, fy)
        return
    _repository_from_service(service).save_store_mapping(file_type, store_id, mapping, fy)


def _delete_config(service: MappingConfigService, config_id: str) -> None:
    deleter = getattr(service, "delete_config", None)
    if callable(deleter):
        deleter(config_id)
        return
    _repository_from_service(service).delete_config(config_id)


def _copy_config_to_store(service: MappingConfigService, config_id: str, target_store_id: str, target_fy: str = "") -> None:
    copier = getattr(service, "copy_config_to_store", None)
    if callable(copier):
        copier(config_id, target_store_id, target_fy)
        return
    _repository_from_service(service).copy_config_to_store(config_id, target_store_id, target_fy)


def _widget_key(section: str, name: str, suffix: str = "") -> str:
    parts = [section, name]
    if suffix:
        parts.append(str(suffix))
    return "__".join(
        str(part).strip().replace(" ", "_").replace("/", "_").lower()
        for part in parts
        if part is not None and str(part).strip() != ""
    )


def _store_options() -> tuple[list[str], dict[str, str]]:
    stores = store_manager.load_stores(active_only=False)
    labels: list[str] = []
    lookup: dict[str, str] = {}
    for _, row in stores.iterrows():
        store_id = str(row.get("Store ID", ""))
        label = f"{store_id} | {row.get('Store Name', store_id)}"
        labels.append(label)
        lookup[label] = store_id
    return labels, lookup


def _year_options(default_year: str = "", existing_years: list[str] | None = None) -> tuple[list[str], int]:
    options = sorted(set((existing_years or []) + ["22-23", "23-24", "24-25", "25-26", "26-27", default_year]))
    options = [year for year in options if year]
    index = options.index(default_year) if default_year in options else 0
    return options, index


def _mapping_from_text_inputs(file_type: str, section_prefix: str, defaults: dict | None = None) -> dict[str, str | None]:
    defaults = defaults or {}
    mapping: dict[str, str | None] = {}
    for spec in get_field_specs(file_type):
        field = str(spec["field"])
        label = f"{field}{' *' if spec.get('required') else ''}"
        value = st.text_input(
            label,
            value=str(defaults.get(field) or ""),
            key=_widget_key(section_prefix, "field", field),
        )
        mapping[field] = value.strip() or None
    return mapping


def _render_config_form(
    file_type: str,
    section_prefix: str,
    config: MappingConfig | None = None,
) -> tuple[str, str, str, str, dict[str, str | None]]:
    source_options = ["Reusable Template", "Store Mapping"]
    source_index = 1 if config and config.source_kind == "store" else 0
    source_kind = st.radio(
        "Configuration Type",
        source_options,
        index=source_index,
        horizontal=True,
        key=_widget_key(section_prefix, "source_kind"),
    )

    template_name = config.template_name if config and config.source_kind == "template" else ""
    store_id = config.store_id if config and config.source_kind == "store" else ""
    fy = config.fy if config and config.source_kind == "store" else ""

    if source_kind == "Reusable Template":
        template_name = st.text_input(
            "Template Name",
            value=template_name,
            key=_widget_key(section_prefix, "template_name"),
        )
    else:
        labels, lookup = _store_options()
        current_label = next((label for label, value in lookup.items() if value == store_id), labels[0] if labels else "")
        if labels:
            selected = st.selectbox(
                "Store",
                labels,
                index=labels.index(current_label) if current_label in labels else 0,
                key=_widget_key(section_prefix, "store"),
            )
            store_id = lookup[selected]
        else:
            st.warning("No stores available. Add a store before saving store-specific mapping.")
        if file_type == "sales":
            existing_years = file_manager.list_available_sales_years(store_id) if store_id else []
            year_options, year_index = _year_options(fy, existing_years)
            fy = st.selectbox(
                "Financial Year",
                year_options,
                index=year_index,
                key=_widget_key(section_prefix, "fy"),
            )

    defaults = config.mapping if config else {}
    st.markdown("**Logical Field Mapping**")
    mapping = _mapping_from_text_inputs(file_type, section_prefix, defaults)
    return source_kind, template_name, store_id, fy, mapping


def _save_config_from_form(
    service: MappingConfigService,
    file_type: str,
    source_kind: str,
    template_name: str,
    store_id: str,
    fy: str,
    mapping: dict,
    previous_template_name: str = "",
) -> None:
    if source_kind == "Reusable Template":
        saved_name = _save_template(service, file_type, template_name, mapping, previous_template_name)
        add_notification("success", f"Saved mapping template {saved_name}.", context="Mapping Configuration")
        return
    _save_store_mapping(service, file_type, store_id, mapping, fy)
    add_notification("success", "Saved store mapping configuration.", context="Mapping Configuration")


def _modal_config(service: MappingConfigService, config_id: str, state_key: str) -> MappingConfig | None:
    config_id = str(config_id or "").strip()
    if not config_id:
        st.session_state[state_key] = ""
        return None
    try:
        config = _get_config(service, config_id)
    except Exception as exc:
        st.session_state[state_key] = ""
        st.error(f"Could not load mapping configuration: {exc}")
        return None
    if not config:
        st.session_state[state_key] = ""
        st.warning("Mapping configuration not found.")
        return None
    return config


def _render_add_modal(file_type: str) -> None:
    service = _service()
    title = "Add Stock Mapping" if file_type == "stock" else "Add Item-wise Sales Mapping"

    def body() -> None:
        with st.form(_widget_key("mapping_config_add", "form", file_type)):
            source_kind, template_name, store_id, fy, mapping = _render_config_form(file_type, f"mapping_config_add_{file_type}")
            col_a, col_b = st.columns(2)
            save = col_a.form_submit_button("Save Mapping", type="primary")
            cancel = col_b.form_submit_button("Cancel")
            if cancel:
                st.session_state[f"show_add_{file_type}_mapping"] = False
                st.rerun()
            if save:
                try:
                    _save_config_from_form(service, file_type, source_kind, template_name, store_id, fy, mapping)
                    st.session_state[f"show_add_{file_type}_mapping"] = False
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

    if hasattr(st, "dialog"):
        @st.dialog(title)
        def add_dialog():
            body()

        add_dialog()
    else:
        with st.expander(title, expanded=True):
            body()


def _render_edit_modal(config_id: str) -> None:
    service = _service()
    config = _modal_config(service, config_id, "edit_mapping_config_id")
    if not config:
        return
    title = f"Edit {config.label}"

    def body() -> None:
        with st.form(_widget_key("mapping_config_edit", "form", config_id)):
            source_kind, template_name, store_id, fy, mapping = _render_config_form(
                config.file_type,
                f"mapping_config_edit_{config_id}",
                config,
            )
            col_a, col_b = st.columns(2)
            save = col_a.form_submit_button("Save Changes", type="primary")
            cancel = col_b.form_submit_button("Cancel")
            if cancel:
                st.session_state["edit_mapping_config_id"] = ""
                st.rerun()
            if save:
                try:
                    previous_name = config.template_name if config.source_kind == "template" else ""
                    if config.source_kind == "store" and source_kind == "Reusable Template":
                        _delete_config(service, config.config_id)
                    elif config.source_kind == "template" and source_kind == "Store Mapping":
                        _delete_config(service, config.config_id)
                    _save_config_from_form(service, config.file_type, source_kind, template_name, store_id, fy, mapping, previous_name)
                    st.session_state["edit_mapping_config_id"] = ""
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

    if hasattr(st, "dialog"):
        @st.dialog(title)
        def edit_dialog():
            body()

        edit_dialog()
    else:
        with st.expander(title, expanded=True):
            body()


def _render_delete_modal(config_id: str) -> None:
    service = _service()
    config = _modal_config(service, config_id, "delete_mapping_config_id")
    if not config:
        return

    def body() -> None:
        st.warning(f"Delete mapping configuration: {config.label}?")
        col_a, col_b = st.columns(2)
        if col_a.button("Delete", type="primary", key=_widget_key("mapping_config_delete", "confirm", config_id)):
            try:
                _delete_config(service, config_id)
                st.session_state["delete_mapping_config_id"] = ""
                add_notification("warning", "Mapping configuration deleted.", context="Mapping Configuration")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if col_b.button("Cancel", key=_widget_key("mapping_config_delete", "cancel", config_id)):
            st.session_state["delete_mapping_config_id"] = ""
            st.rerun()

    if hasattr(st, "dialog"):
        @st.dialog("Delete Mapping Configuration")
        def delete_dialog():
            body()

        delete_dialog()
    else:
        with st.expander("Delete Mapping Configuration", expanded=True):
            body()


def _render_copy_modal(config_id: str) -> None:
    service = _service()
    config = _modal_config(service, config_id, "copy_mapping_config_id")
    if not config:
        return
    labels, lookup = _store_options()

    def body() -> None:
        if not labels:
            st.warning("No stores available.")
            return
        with st.form(_widget_key("mapping_config_copy", "form", config_id)):
            selected = st.selectbox("Copy to Store", labels, key=_widget_key("mapping_config_copy", "store", config_id))
            target_store_id = lookup[selected]
            target_fy = ""
            if config.file_type == "sales":
                existing_years = file_manager.list_available_sales_years(target_store_id)
                year_options, year_index = _year_options(config.fy, existing_years)
                target_fy = st.selectbox(
                    "Target Financial Year",
                    year_options,
                    index=year_index,
                    key=_widget_key("mapping_config_copy", "fy", config_id),
                )
            col_a, col_b = st.columns(2)
            copy = col_a.form_submit_button("Copy Mapping", type="primary")
            cancel = col_b.form_submit_button("Cancel")
            if cancel:
                st.session_state["copy_mapping_config_id"] = ""
                st.rerun()
            if copy:
                try:
                    _copy_config_to_store(service, config_id, target_store_id, target_fy)
                    st.session_state["copy_mapping_config_id"] = ""
                    add_notification("success", "Mapping configuration copied.", context="Mapping Configuration")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

    if hasattr(st, "dialog"):
        @st.dialog(f"Copy {config.label}")
        def copy_dialog():
            body()

        copy_dialog()
    else:
        with st.expander(f"Copy {config.label}", expanded=True):
            body()


def _render_mapping_configs(configs: list[MappingConfig], empty_message: str) -> None:
    if not configs:
        st.info(empty_message)
        return
    for config in configs:
        with st.container(border=True):
            st.subheader(config.label)
            meta = "Template" if config.source_kind == "template" else "Store Mapping"
            if config.fy:
                meta = f"{meta} | FY {config.fy}"
            st.caption(meta)
            st.dataframe(config.to_table(), hide_index=True, width="stretch")
            action_cols = st.columns(4)
            if action_cols[0].button("Edit", key=_widget_key("mapping_config", "edit", config.config_id), width="stretch"):
                st.session_state["edit_mapping_config_id"] = config.config_id
            if action_cols[1].button("Delete", key=_widget_key("mapping_config", "delete", config.config_id), width="stretch"):
                st.session_state["delete_mapping_config_id"] = config.config_id
            if action_cols[2].button("Copy to Store", key=_widget_key("mapping_config", "copy", config.config_id), width="stretch"):
                st.session_state["copy_mapping_config_id"] = config.config_id
            if action_cols[3].button("Use as Template", key=_widget_key("mapping_config", "template", config.config_id), width="stretch"):
                service = _service()
                name = f"{config.label} Copy"
                try:
                    _save_template(service, config.file_type, name, config.mapping)
                    add_notification("success", f"Saved template {name}.", context="Mapping Configuration")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def render_mapping_configuration_page(active_store_id: str, active_store_name: str) -> None:
    st.title("Mapping Configuration")
    st.caption(f"Selected store: {active_store_name} ({active_store_id})")
    include_all_stores = st.toggle(
        "Show mappings for all stores",
        value=False,
        key="mapping_configuration__all_stores",
    )

    service = _service()
    stock_tab, sales_tab = st.tabs(["Stock Mapping", "Item-wise Sales Mapping"])
    with stock_tab:
        if st.button("Add Stock Mapping", type="primary", key="mapping_configuration__add_stock"):
            st.session_state["show_add_stock_mapping"] = True
        stock_configs = service.list_stock_configs(include_all_stores=include_all_stores, active_store_id=active_store_id)
        _render_mapping_configs(stock_configs, "No saved stock mapping configuration found.")
    with sales_tab:
        if st.button("Add Item-wise Sales Mapping", type="primary", key="mapping_configuration__add_sales"):
            st.session_state["show_add_sales_mapping"] = True
        sales_configs = service.list_sales_configs(include_all_stores=include_all_stores, active_store_id=active_store_id)
        _render_mapping_configs(sales_configs, "No saved item-wise sales mapping configuration found.")

    if st.session_state.get("show_add_stock_mapping"):
        _render_add_modal("stock")
    if st.session_state.get("show_add_sales_mapping"):
        _render_add_modal("sales")
    if st.session_state.get("edit_mapping_config_id"):
        _render_edit_modal(str(st.session_state["edit_mapping_config_id"]))
    if st.session_state.get("delete_mapping_config_id"):
        _render_delete_modal(str(st.session_state["delete_mapping_config_id"]))
    if st.session_state.get("copy_mapping_config_id"):
        _render_copy_modal(str(st.session_state["copy_mapping_config_id"]))
