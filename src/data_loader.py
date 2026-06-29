from __future__ import annotations

from pathlib import Path

import pandas as pd

from .cleaner import clean_sales, clean_stock
from .column_mapper import detect_columns
from .file_manager import get_sales_year_from_path


def read_csv_flexible(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "latin1"]
    last_error = None
    for encoding in encodings:
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise last_error


def load_sales_files(paths: list[Path], mappings: dict[str, dict[str, str | None]] | None = None) -> tuple[pd.DataFrame, dict[str, dict[str, str | None]]]:
    frames = []
    used_mappings = {}
    for path in paths:
        fy = get_sales_year_from_path(path)
        raw = read_csv_flexible(path)
        mapping = mappings.get(fy) if mappings else detect_columns(raw.columns, "sales")
        used_mappings[fy] = mapping
        frames.append(clean_sales(raw, mapping, fy))
    if not frames:
        return pd.DataFrame(), used_mappings
    return pd.concat(frames, ignore_index=True), used_mappings


def load_stock_file(path: Path, mapping: dict[str, str | None] | None = None) -> tuple[pd.DataFrame, dict[str, str | None]]:
    raw = read_csv_flexible(path)
    mapping = mapping or detect_columns(raw.columns, "stock")
    return clean_stock(raw, mapping), mapping
