"""Input validation. Pure functions, no network.

Every tool argument passes through here before any data is touched, so bad
input fails fast with a message an assistant can relay to a person.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone

# Guardrails (kept small so every call stays fast and cheap for the public API).
MAX_BBOX_KM2 = 25.0  # area_summary / search_imagery bbox cap
MAX_BUFFER_M = 500.0  # point buffers
MIN_BUFFER_M = 0.0
MAX_DAYS = 731  # longest date range for a time series (2 years keeps a call near a minute)
MAX_LIMIT = 50
EARLIEST = date(2015, 6, 23)  # Sentinel-2A launch

SUPPORTED_SEARCH_COLLECTIONS = ("sentinel-2-l2a", "landsat-c2-l2")


class ValidationError(ValueError):
    """Raised for input the server refuses to run. The message is user-facing."""


@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.west, self.south, self.east, self.north)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.west + self.east) / 2, (self.south + self.north) / 2)


def check_lon_lat(lon: float, lat: float) -> tuple[float, float]:
    """Return (lon, lat) as floats or raise ValidationError."""
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        raise ValidationError("lon and lat must be numbers (decimal degrees, WGS84).") from None
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise ValidationError("lon and lat must be finite numbers.")
    if not -180.0 <= lon <= 180.0:
        raise ValidationError(f"lon={lon} is outside [-180, 180]. Did you swap lon and lat?")
    if not -90.0 <= lat <= 90.0:
        raise ValidationError(f"lat={lat} is outside [-90, 90]. Did you swap lon and lat?")
    if abs(lat) > 84.0:
        raise ValidationError("Latitudes beyond +/-84 degrees are not supported (UTM grid limit).")
    return lon, lat


def bbox_area_km2(b: BBox) -> float:
    """Approximate area of a lon/lat box on a sphere (km^2). Good to <1% for small boxes."""
    r = 6371.0088
    dlon = math.radians(b.east - b.west)
    return abs(r * r * dlon * (math.sin(math.radians(b.north)) - math.sin(math.radians(b.south))))


def check_bbox(bbox: list[float] | tuple[float, ...], max_km2: float = MAX_BBOX_KM2) -> BBox:
    """Validate [west, south, east, north] in degrees and enforce the area cap."""
    if bbox is None or len(bbox) != 4:
        raise ValidationError("bbox must be [west, south, east, north] in decimal degrees.")
    w, s = check_lon_lat(bbox[0], bbox[1])
    e, n = check_lon_lat(bbox[2], bbox[3])
    if w >= e:
        raise ValidationError("bbox west must be less than east (boxes crossing the antimeridian are not supported).")
    if s >= n:
        raise ValidationError("bbox south must be less than north.")
    b = BBox(w, s, e, n)
    area = bbox_area_km2(b)
    if area > max_km2:
        raise ValidationError(
            f"bbox covers about {area:.1f} km^2; the limit is {max_km2:g} km^2 to keep calls fast. "
            "Use a smaller box (e.g. 0.04 x 0.04 degrees)."
        )
    return b


def parse_date(value: str, name: str) -> date:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"{name}='{value}' is not a date in YYYY-MM-DD form.") from None


def check_dates(start: str, end: str, max_days: int = MAX_DAYS, today: date | None = None) -> tuple[date, date]:
    """Validate an inclusive date range: ISO format, order, span and archive start."""
    s, e = parse_date(start, "start"), parse_date(end, "end")
    today = today or datetime.now(timezone.utc).date()
    if s > e:
        raise ValidationError(f"start ({s}) is after end ({e}).")
    if s > today:
        raise ValidationError(f"start ({s}) is in the future.")
    if e < EARLIEST:
        raise ValidationError(f"Sentinel-2 data begins {EARLIEST}; end ({e}) is earlier.")
    if (e - s).days > max_days:
        raise ValidationError(f"Date range is {(e - s).days} days; the limit is {max_days} days.")
    return s, e


def check_range(value: float, name: str, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be a number.") from None
    if not (math.isfinite(v) and lo <= v <= hi):
        raise ValidationError(f"{name}={value} must be between {lo:g} and {hi:g}.")
    return v


def check_collection(collection: str) -> str:
    if collection not in SUPPORTED_SEARCH_COLLECTIONS:
        raise ValidationError(
            f"collection '{collection}' is not supported. Choose one of: {', '.join(SUPPORTED_SEARCH_COLLECTIONS)}."
        )
    return collection


def utm_epsg(lon: float, lat: float) -> int:
    """EPSG code of the WGS84 UTM zone containing (lon, lat)."""
    zone = min(int((lon + 180) // 6) + 1, 60)
    return (32600 if lat >= 0 else 32700) + zone


def point_bbox(lon: float, lat: float, half_m: float) -> BBox:
    """A lon/lat box of +/- half_m metres around a point (small-distance approximation)."""
    dlat = half_m / 110_574.0
    dlon = half_m / (111_320.0 * math.cos(math.radians(lat)))
    return BBox(lon - dlon, lat - dlat, lon + dlon, lat + dlat)
