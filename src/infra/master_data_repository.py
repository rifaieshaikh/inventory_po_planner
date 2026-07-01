from __future__ import annotations

import pandas as pd

from src import master_data_manager as mdm


class MasterDataRepository:
    """Infrastructure adapter for master-data CSV persistence."""

    def ensure_uncategorized_category_exists(self) -> dict:
        return mdm.ensure_uncategorized_category_exists()

    def load_categories(self, active_only: bool = False) -> pd.DataFrame:
        return mdm.load_categories(active_only=active_only)

    def load_suppliers(self, active_only: bool = False) -> pd.DataFrame:
        return mdm.load_suppliers(active_only=active_only)

    def load_item_categories(self, store_id: str) -> pd.DataFrame:
        return mdm.load_item_categories(store_id)

    def load_item_suppliers(self, store_id: str) -> pd.DataFrame:
        return mdm.load_item_suppliers(store_id)

    def set_item_category(
        self,
        store_id: str,
        item_key: str,
        item_code: str,
        item_name: str,
        category_id: str,
        category_name: str,
    ) -> None:
        mdm.set_item_category(store_id, item_key, item_code, item_name, category_id, category_name)

    def set_item_supplier(
        self,
        store_id: str,
        item_key: str,
        item_code: str,
        item_name: str,
        supplier_id: str,
        supplier_name: str,
    ) -> None:
        mdm.set_item_supplier(store_id, item_key, item_code, item_name, supplier_id, supplier_name)

    def set_discontinued_item(
        self,
        store_id: str,
        item_key: str,
        item_code: str,
        item_name: str,
        discontinued: bool,
        reason: str = "",
    ) -> None:
        mdm.set_discontinued_item(store_id, item_key, item_code, item_name, discontinued, reason)
