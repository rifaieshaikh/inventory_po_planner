from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from src import file_manager, store_manager
from src.column_mapper import load_mapping, normalize_mapping, save_mapping
from src.domain.mapping_config import FieldMapping, MappingConfig


def _file_type_key(file_type: str) -> str:
    return "sales" if str(file_type).strip().lower() in {"sales", "item-wise sales", "item-wise-sales"} else "stock"


def _template_file_name(template_name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(template_name or "")).strip(" .")
    if not name:
        raise ValueError("Template name is required.")
    return f"{name}.json"


def _mapping_fields(mapping: dict, file_type: str) -> tuple[FieldMapping, ...]:
    normalized = normalize_mapping(mapping, _file_type_key(file_type))
    return tuple(
        FieldMapping(
            logical_field=str(logical_field),
            field_in_file=str(field_in_file or "Not Available"),
        )
        for logical_field, field_in_file in normalized.items()
    )


class MappingConfigRepository:
    """Infrastructure adapter for saved mapping configs and templates."""

    def list_stock_configs(self, include_all_stores: bool = False, active_store_id: str = "") -> list[MappingConfig]:
        configs: list[MappingConfig] = []
        stores = store_manager.load_stores(active_only=False)
        if not include_all_stores and active_store_id:
            stores = stores[stores["Store ID"].astype(str).eq(str(active_store_id))]

        for _, store in stores.iterrows():
            store_id = str(store.get("Store ID", ""))
            store_name = str(store.get("Store Name", store_id))
            mapping = load_mapping(file_manager.get_stock_mapping_path(store_id))
            if mapping:
                configs.append(
                    MappingConfig(
                        config_id=f"store_stock::{store_id}",
                        config_type="Stock",
                        label=f"{store_name} ({store_id})",
                        file_type="stock",
                        source_kind="store",
                        store_id=store_id,
                        store_name=store_name,
                        fields=_mapping_fields(mapping, "stock"),
                    )
                )
        configs.extend(self._list_template_configs("stock", "Stock Template"))
        return configs

    def list_sales_configs(self, include_all_stores: bool = False, active_store_id: str = "") -> list[MappingConfig]:
        configs: list[MappingConfig] = []
        stores = store_manager.load_stores(active_only=False)
        if not include_all_stores and active_store_id:
            stores = stores[stores["Store ID"].astype(str).eq(str(active_store_id))]

        for _, store in stores.iterrows():
            store_id = str(store.get("Store ID", ""))
            store_name = str(store.get("Store Name", store_id))
            for fy in file_manager.list_available_sales_years(store_id):
                mapping = load_mapping(file_manager.get_sales_mapping_path(store_id, fy))
                if mapping:
                    configs.append(
                        MappingConfig(
                            config_id=f"store_sales::{store_id}::{fy}",
                            config_type="Item-wise Sales",
                            label=f"{store_name} ({store_id}) - FY {fy}",
                            file_type="sales",
                            source_kind="store",
                            store_id=store_id,
                            store_name=store_name,
                            fy=fy,
                            fields=_mapping_fields(mapping, "sales"),
                        )
                    )
        configs.extend(self._list_template_configs("sales", "Item-wise Sales Template"))
        return configs

    def list_all_configs(self, include_all_stores: bool = True, active_store_id: str = "") -> list[MappingConfig]:
        return self.list_stock_configs(include_all_stores, active_store_id) + self.list_sales_configs(include_all_stores, active_store_id)

    def get_config(self, config_id: str) -> MappingConfig | None:
        for config in self.list_all_configs(include_all_stores=True):
            if config.config_id == config_id:
                return config
        return None

    def save_template(self, file_type: str, template_name: str, mapping: dict, previous_template_name: str = "") -> str:
        key = _file_type_key(file_type)
        template_name = str(template_name or "").strip()
        if not template_name:
            raise ValueError("Template name is required.")
        template_dir = file_manager.get_mapping_template_dir(key)
        template_dir.mkdir(parents=True, exist_ok=True)
        template_path = template_dir / _template_file_name(template_name)
        previous_path = template_dir / _template_file_name(previous_template_name) if previous_template_name else template_path
        existing = self._load_template_payload(previous_path)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        payload = {
            "template_name": str(template_name).strip(),
            "file_type": key,
            "mapping": normalize_mapping(mapping, key),
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }
        template_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if previous_template_name and previous_path != template_path:
            previous_path.unlink(missing_ok=True)
        return template_path.stem

    def save_store_mapping(self, file_type: str, store_id: str, mapping: dict, fy: str = "") -> None:
        key = _file_type_key(file_type)
        store_id = str(store_id or "").strip()
        if not store_id:
            raise ValueError("Store is required for store mapping.")
        if key == "sales":
            if not str(fy).strip():
                raise ValueError("Financial year is required for item-wise sales mapping.")
            save_mapping(file_manager.get_sales_mapping_path(store_id, fy), normalize_mapping(mapping, key))
        else:
            save_mapping(file_manager.get_stock_mapping_path(store_id), normalize_mapping(mapping, key))

    def delete_config(self, config_id: str) -> None:
        config = self.get_config(config_id)
        if config is None:
            raise ValueError("Mapping configuration not found.")
        if config.source_kind == "template":
            self._template_path_from_config(config).unlink(missing_ok=True)
            return
        if config.file_type == "sales":
            file_manager.get_sales_mapping_path(config.store_id, config.fy).unlink(missing_ok=True)
        else:
            file_manager.get_stock_mapping_path(config.store_id).unlink(missing_ok=True)

    def copy_config_to_store(self, config_id: str, target_store_id: str, target_fy: str = "") -> None:
        config = self.get_config(config_id)
        if config is None:
            raise ValueError("Mapping configuration not found.")
        self.save_store_mapping(config.file_type, target_store_id, config.mapping, target_fy)

    def _list_template_configs(self, file_type: str, label_prefix: str) -> list[MappingConfig]:
        configs: list[MappingConfig] = []
        template_dir = file_manager.get_mapping_template_dir(file_type)
        if not template_dir.exists():
            return configs
        for template_path in sorted(template_dir.glob("*.json")):
            payload = self._load_template_payload(template_path)
            mapping = payload.get("mapping", {})
            if isinstance(mapping, dict) and mapping:
                template_name = str(payload.get("template_name", template_path.stem)).strip() or template_path.stem
                configs.append(
                    MappingConfig(
                        config_id=f"template::{file_type}::{template_path.stem}",
                        config_type=label_prefix,
                        label=f"{label_prefix}: {template_name}",
                        file_type=file_type,
                        source_kind="template",
                        template_name=template_name,
                        fields=_mapping_fields(mapping, file_type),
                    )
                )
        return configs

    def _template_path(self, file_type: str, template_name: str) -> Path:
        key = _file_type_key(file_type)
        return file_manager.get_mapping_template_dir(key) / _template_file_name(template_name)

    def _template_path_from_config(self, config: MappingConfig) -> Path:
        parts = config.config_id.split("::", 2)
        if len(parts) == 3 and parts[0] == "template":
            return file_manager.get_mapping_template_dir(parts[1]) / f"{parts[2]}.json"
        return self._template_path(config.file_type, config.template_name)

    @staticmethod
    def _load_template_payload(template_path: Path) -> dict:
        try:
            payload = json.loads(template_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}
