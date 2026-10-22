"""Offline unit tests: validation, index math, masks and the MCP surface (no network)."""

import asyncio
import json
import math
from datetime import date

import numpy as np
import pytest

from open_earth_mcp import science as sci
from open_earth_mcp import validation as v


# --- validation ---------------------------------------------------------------
def test_lon_lat_ok():
    assert v.check_lon_lat(-96.3365, 30.6187) == (-96.3365, 30.6187)


@pytest.mark.parametrize("lon,lat", [(-200, 30), (30, -96.3), (0, 91), ("a", 1), (float("nan"), 0), (0, 85)])
def test_lon_lat_rejected(lon, lat):
    with pytest.raises(v.ValidationError):
        v.check_lon_lat(lon, lat)


def test_swapped_hint():
    with pytest.raises(v.ValidationError, match="swap"):
        v.check_lon_lat(30.6, -96.3)


def test_bbox_area_known_value():
    # 0.1 x 0.1 degree at the equator ~ 123.6 km^2
    assert v.bbox_area_km2(v.BBox(0, 0, 0.1, 0.1)) == pytest.approx(123.6, rel=0.01)


def test_bbox_cap_and_order():
    assert v.check_bbox([-96.36, 30.60, -96.32, 30.63]).west == -96.36
    with pytest.raises(v.ValidationError, match="limit"):
        v.check_bbox([-97, 30, -96, 31])
    with pytest.raises(v.ValidationError, match="west"):
        v.check_bbox([-96.32, 30.60, -96.36, 30.63])
    with pytest.raises(v.ValidationError):
        v.check_bbox([1, 2, 3])


def test_dates():
    today = date(2026, 10, 22)
    assert v.check_dates("2026-01-01", "2026-06-30", today=today) == (date(2026, 1, 1), date(2026, 6, 30))
    with pytest.raises(v.ValidationError, match="after"):
        v.check_dates("2026-06-30", "2026-01-01", today=today)
    with pytest.raises(v.ValidationError, match="YYYY-MM-DD"):
        v.check_dates("06/30/2026", "2026-07-01", today=today)
    with pytest.raises(v.ValidationError, match="future"):
        v.check_dates("2027-01-01", "2027-02-01", today=today)
    with pytest.raises(v.ValidationError, match="limit"):
        v.check_dates("2016-01-01", "2026-01-01", today=today)
    with pytest.raises(v.ValidationError, match="begins"):
        v.check_dates("2010-01-01", "2010-06-01", today=today)


def test_utm_zone():
    assert v.utm_epsg(-96.3365, 30.6187) == 32614
    assert v.utm_epsg(151.2, -33.9) == 32756
    assert v.utm_epsg(180.0, 0) == 32660


def test_point_bbox_size():
    b = v.point_bbox(-96.3, 30.6, 1000)
    assert math.sqrt(v.bbox_area_km2(b)) == pytest.approx(2.0, rel=0.01)


def test_collection_whitelist():
    assert v.check_collection("sentinel-2-l2a") == "sentinel-2-l2a"
    with pytest.raises(v.ValidationError):
        v.check_collection("https://example.com/evil")


# --- index math ---------------------------------------------------------------
def test_ndvi_values():
    red = np.array([0.1, 0.2, 0.0, 0.3])
    nir = np.array([0.5, 0.2, 0.0, 0.1])
    out = sci.ndvi(red, nir)
    assert out[0] == pytest.approx(0.4 / 0.6)
    assert out[1] == 0.0
    assert np.isnan(out[2])  # 0/0 -> NaN, not an error
    assert out[3] == pytest.approx(-0.5)


def test_ndvi_bounds_random():
    rng = np.random.default_rng(0)
    out = sci.ndvi(rng.uniform(0, 1, 10_000), rng.uniform(0, 1, 10_000))
    assert np.nanmin(out) >= -1 and np.nanmax(out) <= 1


def test_boa_offset_by_baseline():
    assert sci.s2_boa_offset("05.11") == -1000.0
    assert sci.s2_boa_offset("04.00") == -1000.0
    assert sci.s2_boa_offset("03.01") == 0.0
    assert sci.s2_boa_offset(None) == 0.0


def test_offset_changes_ndvi():
    # A dark red / bright NIR pixel stored with the +1000 offset (baseline >= 04.00).
    red_dn, nir_dn = np.array([1300.0]), np.array([4000.0])
    right = sci.ndvi(sci.s2_reflectance(red_dn, -1000), sci.s2_reflectance(nir_dn, -1000))[0]
    wrong = sci.ndvi(sci.s2_reflectance(red_dn, 0), sci.s2_reflectance(nir_dn, 0))[0]
    assert right == pytest.approx((0.3 - 0.03) / (0.3 + 0.03))
    assert wrong < right - 0.2  # forgetting the offset biases NDVI low


def test_reflectance_nodata():
    r = sci.s2_reflectance(np.array([0, 2000]), -1000)
    assert np.isnan(r[0]) and r[1] == pytest.approx(0.1)


def test_scl_clear_mask():
    scl = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
    assert scl[sci.clear_mask(scl)].tolist() == [4, 5, 6]  # snow/ice (11) is not clear for NDVI


def test_summarize_empty_and_values():
    assert sci.summarize(np.array([np.nan]))["count"] == 0
    s = sci.summarize(np.array([0.2, 0.4, np.nan]))
    assert s["mean"] == pytest.approx(0.3) and s["count"] == 2


def test_class_shares():
    a = np.array([[40, 40, 40], [10, 10, 0]])
    out = sci.class_shares(a)
    assert out["pixels"] == 5
    assert out["shares"][0] == {"code": 40, "name": "Cropland", "percent": 60.0, "pixels": 3}
    assert sum(s["percent"] for s in out["shares"]) == pytest.approx(100)
    json.dumps(out)  # plain Python types only


def test_slope_horn_plane():
    # z rises 1 m per 30 m cell eastward -> slope atan(1/30)
    z = np.tile(np.arange(5, dtype=float), (5, 1))
    s = sci.slope_horn(z, 30.0, 30.0)
    assert np.isnan(s[0, 0])
    assert s[2, 2] == pytest.approx(math.degrees(math.atan(1 / 30)))
    assert sci.slope_horn(np.zeros((5, 5)), 30, 30)[2, 2] == 0


# --- MCP surface (in-process, no network) ---------------------------------------
def test_mcp_lists_tools_and_rejects_bad_input():
    from mcp import Client

    from open_earth_mcp.server import mcp

    async def run():
        async with Client(mcp) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert names == {"search_imagery", "ndvi_timeseries", "land_cover", "elevation", "area_summary", "verify"}
            for t in (await c.list_tools()).tools:
                assert t.annotations.read_only_hint is True
            bad = await c.call_tool("elevation", {"lon": -200, "lat": 30})
            assert bad.is_error and "outside" in bad.content[0].text
            bad = await c.call_tool("area_summary", {"bbox": [-97, 30, -96, 31]})
            assert bad.is_error and "km^2" in bad.content[0].text
            bad = await c.call_tool("ndvi_timeseries", {"lon": -96.3, "lat": 30.6, "start": "2026-05-01",
                                                        "end": "2026-01-01"})
            assert bad.is_error and "after" in bad.content[0].text
            res = await c.read_resource("catalog://collections")
            cat = json.loads(res.contents[0].text)
            assert cat["collections"]["esa-worldcover"]["license"] == "CC-BY-4.0"
            prompts = {p.name for p in (await c.list_prompts()).prompts}
            assert "describe_place" in prompts

    asyncio.run(run())


def test_only_planetary_computer_hosts():
    from open_earth_mcp.data import DataError, _check_href

    assert _check_href("https://sentinel2l2a01.blob.core.windows.net/x.tif?sig=1")
    for bad in ("https://example.com/x.tif", "http://sentinel2l2a01.blob.core.windows.net/x.tif", "file:///etc/x"):
        with pytest.raises(DataError):
            _check_href(bad)


def test_suspect_dips():
    assert sci.suspect_dips([0.8, 0.3, 0.85, 0.8]) == [1]
    assert sci.suspect_dips([0.8, 0.7, 0.6, 0.2]) == []  # a sustained decline (harvest) is not a dip
    assert sci.suspect_dips([0.5]) == []


def test_mosaic_mixed_baselines_scales_each_scene():
    # Same day, two tiles: tile A is pre-04.00 (no offset) and covers the left column;
    # tile B is 04.00+ (+1000 DN offset) and covers the right column. True reflectance is
    # red 0.05 / nir 0.40 everywhere, so NDVI must be identical on both sides.
    scl_a = np.array([[4, 0], [4, 0]])
    scl_b = np.array([[0, 4], [0, 4]])
    a = {"red": np.where(scl_a, 500, 0), "nir": np.where(scl_a, 4000, 0), "scl": scl_a,
         "offset": sci.s2_boa_offset("03.01")}
    b = {"red": np.where(scl_b, 1500, 0), "nir": np.where(scl_b, 5000, 0), "scl": scl_b,
         "offset": sci.s2_boa_offset("04.00")}
    m = sci.mosaic_scenes([a, b])
    nd = sci.ndvi(m["red"], m["nir"])
    expected = (0.40 - 0.05) / (0.40 + 0.05)
    assert np.allclose(nd, expected)
    assert m["offsets"].tolist() == [[0.0, -1000.0], [0.0, -1000.0]]
    ok, lo, hi = sci.reflectance_plausible(m["red"], m["nir"])
    assert ok and lo == pytest.approx(0.05) and hi == pytest.approx(0.40)
    # The old approach (one offset for the whole mosaic) gets the left column wrong and the
    # range check catches it: 500 DN - 1000 -> -0.05 reflectance.
    wrong_red = sci.s2_reflectance(np.where(scl_a, 500, 1500), -1000)
    assert not sci.reflectance_plausible(wrong_red, np.full((2, 2), 0.4))[0]


def test_mosaic_first_valid_scene_wins():
    s1 = {"red": np.array([[1500]]), "nir": np.array([[3000]]), "scl": np.array([[9]]), "offset": -1000.0}
    s2 = {"red": np.array([[1200]]), "nir": np.array([[5000]]), "scl": np.array([[4]]), "offset": -1000.0}
    m = sci.mosaic_scenes([s1, s2])
    assert m["scl"][0, 0] == 9  # cloud from the first scene is kept, then masked by clear_mask
    assert not sci.clear_mask(m["scl"])[0, 0]


def test_snow_excluded_from_ndvi_mask():
    scl = np.array([[11, 4], [11, 11]])
    assert sci.clear_mask(scl).sum() == 1
