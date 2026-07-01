from __future__ import annotations

import streamlit as st

from src.app.notifications import add_notification
from src.business.mapping_config_service import MappingConfigService
from src.column_mapper import get_field_specs
from src.infra.mapping_config_repository import MappingConfigRepository


def _service() -> MappingConfigService:
    return MappingConfigService(MappingConfigRepository())


def _widget_key(section: str, name: str, suffix: str = "") -> str:
    parts = [section, name]
    if suffix:
        parts.append(str(suffix))
    return "__".join(
        str(part).strip().replace(" ", "_").replace("/", "_").lower()
        for part in parts
        if part is not None and str(part).strip() != ""
    )


def _render_add_template_modal(file_type: str, mapping: dict, uploaded_columns: list[str], section_prefix: str) -> None:
    title = "Add Stock Mapping Template" if file_type == "stock" else "Add Item-wise Sales Mapping Template"
    options = ["Not Available"] + [str(column) for column in uploaded_columns]

    def body() -> None:
        with st.form(_widget_key(section_prefix, "add_template_form")):
            template_name = st.text_input("Template Name", key=_widget_key(section_prefix, "template_name"))
            template_mapping: dict[str, str | None] = {}
            for spec in get_field_specs(file_type):
                field = str(spec["field"])
                current = mapping.get(field)
                index = options.index(current) if current in options else 0
                choice = st.selectbox(
                    f"{field}{' *' if spec.get('required') else ''}",
                    options,
                    index=index,
                    key=_widget_key(section_prefix, "field", field),
                )
                template_mapping[field] = None if choice == "Not Available" else choice

            col_a, col_b = st.columns(2)
            save = col_a.form_submit_button("Save Template", type="primary")
            cancel = col_b.form_submit_button("Cancel")
            if cancel:
                st.session_state[_widget_key(section_prefix, "show_add_template")] = False
                st.rerun()
            if save:
                try:
                    saved_name = _service().save_template(file_type, template_name, template_mapping)
                    st.session_state[_widget_key(section_prefix, "show_add_template")] = False
                    add_notification("success", f"Saved mapping template {saved_name}.", context="Mapping Upload")
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


def render_upload_mapping_template_actions(
    file_type: str,
    mapping: dict,
    uploaded_columns: list[str],
    section_prefix: str,
) -> None:
    st.markdown("**Mapping Templates**")
    col_a, col_b = st.columns([1, 3])
    if col_a.button("Add Template", key=_widget_key(section_prefix, "add_template"), width="stretch"):
        st.session_state[_widget_key(section_prefix, "show_add_template")] = True
    col_b.caption("Save the current upload mapping as a reusable template.")

    if st.session_state.get(_widget_key(section_prefix, "show_add_template")):
        _render_add_template_modal(file_type, mapping, uploaded_columns, section_prefix)
