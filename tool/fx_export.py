"""Export a Dataky FX project as standalone, offline Roblox Luau source.

The generated ModuleScript exposes build(parent, origin), play(), stop(), clear(),
pause(), resume(), status(). It never calls an HTTP endpoint or uses loadstring.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

RUNTIME_PATH = Path(__file__).with_name("fx_runtime.lua")


def _lua(value: Any) -> str:
    """Serialize JSON values as Luau literals without executable interpolation."""
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("Non-finite numbers cannot be exported")
        return str(value)
    if isinstance(value, str):
        # JSON's \uXXXX is not Lua syntax; utf-8 text is valid in quoted Luau.
        # Escape controls with unambiguous three-digit decimal escapes.
        result = []
        for char in value:
            code = ord(char)
            if char == "\\":
                result.append("\\\\")
            elif char == '"':
                result.append('\\"')
            elif code < 32 or code == 127:
                result.append(f"\\{code:03d}")
            else:
                result.append(char)
        return '"' + "".join(result) + '"'
    if isinstance(value, list):
        return "{" + ",".join(_lua(item) for item in value) + "}"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("Project dictionary keys must be strings")
        return "{" + ",".join("[" + _lua(key) + "]=" + _lua(item) for key, item in value.items() if item is not None) + "}"
    raise ValueError(f"Unsupported project value: {type(value).__name__}")


def export_project(project: dict[str, Any]) -> str:
    if __package__:
        from .fx_schema import validate_project
    else:
        from fx_schema import validate_project
    project = validate_project(project)
    if not isinstance(project, dict) or project.get("version") != 1 or not isinstance(project.get("nodes"), list):
        raise ValueError("Dataky FX project version 1 with nodes is required")
    if len(project["nodes"]) > 400:
        raise ValueError("A project can contain at most 400 nodes")
    source = RUNTIME_PATH.read_text(encoding="utf-8-sig")
    literal = _lua(project)
    return (
        "-- Dataky FX Studio — standalone native Roblox effect\n"
        "-- Put this source in a ModuleScript; no local server or AI is required.\n"
        "-- local fx = require(path.To.ThisModule)\n"
        "-- fx.build(workspace, Vector3.new(0, 4, 0)); fx.play()\n"
        "-- Coordinates of BaseParts are relative to the supplied origin.\n"
        "local Runtime = (function()\n" + source + "\nend)()\n"
        "local Project = " + literal + "\n"
        "local Effect = {}\n"
        "function Effect.build(parent, origin)\n"
        "    origin = origin or Vector3.zero\n"
        "    return Runtime.apply(Project, {preview=false, camera=false, parent=parent or workspace, "
        "rootName=Project.name or 'DatakyFX', origin={origin.X,origin.Y,origin.Z}})\n"
        "end\n"
        "function Effect.play()\n"
        "    if not Runtime.status().ready then Effect.build() end\n"
        "    return Runtime.play()\n"
        "end\n"
        "Effect.stop = Runtime.stop\n"
        "Effect.clear = Runtime.clear\n"
        "Effect.pause = Runtime.pause\n"
        "Effect.resume = Runtime.resume\n"
        "Effect.status = Runtime.status\n"
        "return Effect\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.project.read_text(encoding="utf-8-sig"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(export_project(data), encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
