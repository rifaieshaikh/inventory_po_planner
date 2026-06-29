from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from src import file_manager
from src import store_manager
from src.data_loader import load_sales_files, load_stock_file
from src.debug_tools import item_debug_report
from src.po_calculator import calculate_po
from src.sales_analysis import analyze_sales
from src.stock_analysis import merge_stock_sales
from src.trend_analysis import analyze_trends


def main() -> int:
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print('Usage: python scripts/debug_item_velocity.py "VB-1114 MAT (0.45MMX22MM)"')
        return 1

    store_id = store_manager.create_default_store_if_missing()
    file_manager.migrate_single_store_data_to_default_store()
    sales_paths = file_manager.get_sales_file_paths(store_id)
    stock_path = file_manager.get_stock_file_path(store_id)
    if not stock_path or not sales_paths:
        print("Missing stock file or sales files.")
        return 1

    stock, _ = load_stock_file(stock_path)
    sales, _ = load_sales_files(sales_paths)
    sales_summary, monthly = analyze_sales(sales, 6)
    trend = analyze_trends(monthly, "Manual recent months", 6)
    merged = merge_stock_sales(sales_summary, trend, stock)
    settings = {
        "recent_period_months": 6,
        "very_fast_upward_months": 3.5,
        "fast_stable_months": 2.5,
        "medium_stable_months": 2.0,
        "slow_stable_months": 1.0,
        "recent_period_mode": "Manual recent months",
        "enable_budget_optimization": False,
        "purchase_budget_amount": 0,
        "allow_excess_rounding_fast": True,
        "allow_excess_rounding_slow": False,
        "skip_slow_excess_rounding": True,
        "exclude_dormant_dead": True,
        "apply_box_rounding": True,
        "min_purchase_value": 0,
    }
    detail = calculate_po(merged, settings)
    report = item_debug_report(query, sales_paths, sales, monthly, detail, stock)

    for title, df in report.items():
        print(f"\n=== {title} ===")
        if df.empty:
            print("(no rows)")
        else:
            pd.set_option("display.max_columns", None)
            pd.set_option("display.width", 220)
            print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
