// Windows desktop launcher. Prefers the packaged runtime when available.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32.SafeHandles;

internal sealed class DatakyDesktop : ApplicationContext
{
    private readonly string root;
    private readonly string url;
    private readonly NotifyIcon tray;
    private readonly ContextMenuStrip menu;
    private Process server;
    private int checkingUpdates;
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFile(string name, uint access, uint share, IntPtr security, uint mode, uint flags, IntPtr template);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandle(SafeFileHandle file, StringBuilder path, uint size, uint flags);

    private static string ResolvedDirectory(string path)
    {
        string absolute = Path.GetFullPath(path).TrimEnd('\\');
        using (SafeFileHandle file = CreateFile(absolute, 0, 7, IntPtr.Zero, 3, 0x02000000, IntPtr.Zero))
        {
            if (file.IsInvalid) return absolute;
            var final = new StringBuilder(32768);
            uint length = GetFinalPathNameByHandle(file, final, (uint)final.Capacity, 0);
            if (length == 0 || length >= final.Capacity) return absolute;
            string value = final.ToString();
            if (value.StartsWith(@"\\?\UNC\", StringComparison.OrdinalIgnoreCase)) value = @"\\" + value.Substring(8);
            else if (value.StartsWith(@"\\?\", StringComparison.Ordinal)) value = value.Substring(4);
            return value.TrimEnd('\\');
        }
    }

    private DatakyDesktop(string library, string address, Process owned)
    {
        root = library; url = address; server = owned;
        tray = new NotifyIcon();
        tray.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        tray.Text = "Dataky FX Studio " + ReadVersion(library);
        menu = new ContextMenuStrip();
        menu.Items.Add("Ouvrir Dataky FX Studio", null, delegate { OpenWindow(url); });
        menu.Items.Add("Vérifier les mises à jour", null, delegate { CheckUpdates(true); });
        menu.Items.Add("Télécharger la dernière version", null, delegate { Process.Start("https://github.com/Esteban72470/Dataky-FX-Studio/releases/latest"); });
        menu.Items.Add("Quitter Dataky FX Studio", null, delegate { ExitThread(); });
        tray.ContextMenuStrip = menu;
        tray.DoubleClick += delegate { OpenWindow(url); };
        tray.Visible = true;
        Application.ApplicationExit += delegate { StopOwnedServer(); tray.Dispose(); };
        OpenWindow(url);
        IntPtr handle = menu.Handle;
        if (Environment.GetEnvironmentVariable("DATAKY_UPDATE_CHECKED") != "1") CheckUpdates(false);
    }

    private static string ReadVersion(string library)
    {
        try { var value = Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(Path.Combine(library, "version.json"), Encoding.UTF8)); return value.ContainsKey("version") ? (string)value["version"] : ""; }
        catch (Exception error) { if (error is IOException || error is UnauthorizedAccessException || error is ArgumentException || error is InvalidCastException || error is InvalidOperationException) return ""; throw; }
    }

    private void CheckUpdates(bool manual)
    {
        if (Interlocked.Exchange(ref checkingUpdates, 1) != 0) return;
        ThreadPool.QueueUserWorkItem(delegate
        {
            Dictionary<string, object> report = null;
            try
            {
                string script = Path.Combine(root, "tool", "fx_update.py");
                if (!File.Exists(script)) throw new IOException("Service de mise à jour absent.");
                var start = new ProcessStartInfo(FindPython(), Quote(script) + " --root " + Quote(root) + " --check");
                start.WorkingDirectory = root; start.UseShellExecute = false; start.CreateNoWindow = true; start.WindowStyle = ProcessWindowStyle.Hidden;
                start.RedirectStandardOutput = true; start.RedirectStandardError = true;
                start.EnvironmentVariables["PYTHONUTF8"] = "1";
                start.EnvironmentVariables.Remove("PYTHONHOME"); start.EnvironmentVariables.Remove("PYTHONPATH");
                var output = new StringBuilder();
                using (var process = new Process())
                {
                    process.StartInfo = start;
                    process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs line) { if (line.Data != null) lock (output) { if (output.Length < 65536) output.AppendLine(line.Data); } };
                    process.ErrorDataReceived += delegate { };
                    process.Start(); process.BeginOutputReadLine(); process.BeginErrorReadLine();
                    if (!process.WaitForExit(20000)) { process.Kill(); process.WaitForExit(3000); throw new IOException("Vérification expirée."); }
                    process.WaitForExit();
                    report = Json.Deserialize<Dictionary<string, object>>(output.ToString());
                }
            }
            catch (Exception) { report = new Dictionary<string, object> { { "status", "unavailable" }, { "message", "Vérification indisponible. Réessayez plus tard." } }; }
            finally { Interlocked.Exchange(ref checkingUpdates, 0); }
            try
            {
                menu.BeginInvoke((MethodInvoker)delegate
                {
                    object status;
                    if (report == null || !report.TryGetValue("status", out status)) return;
                    if ((string)status == "available")
                    {
                        object latest; report.TryGetValue("latest_version", out latest);
                        tray.ShowBalloonTip(8000, "Mise à jour disponible", "Version " + Convert.ToString(latest) + ". Quittez l’atelier puis relancez le fichier complet pour l’installer.", ToolTipIcon.Info);
                    }
                    else if (manual)
                    {
                        string text = (string)status == "up_to_date" ? "Votre application est à jour (" + ReadVersion(root) + ")." : "Vérification indisponible. Réessayez plus tard.";
                        tray.ShowBalloonTip(5000, "Dataky FX Studio", text, ToolTipIcon.Info);
                    }
                });
            }
            catch (InvalidOperationException) { }
        });
    }

    private static string StartupKey(string directory)
    {
        using (var hash = SHA256.Create()) return "Local\\DatakyFX-Startup-" + BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(ResolvedDirectory(directory).ToLowerInvariant()))).Replace("-", "").ToLowerInvariant().Substring(0, 24);
    }

    protected override void ExitThreadCore()
    {
        StopOwnedServer(); tray.Visible = false; tray.Dispose(); base.ExitThreadCore();
    }

    private void StopOwnedServer()
    {
        if (server == null) return;
        try { if (!server.HasExited) { server.Kill(); server.WaitForExit(5000); } }
        catch (InvalidOperationException) { }
        finally { server.Dispose(); server = null; }
    }

    private static string Quote(string value) { return "\"" + value.Replace("\"", "") + "\""; }

    private static string FindPython()
    {
        string bundled = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "_runtime", "python", "pythonw.exe");
        if (File.Exists(bundled)) return bundled;
        string programs = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python");
        if (Directory.Exists(programs))
        {
            var dirs = Directory.GetDirectories(programs, "Python3*");
            Array.Sort(dirs, StringComparer.OrdinalIgnoreCase); Array.Reverse(dirs);
            foreach (string dir in dirs)
            {
                string file = Path.Combine(dir, "pythonw.exe");
                if (File.Exists(file)) return file;
            }
        }
        foreach (string folder in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
        {
            if (String.IsNullOrWhiteSpace(folder)) continue;
            try { string file = Path.Combine(folder.Trim('"'), "pythonw.exe"); if (File.Exists(file) && file.IndexOf("WindowsApps", StringComparison.OrdinalIgnoreCase) < 0) return file; }
            catch (ArgumentException) { }
        }
        throw new InvalidOperationException("Python 3 est introuvable. Installez Python 3, puis relancez Dataky FX Studio.");
    }

    private static string FindBrowser()
    {
        string bundled = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "_runtime", "browsers");
        if (Directory.Exists(bundled))
        {
            string[] browsers = Directory.GetFiles(bundled, "chrome.exe", SearchOption.AllDirectories);
            Array.Sort(browsers, StringComparer.OrdinalIgnoreCase);
            if (browsers.Length > 0) return browsers[0];
        }
        string[] bases = { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) };
        string[] paths = { @"BraveSoftware\Brave-Browser\Application\brave.exe", @"Google\Chrome\Application\chrome.exe", @"Microsoft\Edge\Application\msedge.exe" };
        foreach (string item in paths) foreach (string folder in bases)
        { string file = Path.Combine(folder, item); if (File.Exists(file)) return file; }
        return null;
    }

    private static void OpenWindow(string address)
    {
        string browser = FindBrowser();
        if (browser == null) { Process.Start(address); return; }
        // The Windows activation-context loader must see the real directory
        // when a Store-hosted process has redirected the packaged browser.
        browser = Path.Combine(ResolvedDirectory(Path.GetDirectoryName(browser)), Path.GetFileName(browser));
        string profile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DatakyFXStudio", "Browser-" + Path.GetFileNameWithoutExtension(browser));
        var start = new ProcessStartInfo(browser, "--no-first-run --no-default-browser-check --user-data-dir=" + Quote(profile) + " --app=" + Quote(address));
        start.UseShellExecute = false; start.CreateNoWindow = true;
        Process.Start(start);
    }

    private static bool Matches(string address, string library)
    {
        try
        {
            var request = (HttpWebRequest)WebRequest.Create(address + "api/status");
            request.Timeout = 400; request.ReadWriteTimeout = 400; request.Proxy = null;
            using (var response = request.GetResponse()) using (var reader = new StreamReader(response.GetResponseStream()))
            {
                var data = Json.Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
                return data.ContainsKey("app") && (string)data["app"] == "Dataky FX Studio" && data.ContainsKey("library") &&
                    String.Equals(ResolvedDirectory((string)data["library"]), ResolvedDirectory(library), StringComparison.OrdinalIgnoreCase);
            }
        }
        catch (WebException) { return false; }
        catch (ArgumentException) { return false; }
        catch (InvalidCastException) { return false; }
    }

    private static string StartServer(string library, out Process owned)
    {
        owned = null;
        int chosen = 0;
        for (int port = 48754; port <= 48774; port++)
        {
            string address = "http://127.0.0.1:" + port + "/";
            if (Matches(address, library)) return address;
            if (chosen != 0) continue;
            try { var probe = new TcpListener(IPAddress.Loopback, port); probe.Start(); probe.Stop(); chosen = port; }
            catch (SocketException) { }
        }
        if (chosen == 0) throw new InvalidOperationException("Aucun port local libre pour Dataky FX Studio.");
        string logDir = Path.Combine(library, "editor", "desktoplogs"); Directory.CreateDirectory(logDir);
        string logPath = Path.Combine(logDir, "serveur.log");
        var start = new ProcessStartInfo(FindPython(), Quote(Path.Combine(library, "tool", "fx_server.py")) + " --port " + chosen + " --no-browser");
        start.WorkingDirectory = library; start.UseShellExecute = false; start.CreateNoWindow = true;
        start.RedirectStandardError = true; start.RedirectStandardOutput = true;
        start.EnvironmentVariables["PYTHONUTF8"] = "1";
        string runtime = Path.Combine(library, "_runtime");
        if (Directory.Exists(runtime))
        {
            start.EnvironmentVariables.Remove("PYTHONHOME");
            start.EnvironmentVariables.Remove("PYTHONPATH");
            start.EnvironmentVariables["PATH"] = Path.Combine(runtime, "node") + Path.PathSeparator + (Environment.GetEnvironmentVariable("PATH") ?? "");
            start.EnvironmentVariables["NODE_PATH"] = Path.Combine(runtime, "node_modules");
            start.EnvironmentVariables["PLAYWRIGHT_BROWSERS_PATH"] = Path.Combine(runtime, "browsers");
        }
        var logLock = new object();
        var process = new Process(); process.StartInfo = start;
        DataReceivedEventHandler log = delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null) lock(logLock) { try { File.AppendAllText(logPath, e.Data + Environment.NewLine, Encoding.UTF8); } catch (IOException) { } } };
        process.OutputDataReceived += log; process.ErrorDataReceived += log;
        process.Start(); process.BeginOutputReadLine(); process.BeginErrorReadLine();
        string result = "http://127.0.0.1:" + chosen + "/";
        for (int n = 0; n < 100; n++)
        {
            if (Matches(result, library)) { owned = process; return result; }
            if (process.HasExited) break;
            Thread.Sleep(100);
        }
        try { if (!process.HasExited) process.Kill(); } finally { process.Dispose(); }
        throw new InvalidOperationException("Le serveur n’a pas démarré. Consultez editor\\desktoplogs\\serveur.log.");
    }

    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        string root = Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory);
        Process owned = null;
        bool selfTest = args.Length > 0 && args[0] == "--self-test";
        try
        {
            if (!File.Exists(Path.Combine(root, "tool", "fx_server.py")) || !File.Exists(Path.Combine(root, "editor", "index.html")))
                throw new InvalidOperationException("Conservez Dataky FX Studio.exe dans le dossier de l’application, avec tool et editor.");
            string address;
            using (var startup = new Mutex(false, StartupKey(root)))
            {
                bool acquired;
                try { acquired = startup.WaitOne(TimeSpan.FromMinutes(3)); }
                catch (AbandonedMutexException) { acquired = true; }
                if (!acquired) throw new IOException("Un autre démarrage est encore en cours. Relancez dans un instant.");
                try { address = StartServer(root, out owned); }
                finally { startup.ReleaseMutex(); }
            }
            if (selfTest)
            {
                string report = args.Length > 1 ? Path.GetFullPath(args[1]) : Path.Combine(root, "editor", "desktoplogs", "verification.json");
                Directory.CreateDirectory(Path.GetDirectoryName(report));
                File.WriteAllText(report, Json.Serialize(new { app = "Dataky FX Studio", status = "ok", library = root, url = address, python = FindPython(), browser = FindBrowser(), owned_server = owned != null }), Encoding.UTF8);
                if (owned != null) { owned.Kill(); owned.WaitForExit(5000); owned.Dispose(); owned = null; }
                return 0;
            }
            string key;
            using (var hash = SHA256.Create()) key = BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(root.ToLowerInvariant()))).Replace("-", "").Substring(0, 24);
            bool created;
            using (var mutex = new Mutex(true, "Local\\DatakyFXStudio-" + key, out created))
            {
                if (!created) { OpenWindow(address); if (owned != null) owned.Dispose(); return 0; }
                Application.Run(new DatakyDesktop(root, address, owned)); owned = null;
                mutex.ReleaseMutex();
            }
            return 0;
        }
        catch (Exception ex)
        {
            if (owned != null) { try { if (!owned.HasExited) owned.Kill(); } catch (InvalidOperationException) { } owned.Dispose(); }
            if (selfTest)
            {
                try
                {
                    string report = args.Length > 1 ? Path.GetFullPath(args[1]) : Path.Combine(root, "editor", "desktoplogs", "verification.json");
                    Directory.CreateDirectory(Path.GetDirectoryName(report));
                    File.WriteAllText(report, Json.Serialize(new { status = "error", error = ex.Message, detail = ex.ToString() }), Encoding.UTF8);
                }
                catch (IOException) { }
            }
            else MessageBox.Show(ex.Message, "Dataky FX Studio", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
