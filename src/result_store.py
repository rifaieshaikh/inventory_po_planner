from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import store_manager
from .excel_exporter import export_excel
from .file_manager import SALES_FILENAME, STOCK_FILENAME, get_sales_year_from_path
from .utils import DATA_DIR, RUNS_DIR


LEGACY_RESULTS_DIR = DATA_DIR / "results"
LEGACY_LATEST_DIR = LEGACY_RESULTS_DIR / "latest"
LEGACY_HISTORY_DIR = LEGACY_RESULTS_DIR / "history"

CSV_MAPPING = {
    "Store Summary": "store_summary.csv",
    "Executive Summary": "executive_summary.csv",
    "Data Validation": "data_validation.csv",
    "Velocity Calculation Warnings": "velocity_calculation_warnings.csv",
    "Velocity Analysis": "velocity_analysis.csv",
    "Trend Analysis": "trend_analysis.csv",
    "Stock Risk": "stock_risk.csv",
    "Detailed Item Analysis": "detailed_item_analysis.csv",
    "Optimized PO": "optimized_po.csv",
    "Supplier Ready PO": "supplier_ready_po.csv",
    "Supplier Ready PO Edited": "supplier_ready_po_edited.csv",
    "Overstock Dead Stock": "overstock_dead_stock.csv",
    "Discontinued Items": "discontinued_items.csv",
    "Supplier Master": "supplier_master.csv",
    "Item Supplier Mapping": "item_supplier_mapping.csv",
    "Categories": "categories.csv",
    "Item Category Mapping": "item_categories.csv",
    "Category Size Summary": "category_size_summary.csv",
}

TEXT_MAPPING = {
    "Business Recommendations": "business_recommendations.txt",
    "Assumptions": "assumptions.txt",
}


def results_dir(store_id: str) -> Path:
    return RUNS_DIR / str(store_id).strip()


def latest_dir(store_id: str) -> Path:
    return results_dir(store_id) / "latest" / "result"


def history_dir(store_id: str) -> Path:
    return results_dir(store_id)


def run_dir(store_id: str, run_id: str) -> Path:
    return history_dir(store_id) / run_id


def run_result_dir(store_id: str, run_id: str) -> Path:
    return run_dir(store_id, run_id) / "result"


def ensure_result_dirs(store_id: str) -> None:
    latest_dir(store_id).mkdir(parents=True, exist_ok=True)
    history_dir(store_id).mkdir(parents=True, exist_ok=True)


def generate_run_id(store_id: str) -> str:
    ensure_result_dirs(store_id)
    base = datetime.now().strftime("RUN-%Y%m%d-%H%M%S")
    run_id = base
    counter = 1
    while run_dir(store_id, run_id).exists():
        counter += 1
        run_id = f"{base}-{counter}"
    return run_id


def _relative(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(DATA_DIR.parent))
    except ValueError:
        return str(path)


def _modified(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def _summary_value(summary: pd.DataFrame, label: str, default=0):
    if summary is None or summary.empty or not {"Metric", "Value"}.issubset(summary.columns):
        return default
    rows = summary[summary["Metric"].astype(str).eq(label)]
    if rows.empty:
        return default
    value = rows.iloc[0]["Value"]
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _settings_summary(settings: dict) -> dict:
    return {
        "recent_period_months": settings.get("recent_period_months", 6),
        "budget_optimization_enabled": settings.get("enable_budget_optimization", False),
        "purchase_budget": settings.get("purchase_budget_amount", 0),
        "edge_band_rounding_enabled": settings.get("apply_box_rounding", True),
    }


def _write_report_files(report: dict, run_dir: Path) -> dict:
    files = {}
    for key, filename in CSV_MAPPING.items():
        df = report.get(key)
        if key == "Optimized PO" and df is None:
            df = report.get("Final PO")
        if isinstance(df, pd.DataFrame):
            df.to_csv(run_dir / filename, index=False)
            files[key] = filename

    for key, filename in TEXT_MAPPING.items():
        value = report.get(key)
        path = run_dir / filename
        if isinstance(value, pd.DataFrame):
            value.to_csv(path, sep="\t", index=False)
        elif value is not None:
            path.write_text(str(value), encoding="utf-8")
        else:
            pd.DataFrame().to_csv(path, sep="\t", index=False)
        files[key] = filename
    return files


def _snapshot_inputs(run_root: Path, stock_path: Path | None, sales_paths: list[Path]) -> tuple[Path | None, list[Path]]:
    stock_snapshot = None
    if stock_path and stock_path.exists():
        stock_snapshot = run_root / "stock" / STOCK_FILENAME
        stock_snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stock_path, stock_snapshot)

    sales_snapshots = []
    for source in sales_paths:
        if not source.exists():
            continue
        fy = get_sales_year_from_path(source)
        target = run_root / "item-wise-sales" / fy / SALES_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        sales_snapshots.append(target)
    return stock_snapshot, sales_snapshots


def _build_manifest(
    store_id: str,
    store_name: str,
    run_id: str,
    report: dict,
    settings: dict,
    selected_sales_years: list[str],
    stock_path: Path | None,
    sales_paths: list[Path],
    files: dict,
) -> dict:
    now = datetime.now().astimezone()
    summary = report.get("Executive Summary", pd.DataFrame())
    categories = report.get("Categories", pd.DataFrame())
    detail = report.get("Detailed Item Analysis", pd.DataFrame())
    category_name_series = detail["Category Name"] if isinstance(detail, pd.DataFrame) and "Category Name" in detail.columns else pd.Series(dtype=str)
    box_qty_series = categories["Box Qty"] if isinstance(categories, pd.DataFrame) and "Box Qty" in categories.columns else pd.Series(dtype=float)
    return {
        "run_id": run_id,
        "store_id": store_id,
        "store_name": store_name,
        "created_at": now.isoformat(timespec="seconds"),
        "created_at_display": now.strftime("%d-%b-%Y %I:%M %p"),
        "app_version": "",
        "stock_file": _relative(stock_path),
        "stock_file_modified_at": _modified(stock_path),
        "sales_years": selected_sales_years,
        "sales_files": [
            {"fy": get_sales_year_from_path(path), "path": _relative(path), "modified_at": _modified(path)}
            for path in sales_paths
        ],
        "settings": _settings_summary(settings),
        "summary": {
            "total_items_analyzed": _summary_value(summary, "Total items analyzed", 0),
            "items_recommended_for_purchase": _summary_value(summary, "Items recommended for purchase", 0),
            "urgent_items": _summary_value(summary, "Urgent PO items", 0),
            "high_items": _summary_value(summary, "High PO items", 0),
            "total_po_value": _summary_value(summary, "Total PO value", 0),
        },
        "category_summary": {
            "total_categories": int(len(categories)) if isinstance(categories, pd.DataFrame) else 0,
            "uncategorized_items": int(category_name_series.astype(str).eq("Uncategorized").sum()),
            "categories_missing_box_qty": int(pd.to_numeric(box_qty_series, errors="coerce").fillna(0).le(0).sum()),
        },
        "files": {
            "store_summary": files.get("Store Summary", "store_summary.csv"),
            "detailed_item_analysis": files.get("Detailed Item Analysis", "detailed_item_analysis.csv"),
            "optimized_po": files.get("Optimized PO", "optimized_po.csv"),
            "supplier_ready_po": files.get("Supplier Ready PO", "supplier_ready_po.csv"),
            "supplier_ready_po_edited": files.get("Supplier Ready PO Edited", ""),
            "categories": files.get("Categories", "categories.csv"),
            "item_categories": files.get("Item Category Mapping", "item_categories.csv"),
            "excel_report": "inventory_report.xlsx",
        },
    }


def _copy_tree_contents(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        target = destination / path.name
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)


def save_analysis_result(
    store_id: str,
    report: dict,
    settings: dict,
    selected_sales_years: list[str],
    stock_path: Path,
    sales_paths: list[Path],
    excel_bytes_or_path=None,
) -> str:
    ensure_result_dirs(store_id)
    store = store_manager.get_store_by_id(store_id) or {}
    store_name = str(store.get("Store Name", store_id))
    run_id = generate_run_id(store_id)
    run_root = run_dir(store_id, run_id)
    result_path = run_root / "result"
    result_path.mkdir(parents=True, exist_ok=False)
    stock_snapshot, sales_snapshots = _snapshot_inputs(run_root, stock_path, sales_paths)

    files = _write_report_files(report, result_path)
    excel_target = result_path / "inventory_report.xlsx"
    if excel_bytes_or_path:
        source = Path(excel_bytes_or_path)
        if source.exists():
            shutil.copy2(source, excel_target)
        else:
            export_excel(report, excel_target)
    else:
        export_excel(report, excel_target)

    manifest = _build_manifest(
        store_id,
        store_name,
        run_id,
        report,
        settings,
        selected_sales_years,
        stock_snapshot or stock_path,
        sales_snapshots or sales_paths,
        files,
    )
    manifest["run_root"] = _relative(run_root)
    manifest["result_path"] = _relative(result_path)
    (result_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _copy_tree_contents(result_path, latest_dir(store_id))
    return run_id


def _load_text_dataframe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, sep="\t").fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _load_run_dir(run_dir: Path) -> dict | None:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    report = {}
    warnings = []
    for key, filename in CSV_MAPPING.items():
        path = run_dir / filename
        if path.exists():
            try:
                report[key] = pd.read_csv(path).fillna("")
            except pd.errors.EmptyDataError:
                report[key] = pd.DataFrame()
        else:
            warnings.append(["Saved result file missing", "Warning", "", "", filename])
            report[key] = pd.DataFrame()

    for key, filename in TEXT_MAPPING.items():
        report[key] = _load_text_dataframe(run_dir / filename)

    if "Final PO" not in report:
        report["Final PO"] = report.get("Optimized PO", pd.DataFrame()).copy()
    if warnings:
        warning_df = pd.DataFrame(warnings, columns=["Issue Type", "Severity", "Item Code / SKU", "Item Name", "Details"])
        existing = report.get("Data Validation", pd.DataFrame())
        report["Data Validation"] = pd.concat([existing, warning_df], ignore_index=True)

    return {"report": report, "manifest": manifest, "path": run_dir, "excel_path": run_dir / "inventory_report.xlsx"}


def load_latest_result(store_id: str) -> dict | None:
    ensure_result_dirs(store_id)
    return _load_run_dir(latest_dir(store_id))


def _valid_run_id(run_id: str) -> bool:
    return bool(run_id) and run_id.startswith("RUN-") and "/" not in run_id and "\\" not in run_id and ".." not in run_id


def load_result(store_id: str, run_id: str) -> dict | None:
    ensure_result_dirs(store_id)
    if not _valid_run_id(run_id):
        return None
    return _load_run_dir(run_result_dir(store_id, run_id))


def list_result_runs(store_id: str) -> pd.DataFrame:
    ensure_result_dirs(store_id)
    rows = []
    for run_root in sorted([p for p in history_dir(store_id).iterdir() if p.is_dir() and _valid_run_id(p.name)], reverse=True):
        result_path = run_root / "result"
        manifest_path = result_path / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        summary = manifest.get("summary", {})
        rows.append(
            {
                "Store ID": manifest.get("store_id", store_id),
                "Store Name": manifest.get("store_name", ""),
                "Run ID": manifest.get("run_id", run_root.name),
                "Created At": manifest.get("created_at_display", manifest.get("created_at", "")),
                "Sales Years": ", ".join(manifest.get("sales_years", [])),
                "Total Items": summary.get("total_items_analyzed", 0),
                "PO Items": summary.get("items_recommended_for_purchase", 0),
                "Urgent Items": summary.get("urgent_items", 0),
                "High Items": summary.get("high_items", 0),
                "Total PO Value": summary.get("total_po_value", 0),
                "Path": str(result_path),
            }
        )
    return pd.DataFrame(rows)


def copy_result_to_latest(store_id: str, run_id: str) -> bool:
    if not _valid_run_id(run_id):
        return False
    source = run_result_dir(store_id, run_id)
    if not source.exists() or not source.is_dir():
        return False
    _copy_tree_contents(source, latest_dir(store_id))
    return True


def delete_result(store_id: str, run_id: str) -> bool:
    if not _valid_run_id(run_id):
        return False
    target = run_dir(store_id, run_id)
    try:
        target.resolve().relative_to(history_dir(store_id).resolve())
    except ValueError:
        return False
    if not target.exists() or not target.is_dir():
        return False
    shutil.rmtree(target)
    return True


def delete_all_results_except_latest(store_id: str) -> int:
    ensure_result_dirs(store_id)
    latest_run_id = ""
    latest_manifest = latest_dir(store_id) / "manifest.json"
    if latest_manifest.exists():
        try:
            latest_run_id = json.loads(latest_manifest.read_text(encoding="utf-8")).get("run_id", "")
        except json.JSONDecodeError:
            latest_run_id = ""
    deleted = 0
    for run_root in history_dir(store_id).iterdir():
        if run_root.is_dir() and run_root.name != latest_run_id and _valid_run_id(run_root.name):
            shutil.rmtree(run_root)
            deleted += 1
    return deleted
