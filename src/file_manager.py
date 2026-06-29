from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from . import store_manager
from .utils import DATA_DIR, EXPORTS_DIR, RUNS_DIR, SALES_DIR, STOCK_DIR, STORES_DIR


SALES_FILENAME = "item-wise-sales.csv"
LEGACY_COMPACT_SALES_DIR = DATA_DIR / "itemwisesales"
LEGACY_COMPACT_SALES_FILENAME = "itemwisesales.csv"
STOCK_FILENAME = "stock.csv"
MIGRATION_NOTE = DATA_DIR / "stores" / ".single_store_migration.json"
MAPPING_FILENAME = "mapping.json"
UPLOAD_METADATA_FILENAME = "upload_metadata.json"
ORIGINAL_UPLOAD_DIRNAME = "original"
MAPPING_TEMPLATES_DIR = DATA_DIR / "master" / "mapping-templates"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SALES_DIR.mkdir(parents=True, exist_ok=True)
    STOCK_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    STORES_DIR.mkdir(parents=True, exist_ok=True)
    (MAPPING_TEMPLATES_DIR / "sales").mkdir(parents=True, exist_ok=True)
    (MAPPING_TEMPLATES_DIR / "stock").mkdir(parents=True, exist_ok=True)


def get_store_dir(store_id: str) -> Path:
    return store_manager.get_store_folder(store_id)


def get_store_sales_dir(store_id: str) -> Path:
    return SALES_DIR


def get_store_stock_dir(store_id: str) -> Path:
    return STOCK_DIR / str(store_id).strip()


def get_sales_store_dir(store_id: str, fy: str) -> Path:
    return SALES_DIR / str(fy).strip() / str(store_id).strip()


def get_stock_store_dir(store_id: str, fy: str) -> Path:
    return get_store_stock_dir(store_id)


def get_sales_file_path_for_year(store_id: str, fy: str) -> Path:
    return get_sales_store_dir(store_id, fy) / SALES_FILENAME


def get_sales_mapping_path(store_id: str, fy: str) -> Path:
    return get_sales_store_dir(store_id, fy) / MAPPING_FILENAME


def get_sales_upload_metadata_path(store_id: str, fy: str) -> Path:
    return get_sales_store_dir(store_id, fy) / UPLOAD_METADATA_FILENAME


def get_sales_original_dir(store_id: str, fy: str) -> Path:
    return get_sales_store_dir(store_id, fy) / ORIGINAL_UPLOAD_DIRNAME


def get_sales_year_from_path(path: Path) -> str:
    path = Path(path)
    if path.parent.parent.parent.name in {SALES_DIR.name, LEGACY_COMPACT_SALES_DIR.name}:
        return path.parent.parent.name
    return path.parent.name


def get_stock_file_path_for_year(store_id: str, fy: str | None = None) -> Path:
    return get_store_stock_dir(store_id) / STOCK_FILENAME


def get_stock_mapping_path(store_id: str, fy: str | None = None) -> Path:
    return get_store_stock_dir(store_id) / MAPPING_FILENAME


def get_stock_upload_metadata_path(store_id: str, fy: str | None = None) -> Path:
    return get_store_stock_dir(store_id) / UPLOAD_METADATA_FILENAME


def get_stock_original_dir(store_id: str, fy: str | None = None) -> Path:
    return get_store_stock_dir(store_id) / ORIGINAL_UPLOAD_DIRNAME


def get_mapping_template_dir(file_type: str) -> Path:
    folder = "sales" if str(file_type).strip().lower() in {"sales", "item-wise sales", "item-wise-sales"} else "stock"
    return MAPPING_TEMPLATES_DIR / folder


def get_store_master_dir(store_id: str) -> Path:
    return get_store_dir(store_id) / "master"


def get_store_results_dir(store_id: str) -> Path:
    return RUNS_DIR / str(store_id).strip()


def ensure_store_dirs(store_id: str) -> None:
    ensure_data_dirs()
    store_dir = get_store_dir(store_id)
    for path in [
        store_dir,
        SALES_DIR,
        STOCK_DIR,
        get_store_stock_dir(store_id),
        get_store_results_dir(store_id),
        get_store_master_dir(store_id),
    ]:
        path.mkdir(parents=True, exist_ok=True)


def _save_uploaded(uploaded_file, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        uploaded_file.seek(0)
        shutil.copyfileobj(uploaded_file, output)
    return destination


def _safe_filename(filename: str) -> str:
    name = Path(str(filename or "uploaded_file")).name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name or "uploaded_file"


def save_original_upload(uploaded_file, destination_dir: Path, timestamp: str | None = None) -> Path:
    timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _safe_filename(getattr(uploaded_file, "name", "uploaded_file"))
    destination = destination_dir / f"{timestamp}_{safe_name}"
    return _save_uploaded(uploaded_file, destination)


def save_sales_file(store_id: str, uploaded_file, fy: str) -> Path:
    fy = fy.strip()
    if not fy:
        raise ValueError("Financial year is required before saving a sales file.")
    ensure_store_dirs(store_id)
    return _save_uploaded(uploaded_file, get_sales_file_path_for_year(store_id, fy))


def save_stock_file(store_id: str, uploaded_file, fy: str | None = None) -> Path:
    ensure_store_dirs(store_id)
    return _save_uploaded(uploaded_file, get_stock_file_path_for_year(store_id))


def list_available_sales_years(store_id: str) -> list[str]:
    ensure_store_dirs(store_id)
    years = []
    for fy_dir in SALES_DIR.iterdir():
        if not fy_dir.is_dir():
            continue
        store_dir = fy_dir / store_id
        if (store_dir / SALES_FILENAME).exists() or (store_dir / LEGACY_COMPACT_SALES_FILENAME).exists():
            years.append(fy_dir.name)
    return sorted(years)


def list_available_stock_years(store_id: str) -> list[str]:
    ensure_store_dirs(store_id)
    return ["Current"] if get_stock_file_path(store_id) else []


def get_sales_file_paths(store_id: str, selected_years: list[str] | None = None) -> list[Path]:
    ensure_store_dirs(store_id)
    years = selected_years if selected_years is not None else list_available_sales_years(store_id)
    paths = []
    for fy in years:
        path = get_sales_file_path_for_year(store_id, fy)
        legacy_path = get_sales_store_dir(store_id, fy) / LEGACY_COMPACT_SALES_FILENAME
        if path.exists():
            paths.append(path)
        elif legacy_path.exists():
            paths.append(legacy_path)
    return paths


def get_stock_file_path(store_id: str, fy: str | None = None) -> Path | None:
    ensure_store_dirs(store_id)
    path = get_stock_file_path_for_year(store_id)
    if path.exists():
        return path
    return None


def delete_sales_year(store_id: str, fy: str) -> None:
    path = get_sales_store_dir(store_id, fy)
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


def get_store_data_status(store_id: str) -> dict[str, object]:
    ensure_store_dirs(store_id)
    stock = get_stock_file_path(store_id)
    sales_rows = []
    for fy in list_available_sales_years(store_id):
        path = get_sales_file_path_for_year(store_id, fy)
        if not path.exists():
            path = get_sales_store_dir(store_id, fy) / LEGACY_COMPACT_SALES_FILENAME
        sales_rows.append({"FY": fy, "Path": path, "Modified": path.stat().st_mtime if path.exists() else None})
    stock_path = stock or get_stock_file_path_for_year(store_id)
    stock_rows = [{"Path": stock_path, "Modified": stock_path.stat().st_mtime if stock_path.exists() else None}]
    latest_manifest = get_store_results_dir(store_id) / "latest" / "result" / "manifest.json"
    latest_run_id = ""
    latest_created_at = ""
    if latest_manifest.exists():
        try:
            manifest = json.loads(latest_manifest.read_text(encoding="utf-8"))
            latest_run_id = manifest.get("run_id", "")
            latest_created_at = manifest.get("created_at_display", manifest.get("created_at", ""))
        except json.JSONDecodeError:
            latest_run_id = ""
            latest_created_at = ""
    return {
        "stock_exists": bool(stock),
        "stock_path": stock_path,
        "stock_modified": stock.stat().st_mtime if stock and stock.exists() else None,
        "stock_years": list_available_stock_years(store_id),
        "stock_files": stock_rows,
        "sales_years": [row["FY"] for row in sales_rows],
        "sales_files": sales_rows,
        "latest_result_exists": latest_manifest.exists(),
        "latest_run_id": latest_run_id,
        "latest_created_at": latest_created_at,
    }


def _copy_file_if_missing(source: Path, destination: Path, copied: list[dict[str, str]]) -> None:
    if source.exists() and source.is_file() and not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append({"source": str(source), "destination": str(destination)})


def _copy_tree_if_destination_missing(source: Path, destination: Path, copied: list[dict[str, str]]) -> None:
    if source.exists() and source.is_dir() and not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        copied.append({"source": str(source), "destination": str(destination)})


def _copy_tree_contents_if_missing(source: Path, destination: Path, copied: list[dict[str, str]]) -> None:
    if not source.exists() or not source.is_dir():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            _copy_tree_if_destination_missing(child, target, copied)
            if target.exists():
                _copy_tree_contents_if_missing(child, target, copied)
        else:
            _copy_file_if_missing(child, target, copied)


def migrate_single_store_data_to_default_store() -> dict[str, object]:
    ensure_data_dirs()
    default_store_id = store_manager.create_default_store_if_missing()
    ensure_store_dirs(default_store_id)

    copied: list[dict[str, str]] = []
    source_sales_dirs = [
        SALES_DIR,
        LEGACY_COMPACT_SALES_DIR,
        store_manager.get_store_folder(default_store_id) / "item-wise-sales",
    ]
    for source_sales_dir in source_sales_dirs:
        if source_sales_dir.exists():
            for fy_dir in source_sales_dir.iterdir():
                if not fy_dir.is_dir():
                    continue
                source_file = fy_dir / SALES_FILENAME
                if not source_file.exists():
                    source_file = fy_dir / LEGACY_COMPACT_SALES_FILENAME
                if not source_file.exists() and (fy_dir / default_store_id).is_dir():
                    source_file = fy_dir / default_store_id / SALES_FILENAME
                    if not source_file.exists():
                        source_file = fy_dir / default_store_id / LEGACY_COMPACT_SALES_FILENAME
                _copy_file_if_missing(source_file, get_sales_file_path_for_year(default_store_id, fy_dir.name), copied)

    if SALES_DIR.exists():
        for fy_dir in SALES_DIR.iterdir():
            if fy_dir.is_dir():
                for store_dir in fy_dir.iterdir():
                    if store_dir.is_dir():
                        legacy_file = store_dir / LEGACY_COMPACT_SALES_FILENAME
                        if legacy_file.exists():
                            _copy_file_if_missing(legacy_file, store_dir / SALES_FILENAME, copied)

    _copy_file_if_missing(STOCK_DIR / STOCK_FILENAME, get_stock_file_path_for_year(default_store_id), copied)
    old_store_stock = store_manager.get_store_folder(default_store_id) / "stock" / STOCK_FILENAME
    _copy_file_if_missing(old_store_stock, get_stock_file_path_for_year(default_store_id), copied)
    for fy_dir in STOCK_DIR.iterdir():
        if fy_dir.is_dir():
            _copy_file_if_missing(fy_dir / default_store_id / STOCK_FILENAME, get_stock_file_path_for_year(default_store_id), copied)
    target_results = get_store_results_dir(default_store_id)
    for legacy_results in [DATA_DIR / "results", store_manager.get_store_folder(default_store_id) / "results"]:
        latest_result = legacy_results / "latest"
        if latest_result.exists() and latest_result.is_dir():
            _copy_tree_contents_if_missing(latest_result, target_results / "latest" / "result", copied)
        history_results = legacy_results / "history"
        if history_results.exists() and history_results.is_dir():
            for run_dir in history_results.iterdir():
                if run_dir.is_dir() and run_dir.name.startswith("RUN-"):
                    _copy_tree_contents_if_missing(run_dir, target_results / run_dir.name / "result", copied)

    legacy_master_files = ["discontinued-items.csv", "item-suppliers.csv", "item-categories.csv"]
    for filename in legacy_master_files:
        _copy_file_if_missing(DATA_DIR / "master" / filename, get_store_master_dir(default_store_id) / filename, copied)

    if copied:
        MIGRATION_NOTE.parent.mkdir(parents=True, exist_ok=True)
        payload = {"default_store_id": default_store_id, "copied": copied}
        MIGRATION_NOTE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"default_store_id": default_store_id, "copied": copied, "note_path": MIGRATION_NOTE if copied else None}
