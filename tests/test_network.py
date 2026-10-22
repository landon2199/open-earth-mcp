"""Live integration test against Planetary Computer. Run with:  pytest -m network"""

from datetime import date

import pytest

pytestmark = pytest.mark.network

LON, LAT = -96.3365, 30.6187  # Texas A&M campus, College Station


def test_live_point_tools():
    from open_earth_mcp import data

    el = data.elevation(LON, LAT)
    assert 60 < el["elevation_m"] < 160  # College Station sits ~70-120 m above sea level
    assert all(c["passed"] for c in el["checks"])

    lc = data.land_cover(LON, LAT, 50)
    assert lc["class_code"] in (10, 20, 30, 40, 50, 60, 80, 90)
    assert lc["sources"]["item_ids"]

    ts = data.ndvi_timeseries(LON, LAT, date(2025, 4, 1), date(2025, 6, 30), 30, 60)
    assert ts["count"] > 0
    assert all(-1 <= r["ndvi_mean"] <= 1 and r["clear_pixels"] > 0 for r in ts["series"])
    assert all(r["item_ids"] for r in ts["series"])
    assert {c["name"]: c["passed"] for c in ts["checks"]}["ndvi_in_valid_range"]
