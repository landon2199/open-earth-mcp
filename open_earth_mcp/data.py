"""Data access: Microsoft Planetary Computer STAC + Cloud-Optimized GeoTIFF reads.

Every public function returns a JSON-serializable dict with:
  * the values, with units in the key names or a `units` field,
  * `sources`: STAC collection, item IDs and acquisition dates actually used,
  * `checks`: sanity checks run on the result (name, passed, detail),
  * `notes`: plain-language caveats, so an assistant can state uncertainty.

Only the fixed Planetary Computer STAC endpoint is contacted, and only asset
links returned (and signed) by it are opened. Nothing is written anywhere.
"""

from __future__ import annotations

import math
import os
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from urllib.parse import urlparse

# GDAL network settings must be in place before rasterio is imported.
_GDAL_DEFAULTS = {
    "GDAL_HTTP_TIMEOUT": "30",
    "GDAL_HTTP_CONNECTTIMEOUT": "10",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
}
for _k, _v in _GDAL_DEFAULTS.items():
    os.environ.setdefault(_k, _v)
import numpy as np  # noqa: E402
import odc.stac  # noqa: E402
import planetary_computer  # noqa: E402
import pystac_client  # noqa: E402
import rasterio  # noqa: E402
from affine import Affine  # noqa: E402
from odc.geo.geobox import GeoBox  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.errors import NotGeoreferencedWarning  # noqa: E402
from rasterio.windows import Window  # noqa: E402

from . import science as sci  # noqa: E402
from .validation import BBox, ValidationError, point_bbox, utm_epsg  # noqa: E402

# odc-stac reprojects into plain in-memory arrays, which makes rasterio emit this harmless warning.
warnings.filterwarnings("ignore", category=NotGeoreferencedWarning)

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
ALLOWED_ASSET_HOST_SUFFIX = ".blob.core.windows.net"
STAC_TIMEOUT_S = 30
READ_THREADS = 8


class _PersistentPool(ThreadPoolExecutor):
    """A thread pool that survives odc-stac's `with pool:` block.

    odc-stac shuts down any executor it is handed. Creating and tearing down a pool per
    call made new worker threads hang at start-up on Windows (GDAL/curl threads exiting
    while new ones attach), so one pool is created once and its threads are reused.
    """

    def __exit__(self, *exc) -> bool:
        return False


_POOL = _PersistentPool(max_workers=READ_THREADS, thread_name_prefix="cog-read")

COLLECTIONS = {
    "sentinel-2-l2a": {
        "title": "Sentinel-2 Level-2A surface reflectance",
        "used_for": "search_imagery, ndvi_timeseries, area_summary, verify",
        "resolution_m": "10 (B04, B08), 20 (SCL)",
        "license": "Copernicus Sentinel data terms (free, full and open; attribution required)",
        "license_url": "https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice",
        "attribution": "Contains modified Copernicus Sentinel data [year]",
    },
    "landsat-c2-l2": {
        "title": "Landsat Collection 2 Level-2",
        "used_for": "search_imagery",
        "resolution_m": "30",
        "license": "Public domain (USGS)",
        "license_url": "https://www.usgs.gov/core-science-systems/hdds/data-policy",
        "attribution": "Landsat imagery courtesy of the U.S. Geological Survey",
    },
    "esa-worldcover": {
        "title": "ESA WorldCover 10 m 2021 (v200)",
        "used_for": "land_cover, area_summary, verify",
        "resolution_m": "10",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "(c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) "
        "processed by ESA WorldCover consortium",
    },
    "cop-dem-glo-30": {
        "title": "Copernicus DEM GLO-30",
        "used_for": "elevation, area_summary, verify",
        "resolution_m": "30 (1 arc-second)",
        "license": "Copernicus DEM licence (free; attribution required)",
        "license_url": "https://spacedata.copernicus.eu/documents/20126/0/CSCDA_ESA_Mission-specific+Annex.pdf",
        "attribution": "(c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH 2014-2018 provided under "
        "COPERNICUS by the European Union and ESA; all rights reserved",
    },
}
PLATFORM_TERMS = "https://planetarycomputer.microsoft.com/terms-of-use"


class DataError(RuntimeError):
    """Raised when data cannot be found or read. The message is user-facing."""


# --- helpers -----------------------------------------------------------------
@lru_cache(maxsize=1)
def _catalog() -> pystac_client.Client:
    return pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace, timeout=STAC_TIMEOUT_S)


def _check_href(href: str) -> str:
    host = urlparse(href).hostname or ""
    if urlparse(href).scheme != "https" or not host.endswith(ALLOWED_ASSET_HOST_SUFFIX):
        raise DataError(f"Refusing to open an asset outside Planetary Computer storage: {host}")
    return href


def _search(collection: str, bbox: BBox, datetime_range: str | None = None, query: dict | None = None,
            max_items: int = 100, sortby: list | None = None) -> list:
    try:
        s = _catalog().search(
            collections=[collection],
            bbox=bbox.as_tuple(),
            datetime=datetime_range,
            query=query,
            max_items=max_items,
            sortby=sortby,
        )
        return list(s.items())
    except Exception as exc:  # network, HTTP 5xx, timeouts
        raise DataError(f"Planetary Computer STAC search failed ({type(exc).__name__}): {exc}") from exc


def _check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _iso(d) -> str:
    return d.strftime("%Y-%m-%d") if d else None


def _to_utm(lon: float, lat: float, epsg: int) -> tuple[float, float]:
    return Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)


def _point_geobox(lon: float, lat: float, half_m: float, res: float) -> tuple[GeoBox, int]:
    """Odd-sized UTM grid whose centre cell is centred on the point. Returns (geobox, centre index)."""
    epsg = utm_epsg(lon, lat)
    x, y = _to_utm(lon, lat, epsg)
    k = max(1, math.ceil(half_m / res))
    n = 2 * k + 1
    half = n * res / 2
    gb = GeoBox((n, n), Affine(res, 0.0, x - half, 0.0, -res, y + half), f"EPSG:{epsg}")
    return gb, k


def _disk(shape: tuple[int, int], centre: int, res: float, radius_m: float) -> np.ndarray:
    """Boolean mask of cells whose centres lie within radius_m of the centre cell."""
    yy, xx = np.indices(shape)
    d = np.hypot((yy - centre) * res, (xx - centre) * res)
    return d <= max(radius_m, 0.0) + 1e-9


def _load(items, bands, geobox: GeoBox, resampling, groupby="solar_day"):
    """Load onto `geobox`. groupby="id" keeps one slice per item, in input order (no mosaic)."""
    try:
        return odc.stac.load(
            items,
            bands=bands,
            geobox=geobox,
            groupby=groupby,
            resampling=resampling,
            pool=_POOL,
            fail_on_error=True,
            preserve_original_order=(groupby == "id"),
        )
    except Exception as exc:
        raise DataError(f"Reading imagery failed ({type(exc).__name__}): {exc}") from exc


def _sample_native(href: str, lon: float, lat: float) -> tuple[float, dict]:
    """Value of the native pixel containing (lon, lat), read straight from the COG (no resampling)."""
    with rasterio.open(_check_href(href)) as ds:
        x, y = (lon, lat) if ds.crs.to_epsg() == 4326 else _to_utm(lon, lat, ds.crs.to_epsg())
        row, col = ds.index(x, y)
        if not (0 <= row < ds.height and 0 <= col < ds.width):
            raise DataError("Point falls outside this tile.")
        v = ds.read(1, window=Window(col, row, 1, 1))[0, 0]
        nodata = ds.nodata
        meta = {"crs": str(ds.crs), "row": int(row), "col": int(col), "pixel_size": [abs(ds.res[0]), abs(ds.res[1])]}
    if nodata is not None and v == nodata:
        return float("nan"), meta
    return float(v), meta


def _pick_item_for_point(items, lon: float, lat: float):
    from shapely.geometry import Point, shape

    p = Point(lon, lat)
    for it in items:
        if shape(it.geometry).contains(p):
            return it
    return items[0] if items else None


# --- 1. search_imagery ---------------------------------------------------------
def search_imagery(bbox: BBox, start: date, end: date, collection: str, max_cloud: float, limit: int) -> dict:
    items = _search(
        collection,
        bbox,
        f"{start}/{end}",
        query={"eo:cloud_cover": {"lte": max_cloud}},
        max_items=limit,
        sortby=[{"field": "properties.datetime", "direction": "desc"}],
    )
    rows = []
    for it in items:
        p = it.properties
        rows.append({
            "id": it.id,
            "datetime_utc": p.get("datetime"),
            "cloud_cover_percent": p.get("eo:cloud_cover"),
            "platform": p.get("platform"),
            "tile": p.get("s2:mgrs_tile") or (f"{p.get('landsat:wrs_path')}/{p.get('landsat:wrs_row')}"
                                              if p.get("landsat:wrs_path") else None),
            "processing_baseline": p.get("s2:processing_baseline"),
            "preview": it.assets["rendered_preview"].href.split("?")[0] if "rendered_preview" in it.assets else None,
        })
    clouds = [r["cloud_cover_percent"] for r in rows if r["cloud_cover_percent"] is not None]
    checks = [
        _check("cloud_filter_respected", all(c <= max_cloud for c in clouds),
               f"all {len(clouds)} scenes have scene-level cloud cover <= {max_cloud}%"),
        _check("dates_in_range", all(str(start) <= r["datetime_utc"][:10] <= str(end) for r in rows),
               f"all acquisition dates between {start} and {end}"),
    ]
    notes = ["Cloud cover is the scene-level estimate for the whole ~110 km tile, not for this box."]
    if len(rows) == limit:
        notes.append(f"Result was capped at limit={limit}; more scenes may exist.")
    if not rows:
        notes.append("No scenes matched. Try a longer date range or a higher max_cloud.")
    return {
        "collection": collection,
        "bbox": list(bbox.as_tuple()),
        "date_range": [str(start), str(end)],
        "max_cloud_percent": max_cloud,
        "count": len(rows),
        "scenes": rows,
        "sources": {"stac_api": STAC_URL, "collection": collection, "item_ids": [r["id"] for r in rows]},
        "checks": checks,
        "notes": notes,
    }


# --- 2. ndvi_timeseries -------------------------------------------------------
def _ndvi_scenes(lon: float, lat: float, start: date, end: date, buffer_m: float, max_scene_cloud: float,
                 max_items: int = 150) -> dict:
    res = 10.0
    gb, c = _point_geobox(lon, lat, max(buffer_m, res), res)
    items = _search("sentinel-2-l2a", point_bbox(lon, lat, 1.0), f"{start}/{end}",
                    query={"eo:cloud_cover": {"lte": max_scene_cloud}}, max_items=max_items)
    if not items:
        return {"items": [], "rows": [], "skipped": [], "truncated": False}
    # One slice per item (no odc mosaic), so each item is scaled with its own baseline offset.
    ds = _load(items, ["B04", "B08", "SCL"], gb, resampling="nearest", groupby="id")
    disk = _disk((gb.shape[0], gb.shape[1]), c, res, buffer_m)

    by_day: dict[str, list[int]] = {}
    for i, it in enumerate(items):
        local = it.datetime + timedelta(hours=lon / 15.0)  # local solar day
        by_day.setdefault(local.date().isoformat(), []).append(i)

    rows, skipped = [], []
    for day in sorted(by_day):
        idx = by_day[day]
        ids = [items[i].id for i in idx]
        baselines = [items[i].properties.get("s2:processing_baseline") for i in idx]
        m = sci.mosaic_scenes([{"red": ds.B04.values[i], "nir": ds.B08.values[i], "scl": ds.SCL.values[i],
                                "offset": sci.s2_boa_offset(b)} for i, b in zip(idx, baselines)])
        scl = m["scl"]
        valid = (scl != 0) & disk
        clear = sci.clear_mask(scl) & disk
        n_valid, n_clear = int(valid.sum()), int(clear.sum())
        if n_valid == 0:
            skipped.append({"date": day, "reason": "no data at point", "item_ids": ids})
            continue
        if n_clear == 0:
            classes = {sci.SCL_CLASSES[int(k)]: int(v) for k, v in zip(*np.unique(scl[valid], return_counts=True))}
            skipped.append({"date": day, "reason": "no clear pixels", "scl_counts": classes, "item_ids": ids})
            continue
        v = sci.ndvi(m["red"], m["nir"])[clear]
        st = sci.summarize(v)
        if st["count"] == 0:
            skipped.append({"date": day, "reason": "clear pixels had no valid reflectance", "item_ids": ids})
            continue
        refl_ok, rmin, rmax = sci.reflectance_plausible(m["red"][clear], m["nir"][clear])
        used = sorted({float(o) for o in np.unique(m["offsets"][clear])})
        rows.append({
            "date": day,
            "ndvi_mean": st["mean"],
            "ndvi_std": st["std"],
            "clear_pixels": n_clear,
            "total_pixels": n_valid,
            "clear_fraction": round(n_clear / n_valid, 3),
            "snow_pixels": int(((scl == sci.SCL_SNOW) & disk).sum()),
            "item_ids": ids,
            "processing_baseline": sorted({b for b in baselines if b}),
            "boa_offset_applied": used[0] if len(used) == 1 else used,
            "_baseline_known": all(baselines),
            "_refl": (refl_ok, rmin, rmax),
            "_ndvi_min": st["min"],
            "_ndvi_max": st["max"],
        })
    return {"items": items, "rows": rows, "skipped": skipped, "window_pixels": int(disk.sum()),
            "truncated": len(items) >= max_items}


def ndvi_timeseries(lon: float, lat: float, start: date, end: date, buffer_m: float, max_scene_cloud: float) -> dict:
    r = _ndvi_scenes(lon, lat, start, end, buffer_m, max_scene_cloud)
    rows = r["rows"]
    mins = [x.pop("_ndvi_min") for x in rows]
    maxs = [x.pop("_ndvi_max") for x in rows]
    refl = [x.pop("_refl") for x in rows]
    known = [x.pop("_baseline_known") for x in rows]
    mixed = [x["date"] for x in rows if len({sci.s2_boa_offset(b) for b in x["processing_baseline"]}) > 1]
    bad_refl = [x["date"] for x, rf in zip(rows, refl) if not rf[0]]
    low_conf = [x["date"] for x in rows if x["clear_fraction"] < 0.5]
    for x in rows:
        x["low_confidence"] = x["clear_fraction"] < 0.5
    dips = set(sci.suspect_dips([x["ndvi_mean"] for x in rows]))
    for i, x in enumerate(rows):
        x["suspect_dip"] = i in dips
    # min/max dates use only dates that are neither low-confidence nor a one-date dip
    conf = [x for x in rows if not x["low_confidence"] and not x["suspect_dip"]]
    checks = [
        _check("ndvi_in_valid_range", all(-1 <= a and b <= 1 for a, b in zip(mins, maxs)),
               "every per-pixel NDVI lies in [-1, 1]"),
        _check("clear_pixels_positive", all(x["clear_pixels"] > 0 for x in rows),
               "every reported date has at least one clear pixel"),
        _check("processing_baseline_known", all(known),
               "every scene reports s2:processing_baseline, so its BOA offset (-1000 from 04.00) is known"
               if all(known) else "some scenes lack s2:processing_baseline; their offset was assumed to be 0"),
        _check("reflectance_in_expected_range", bool(rows) and not bad_refl,
               (f"clear-pixel B04/B08 reflectance after scaling lies in {list(sci.REFLECTANCE_RANGE)} on every "
                f"date (observed {min(r[1] for r in refl):.3f} to {max(r[2] for r in refl):.3f})")
               if rows and not bad_refl else
               f"reflectance outside {list(sci.REFLECTANCE_RANGE)} (wrong offset or bad pixels?) on: "
               f"{', '.join(bad_refl) or 'no dates'}"),
        _check("has_observations", len(rows) > 0, f"{len(rows)} clear dates out of {len(rows) + len(r['skipped'])}"),
    ]
    notes = [
        f"NDVI = (B08 - B04) / (B08 + B04) on surface reflectance, averaged over clear 10 m pixels within "
        f"{buffer_m:g} m of the point ({r.get('window_pixels', 0)} pixels when fully clear).",
        "Clear = SCL classes vegetation, not-vegetated and water. Cloud, cloud shadow, cirrus, dark-area "
        "shadow, defective, unclassified and snow/ice pixels are dropped. Each scene is scaled with its own "
        "processing-baseline offset before same-day tiles are mosaicked. SCL misses some thin cloud and haze, so "
        "isolated low values can still be cloud effects.",
        "Dates with clear_fraction < 0.5 are marked low_confidence. A suspect_dip date is > 0.2 below both "
        "neighbouring dates; that is more often missed thin cloud or haze than real change.",
    ]
    if mixed:
        notes.append(f"Dates mixing processing baselines before/after 04.00: {', '.join(mixed)}. Each scene was "
                     "scaled with its own offset before mosaicking.")
    if any(x["snow_pixels"] for x in rows):
        notes.append("Some dates had snow/ice pixels (SCL 11); they are excluded from NDVI (see snow_pixels).")
    if r.get("truncated"):
        notes.append("The scene search hit its cap of 150 items, so the earliest part of the range may be "
                     "missing. Use a shorter range for complete coverage.")
    if r["skipped"]:
        notes.append(f"{len(r['skipped'])} date(s) were skipped (fully cloudy or no data); see 'skipped'.")
    return {
        "point": {"lon": lon, "lat": lat},
        "buffer_m": buffer_m,
        "date_range": [str(start), str(end)],
        "units": {"ndvi": "unitless, -1 to 1", "pixels": "count of 10 m Sentinel-2 pixels"},
        "count": len(rows),
        "series": rows,
        "skipped": r["skipped"],
        "summary": {
            "ndvi_mean_of_dates": round(float(np.mean([x["ndvi_mean"] for x in rows])), 4) if rows else None,
            "ndvi_min_date": min(conf, key=lambda x: x["ndvi_mean"])["date"] if conf else None,
            "ndvi_max_date": max(conf, key=lambda x: x["ndvi_mean"])["date"] if conf else None,
            "low_confidence_dates": low_conf,
            "suspect_dip_dates": [x["date"] for x in rows if x["suspect_dip"]],
        },
        "sources": {"stac_api": STAC_URL, "collection": "sentinel-2-l2a",
                    "item_ids": sorted({i for x in rows for i in x["item_ids"]}),
                    "dates": [x["date"] for x in rows]},
        "checks": checks,
        "notes": notes,
    }


# --- 3. land_cover ------------------------------------------------------------
def _worldcover_items(bbox: BBox) -> list:
    items = _search("esa-worldcover", bbox, "2021-01-01/2021-12-31", max_items=20)
    items = [it for it in items if "2021" in it.id]
    if not items:
        raise DataError("No ESA WorldCover 2021 tile covers this location.")
    return items


def land_cover(lon: float, lat: float, buffer_m: float) -> dict:
    items = _worldcover_items(point_bbox(lon, lat, max(buffer_m, 20.0)))
    it = _pick_item_for_point(items, lon, lat)
    code, meta = _sample_native(it.assets["map"].href, lon, lat)
    code_i = None if math.isnan(code) else int(code)
    out = {
        "point": {"lon": lon, "lat": lat},
        "class_code": code_i,
        "class_name": sci.WORLDCOVER_CLASSES.get(code_i, "no data") if code_i is not None else "no data",
        "product": "ESA WorldCover 10 m 2021 v200",
        "pixel": meta,
    }
    checks = [_check("class_code_known", code_i in sci.WORLDCOVER_CLASSES,
                     f"code {code_i} is one of the 11 WorldCover classes")]
    used = [it.id]
    if buffer_m > 0:
        gb, c = _point_geobox(lon, lat, buffer_m, 10.0)
        ds = _load(items, ["map"], gb, resampling="nearest", groupby="id")
        arr = ds["map"].values.max(axis=0) if "time" in ds["map"].dims else ds["map"].values
        disk = _disk(arr.shape, c, 10.0, buffer_m)
        shares = sci.class_shares(arr[disk])
        out["buffer_m"] = buffer_m
        out["shares_within_buffer"] = shares["shares"]
        out["buffer_pixels"] = shares["pixels"]
        checks.append(_check("shares_sum_to_100", abs(sum(s["percent"] for s in shares["shares"]) - 100) < 0.1,
                             "class percentages sum to 100"))
        checks.append(_check("centre_matches_native", int(arr[c, c]) == code_i,
                             f"regridded centre cell ({int(arr[c, c])}) vs native pixel ({code_i})"))
        used = [i.id for i in items]
    return out | {
        "units": {"percent": "% of 10 m pixels"},
        "sources": {"stac_api": STAC_URL, "collection": "esa-worldcover", "item_ids": used, "reference_year": 2021},
        "checks": checks,
        "notes": [
            "WorldCover 2021 is a 10 m global map with ~77% overall accuracy (ESA validation report); "
            "single-pixel answers near class edges are uncertain, so use buffer_m > 0 for context.",
            "The map shows 2021 conditions and may not reflect later change.",
        ],
    }


# --- 4. elevation -------------------------------------------------------------
def _dem_items(bbox: BBox) -> list:
    items = _search("cop-dem-glo-30", bbox, max_items=10)
    if not items:
        raise DataError("No Copernicus GLO-30 tile covers this location.")
    return items


def _dem_window(lon: float, lat: float, items, half_m: float = 60.0):
    gb, c = _point_geobox(lon, lat, half_m, 30.0)
    ds = _load(items, ["data"], gb, resampling="bilinear", groupby="solar_day")
    z = ds["data"].values[0].astype("float64")
    z[z <= -32767] = np.nan
    return z, c


def elevation(lon: float, lat: float) -> dict:
    items = _dem_items(point_bbox(lon, lat, 100.0))
    it = _pick_item_for_point(items, lon, lat)
    z_native, meta = _sample_native(it.assets["data"].href, lon, lat)
    z, c = _dem_window(lon, lat, items)
    slope = sci.slope_horn(z, 30.0, 30.0)
    s_c = slope[c, c]
    local = slope[c - 1:c + 2, c - 1:c + 2]
    checks = [
        _check("elevation_plausible", -450 <= z_native <= 8900, f"{z_native:.1f} m lies within Earth's land range"),
        _check("native_vs_regridded", abs(z_native - z[c, c]) <= max(3.0, 30 * math.tan(math.radians(s_c))),
               f"native pixel {z_native:.1f} m vs bilinear 30 m UTM cell {z[c, c]:.1f} m"),
        _check("slope_in_range", 0 <= s_c <= 90, f"slope {s_c:.2f} degrees"),
    ]
    return {
        "point": {"lon": lon, "lat": lat},
        "elevation_m": round(z_native, 2),
        "slope_deg": round(float(s_c), 2),
        "slope_deg_mean_3x3": round(float(np.nanmean(local)), 2),
        "relief_m_150m_window": round(float(np.nanmax(z) - np.nanmin(z)), 2),
        "vertical_datum": "EGM2008 geoid (orthometric height)",
        "pixel": meta,
        "units": {"elevation": "metres above EGM2008", "slope": "degrees"},
        "sources": {"stac_api": STAC_URL, "collection": "cop-dem-glo-30", "item_ids": [i.id for i in items]},
        "checks": checks,
        "notes": [
            "Elevation is the native GLO-30 pixel (~30 m) containing the point. GLO-30 is a surface model: over "
            "buildings and forest it gives roof or canopy height, not bare ground.",
            "Slope uses Horn's 3x3 method on a 30 m UTM grid resampled bilinearly from GLO-30.",
            "GLO-30 absolute vertical accuracy is reported as < 4 m (90% linear error).",
        ],
    }


# --- 5. area_summary ----------------------------------------------------------
def _bbox_geobox(b: BBox, res: float) -> GeoBox:
    lon, lat = b.center
    epsg = utm_epsg(lon, lat)
    t = Transformer.from_crs(4326, epsg, always_xy=True)
    xs, ys = t.transform([b.west, b.east, b.west, b.east], [b.south, b.south, b.north, b.north])
    return GeoBox.from_bbox((min(xs), min(ys), max(xs), max(ys)), crs=f"EPSG:{epsg}", resolution=res)


def _latest_clear_ndvi(b: BBox, days_back: int, min_clear: float = 0.6, max_tries: int = 6) -> dict:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days_back)
    items = _search("sentinel-2-l2a", b, f"{start}/{end}", query={"eo:cloud_cover": {"lte": 40}}, max_items=40,
                    sortby=[{"field": "properties.datetime", "direction": "desc"}])
    gb = _bbox_geobox(b, 20.0)
    tried = []
    seen_days = []
    for it in items:
        day = it.datetime.date().isoformat()
        if day in seen_days:
            continue
        seen_days.append(day)
        same_day = [i for i in items if i.datetime.date().isoformat() == day]
        ds = _load(same_day, ["B04", "B08", "SCL"], gb, resampling="nearest", groupby="id")
        m = sci.mosaic_scenes([{"red": ds.B04.values[i], "nir": ds.B08.values[i], "scl": ds.SCL.values[i],
                                "offset": sci.s2_boa_offset(x.properties.get("s2:processing_baseline"))}
                               for i, x in enumerate(same_day)])
        scl = m["scl"]
        valid = scl != 0
        clear = sci.clear_mask(scl)
        frac = float(clear.sum() / valid.sum()) if valid.sum() else 0.0
        tried.append({"date": day, "clear_fraction": round(frac, 3)})
        if frac >= min_clear:
            st = sci.summarize(sci.ndvi(m["red"], m["nir"])[clear])
            refl_ok, rmin, rmax = sci.reflectance_plausible(m["red"][clear], m["nir"][clear])
            return {"date": day, "item_ids": [i.id for i in same_day], "clear_fraction": round(frac, 3),
                    "ndvi": st, "reflectance_range": [round(rmin, 4), round(rmax, 4)],
                    "reflectance_ok": refl_ok, "scenes_tried": tried}
        if len(tried) >= max_tries:
            break
    return {"date": None, "item_ids": [], "clear_fraction": None, "ndvi": None, "scenes_tried": tried}


def area_summary(b: BBox, days_back: int) -> dict:
    from .validation import bbox_area_km2

    lc_items = _worldcover_items(b)
    gb10 = _bbox_geobox(b, 10.0)
    lc = _load(lc_items, ["map"], gb10, resampling="nearest", groupby="id")
    arr = lc["map"].values.max(axis=0)
    shares = sci.class_shares(arr)

    dem_items = _dem_items(b)
    gb30 = _bbox_geobox(b, 30.0)
    z = _load(dem_items, ["data"], gb30, resampling="bilinear")["data"].values[0].astype("float64")
    z[z <= -32767] = np.nan
    slope = sci.slope_horn(z, 30.0, 30.0)

    nd = _latest_clear_ndvi(b, days_back)

    checks = [
        _check("landcover_pixels_positive", shares["pixels"] > 0, f"{shares['pixels']} WorldCover pixels"),
        _check("shares_sum_to_100", abs(sum(s["percent"] for s in shares["shares"]) - 100) < 0.1 if shares["shares"]
               else False, "class percentages sum to 100"),
        _check("dem_complete", bool(np.isfinite(z).all()), f"{int(np.isfinite(z).sum())}/{z.size} DEM cells valid"),
        _check("ndvi_found", nd["date"] is not None,
               f"clear scene found in last {days_back} days" if nd["date"] else
               f"no scene >= 60% clear in last {days_back} days"),
    ]
    if nd["ndvi"]:
        checks.append(_check("ndvi_in_valid_range", -1 <= nd["ndvi"]["min"] and nd["ndvi"]["max"] <= 1,
                             "every per-pixel NDVI lies in [-1, 1]"))
        checks.append(_check("reflectance_in_expected_range", nd["reflectance_ok"],
                             f"clear-pixel B04/B08 reflectance {nd['reflectance_range']} vs expected "
                             f"{list(sci.REFLECTANCE_RANGE)}"))
    return {
        "bbox": list(b.as_tuple()),
        "area_km2": round(bbox_area_km2(b), 3),
        "land_cover": {"reference_year": 2021, "pixels": shares["pixels"], "shares": shares["shares"][:6]},
        "terrain": {
            "elevation_m_mean": round(float(np.nanmean(z)), 2),
            "elevation_m_min": round(float(np.nanmin(z)), 2),
            "elevation_m_max": round(float(np.nanmax(z)), 2),
            "slope_deg_mean": round(float(np.nanmean(slope)), 2),
        },
        "latest_clear_ndvi": nd,
        "units": {"percent": "% of 10 m pixels", "elevation": "m (EGM2008)", "slope": "degrees",
                  "ndvi": "unitless, 20 m pixels"},
        "sources": {
            "stac_api": STAC_URL,
            "esa-worldcover": [i.id for i in lc_items],
            "cop-dem-glo-30": [i.id for i in dem_items],
            "sentinel-2-l2a": nd["item_ids"],
        },
        "checks": checks,
        "notes": [
            "Land-cover shares are for 2021. NDVI is from the most recent Sentinel-2 scene in which >= 60% of the "
            "box was clear, using only clear pixels, at 20 m.",
            "Elevation is a surface model (includes buildings and canopy).",
        ],
    }


# --- 6. verify ----------------------------------------------------------------
def _native_ndvi(item, lon: float, lat: float, radius_m: float) -> dict:
    """Independent NDVI: read B04/B08/SCL straight from the scene's own UTM grid with rasterio (no odc-stac)."""
    off = sci.s2_boa_offset(item.properties.get("s2:processing_baseline"))
    with rasterio.open(_check_href(item.assets["B04"].href)) as ds:
        x, y = _to_utm(lon, lat, ds.crs.to_epsg())
        res = abs(ds.res[0])
        row, col = ds.index(x, y)
        k = math.ceil(radius_m / res) + 1
        win = Window(col - k, row - k, 2 * k + 1, 2 * k + 1)
        b4 = ds.read(1, window=win, boundless=True, fill_value=0)
        wt = ds.window_transform(win)
    with rasterio.open(_check_href(item.assets["B08"].href)) as ds:
        b8 = ds.read(1, window=win, boundless=True, fill_value=0)
    rr, cc = np.indices(b4.shape)
    px, py = rasterio.transform.xy(wt, rr.ravel(), cc.ravel())
    px, py = np.asarray(px), np.asarray(py)
    with rasterio.open(_check_href(item.assets["SCL"].href)) as ds:  # 20 m: look up the cell under each 10 m centre
        srow, scol = rasterio.transform.rowcol(ds.transform, px, py)
        srow, scol = np.asarray(srow), np.asarray(scol)
        r0, c0 = srow.min(), scol.min()
        swin = Window(c0, r0, scol.max() - c0 + 1, srow.max() - r0 + 1)
        scl_block = ds.read(1, window=swin, boundless=True, fill_value=0)
    scl = scl_block[srow - r0, scol - c0].reshape(b4.shape)
    dist = np.hypot(px - x, py - y).reshape(b4.shape)
    clear = sci.clear_mask(scl) & (dist <= radius_m + 1e-9) & (b4 > 0)
    v = sci.ndvi(sci.s2_reflectance(b4, off), sci.s2_reflectance(b8, off))[clear]
    return {"ndvi_mean": sci.summarize(v)["mean"], "clear_pixels": int(clear.sum()), "boa_offset": off}


def verify(lon: float, lat: float, days_back: int = 120, buffer_m: float = 30.0) -> dict:
    checks, details = [], {}
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days_back)

    # A. NDVI: the odc-stac pipeline vs an independent rasterio read of the native scene grid.
    ts = _ndvi_scenes(lon, lat, start, end, buffer_m, 30.0)
    good = [r for r in ts["rows"] if r["clear_fraction"] >= 0.9]
    if good:
        row = good[-1]
        item = _pick_item_for_point([i for i in ts["items"] if i.id in row["item_ids"]], lon, lat)
        nat = _native_ndvi(item, lon, lat, buffer_m)
        diff = abs(nat["ndvi_mean"] - row["ndvi_mean"]) if nat["ndvi_mean"] is not None else None
        details["ndvi"] = {"date": row["date"], "item_id": item.id, "pipeline_ndvi": row["ndvi_mean"],
                           "independent_ndvi": nat["ndvi_mean"], "abs_difference": round(diff, 4) if diff is not None
                           else None, "pipeline_pixels": row["clear_pixels"], "independent_pixels": nat["clear_pixels"]}
        checks.append(_check("ndvi_recomputed_from_raw_bands", diff is not None and diff <= 0.03,
                             f"{row['date']}: pipeline {row['ndvi_mean']} vs raw-band recompute {nat['ndvi_mean']} "
                             f"(|diff| {diff:.4f}, tolerance 0.03 for grid alignment)" if diff is not None
                             else "independent read had no clear pixels"))
        checks.append(_check("ndvi_in_valid_range", -1 <= row["ndvi_mean"] <= 1, f"{row['ndvi_mean']}"))
        if nat["boa_offset"]:
            used = row["boa_offset_applied"]
            used = used if isinstance(used, list) else [used]
            checks.append(_check("boa_offset_applied", nat["boa_offset"] in used,
                                 f"both paths removed the {nat['boa_offset']:g} DN offset"))
    else:
        checks.append(_check("ndvi_recomputed_from_raw_bands", False,
                             f"no scene >= 90% clear at this point in the last {days_back} days; NDVI not verified"))

    # B. Elevation: native GLO-30 pixel vs regridded window used for slope.
    dem_items = _dem_items(point_bbox(lon, lat, 100.0))
    it = _pick_item_for_point(dem_items, lon, lat)
    z_nat, _ = _sample_native(it.assets["data"].href, lon, lat)
    z, c = _dem_window(lon, lat, dem_items)
    tol = max(3.0, float(np.nanmax(z) - np.nanmin(z)) / 2)
    details["elevation"] = {"native_m": round(z_nat, 2), "regridded_m": round(float(z[c, c]), 2), "tolerance_m": tol}
    checks.append(_check("elevation_native_vs_regridded", abs(z_nat - z[c, c]) <= tol,
                         f"{z_nat:.1f} m vs {z[c, c]:.1f} m (tolerance {tol:.1f} m)"))

    # C. Land cover: native pixel vs regridded centre, and plausibility against NDVI.
    lc = land_cover(lon, lat, 30.0)
    details["land_cover"] = {"class_name": lc["class_name"],
                             "top_share_30m": lc["shares_within_buffer"][0] if lc["shares_within_buffer"] else None}
    checks.extend(x for x in lc["checks"] if x["name"] == "centre_matches_native")
    if good and lc["class_code"] in (10, 20, 30, 40, 90, 95) and details["ndvi"]["pipeline_ndvi"] is not None:
        checks.append(_check("vegetated_class_has_positive_ndvi", details["ndvi"]["pipeline_ndvi"] > 0.1,
                             f"{lc['class_name']} (2021) with NDVI {details['ndvi']['pipeline_ndvi']}"))
    if lc["class_code"] == 80 and good:
        checks.append(_check("water_class_has_low_ndvi", details["ndvi"]["pipeline_ndvi"] < 0.2,
                             f"water (2021) with NDVI {details['ndvi']['pipeline_ndvi']}"))

    n_pass = sum(x["passed"] for x in checks)
    status = "pass" if n_pass == len(checks) else ("fail" if n_pass < len(checks) / 2 else "warn")
    return {
        "point": {"lon": lon, "lat": lat},
        "status": status,
        "passed": n_pass,
        "total": len(checks),
        "checks": checks,
        "details": details,
        "notes": [
            "verify re-derives values through a second, simpler code path (direct rasterio reads of the native "
            "pixels) and compares them with the main pipeline. 'warn' means some checks disagree: report the "
            "value with that caveat rather than as fact.",
            "A land-cover vs NDVI mismatch can be real change since 2021, a harvest, or a class edge.",
        ],
    }
