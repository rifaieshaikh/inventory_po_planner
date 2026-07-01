from __future__ import annotations

from typing import Protocol

from src.domain.mapping_config import MappingConfig


class MappingConfigRepositoryProtocol(Protocol):
    def list_stock_configs(self, include_all_stores: bool = False, active_store_id: str = "") -> list[MappingConfig]: ...
    def list_sales_configs(self, include_all_stores: bool = False, active_store_id: str = "") -> list[MappingConfig]: ...
    def get_config(self, config_id: str) -> MappingConfig | None: ...
    def save_template(self, file_type: str, template_name: str, mapping: dict, previous_template_name: str = "") -> str: ...
    def save_store_mapping(self, file_type: str, store_id: str, mapping: dict, fy: str = "") -> None: ...
    def delete_config(self, config_id: str) -> None: ...
    def copy_config_to_store(self, config_id: str, target_store_id: str, target_fy: str = "") -> None: ...


class MappingConfigService:
    def __init__(self, repository: MappingConfigRepositoryProtocol):
        self.repository = repository

    def list_stock_configs(self, include_all_stores: bool, active_store_id: str) -> list[MappingConfig]:
        return self.repository.list_stock_configs(include_all_stores=include_all_stores, active_store_id=active_store_id)

    def list_sales_configs(self, include_all_stores: bool, active_store_id: str) -> list[MappingConfig]:
        return self.repository.list_sales_configs(include_all_stores=include_all_stores, active_store_id=active_store_id)

    def get_config(self, config_id: str) -> MappingConfig | None:
        return self.repository.get_config(config_id)

    def save_template(self, file_type: str, template_name: str, mapping: dict, previous_template_name: str = "") -> str:
        return self.repository.save_template(file_type, template_name, mapping, previous_template_name)

    def save_store_mapping(self, file_type: str, store_id: str, mapping: dict, fy: str = "") -> None:
        self.repository.save_store_mapping(file_type, store_id, mapping, fy)

    def delete_config(self, config_id: str) -> None:
        self.repository.delete_config(config_id)

    def copy_config_to_store(self, config_id: str, target_store_id: str, target_fy: str = "") -> None:
        self.repository.copy_config_to_store(config_id, target_store_id, target_fy)
