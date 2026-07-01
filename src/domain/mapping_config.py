from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class FieldMapping:
    logical_field: str
    field_in_file: str


@dataclass(frozen=True)
class MappingConfig:
    config_id: str
    config_type: str
    label: str
    file_type: str
    source_kind: str
    fields: tuple[FieldMapping, ...]
    store_id: str = ""
    store_name: str = ""
    fy: str = ""
    template_name: str = ""

    @property
    def mapping(self) -> dict[str, str | None]:
        return {
            field.logical_field: None if field.field_in_file == "Not Available" else field.field_in_file
            for field in self.fields
        }

    def to_table(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Logical Field": field.logical_field,
                    "Field in File": field.field_in_file,
                }
                for field in self.fields
            ],
            columns=["Logical Field", "Field in File"],
        )
