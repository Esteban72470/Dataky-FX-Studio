"""Execute the actual bridge under Edit and Play client/server DataModels."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

TOOL = Path(__file__).resolve().parent


@unittest.skipUnless(os.environ.get("DATAKY_LUAU") or shutil.which("luau"), "Luau CLI absent")
class PluginTests(unittest.TestCase):
    def test_connection_hint_is_once_in_edit_and_never_play_server_or_client(self):
        source = '''
local _G = {}
local messages, workers = {}, {}
local print = function(message) table.insert(messages, message) end
local running, editing, server = false, true, false
local signal = {Connect=function() return {Disconnect=function() end} end}
local runtime = {apply=function() end, clear=function() end, status=function() return {} end}
local require = function() return runtime end
local module = {IsA=function(_, name) return name == "ModuleScript" end}
local script = {FindFirstChild=function() return module end}
local task = {spawn=function(fn) table.insert(workers, fn); return fn end}
local Enum = {}
local services = {
    HttpService={GenerateGUID=function() return "test-datamodel" end},
    RunService={IsRunning=function() return running end, IsEdit=function() return editing end,
        IsServer=function() return server end, IsClient=function() return not server end},
    Workspace={}, UserInputService={WindowFocused=signal, WindowFocusReleased=signal},
}
local game = {GetService=function(_, name) return services[name] end}
local function control()
    return {SetActive=function() end, Destroy=function() end, Click=signal}
end
local plugin = {Unloading=signal, CreateToolbar=function()
    return {CreateButton=function() return control() end, Destroy=function() end}
end}
local function loadBridge()
'''
        source += (TOOL / "fx_plugin.lua").read_text(encoding="utf-8") + "\nend\n"
        source += '''
loadBridge()
loadBridge()
assert(#messages == 1, "Edit hint once even after reload")
for _, isServer in ipairs({true, false}) do
    _G = {}
    running, editing, server = true, true, isServer
    local count = #messages
    loadBridge()
    loadBridge()
    assert(#messages == count, "No hint in running Play DataModel (server/client), even if IsEdit says true")
    assert(not _G.DatakyFXConnectionHintShown, "Play does not consume Edit hint")
    running, editing = false, false
    loadBridge()
    assert(#messages == count, "No hint in paused non-Edit DataModel")
end
print = nil
'''
        with tempfile.NamedTemporaryFile("w", suffix=".luau", delete=False, encoding="utf-8") as handle:
            handle.write(source)
        try:
            result = subprocess.run([os.environ.get("DATAKY_LUAU") or shutil.which("luau"), handle.name], capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(handle.name)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
