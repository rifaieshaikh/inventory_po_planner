from __future__ import annotations

import re


EDGE_BAND_RULES = {
    "0.45 x 22": {"rolls": 26, "box_qty": 1300.0, "unit": "Meters"},
    "0.5 x 22": {"rolls": 26, "box_qty": 1300.0, "unit": "Meters"},
    "0.5 x 40": {"rolls": 15, "box_qty": 750.0, "unit": "Meters"},
    "0.8 x 22": {"rolls": 15, "box_qty": 750.0, "unit": "Meters"},
    "2 x 22": {"rolls": 6, "box_qty": 600.0, "unit": "Meters"},
}


def detect_edge_band_size(item_name: object) -> tuple[str | None, float | None]:
    text = str(item_name or "").upper().replace("MM", "")
    text = re.sub(r"\s+", "", text)
    patterns = [
        (r"(?<!\d)(?:0?\.45|0\.45)X22(?!\d)", "0.45 x 22"),
        (r"(?<!\d)(?:0?\.5|0\.50|0\.5)X22(?!\d)", "0.5 x 22"),
        (r"(?<!\d)(?:0?\.5|0\.50|0\.5)X40(?!\d)", "0.5 x 40"),
        (r"(?<!\d)(?:0?\.8|0\.80|0\.8)X22(?!\d)", "0.8 x 22"),
        (r"(?<!\d)2(?:\.0)?X22(?!\d)", "2 x 22"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, text):
            return label, EDGE_BAND_RULES[label]["box_qty"]
    return None, None
