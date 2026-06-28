from __future__ import annotations

from pathlib import Path

import pandas as pd
from xlsxwriter.utility import xl_col_to_name

from .utils import REPORT_PATH
from .utils import ensure_required_output_columns


def _write_df(writer, sheet_name: str, df: pd.DataFrame) -> None:
    df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    workbook = writer.book
    worksheet = writer.sheets[sheet_name[:31]]
    header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
    money_fmt = workbook.add_format({"num_format": '#,##0.00'})
    qty_fmt = workbook.add_format({"num_format": '#,##0.00'})
    urgent_fmt = workbook.add_format({"bg_color": "#F4CCCC"})
    high_fmt = workbook.add_format({"bg_color": "#FCE5CD"})
    dead_fmt = workbook.add_format({"bg_color": "#EADCF8"})
    for col_num, value in enumerate(df.columns):
        worksheet.write(0, col_num, value, header_fmt)
        width = max(12, min(45, max([len(str(value))] + [len(str(v)) for v in df[value].head(100).tolist()])))
        worksheet.set_column(col_num, col_num, width)
        lower = str(value).lower()
        if "amount" in lower or "value" in lower or "price" in lower:
            worksheet.set_column(col_num, col_num, width, money_fmt)
        if "qty" in lower or "quantity" in lower or "stock" in lower:
            worksheet.set_column(col_num, col_num, width, qty_fmt)
    if len(df) > 0:
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(df), max(0, len(df.columns) - 1))
        if "Purchase Priority" in df.columns:
            col = df.columns.get_loc("Purchase Priority")
            col_name = xl_col_to_name(col)
            worksheet.conditional_format(1, 0, len(df), len(df.columns) - 1, {"type": "formula", "criteria": f'=${col_name}2="Urgent"', "format": urgent_fmt})
            worksheet.conditional_format(1, 0, len(df), len(df.columns) - 1, {"type": "formula", "criteria": f'=${col_name}2="High"', "format": high_fmt})
        class_col = "Velocity Class" if "Velocity Class" in df.columns else "Movement Category" if "Movement Category" in df.columns else None
        if class_col:
            col = df.columns.get_loc(class_col)
            col_name = xl_col_to_name(col)
            worksheet.conditional_format(1, 0, len(df), len(df.columns) - 1, {"type": "formula", "criteria": f'=${col_name}2="Dead Stock / No Sales"', "format": dead_fmt})
            worksheet.conditional_format(1, 0, len(df), len(df.columns) - 1, {"type": "formula", "criteria": f'=${col_name}2="Dormant"', "format": dead_fmt})
        if "Stock Risk Level" in df.columns:
            col = df.columns.get_loc("Stock Risk Level")
            col_name = xl_col_to_name(col)
            worksheet.conditional_format(1, 0, len(df), len(df.columns) - 1, {"type": "formula", "criteria": f'=${col_name}2="Overstock Risk"', "format": dead_fmt})


def export_excel(report: dict[str, pd.DataFrame], path: Path = REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        for sheet_name, df in report.items():
            if not isinstance(df, pd.DataFrame) or sheet_name.startswith("_"):
                continue
            if sheet_name in {"Detailed Item Analysis", "Final PO", "Optimized PO"}:
                df = ensure_required_output_columns(df)
            _write_df(writer, sheet_name, df)
    return path
