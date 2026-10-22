"""Open Earth MCP: traceable open Earth-observation data for AI assistants."""

import os
import sys
from pathlib import Path

__version__ = "0.1.0"


def _conda_runtime_paths() -> None:
    """MCP clients usually start the interpreter without `conda activate`.

    On Windows that leaves the env's DLL folder off PATH, so numpy/GDAL can pick up
    incompatible DLLs from elsewhere on the system. Put the env's own folders first,
    and point GDAL/PROJ at their data, before any of those libraries load.
    """
    lib_bin = Path(sys.prefix, "Library", "bin")
    if os.name == "nt" and lib_bin.is_dir():
        path = os.environ.get("PATH", "")
        if not path.lower().startswith(str(lib_bin).lower()):
            os.environ["PATH"] = os.pathsep.join([str(lib_bin), sys.prefix, path])
    for var, sub in (("GDAL_DATA", ("Library", "share", "gdal")), ("PROJ_DATA", ("Library", "share", "proj"))):
        p = Path(sys.prefix, *sub)
        if var not in os.environ and p.is_dir():
            os.environ[var] = str(p)


_conda_runtime_paths()
