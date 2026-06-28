from __future__ import annotations

import shutil
from pathlib import Path

from .utils import DATA_DIR, EXPORTS_DIR, SALES_DIR, STOCK_DIR


SALES_FILENAME = "item-wise-sales.csv"
STOCK_FILENAME = "stock.csv"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SALES_DIR.mkdir(parents=True, exist_ok=True)
    STOCK_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _save_uploaded(uploaded_file, destination: Path) -> Path:
    ensure_data_dirs()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        uploaded_file.seek(0)
        shutil.copyfileobj(uploaded_file, output)
    return destination


def save_sales_file(uploaded_file, fy: str) -> Path:
    fy = fy.strip()
    if not fy:
        raise ValueError("Financial year is required before saving a sales file.")
    return _save_uploaded(uploaded_file, SALES_DIR / fy / SALES_FILENAME)


def save_stock_file(uploaded_file) -> Path:
    return _save_uploaded(uploaded_file, STOCK_DIR / STOCK_FILENAME)


def list_available_sales_years() -> list[str]:
    ensure_data_dirs()
    years = []
    for path in SALES_DIR.iterdir():
        if path.is_dir() and (path / SALES_FILENAME).exists():
            years.append(path.name)
    return sorted(years)


def get_sales_file_paths(selected_years: list[str] | None = None) -> list[Path]:
    ensure_data_dirs()
    years = selected_years if selected_years is not None else list_available_sales_years()
    paths = []
    for fy in years:
        path = SALES_DIR / fy / SALES_FILENAME
        if path.exists():
            paths.append(path)
    return paths


def get_stock_file_path() -> Path | None:
    ensure_data_dirs()
    path = STOCK_DIR / STOCK_FILENAME
    return path if path.exists() else None


def delete_sales_year(fy: str) -> None:
    path = SALES_DIR / fy
    if path.exists() and path.is_dir():
        shutil.rmtree(path)


def describe_file(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {"available": False, "message": "Not available", "path": None, "modified": None}
    return {
        "available": True,
        "message": "Available",
        "path": path,
        "modified": path.stat().st_mtime,
    }
