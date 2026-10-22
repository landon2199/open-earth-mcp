"""Launch open-earth-mcp over stdio with the MCP client SDK and exercise every tool.

    python examples/demo_client.py            # writes examples/demo_output.md and examples/demo_ndvi.json

The transcript records each request and a trimmed view of each response, so the
README's example numbers can be traced back to a real run.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from mcp import Client, StdioServerParameters

HERE = Path(__file__).resolve().parent
OUT_MD = HERE / "demo_output.md"
OUT_JSON = HERE / "demo_ndvi.json"

CAMPUS = (-96.3365, 30.6187)  # Texas A&M University campus, College Station, TX
FARM = (-96.5733, 30.6805)  # cropland in the Brazos River bottoms west of Bryan, TX (WorldCover 2021: Cropland)

TODAY = date.today()


def _trim(obj, max_list: int = 6):
    """Shorten long lists so the transcript stays readable (full JSON is kept for the NDVI series)."""
    if isinstance(obj, dict):
        return {k: _trim(v, max_list) for k, v in obj.items()}
    if isinstance(obj, list):
        out = [_trim(v, max_list) for v in obj[:max_list]]
        if len(obj) > max_list:
            out.append(f"... {len(obj) - max_list} more")
        return out
    return obj


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "open_earth_mcp.server"],
                                   cwd=str(HERE.parent))
    md: list[str] = [
        "# open-earth-mcp demo transcript",
        "",
        f"Run on {TODAY} by `examples/demo_client.py`: the server was launched over **stdio** and called through "
        "the MCP Python client SDK. Responses are real; long lists are trimmed.",
        "",
    ]
    saved: dict = {}

    async with Client(params, read_timeout_seconds=300) as client:
        tools = (await client.list_tools()).tools
        md += ["## tools/list", ""] + [f"- **{t.name}** - {t.description.splitlines()[0]}" for t in tools] + [""]

        res = await client.read_resource("catalog://collections")
        cat = json.loads(res.contents[0].text)
        md += ["## resources/read `catalog://collections`", "", "| collection | license |", "|---|---|"]
        md += [f"| {k} | {v['license']} |" for k, v in cat["collections"].items()] + [""]

        prompt = await client.get_prompt("describe_place", {"lon": str(CAMPUS[0]), "lat": str(CAMPUS[1])})
        md += ["## prompts/get `describe_place`", "", "```text", prompt.messages[0].content.text, "```", ""]

        calls = [
            ("search_imagery", {"lon": CAMPUS[0], "lat": CAMPUS[1], "start": str(TODAY - timedelta(days=60)),
                                "end": str(TODAY), "max_cloud": 20, "limit": 5}),
            ("land_cover", {"lon": CAMPUS[0], "lat": CAMPUS[1], "buffer_m": 200}),
            ("land_cover", {"lon": FARM[0], "lat": FARM[1], "buffer_m": 200}),
            ("elevation", {"lon": CAMPUS[0], "lat": CAMPUS[1]}),
            ("ndvi_timeseries", {"lon": FARM[0], "lat": FARM[1], "start": "2025-10-01", "end": str(TODAY),
                                 "buffer_m": 30}),
            ("ndvi_timeseries", {"lon": CAMPUS[0], "lat": CAMPUS[1], "start": "2025-10-01", "end": str(TODAY),
                                 "buffer_m": 30}),
            ("area_summary", {"bbox": [-96.36, 30.60, -96.32, 30.63]}),
            ("verify", {"lon": FARM[0], "lat": FARM[1]}),
            ("verify", {"lon": CAMPUS[0], "lat": CAMPUS[1]}),
            ("area_summary", {"bbox": [-97.5, 30.0, -96.0, 31.0]}),  # guardrail demo: too large
            ("ndvi_timeseries", {"lon": 30.6187, "lat": -96.3365, "start": "2026-01-01", "end": "2026-02-01"}),
        ]
        for name, args in calls:
            t0 = time.perf_counter()
            r = await client.call_tool(name, args)
            dt = time.perf_counter() - t0
            md += [f"## tools/call `{name}`", "", "```json", json.dumps(args), "```", ""]
            if r.is_error:
                md += [f"Error returned in {dt:.1f} s (as designed):", "", "```text", r.content[0].text, "```", ""]
                print(f"{name}: error -> {r.content[0].text[:90]}")
                continue
            data = r.structured_content
            if data is None:
                data = json.loads(r.content[0].text)
            if "result" in data and len(data) == 1:
                data = data["result"]
            if name == "ndvi_timeseries":
                key = "farm" if args["lon"] == FARM[0] else "campus"
                saved[key] = data
            md += [f"Response in {dt:.1f} s:", "", "```json", json.dumps(_trim(data), indent=2), "```", ""]
            print(f"{name}: ok in {dt:.1f} s")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(saved, indent=1), encoding="utf-8")
    print(f"wrote {OUT_MD} and {OUT_JSON}")


if __name__ == "__main__":
    asyncio.run(main())
