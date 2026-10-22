"""Repeatable Luau mock timings; these are not Roblox/phone measurements."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

try:
    from .fx_export import _lua
except ImportError:
    from fx_export import _lua

TOOL = Path(__file__).resolve().parent


def benchmark(source_path: Path, samples: int = 300) -> dict:
    luau = os.environ.get("DATAKY_LUAU") or shutil.which("luau")
    if not luau:
        raise RuntimeError("DATAKY_LUAU is required")
    recipes = {name: json.loads((TOOL / "fixtures" / "blueberrinni" / (name + ".json")).read_text(encoding="utf-8-sig"))
               for name in ("A2_Slam", "A1_Splat")}
    source = (TOOL / "luau_roblox_mock.luau").read_text(encoding="utf-8")
    source += "\nlocal FX = (function()\n" + source_path.read_text(encoding="utf-8-sig") + "\nend)()\n"
    source += "local recipes = " + _lua(recipes) + "\nlocal samples = " + str(samples) + "\n"
    source += r'''
local function copy(t)
    if type(t) ~= "table" or getmetatable(t) then return t end
    local out = {}
    for k,v in pairs(t) do out[k] = copy(v) end
    return out
end
local function median(a) table.sort(a); return a[math.ceil(#a/2)] end
-- Disable event tracing equally for all paths: it is mock I/O, not Roblox work.
if SetMockRecording then SetMockRecording(false) end
for name,recipe in pairs(recipes) do
    local cold, warm, prepared = {}, {}, {}
    for i=1,samples do
        local fresh = copy(recipe)
        local t = os.clock(); local a = FX.play(fresh,CFrame.new(),{quality="High"}); cold[i] = (os.clock()-t)*1000
        a:Stop()
        t = os.clock(); local b = FX.play(fresh,CFrame.new(),{quality="High"}); warm[i] = (os.clock()-t)*1000
        b:Stop()
        if FX.prepare then
            local primed = copy(recipe); FX.prepare(primed)
            t = os.clock(); local c = FX.play(primed,CFrame.new(),{quality="High"}); prepared[i]=(os.clock()-t)*1000
            c:Stop()
        end
        table.clear(EVENTS)
    end
    local c,w,p = median(cold),median(warm),#prepared>0 and median(prepared) or 0
    print(string.format("BENCH %s %.9f %.9f %.9f %.6f",name,c,w,p,c/w))
end
'''
    with tempfile.NamedTemporaryFile("w", suffix=".luau", delete=False, encoding="utf-8") as script:
        script.write(source)
    try:
        process = subprocess.run([luau, script.name], capture_output=True, text=True, timeout=90)
    finally:
        os.unlink(script.name)
    if process.returncode:
        raise RuntimeError(process.stderr + process.stdout)
    result = {"source": str(source_path), "samples": samples, "unit": "ms", "statistic": "median", "environment": "Luau CLI + Roblox mock", "recipes": {}}
    for line in process.stdout.splitlines():
        if line.startswith("BENCH "):
            _, name, cold, warm, prepared, speedup = line.split()
            result["recipes"][name] = {"first_play_ms": float(cold), "second_play_ms": float(warm), "prepared_play_ms": float(prepared), "speedup": float(speedup)}
    if len(result["recipes"]) != len(recipes):
        raise RuntimeError("Missing benchmark cases: " + process.stdout)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=TOOL / "fx_kit.lua")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--samples", type=int, default=300)
    args = parser.parse_args()
    result = benchmark(args.source, args.samples)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
