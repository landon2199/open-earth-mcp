"""open-earth-mcp: an MCP server for traceable, verifiable open Earth-observation data.

Run over stdio:  python -m open_earth_mcp.server   (or the `open-earth-mcp` entry point)
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Callable

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__
from . import validation as v

log = logging.getLogger("open_earth_mcp")

TOOL_TIMEOUT_S = 120

INSTRUCTIONS = """\
Tools for open Earth-observation data from Microsoft Planetary Computer (no API key).
Every result carries `sources` (STAC collection + item IDs + dates), `checks` and `notes`.
When you answer: cite the dates and item IDs you used, mention any failed check or
low_confidence flag, and call `verify` before stating a number as fact. If data is missing
or cloudy, say so; do not fill gaps by guessing. Coordinates are WGS84 decimal degrees (lon, lat)."""

mcp = MCPServer(
    name="open-earth",
    title="Open Earth MCP",
    description="Sentinel-2 NDVI, ESA WorldCover land cover and Copernicus DEM elevation, with sources and checks.",
    instructions=INSTRUCTIONS,
    version=__version__,
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def _run(fn: Callable[..., dict], *args: Any) -> dict:
    """Run a blocking data call in a worker thread with a hard timeout and friendly errors."""
    from .data import DataError  # imported lazily so `--help` and unit tests stay light

    try:
        with anyio.fail_after(TOOL_TIMEOUT_S):
            return await anyio.to_thread.run_sync(fn, *args, abandon_on_cancel=True)
    except TimeoutError:
        raise ToolError(f"Timed out after {TOOL_TIMEOUT_S} s. Try a shorter date range or a smaller area.") from None
    except (v.ValidationError, DataError) as exc:
        raise ToolError(str(exc)) from None
    except Exception as exc:  # pragma: no cover - last-resort message
        log.exception("unexpected error")
        raise ToolError(f"Unexpected error ({type(exc).__name__}): {exc}") from None


def _guard(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except v.ValidationError as exc:
        raise ToolError(str(exc)) from None


# ---------------------------------------------------------------------------- tools
@mcp.tool(title="Search satellite imagery", annotations=READ_ONLY)
async def search_imagery(
    start: str,
    end: str,
    bbox: list[float] | None = None,
    lon: float | None = None,
    lat: float | None = None,
    collection: str = "sentinel-2-l2a",
    max_cloud: float = 20.0,
    limit: int = 10,
) -> dict:
    """List satellite scenes covering a place and date range (newest first).

    Give either `bbox` = [west, south, east, north] or a point (`lon`, `lat`), in WGS84 degrees.
    Dates are YYYY-MM-DD (inclusive). `collection` is "sentinel-2-l2a" or "landsat-c2-l2".
    `max_cloud` is the scene-level cloud cover limit in percent; `limit` caps results (1-50).
    Returns scene IDs, acquisition times, cloud cover and tile, plus sources/checks/notes.
    """
    def prep():
        if bbox is not None:
            b = v.check_bbox(bbox)
        elif lon is not None and lat is not None:
            x, y = v.check_lon_lat(lon, lat)
            b = v.point_bbox(x, y, 1.0)
        else:
            raise v.ValidationError("Give either bbox=[west, south, east, north] or both lon and lat.")
        s, e = v.check_dates(start, end)
        return (b, s, e, v.check_collection(collection), v.check_range(max_cloud, "max_cloud", 0, 100),
                int(v.check_range(limit, "limit", 1, v.MAX_LIMIT)))

    args = _guard(prep)
    from .data import search_imagery as impl

    return await _run(impl, *args)


@mcp.tool(title="NDVI time series", annotations=READ_ONLY)
async def ndvi_timeseries(
    lon: float,
    lat: float,
    start: str,
    end: str,
    buffer_m: float = 30.0,
    max_scene_cloud: float = 60.0,
) -> dict:
    """Sentinel-2 L2A NDVI at a point for every usable scene between start and end (YYYY-MM-DD).

    NDVI is averaged over clear 10 m pixels within `buffer_m` metres (0-500) of the point; clouds,
    cloud shadow and cirrus are masked with the Scene Classification Layer. Fully cloudy dates are
    skipped and listed. `max_scene_cloud` (percent) pre-filters scenes before pixel masking.
    Each date reports ndvi_mean, ndvi_std, clear_pixels, clear_fraction, item_ids and a
    low_confidence flag (clear_fraction < 0.5) and a suspect_dip flag (one-date drop > 0.2 that
    recovers, usually missed haze). Ranges longer than 2 years are refused.
    """
    def prep():
        x, y = v.check_lon_lat(lon, lat)
        s, e = v.check_dates(start, end)
        return (x, y, s, e, v.check_range(buffer_m, "buffer_m", v.MIN_BUFFER_M, v.MAX_BUFFER_M),
                v.check_range(max_scene_cloud, "max_scene_cloud", 0, 100))

    args = _guard(prep)
    from .data import ndvi_timeseries as impl

    return await _run(impl, *args)


@mcp.tool(title="Land cover at a point", annotations=READ_ONLY)
async def land_cover(lon: float, lat: float, buffer_m: float = 0.0) -> dict:
    """ESA WorldCover 2021 (10 m) land-cover class at a point, e.g. 40 = Cropland.

    With `buffer_m` > 0 (max 500) also returns the percent share of each class within that radius.
    """
    def prep():
        x, y = v.check_lon_lat(lon, lat)
        return x, y, v.check_range(buffer_m, "buffer_m", 0, v.MAX_BUFFER_M)

    args = _guard(prep)
    from .data import land_cover as impl

    return await _run(impl, *args)


@mcp.tool(title="Elevation and slope", annotations=READ_ONLY)
async def elevation(lon: float, lat: float) -> dict:
    """Copernicus DEM GLO-30 elevation (metres, EGM2008) at a point, plus slope in degrees
    (Horn 3x3 on a 30 m grid) and local relief in a 150 m window."""
    args = _guard(lambda: v.check_lon_lat(lon, lat))
    from .data import elevation as impl

    return await _run(impl, *args)


@mcp.tool(title="Area summary", annotations=READ_ONLY)
async def area_summary(bbox: list[float], days_back: int = 90) -> dict:
    """Quick report for a small box [west, south, east, north] (max 25 km^2): 2021 land-cover shares,
    elevation and slope statistics, and NDVI from the most recent Sentinel-2 scene in the last
    `days_back` days (15-365) in which at least 60% of the box is clear."""
    def prep():
        return v.check_bbox(bbox), int(v.check_range(days_back, "days_back", 15, 365))

    args = _guard(prep)
    from .data import area_summary as impl

    return await _run(impl, *args)


@mcp.tool(title="Verify values at a point", annotations=READ_ONLY)
async def verify(lon: float, lat: float, days_back: int = 120) -> dict:
    """Independent sanity checks at a point. Recomputes NDVI for the latest clear scene (last
    `days_back` days) directly from the raw B04/B08/SCL bands on the scene's native grid and compares
    it with the ndvi_timeseries pipeline; compares native vs regridded elevation and land cover; and
    checks land cover against NDVI. Returns status pass / warn / fail with each check's detail."""
    def prep():
        x, y = v.check_lon_lat(lon, lat)
        return x, y, int(v.check_range(days_back, "days_back", 15, 365))

    args = _guard(prep)
    from .data import verify as impl

    return await _run(impl, *args)


# ---------------------------------------------------------------------------- resource
@mcp.resource(
    "catalog://collections",
    name="collections",
    title="Supported collections and licenses",
    description="Datasets this server reads, their resolution, license and required attribution.",
    mime_type="application/json",
)
def collections() -> str:
    from .data import COLLECTIONS, PLATFORM_TERMS, STAC_URL

    return json.dumps(
        {"stac_api": STAC_URL, "platform_terms": PLATFORM_TERMS, "collections": COLLECTIONS}, indent=2
    )


# ---------------------------------------------------------------------------- prompt
@mcp.prompt(title="Describe this place")
def describe_place(lon: str, lat: str) -> str:
    """Describe a place from open satellite data, citing sources and stating uncertainty."""
    today = date.today()
    start = today - timedelta(days=365)
    return (
        f"Describe the place at lon {lon}, lat {lat} using the open-earth tools.\n"
        f"1. Call land_cover(lon={lon}, lat={lat}, buffer_m=200) and elevation(lon={lon}, lat={lat}).\n"
        f"2. Call ndvi_timeseries(lon={lon}, lat={lat}, start='{start}', end='{today}') and describe the "
        "seasonal pattern (green-up, peak, low) with dates.\n"
        f"3. Call verify(lon={lon}, lat={lat}).\n"
        "Write 4-6 sentences. Give numbers with units and the dates/item IDs they came from. "
        "If a check failed, a date is low_confidence, or the land cover (2021) disagrees with recent NDVI, "
        "say so plainly instead of smoothing it over. End with a one-line 'Sources:' list."
    )


def main() -> None:
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
