// Small Windows desktop launcher. Uses the installed Python 3 and Chromium browser.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal sealed class DatakyDesktop : ApplicationContext
{
    private readonly string root;
    private readonly string url;
    private readonly NotifyIcon tray;
    private Process server;
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

    private DatakyDesktop(string library, string address, Process owned)
    {
        root = library; url = address; server = owned;
        tray = new NotifyIcon();
        tray.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        tray.Text = "Dataky FX Studio";
        var menu = new ContextMenuStrip();
        menu.Items.Add("Ouvrir Dataky FX Studio", null, delegate { OpenWindow(url); });
        menu.Items.Add("Quitter Dataky FX Studio", null, delegate { ExitThread(); });
        tray.ContextMenuStrip = menu;
        tray.DoubleClick += delegate { OpenWindow(url); };
        tray.Visible = true;
        Application.ApplicationExit += delegate { StopOwnedServer(); tray.Dispose(); };
        OpenWindow(url);
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
        string[] bases = { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) };
        string[] paths = { @"Microsoft\Edge\Application\msedge.exe", @"Google\Chrome\Application\chrome.exe", @"BraveSoftware\Brave-Browser\Application\brave.exe" };
        foreach (string item in paths) foreach (string folder in bases)
        { string file = Path.Combine(folder, item); if (File.Exists(file)) return file; }
        return null;
    }

    private static void OpenWindow(string address)
    {
        string browser = FindBrowser();
        if (browser == null) { Process.Start(address); return; }
        string profile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DatakyFXStudio", "Browser");
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
                    String.Equals(Path.GetFullPath((string)data["library"]).TrimEnd('\\'), library.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase);
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
            string address = StartServer(root, out owned);
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
            if (!selfTest) MessageBox.Show(ex.Message, "Dataky FX Studio", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
