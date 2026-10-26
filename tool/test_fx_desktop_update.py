"""Compile the actual Windows launchers and verify startup/update boundaries."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
CSC = Path(os.environ.get("WINDIR", "C:/Windows")) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"

HARNESS = r'''
using System;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

internal static class DesktopUpdateTests
{
    private static void Assert(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static string Sibling(string parent, char id)
    {
        string root = Path.Combine(parent, new string(id, 24)); Directory.CreateDirectory(root);
        File.WriteAllText(Path.Combine(root, ".dataky-package-ready"), new string(id, 64)); return root;
    }
    private static void Write(string root, string name, string data)
    {
        string target = Path.Combine(root, name); Directory.CreateDirectory(Path.GetDirectoryName(target)); File.WriteAllText(target, data);
    }
    [STAThread]
    private static int Main(string[] args)
    {
        string parent = args[0]; Directory.CreateDirectory(parent);
        string old = Sibling(parent, 'a'), newer = Sibling(parent, 'b'), target = Sibling(parent, 'c');
        Write(old, @"editor\projects\keep.json", "original");
        Write(old, @"editor\projects\same.json", "old");
        Write(old, @"editor\snapshots\frame.png", "snapshot");
        Write(old, @"editor\artistry\review.json", "review");
        Write(old, @"editor\local_ai\meshes\custom.obj", "mesh");
        Write(old, @"editor\local_ai\video\reference.mp4", "video");
        Write(old, @"editor\local_ai\catalog.json", "registry");
        Write(old, @"tool\grid_overrides.json", "grid");
        Write(old, @"exports\effect.lua", "export");
        Write(newer, @"editor\projects\unrelated.json", "newer");
        Write(target, @"editor\projects\same.json", "current");
        Directory.SetLastWriteTimeUtc(old, DateTime.UtcNow.AddHours(-2));
        Directory.SetLastWriteTimeUtc(newer, DateTime.UtcNow.AddHours(-1));
        PortableBootstrap.MigrateUserData(target, parent, new[] {old});
        Assert(File.ReadAllText(Path.Combine(target, @"editor\projects\keep.json")) == "original", "active sibling selected");
        Assert(File.ReadAllText(Path.Combine(target, @"editor\projects\same.json")) == "current", "existing project preserved");
        Assert(File.ReadAllText(Path.Combine(old, @"editor\projects\same.json")) == "old", "original unchanged");
        Assert(!File.Exists(Path.Combine(target, @"editor\projects\unrelated.json")), "did not copy unrelated sibling");
        foreach (string name in new[] {@"editor\snapshots\frame.png", @"editor\artistry\review.json", @"editor\local_ai\meshes\custom.obj", @"editor\local_ai\video\reference.mp4", @"editor\local_ai\catalog.json", @"tool\grid_overrides.json", @"exports\effect.lua"})
            Assert(File.Exists(Path.Combine(target, name)), "missing migration: " + name);
        Write(old, @"editor\projects\late.json", "later");
        PortableBootstrap.MigrateUserData(target, parent, new[] {old});
        Assert(!File.Exists(Path.Combine(target, @"editor\projects\late.json")), "migration marker prevents recopy");
        Assert(!PortableBootstrap.ShouldApplyUpdates(target, new[] {target}), "running root blocks apply");
        Assert(PortableBootstrap.ShouldApplyUpdates(target, new[] {old}), "other root does not block apply");
        var flags = BindingFlags.NonPublic | BindingFlags.Static;
        string bootstrapKey = (string)typeof(PortableBootstrap).GetMethod("StartupKey", flags).Invoke(null, new object[] {target});
        string desktopKey = (string)typeof(DatakyDesktop).GetMethod("StartupKey", flags).Invoke(null, new object[] {target});
        Assert(bootstrapKey == desktopKey, "bootstrap and direct desktop share startup lock");
        string quoted = (string)typeof(PortableBootstrap).GetMethod("Quote", flags).Invoke(null, new object[] {@"C:\My App\tool\fx_update.py"});
        Assert(quoted == "\"C:\\My App\\tool\\fx_update.py\"", "paths with spaces stay one argument");
        Write(target, @"tool\fx_update.py", "# unused stub");
        Write(target, @"_runtime\python\python.exe", "invalid executable");
        using (var app = (Form)Activator.CreateInstance(typeof(PortableBootstrap), BindingFlags.NonPublic | BindingFlags.Instance, null, new object[] {new string[0]}, null))
        {
            IntPtr handle = app.Handle;
            typeof(PortableBootstrap).GetMethod("TryApplyUpdates", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(app, new object[] {target});
        }
        Assert(File.Exists(Path.Combine(target, @"editor\desktoplogs\demarrage.log")), "updater launch failure is logged and fails open");
        Console.WriteLine("PASS: migration, originals, one-time marker, running-root guard, shared lock, quoted paths, fail-open startup");
        return 0;
    }
}
'''


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "Windows .NET Framework compiler required")
class DesktopUpdateTests(unittest.TestCase):
    def test_actual_launchers_and_migration(self):
        with tempfile.TemporaryDirectory(prefix="dataky-desktop-update-") as folder:
            work = Path(folder)
            source = work / "Tests.cs"
            source.write_text(HARNESS, encoding="utf-8")
            binary = work / "Tests.exe"
            refs = ["System.Windows.Forms.dll", "System.Drawing.dll", "System.Web.Extensions.dll", "System.IO.Compression.dll", "System.IO.Compression.FileSystem.dll"]
            command = [str(CSC), "/nologo", "/target:exe", "/main:DesktopUpdateTests", "/out:" + str(binary)]
            command += ["/reference:" + ref for ref in refs]
            command += [str(ROOT / "desktop/PortableBootstrap.cs"), str(ROOT / "desktop/DatakyFXStudio.cs"), str(source)]
            build = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([str(binary), str(work / "prepared")], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS:", result.stdout)


if __name__ == "__main__":
    unittest.main()
