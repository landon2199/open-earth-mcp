"""Index math, class tables and masks. Pure numpy, no network, fully unit-tested."""

from __future__ import annotations

import numpy as np

# --- Sentinel-2 L2A ---------------------------------------------------------
# Scene Classification Layer (SCL) classes, from the ESA L2A product spec.
SCL_CLASSES = {
    0: "no data",
    1: "saturated or defective",
    2: "topographic / dark-area shadow",
    3: "cloud shadow",
    4: "vegetation",
    5: "not vegetated",
    6: "water",
    7: "unclassified",
    8: "cloud, medium probability",
    9: "cloud, high probability",
    10: "thin cirrus",
    11: "snow or ice",
}
# Pixels kept as "clear" for NDVI. Shadow, cloud, cirrus, defective, unclassified and
# snow/ice are dropped (snow is not cloud, but NDVI over snow says nothing about vegetation).
SCL_CLEAR = (4, 5, 6)
SCL_SNOW = 11

S2_QUANTIFICATION = 10_000.0
# From processing baseline 04.00 (25 Jan 2022) L2A digital numbers carry a +1000 offset:
# reflectance = (DN + BOA_ADD_OFFSET) / 10000 with BOA_ADD_OFFSET = -1000.
S2_BOA_OFFSET_NEW = -1000.0


def s2_boa_offset(processing_baseline: str | None) -> float:
    """BOA additive offset for a Sentinel-2 L2A scene given its processing baseline string."""
    if not processing_baseline:
        return 0.0
    try:
        major = float(str(processing_baseline).strip())
    except ValueError:
        return 0.0
    return S2_BOA_OFFSET_NEW if major >= 4.0 else 0.0


def s2_reflectance(dn: np.ndarray, offset: float) -> np.ndarray:
    """Convert L2A digital numbers to surface reflectance. DN 0 is no-data -> NaN."""
    dn = np.asarray(dn, dtype="float64")
    refl = (dn + offset) / S2_QUANTIFICATION
    refl[dn == 0] = np.nan
    return refl


def mosaic_scenes(scenes: list[dict]) -> dict:
    """Mosaic same-day scenes AFTER converting each to reflectance with its own offset.

    Each scene is {"red": DN array, "nir": DN array, "scl": array, "offset": float}. Scenes
    are taken in order; a pixel comes from the first scene with SCL != 0 there. Scaling
    per scene first means a day that mixes processing baselines (possible around the
    04.00 switch in January 2022) is still converted correctly pixel by pixel.
    Returns {"red", "nir" (reflectance, NaN where no data), "scl", "offsets" (per pixel)}.
    """
    shape = np.asarray(scenes[0]["scl"]).shape
    red = np.full(shape, np.nan)
    nir = np.full(shape, np.nan)
    scl = np.zeros(shape, dtype="int16")
    offs = np.full(shape, np.nan)
    for sc in scenes:
        s_scl = np.asarray(sc["scl"])
        take = (scl == 0) & (s_scl != 0)
        red[take] = s2_reflectance(sc["red"], sc["offset"])[take]
        nir[take] = s2_reflectance(sc["nir"], sc["offset"])[take]
        scl[take] = s_scl[take]
        offs[take] = sc["offset"]
    return {"red": red, "nir": nir, "scl": scl, "offsets": offs}


# Plausible surface-reflectance range for clear pixels. Applying the -1000 offset to a
# pre-04.00 scene pushes dark pixels (water, shadow, dark soil) well below the floor.
REFLECTANCE_RANGE = (-0.02, 1.2)


def reflectance_plausible(red: np.ndarray, nir: np.ndarray) -> tuple[bool, float, float]:
    """True when every finite clear-pixel reflectance lies in REFLECTANCE_RANGE. Returns (ok, min, max)."""
    v = np.concatenate([np.ravel(red), np.ravel(nir)])
    v = v[np.isfinite(v)]
    if v.size == 0:
        return False, float("nan"), float("nan")
    lo, hi = float(v.min()), float(v.max())
    return (REFLECTANCE_RANGE[0] <= lo and hi <= REFLECTANCE_RANGE[1]), lo, hi


def ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """NDVI = (NIR - Red) / (NIR + Red). Returns NaN where the denominator is ~0 or inputs are NaN."""
    red = np.asarray(red, dtype="float64")
    nir = np.asarray(nir, dtype="float64")
    den = nir + red
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (nir - red) / den
    out[~np.isfinite(out) | (np.abs(den) < 1e-6)] = np.nan
    return out


def clear_mask(scl: np.ndarray) -> np.ndarray:
    """Boolean mask of SCL pixels considered clear (see SCL_CLEAR)."""
    return np.isin(np.asarray(scl), SCL_CLEAR)


def summarize(values: np.ndarray) -> dict:
    """Mean / median / std / min / max / count of the finite values (None when empty)."""
    v = np.asarray(values, dtype="float64")
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"mean": None, "median": None, "std": None, "min": None, "max": None, "count": 0}
    return {
        "mean": round(float(v.mean()), 4),
        "median": round(float(np.median(v)), 4),
        "std": round(float(v.std(ddof=0)), 4),
        "min": round(float(v.min()), 4),
        "max": round(float(v.max()), 4),
        "count": int(v.size),
    }


def suspect_dips(values: list[float], drop: float = 0.2) -> list[int]:
    """Indices of interior values more than `drop` below BOTH neighbours.

    A one-date NDVI dip that recovers on the next date is more often thin cloud, haze or
    smoke that the SCL mask missed than a real change in vegetation.
    """
    return [i for i in range(1, len(values) - 1)
            if values[i] < min(values[i - 1], values[i + 1]) - drop]


# --- ESA WorldCover 2021 (v200) ---------------------------------------------
WORLDCOVER_CLASSES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}


def class_shares(classes: np.ndarray, names: dict[int, str] = WORLDCOVER_CLASSES, nodata: int = 0) -> dict:
    """Percent share of each class among valid pixels, largest first."""
    a = np.asarray(classes).ravel()
    a = a[a != nodata]
    total = int(a.size)
    if total == 0:
        return {"pixels": 0, "shares": []}
    vals, counts = np.unique(a, return_counts=True)
    order = np.argsort(-counts)
    shares = [
        {
            "code": int(vals[i]),
            "name": names.get(int(vals[i]), "unknown"),
            "percent": round(100.0 * float(counts[i]) / total, 2),
            "pixels": int(counts[i]),
        }
        for i in order
    ]
    return {"pixels": total, "shares": shares}


# --- Terrain ----------------------------------------------------------------
def slope_horn(dem: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Slope in degrees with Horn's (1981) 3x3 method. Edge cells are NaN.

    dx, dy are cell sizes in metres (positive).
    """
    z = np.asarray(dem, dtype="float64")
    out = np.full(z.shape, np.nan)
    if z.shape[0] < 3 or z.shape[1] < 3:
        return out
    a, b, c = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    d, f = z[1:-1, :-2], z[1:-1, 2:]
    g, h, i = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8.0 * dx)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8.0 * dy)
    out[1:-1, 1:-1] = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    return out
