# open-earth-mcp demo transcript

Run on 2026-10-22 by `examples/demo_client.py`: the server was launched over **stdio** and called through the MCP Python client SDK. Responses are real; long lists are trimmed.

## tools/list

- **search_imagery** - List satellite scenes covering a place and date range (newest first).
- **ndvi_timeseries** - Sentinel-2 L2A NDVI at a point for every usable scene between start and end (YYYY-MM-DD).
- **land_cover** - ESA WorldCover 2021 (10 m) land-cover class at a point, e.g. 40 = Cropland.
- **elevation** - Copernicus DEM GLO-30 elevation (metres, EGM2008) at a point, plus slope in degrees
- **area_summary** - Quick report for a small box [west, south, east, north] (max 25 km^2): 2021 land-cover shares,
- **verify** - Independent sanity checks at a point. Recomputes NDVI for the latest clear scene (last

## resources/read `catalog://collections`

| collection | license |
|---|---|
| sentinel-2-l2a | Copernicus Sentinel data terms (free, full and open; attribution required) |
| landsat-c2-l2 | Public domain (USGS) |
| esa-worldcover | CC-BY-4.0 |
| cop-dem-glo-30 | Copernicus DEM licence (free; attribution required) |

## prompts/get `describe_place`

```text
Describe the place at lon -96.3365, lat 30.6187 using the open-earth tools.
1. Call land_cover(lon=-96.3365, lat=30.6187, buffer_m=200) and elevation(lon=-96.3365, lat=30.6187).
2. Call ndvi_timeseries(lon=-96.3365, lat=30.6187, start='2025-10-22', end='2026-10-22') and describe the seasonal pattern (green-up, peak, low) with dates.
3. Call verify(lon=-96.3365, lat=30.6187).
Write 4-6 sentences. Give numbers with units and the dates/item IDs they came from. If a check failed, a date is low_confidence, or the land cover (2021) disagrees with recent NDVI, say so plainly instead of smoothing it over. End with a one-line 'Sources:' list.
```

## tools/call `search_imagery`

```json
{"lon": -96.3365, "lat": 30.6187, "start": "2026-08-23", "end": "2026-10-22", "max_cloud": 20, "limit": 5}
```

Response in 1.7 s:

```json
{
  "collection": "sentinel-2-l2a",
  "bbox": [
    -96.33651043848934,
    30.61869095628267,
    -96.33648956151066,
    30.61870904371733
  ],
  "date_range": [
    "2026-08-23",
    "2026-10-22"
  ],
  "max_cloud_percent": 20.0,
  "count": 5,
  "scenes": [
    {
      "id": "S2C_MSIL2A_20261017T170311_R069_T14RQV_20261017T202312",
      "datetime_utc": "2026-10-17T17:03:11.025000Z",
      "cloud_cover_percent": 11.782552,
      "platform": "Sentinel-2C",
      "tile": "14RQV",
      "processing_baseline": "05.13",
      "preview": "https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png"
    },
    {
      "id": "S2C_MSIL2A_20261017T170311_R069_T14RQU_20261017T202312",
      "datetime_utc": "2026-10-17T17:03:11.025000Z",
      "cloud_cover_percent": 15.879795,
      "platform": "Sentinel-2C",
      "tile": "14RQU",
      "processing_baseline": "05.13",
      "preview": "https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png"
    },
    {
      "id": "S2C_MSIL2A_20261007T170201_R069_T14RQV_20261007T215309",
      "datetime_utc": "2026-10-07T17:02:01.025000Z",
      "cloud_cover_percent": 0.18986,
      "platform": "Sentinel-2C",
      "tile": "14RQV",
      "processing_baseline": "05.13",
      "preview": "https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png"
    },
    {
      "id": "S2C_MSIL2A_20261007T170201_R069_T14RQU_20261007T215309",
      "datetime_utc": "2026-10-07T17:02:01.025000Z",
      "cloud_cover_percent": 3.283645,
      "platform": "Sentinel-2C",
      "tile": "14RQU",
      "processing_baseline": "05.13",
      "preview": "https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png"
    },
    {
      "id": "S2B_MSIL2A_20260922T165919_R069_T14RQV_20260922T223324",
      "datetime_utc": "2026-09-22T16:59:19.024000Z",
      "cloud_cover_percent": 11.339959,
      "platform": "Sentinel-2B",
      "tile": "14RQV",
      "processing_baseline": "05.13",
      "preview": "https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png"
    }
  ],
  "sources": {
    "stac_api": "https://planetarycomputer.microsoft.com/api/stac/v1",
    "collection": "sentinel-2-l2a",
    "item_ids": [
      "S2C_MSIL2A_20261017T170311_R069_T14RQV_20261017T202312",
      "S2C_MSIL2A_20261017T170311_R069_T14RQU_20261017T202312",
      "S2C_MSIL2A_20261007T170201_R069_T14RQV_20261007T215309",
      "S2C_MSIL2A_20261007T170201_R069_T14RQU_20261007T215309",
      "S2B_MSIL2A_20260922T165919_R069_T14RQV_20260922T223324"
    ]
  },
  "checks": [
    {
      "name": "cloud_filter_respected",
      "passed": true,
      "detail": "all 5 scenes have scene-level cloud cover <= 20.0%"
    },
    {
      "name": "dates_in_range",
      "passed": true,
      "detail": "all acquisition dates between 2026-08-23 and 2026-10-22"
    }
  ],
  "notes": [
    "Cloud cover is the scene-level estimate for the whole ~110 km tile, not for this box.",
    "Result was capped at limit=5; more scenes may exist."
  ]
}
```

## tools/call `land_cover`

```json
{"lon": -96.3365, "lat": 30.6187, "buffer_m": 200}
```

Response in 1.9 s:

```json
{
  "point": {
    "lon": -96.3365,
    "lat": 30.6187
  },
  "class_code": 50,
  "class_name": "Built-up",
  "product": "ESA WorldCover 10 m 2021 v200",
  "pixel": {
    "crs": "EPSG:4326",
    "row": 28575,
    "col": 31961,
    "pixel_size": [
      8.333333333333333e-05,
      8.333333333333333e-05
    ]
  },
  "buffer_m": 200.0,
  "shares_within_buffer": [
    {
      "code": 50,
      "name": "Built-up",
      "percent": 68.1,
      "pixels": 856
    },
    {
      "code": 30,
      "name": "Grassland",
      "percent": 25.06,
      "pixels": 315
    },
    {
      "code": 60,
      "name": "Bare / sparse vegetation",
      "percent": 4.22,
      "pixels": 53
    },
    {
      "code": 10,
      "name": "Tree cover",
      "percent": 2.63,
      "pixels": 33
    }
  ],
  "buffer_pixels": 1257,
  "units": {
    "percent": "% of 10 m pixels"
  },
  "sources": {
    "stac_api": "https://planetarycomputer.microsoft.com/api/stac/v1",
    "collection": "esa-worldcover",
    "item_ids": [
      "ESA_WorldCover_10m_2021_v200_N30W099"
    ],
    "reference_year": 2021
  },
  "checks": [
    {
      "name": "class_code_known",
      "passed": true,
      "detail": "code 50 is one of the 11 WorldCover classes"
    },
    {
      "name": "shares_sum_to_100",
      "passed": true,
      "detail": "class percentages sum to 100"
    },
    {
      "name": "centre_matches_native",
      "passed": true,
      "detail": "regridded centre cell (50) vs native pixel (50)"
    }
  ],
  "notes": [
    "WorldCover 2021 is a 10 m global map with ~77% overall accuracy (ESA validation report); single-pixel answers near class edges are uncertain, so use buffer_m > 0 for context.",
    "The map shows 2021 conditions and may not reflect later change."
  ]
}
```

## tools/call `land_cover`

```json
{"lon": -96.5733, "lat": 30.6805, "buffer_m": 200}
```

Response in 0.3 s:

```json
{
  "point": {
    "lon": -96.5733,
    "lat": 30.6805
  },
  "class_code": 40,
  "class_name": "Cropland",
  "product": "ESA WorldCover 10 m 2021 v200",
  "pixel": {
    "crs": "EPSG:4326",
    "row": 27834,
    "col": 29120,
    "pixel_size": [
      8.333333333333333e-05,
      8.333333333333333e-05
    ]
  },
  "buffer_m": 200.0,
  "shares_within_buffer": [
    {
      "code": 40,
      "name": "Cropland",
      "percent": 100.0,
      "pixels": 1257
    }
  ],
  "buffer_pixels": 1257,
  "units": {
    "percent": "% of 10 m pixels"
  },
  "sources": {
    "stac_api": "https://planetarycomputer.microsoft.com/api/stac/v1",
    "collection": "esa-worldcover",
    "item_ids": [
      "ESA_WorldCover_10m_2021_v200_N30W099"
    ],
    "reference_year": 2021
  },
  "checks": [
    {
      "name": "class_code_known",
      "passed": true,
      "detail": "code 40 is one of the 11 WorldCover classes"
    },
    {
      "name": "shares_sum_to_100",
      "passed": true,
      "detail": "class percentages sum to 100"
    },
    {
      "name": "centre_matches_native",
      "passed": true,
      "detail": "regridded centre cell (40) vs native pixel (40)"
    }
  ],
  "notes": [
    "WorldCover 2021 is a 10 m global map with ~77% overall accuracy (ESA validation report); single-pixel answers near class edges are uncertain, so use buffer_m > 0 for context.",
    "The map shows 2021 conditions and may not reflect later change."
  ]
}
```

## tools/call `elevation`

```json
{"lon": -96.3365, "lat": 30.6187}
```

Response in 2.8 s:

```json
{
  "point": {
    "lon": -96.3365,
    "lat": 30.6187
  },
  "elevation_m": 107.8,
  "slope_deg": 2.77,
  "slope_deg_mean_3x3": 3.36,
  "relief_m_150m_window": 8.67,
  "vertical_datum": "EGM2008 geoid (orthometric height)",
  "pixel": {
    "crs": "EPSG:4326",
    "row": 1373,
    "col": 2389,
    "pixel_size": [
      0.0002777777777777778,
      0.0002777777777777778
    ]
  },
  "units": {
    "elevation": "metres above EGM2008",
    "slope": "degrees"
  },
  "sources": {
    "stac_api": "https://planetarycomputer.microsoft.com/api/stac/v1",
    "collection": "cop-dem-glo-30",
    "item_ids": [
      "Copernicus_DSM_COG_10_N30_00_W097_00_DEM"
    ]
  },
  "checks": [
    {
      "name": "elevation_plausible",
      "passed": true,
      "detail": "107.8 m lies within Earth's land range"
    },
    {
      "name": "native_vs_regridded",
      "passed": true,
      "detail": "native pixel 107.8 m vs bilinear 30 m UTM cell 107.4 m"
    },
    {
      "name": "slope_in_range",
      "passed": true,
      "detail": "slope 2.77 degrees"
    }
  ],
  "notes": [
    "Elevation is the native GLO-30 pixel (~30 m) containing the point. GLO-30 is a surface model: over buildings and forest it gives roof or canopy height, not bare ground.",
    "Slope uses Horn's 3x3 method on a 30 m UTM grid resampled bilinearly from GLO-30.",
    "GLO-30 absolute vertical accuracy is reported as < 4 m (90% linear error)."
  ]
}
```

## tools/call `ndvi_timeseries`

```json
{"lon": -96.5733, "lat": 30.6805, "start": "2025-10-01", "end": "2026-10-22", "buffer_m": 30}
```

Response in 25.3 s:

```json
{
  "point": {
    "lon": -96.5733,
    "lat": 30.6805
  },
  "buffer_m": 30.0,
  "date_range": [
    "2025-10-01",
    "2026-10-22"
  ],
  "units": {
    "ndvi": "unitless, -1 to 1",
    "pixels": "count of 10 m Sentinel-2 pixels"
  },
  "count": 53,
  "series": [
    {
      "date": "2025-10-02",
      "ndvi_mean": 0.1842,
      "ndvi_std": 0.0777,
      "clear_pixels": 21,
      "total_pixels": 29,
      "clear_fraction": 0.724,
      "snow_pixels": 0,
      "item_ids": [
        "S2C_MSIL2A_20251002T170141_R069_T14RQV_20251002T222514",
        "S2C_MSIL2A_20251002T170141_R069_T14RQU_20251002T222514"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    {
      "date": "2025-10-07",
      "ndvi_mean": 0.1409,
      "ndvi_std": 0.012,
      "clear_pixels": 29,
      "total_pixels": 29,
      "clear_fraction": 1.0,
      "snow_pixels": 0,
      "item_ids": [
        "S2B_MSIL2A_20251007T170109_R069_T14RQV_20251007T223253",
        "S2B_MSIL2A_20251007T170109_R069_T14RQU_20251007T223253"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    {
      "date": "2025-10-12",
      "ndvi_mean": 0.1722,
      "ndvi_std": 0.0047,
      "clear_pixels": 29,
      "total_pixels": 29,
      "clear_fraction": 1.0,
      "snow_pixels": 0,
      "item_ids": [
        "S2C_MSIL2A_20251012T170251_R069_T14RQV_20251012T214201",
        "S2C_MSIL2A_20251012T170251_R069_T14RQU_20251012T214201"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    {
      "date": "2025-10-14",
      "ndvi_mean": 0.1636,
      "ndvi_std": 0.0054,
      "clear_pixels": 29,
      "total_pixels": 29,
      "clear_fraction": 1.0,
      "snow_pixels": 0,
      "item_ids": [
        "S2A_MSIL2A_20251014T170711_R069_T14RQV_20251014T203723",
        "S2A_MSIL2A_20251014T170711_R069_T14RQU_20251014T203723"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    {
      "date": "2025-10-17",
      "ndvi_mean": 0.1524,
      "ndvi_std": 0.0057,
      "clear_pixels": 29,
      "total_pixels": 29,
      "clear_fraction": 1.0,
      "snow_pixels": 0,
      "item_ids": [
        "S2B_MSIL2A_20251017T170209_R069_T14RQV_20251017T221745",
        "S2B_MSIL2A_20251017T170209_R069_T14RQU_20251017T221745"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    {
      "date": "2025-10-22",
      "ndvi_mean": 0.1707,
      "ndvi_std": 0.0041,
      "clear_pixels": 29,
      "total_pixels": 29,
      "clear_fraction": 1.0,
      "snow_pixels": 0,
      "item_ids": [
        "S2C_MSIL2A_20251022T170401_R069_T14RQV_20251022T203803",
        "S2C_MSIL2A_20251022T170401_R069_T14RQU_20251022T203803"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    "... 47 more"
  ],
  "skipped": [
    {
      "date": "2025-10-27",
      "reason": "no clear pixels",
      "scl_counts": {
        "cloud, high probability": 29
      },
      "item_ids": [
        "S2B_MSIL2A_20251027T170319_R069_T14RQU_20251027T220006"
      ]
    },
    {
      "date": "2025-11-01",
      "reason": "no clear pixels",
      "scl_counts": {
        "cloud, medium probability": 29
      },
      "item_ids": [
        "S2C_MSIL2A_20251101T170501_R069_T14RQU_20251101T204921"
      ]
    },
    {
      "date": "2026-01-12",
      "reason": "no clear pixels",
      "scl_counts": {
        "cloud, medium probability": 15,
        "cloud, high probability": 14
      },
      "item_ids": [
        "S2A_MSIL2A_20260112T170721_R069_T14RQV_20260112T223018",
        "S2A_MSIL2A_20260112T170721_R069_T14RQU_20260112T223018"
      ]
    },
    {
      "date": "2026-02-19",
      "reason": "no clear pixels",
      "scl_counts": {
        "cloud, medium probability": 1,
        "cloud, high probability": 28
      },
      "item_ids": [
        "S2C_MSIL2A_20260219T170341_R069_T14RQV_20260219T202519"
      ]
    },
    {
      "date": "2026-02-24",
      "reason": "no clear pixels",
      "scl_counts": {
        "thin cirrus": 29
      },
      "item_ids": [
        "S2B_MSIL2A_20260224T170209_R069_T14RQU_20260224T223259"
      ]
    },
    {
      "date": "2026-05-10",
      "reason": "no clear pixels",
      "scl_counts": {
        "cloud, medium probability": 2,
        "cloud, high probability": 27
      },
      "item_ids": [
        "S2C_MSIL2A_20260510T165851_R069_T14RQV_20260510T233454",
        "S2C_MSIL2A_20260510T165851_R069_T14RQU_20260510T233454"
      ]
    },
    "... 6 more"
  ],
  "summary": {
    "ndvi_mean_of_dates": 0.2455,
    "ndvi_min_date": "2026-03-01",
    "ndvi_max_date": "2026-06-01",
    "low_confidence_dates": [
      "2025-11-21",
      "2026-10-19"
    ],
    "suspect_dip_dates": [
      "2026-05-25"
    ]
  },
  "sources": {
    "stac_api": "https://planetarycomputer.microsoft.com/api/stac/v1",
    "collection": "sentinel-2-l2a",
    "item_ids": [
      "S2A_MSIL2A_20251014T170711_R069_T14RQU_20251014T203723",
      "S2A_MSIL2A_20251014T170711_R069_T14RQV_20251014T203723",
      "S2A_MSIL2A_20251103T170711_R069_T14RQU_20251103T203914",
      "S2A_MSIL2A_20251103T170711_R069_T14RQV_20251103T203914",
      "S2A_MSIL2A_20251123T170711_R069_T14RQV_20251123T210013",
      "S2A_MSIL2A_20260102T170721_R069_T14RQU_20260102T204416",
      "... 89 more"
    ],
    "dates": [
      "2025-10-02",
      "2025-10-07",
      "2025-10-12",
      "2025-10-14",
      "2025-10-17",
      "2025-10-22",
      "... 47 more"
    ]
  },
  "checks": [
    {
      "name": "ndvi_in_valid_range",
      "passed": true,
      "detail": "every per-pixel NDVI lies in [-1, 1]"
    },
    {
      "name": "clear_pixels_positive",
      "passed": true,
      "detail": "every reported date has at least one clear pixel"
    },
    {
      "name": "processing_baseline_known",
      "passed": true,
      "detail": "every scene reports s2:processing_baseline, so its BOA offset (-1000 from 04.00) is known"
    },
    {
      "name": "reflectance_in_expected_range",
      "passed": true,
      "detail": "clear-pixel B04/B08 reflectance after scaling lies in [-0.02, 1.2] on every date (observed 0.018 to 0.543)"
    },
    {
      "name": "has_observations",
      "passed": true,
      "detail": "53 clear dates out of 65"
    }
  ],
  "notes": [
    "NDVI = (B08 - B04) / (B08 + B04) on surface reflectance, averaged over clear 10 m pixels within 30 m of the point (29 pixels when fully clear).",
    "Clear = SCL classes vegetation, not-vegetated and water. Cloud, cloud shadow, cirrus, dark-area shadow, defective, unclassified and snow/ice pixels are dropped. Each scene is scaled with its own processing-baseline offset before same-day tiles are mosaicked. SCL misses some thin cloud and haze, so isolated low values can still be cloud effects.",
    "Dates with clear_fraction < 0.5 are marked low_confidence. A suspect_dip date is > 0.2 below both neighbouring dates; that is more often missed thin cloud or haze than real change.",
    "12 date(s) were skipped (fully cloudy or no data); see 'skipped'."
  ]
}
```

## tools/call `ndvi_timeseries`

```json
{"lon": -96.3365, "lat": 30.6187, "start": "2025-10-01", "end": "2026-10-22", "buffer_m": 30}
```

Response in 17.5 s:

```json
{
  "point": {
    "lon": -96.3365,
    "lat": 30.6187
  },
  "buffer_m": 30.0,
  "date_range": [
    "2025-10-01",
    "2026-10-22"
  ],
  "units": {
    "ndvi": "unitless, -1 to 1",
    "pixels": "count of 10 m Sentinel-2 pixels"
  },
  "count": 47,
  "series": [
    {
      "date": "2025-10-02",
      "ndvi_mean": 0.2906,
      "ndvi_std": 0.1504,
      "clear_pixels": 29,
      "total_pixels": 29,
      "clear_fraction": 1.0,
      "snow_pixels": 0,
      "item_ids": [
        "S2C_MSIL2A_20251002T170141_R069_T14RQV_20251002T222514",
        "S2C_MSIL2A_20251002T170141_R069_T14RQU_20251002T222514"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    {
      "date": "2025-10-07",
      "ndvi_mean": 0.303,
      "ndvi_std": 0.1646,
      "clear_pixels": 27,
      "total_pixels": 29,
      "clear_fraction": 0.931,
      "snow_pixels": 0,
      "item_ids": [
        "S2B_MSIL2A_20251007T170109_R069_T14RQV_20251007T223253",
        "S2B_MSIL2A_20251007T170109_R069_T14RQU_20251007T223253"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    {
      "date": "2025-10-12",
      "ndvi_mean": 0.2991,
      "ndvi_std": 0.165,
      "clear_pixels": 29,
      "total_pixels": 29,
      "clear_fraction": 1.0,
      "snow_pixels": 0,
      "item_ids": [
        "S2C_MSIL2A_20251012T170251_R069_T14RQV_20251012T214201",
        "S2C_MSIL2A_20251012T170251_R069_T14RQU_20251012T214201"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    {
      "date": "2025-10-14",
      "ndvi_mean": 0.2985,
      "ndvi_std": 0.1616,
      "clear_pixels": 29,
      "total_pixels": 29,
      "clear_fraction": 1.0,
      "snow_pixels": 0,
      "item_ids": [
        "S2A_MSIL2A_20251014T170711_R069_T14RQV_20251014T203723",
        "S2A_MSIL2A_20251014T170711_R069_T14RQU_20251014T203723"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    {
      "date": "2025-10-22",
      "ndvi_mean": 0.3081,
      "ndvi_std": 0.1491,
      "clear_pixels": 29,
      "total_pixels": 29,
      "clear_fraction": 1.0,
      "snow_pixels": 0,
      "item_ids": [
        "S2C_MSIL2A_20251022T170401_R069_T14RQV_20251022T203803",
        "S2C_MSIL2A_20251022T170401_R069_T14RQU_20251022T203803"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    {
      "date": "2025-11-03",
      "ndvi_mean": 0.3037,
      "ndvi_std": 0.1642,
      "clear_pixels": 29,
      "total_pixels": 29,
      "clear_fraction": 1.0,
      "snow_pixels": 0,
      "item_ids": [
        "S2A_MSIL2A_20251103T170711_R069_T14RQV_20251103T203914",
        "S2A_MSIL2A_20251103T170711_R069_T14RQU_20251103T203914"
      ],
      "processing_baseline": [
        "05.11"
      ],
      "boa_offset_applied": -1000.0,
      "low_confidence": false,
      "suspect_dip": false
    },
    "... 41 more"
  ],
  "skipped": [
    {
      "date": "2025-10-17",
      "reason": "no clear pixels",
      "scl_counts": {
        "cloud, high probability": 29
      },
      "item_ids": [
        "S2B_MSIL2A_20251017T170209_R069_T14RQV_20251017T221745",
        "S2B_MSIL2A_20251017T170209_R069_T14RQU_20251017T221745"
      ]
    },
    {
      "date": "2025-10-27",
      "reason": "no clear pixels",
      "scl_counts": {
        "cloud, high probability": 29
      },
      "item_ids": [
        "S2B_MSIL2A_20251027T170319_R069_T14RQU_20251027T220006"
      ]
    },
    {
      "date": "2025-11-01",
      "reason": "no clear pixels",
      "scl_counts": {
        "cloud, medium probability": 29
      },
      "item_ids": [
        "S2C_MSIL2A_20251101T170501_R069_T14RQU_20251101T204921"
      ]
    },
    {
      "date": "2025-11-16",
      "reason": "no clear pixels",
      "scl_counts": {
        "cloud, high probability": 29
      },
      "item_ids": [
        "S2B_MSIL2A_20251116T170509_R069_T14RQV_20251116T205601"
      ]
    },
    {
      "date": "2025-11-21",
      "reason": "no clear pixels",
      "scl_counts": {
        "cloud, medium probability": 29
      },
      "item_ids": [
        "S2C_MSIL2A_20251121T170631_R069_T14RQU_20251121T210118"
      ]
    },
    {
      "date": "2026-01-10",
      "reason": "no clear pixels",
      "scl_counts": {
        "thin cirrus": 29
      },
      "item_ids": [
        "S2C_MSIL2A_20260110T170701_R069_T14RQV_20260110T205817",
        "S2C_MSIL2A_20260110T170701_R069_T14RQU_20260110T205817"
      ]
    },
    "... 12 more"
  ],
  "summary": {
    "ndvi_mean_of_dates": 0.2947,
    "ndvi_min_date": "2025-12-21",
    "ndvi_max_date": "2026-10-17",
    "low_confidence_dates": [
      "2026-08-13",
      "2026-09-09",
      "2026-09-29"
    ],
    "suspect_dip_dates": []
  },
  "sources": {
    "stac_api": "https://planetarycomputer.microsoft.com/api/stac/v1",
    "collection": "sentinel-2-l2a",
    "item_ids": [
      "S2A_MSIL2A_20251014T170711_R069_T14RQU_20251014T203723",
      "S2A_MSIL2A_20251014T170711_R069_T14RQV_20251014T203723",
      "S2A_MSIL2A_20251103T170711_R069_T14RQU_20251103T203914",
      "S2A_MSIL2A_20251103T170711_R069_T14RQV_20251103T203914",
      "S2A_MSIL2A_20251123T170711_R069_T14RQV_20251123T210013",
      "S2A_MSIL2A_20260102T170721_R069_T14RQU_20260102T204416",
      "... 79 more"
    ],
    "dates": [
      "2025-10-02",
      "2025-10-07",
      "2025-10-12",
      "2025-10-14",
      "2025-10-22",
      "2025-11-03",
      "... 41 more"
    ]
  },
  "checks": [
    {
      "name": "ndvi_in_valid_range",
      "passed": true,
      "detail": "every per-pixel NDVI lies in [-1, 1]"
    },
    {
      "name": "clear_pixels_positive",
      "passed": true,
      "detail": "every reported date has at least one clear pixel"
    },
    {
      "name": "processing_baseline_known",
      "passed": true,
      "detail": "every scene reports s2:processing_baseline, so its BOA offset (-1000 from 04.00) is known"
    },
    {
      "name": "reflectance_in_expected_range",
      "passed": true,
      "detail": "clear-pixel B04/B08 reflectance after scaling lies in [-0.02, 1.2] on every date (observed 0.022 to 0.431)"
    },
    {
      "name": "has_observations",
      "passed": true,
      "detail": "47 clear dates out of 65"
    }
  ],
  "notes": [
    "NDVI = (B08 - B04) / (B08 + B04) on surface reflectance, averaged over clear 10 m pixels within 30 m of the point (29 pixels when fully clear).",
    "Clear = SCL classes vegetation, not-vegetated and water. Cloud, cloud shadow, cirrus, dark-area shadow, defective, unclassified and snow/ice pixels are dropped. Each scene is scaled with its own processing-baseline offset before same-day tiles are mosaicked. SCL misses some thin cloud and haze, so isolated low values can still be cloud effects.",
    "Dates with clear_fraction < 0.5 are marked low_confidence. A suspect_dip date is > 0.2 below both neighbouring dates; that is more often missed thin cloud or haze than real change.",
    "18 date(s) were skipped (fully cloudy or no data); see 'skipped'."
  ]
}
```

## tools/call `area_summary`

```json
{"bbox": [-96.36, 30.6, -96.32, 30.63]}
```

Response in 6.5 s:

```json
{
  "bbox": [
    -96.36,
    30.6,
    -96.32,
    30.63
  ],
  "area_km2": 12.769,
  "land_cover": {
    "reference_year": 2021,
    "pixels": 134064,
    "shares": [
      {
        "code": 50,
        "name": "Built-up",
        "percent": 60.24,
        "pixels": 80754
      },
      {
        "code": 30,
        "name": "Grassland",
        "percent": 19.47,
        "pixels": 26096
      },
      {
        "code": 10,
        "name": "Tree cover",
        "percent": 18.61,
        "pixels": 24945
      },
      {
        "code": 60,
        "name": "Bare / sparse vegetation",
        "percent": 1.28,
        "pixels": 1722
      },
      {
        "code": 40,
        "name": "Cropland",
        "percent": 0.4,
        "pixels": 541
      },
      {
        "code": 80,
        "name": "Permanent water bodies",
        "percent": 0.0,
        "pixels": 6
      }
    ]
  },
  "terrain": {
    "elevation_m_mean": 102.18,
    "elevation_m_min": 87.6,
    "elevation_m_max": 131.0,
    "slope_deg_mean": 1.93
  },
  "latest_clear_ndvi": {
    "date": "2026-10-19",
    "item_ids": [
      "S2A_MSIL2A_20261019T170711_R069_T14RQU_20261019T233959"
    ],
    "clear_fraction": 0.647,
    "ndvi": {
      "mean": 0.3457,
      "median": 0.3274,
      "std": 0.1929,
      "min": -0.352,
      "max": 0.9141,
      "count": 21682
    },
    "reflectance_range": [
      0.011,
      0.9854
    ],
    "reflectance_ok": true,
    "scenes_tried": [
      {
        "date": "2026-10-19",
        "clear_fraction": 0.647
      }
    ]
  },
  "units": {
    "percent": "% of 10 m pixels",
    "elevation": "m (EGM2008)",
    "slope": "degrees",
    "ndvi": "unitless, 20 m pixels"
  },
  "sources": {
    "stac_api": "https://planetarycomputer.microsoft.com/api/stac/v1",
    "esa-worldcover": [
      "ESA_WorldCover_10m_2021_v200_N30W099"
    ],
    "cop-dem-glo-30": [
      "Copernicus_DSM_COG_10_N30_00_W097_00_DEM"
    ],
    "sentinel-2-l2a": [
      "S2A_MSIL2A_20261019T170711_R069_T14RQU_20261019T233959"
    ]
  },
  "checks": [
    {
      "name": "landcover_pixels_positive",
      "passed": true,
      "detail": "134064 WorldCover pixels"
    },
    {
      "name": "shares_sum_to_100",
      "passed": true,
      "detail": "class percentages sum to 100"
    },
    {
      "name": "dem_complete",
      "passed": true,
      "detail": "15065/15065 DEM cells valid"
    },
    {
      "name": "ndvi_found",
      "passed": true,
      "detail": "clear scene found in last 90 days"
    },
    {
      "name": "ndvi_in_valid_range",
      "passed": true,
      "detail": "every per-pixel NDVI lies in [-1, 1]"
    },
    {
      "name": "reflectance_in_expected_range",
      "passed": true,
      "detail": "clear-pixel B04/B08 reflectance [0.011, 0.9854] vs expected [-0.02, 1.2]"
    }
  ],
  "notes": [
    "Land-cover shares are for 2021. NDVI is from the most recent Sentinel-2 scene in which >= 60% of the box was clear, using only clear pixels, at 20 m.",
    "Elevation is a surface model (includes buildings and canopy)."
  ]
}
```

## tools/call `verify`

```json
{"lon": -96.5733, "lat": 30.6805}
```

Response in 11.5 s:

```json
{
  "point": {
    "lon": -96.5733,
    "lat": 30.6805
  },
  "status": "pass",
  "passed": 6,
  "total": 6,
  "checks": [
    {
      "name": "ndvi_recomputed_from_raw_bands",
      "passed": true,
      "detail": "2026-10-17: pipeline 0.1685 vs raw-band recompute 0.1683 (|diff| 0.0002, tolerance 0.03 for grid alignment)"
    },
    {
      "name": "ndvi_in_valid_range",
      "passed": true,
      "detail": "0.1685"
    },
    {
      "name": "boa_offset_applied",
      "passed": true,
      "detail": "both paths removed the -1000 DN offset"
    },
    {
      "name": "elevation_native_vs_regridded",
      "passed": true,
      "detail": "76.2 m vs 76.1 m (tolerance 3.0 m)"
    },
    {
      "name": "centre_matches_native",
      "passed": true,
      "detail": "regridded centre cell (40) vs native pixel (40)"
    },
    {
      "name": "vegetated_class_has_positive_ndvi",
      "passed": true,
      "detail": "Cropland (2021) with NDVI 0.1685"
    }
  ],
  "details": {
    "ndvi": {
      "date": "2026-10-17",
      "item_id": "S2C_MSIL2A_20261017T170311_R069_T14RQV_20261017T202312",
      "pipeline_ndvi": 0.1685,
      "independent_ndvi": 0.1683,
      "abs_difference": 0.0002,
      "pipeline_pixels": 29,
      "independent_pixels": 28
    },
    "elevation": {
      "native_m": 76.16,
      "regridded_m": 76.12,
      "tolerance_m": 3.0
    },
    "land_cover": {
      "class_name": "Cropland",
      "top_share_30m": {
        "code": 40,
        "name": "Cropland",
        "percent": 100.0,
        "pixels": 29
      }
    }
  },
  "notes": [
    "verify re-derives values through a second, simpler code path (direct rasterio reads of the native pixels) and compares them with the main pipeline. 'warn' means some checks disagree: report the value with that caveat rather than as fact.",
    "A land-cover vs NDVI mismatch can be real change since 2021, a harvest, or a class edge."
  ]
}
```

## tools/call `verify`

```json
{"lon": -96.3365, "lat": 30.6187}
```

Response in 10.5 s:

```json
{
  "point": {
    "lon": -96.3365,
    "lat": 30.6187
  },
  "status": "pass",
  "passed": 5,
  "total": 5,
  "checks": [
    {
      "name": "ndvi_recomputed_from_raw_bands",
      "passed": true,
      "detail": "2026-10-17: pipeline 0.3486 vs raw-band recompute 0.3342 (|diff| 0.0144, tolerance 0.03 for grid alignment)"
    },
    {
      "name": "ndvi_in_valid_range",
      "passed": true,
      "detail": "0.3486"
    },
    {
      "name": "boa_offset_applied",
      "passed": true,
      "detail": "both paths removed the -1000 DN offset"
    },
    {
      "name": "elevation_native_vs_regridded",
      "passed": true,
      "detail": "107.8 m vs 107.4 m (tolerance 4.3 m)"
    },
    {
      "name": "centre_matches_native",
      "passed": true,
      "detail": "regridded centre cell (50) vs native pixel (50)"
    }
  ],
  "details": {
    "ndvi": {
      "date": "2026-10-17",
      "item_id": "S2C_MSIL2A_20261017T170311_R069_T14RQV_20261017T202312",
      "pipeline_ndvi": 0.3486,
      "independent_ndvi": 0.3342,
      "abs_difference": 0.0144,
      "pipeline_pixels": 29,
      "independent_pixels": 27
    },
    "elevation": {
      "native_m": 107.8,
      "regridded_m": 107.4,
      "tolerance_m": 4.3357391357421875
    },
    "land_cover": {
      "class_name": "Built-up",
      "top_share_30m": {
        "code": 50,
        "name": "Built-up",
        "percent": 89.66,
        "pixels": 26
      }
    }
  },
  "notes": [
    "verify re-derives values through a second, simpler code path (direct rasterio reads of the native pixels) and compares them with the main pipeline. 'warn' means some checks disagree: report the value with that caveat rather than as fact.",
    "A land-cover vs NDVI mismatch can be real change since 2021, a harvest, or a class edge."
  ]
}
```

## tools/call `area_summary`

```json
{"bbox": [-97.5, 30.0, -96.0, 31.0]}
```

Error returned in 0.0 s (as designed):

```text
Error executing tool area_summary: bbox covers about 15980.0 km^2; the limit is 25 km^2 to keep calls fast. Use a smaller box (e.g. 0.04 x 0.04 degrees).
```

## tools/call `ndvi_timeseries`

```json
{"lon": 30.6187, "lat": -96.3365, "start": "2026-01-01", "end": "2026-02-01"}
```

Error returned in 0.0 s (as designed):

```text
Error executing tool ndvi_timeseries: lat=-96.3365 is outside [-90, 90]. Did you swap lon and lat?
```
