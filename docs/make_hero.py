"""Build docs/hero.png (1600x900) from the real demo run in examples/demo_ndvi.json.

    python docs/make_hero.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "examples" / "demo_ndvi.json").read_text(encoding="utf-8"))

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#8a8984"
GRID = "#e6e5e1"
FARM_C = "#2a78d6"  # categorical slot 1
CAMPUS_C = "#eb6834"  # categorical slot 2

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 15, "text.color": INK,
                     "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2})

fig = plt.figure(figsize=(16, 9), dpi=100, facecolor=SURFACE)

# --- title block --------------------------------------------------------------
fig.text(0.045, 0.905, "open-earth-mcp", fontsize=40, weight="bold", color=INK)
fig.text(0.045, 0.855, "An MCP server that lets AI assistants read open satellite data, cite the scenes it used, "
         "and check its own numbers.", fontsize=17, color=INK_2)

# --- NDVI chart -------------------------------------------------------------------
ax = fig.add_axes([0.065, 0.17, 0.57, 0.6], facecolor=SURFACE)
for key, color, label in (("farm", FARM_C, "Cropland, Brazos River bottoms"),
                          ("campus", CAMPUS_C, "Texas A&M campus (built-up)")):
    rows = DATA[key]["series"]
    ok = [r for r in rows if not r["low_confidence"] and not r.get("suspect_dip")]
    flagged = [r for r in rows if r["low_confidence"] or r.get("suspect_dip")]
    d = [datetime.fromisoformat(r["date"]) for r in ok]
    ax.plot(d, [r["ndvi_mean"] for r in ok], color=color, lw=2.2, marker="o", ms=5.5,
            markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3)
    ax.scatter([datetime.fromisoformat(r["date"]) for r in flagged], [r["ndvi_mean"] for r in flagged],
               s=60, facecolors=SURFACE, edgecolors=color, linewidths=1.8, zorder=4)
    ax.plot([], [], color=color, lw=2.2, marker="o", ms=6, label=f"{label} ({len(rows)} dates)")

farm = DATA["farm"]["series"]
peak = max((r for r in farm if not r["low_confidence"] and not r.get("suspect_dip")), key=lambda r: r["ndvi_mean"])
ax.annotate(f"peak NDVI {peak['ndvi_mean']:.2f}\n{datetime.fromisoformat(peak['date']):%d %b %Y}",
            (datetime.fromisoformat(peak["date"]), peak["ndvi_mean"]), xytext=(12, 2),
            textcoords="offset points", fontsize=13, color=INK_2, va="bottom")

ax.legend(loc="upper left", frameon=False, fontsize=13.5, labelcolor=INK, handlelength=1.6)
ax.set_ylim(-0.02, 1.0)
ax.set_ylabel("NDVI (clear 10 m pixels within 30 m)", fontsize=14)
ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax.grid(axis="y", color=GRID, lw=1)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(MUTED)
ax.tick_params(length=0, labelsize=13)
ax.set_title("Sentinel-2 L2A NDVI per clear date, cloud-masked with SCL (real demo run)",
             loc="left", fontsize=15.5, color=INK, pad=14)
ax.text(0.0, -0.12, "Open circles: low-confidence (under 50% clear) or one-date dips flagged as likely haze.",
        transform=ax.transAxes, fontsize=12, color=MUTED)

# --- tools panel ------------------------------------------------------------------
px = 0.715
fig.text(px, 0.735, "Tools", fontsize=19, weight="bold")
tools = [
    ("search_imagery", "STAC scene search"),
    ("ndvi_timeseries", "cloud-masked NDVI per date"),
    ("land_cover", "ESA WorldCover 2021 class"),
    ("elevation", "Copernicus DEM + slope"),
    ("area_summary", "small-box quick report"),
    ("verify", "recompute from raw bands"),
]
for i, (name, desc) in enumerate(tools):
    y = 0.68 - i * 0.058
    fig.text(px, y, name, fontsize=15.5, family="DejaVu Sans Mono", color=INK)
    fig.text(px, y - 0.026, desc, fontsize=12.5, color=INK_2)

fig.text(px, 0.285, "Every answer carries", fontsize=15, weight="bold")
for i, line in enumerate(["STAC item IDs and dates used", "units and sanity checks", "notes on uncertainty"]):
    fig.text(px, 0.248 - i * 0.033, "-  " + line, fontsize=13.5, color=INK_2)

fig.text(0.045, 0.035, "Claude or any MCP client  <->  open-earth-mcp (stdio)  <->  Microsoft Planetary Computer STAC"
         "   |   no API keys   |   read-only", fontsize=12.5, color=INK_2)
fig.text(0.955, 0.075, "Contains modified Copernicus Sentinel data 2025-2026", fontsize=11, color=MUTED, ha="right")

out = ROOT / "docs" / "hero.png"
fig.savefig(out, dpi=100, facecolor=SURFACE)
print(out)
