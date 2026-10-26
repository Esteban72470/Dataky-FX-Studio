// Single-file package bootstrap: local extraction, then verified code-only updates.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32.SafeHandles;

internal sealed class PayloadStream : Stream
{
    private readonly FileStream file;
    private readonly long start;
    private readonly long size;
    private long position;
    public PayloadStream(string path, long offset, long length)
    {
        file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        start = offset; size = length; position = 0;
    }
    public override bool CanRead { get { return true; } }
    public override bool CanSeek { get { return true; } }
    public override bool CanWrite { get { return false; } }
    public override long Length { get { return size; } }
    public override long Position { get { return position; } set { Seek(value, SeekOrigin.Begin); } }
    public override int Read(byte[] buffer, int offset, int count)
    {
        int bounded = (int)Math.Min(count, size - position);
        if (bounded == 0) return 0;
        file.Position = start + position;
        int read = file.Read(buffer, offset, bounded); position += read; return read;
    }
    public override long Seek(long offset, SeekOrigin origin)
    {
        long next = origin == SeekOrigin.Begin ? offset : origin == SeekOrigin.Current ? checked(position + offset) : checked(size + offset);
        if (next < 0 || next > size) throw new IOException("Position hors du paquet.");
        position = next; return next;
    }
    public override void Flush() { }
    public override void SetLength(long value) { throw new NotSupportedException(); }
    public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
    protected override void Dispose(bool disposing) { if (disposing) file.Dispose(); base.Dispose(disposing); }
}

internal sealed class PortableBootstrap : Form
{
    private const string Magic = "DATAKYFXBUNDLE01";
    private const long MaxExpandedBytes = 16L * 1024 * 1024 * 1024;
    private readonly Label message = new Label();
    private readonly ProgressBar progress = new ProgressBar();
    private readonly string[] arguments;
    private readonly bool selfTest;
    private bool finished;
    private int result = 1;
    private long lastUiTicks;
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 32 * 1024 * 1024 };

    private PortableBootstrap(string[] args)
    {
        arguments = args; selfTest = args.Length > 0 && args[0] == "--self-test";
        Text = "Dataky FX Studio"; ClientSize = new Size(500, 170);
        FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen; ControlBox = false;
        BackColor = Color.FromArgb(29, 24, 37); ForeColor = Color.White;
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        var title = new Label { Text = "Dataky FX Studio", Font = new Font("Segoe UI", 17, FontStyle.Bold), AutoSize = false, Location = new Point(24, 20), Size = new Size(450, 36) };
        message.Text = "Préparation de l’application…"; message.Location = new Point(25, 70); message.Size = new Size(450, 40);
        message.Font = new Font("Segoe UI", 10); progress.Location = new Point(25, 120); progress.Size = new Size(450, 16);
        Controls.Add(title); Controls.Add(message); Controls.Add(progress);
        Shown += delegate { ThreadPool.QueueUserWorkItem(delegate { RunPackage(); }); };
        FormClosing += delegate(object sender, FormClosingEventArgs e) { if (!finished) e.Cancel = true; };
    }

    private void Status(int percent, string text)
    {
        long ticks = DateTime.UtcNow.Ticks;
        if (percent != 100 && ticks - lastUiTicks < TimeSpan.TicksPerMillisecond * 100) return;
        lastUiTicks = ticks;
        if (IsDisposed) return;
        BeginInvoke((MethodInvoker)delegate { progress.Value = Math.Max(0, Math.Min(100, percent)); message.Text = text; });
    }

    private static string Hex(byte[] value) { return BitConverter.ToString(value).Replace("-", "").ToLowerInvariant(); }
    private static string Quote(string value) { return "\"" + value.Replace("\"", "") + "\""; }

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

    private static string StartupKey(string directory)
    {
        using (var hash = SHA256.Create()) return "Local\\DatakyFX-Startup-" + Hex(hash.ComputeHash(Encoding.UTF8.GetBytes(ResolvedDirectory(directory).ToLowerInvariant()))).Substring(0, 24);
    }

    private static List<string> RunningLibraries()
    {
        var roots = new List<string>();
        foreach (var process in Process.GetProcessesByName("Dataky FX Studio"))
        {
            using (process)
            {
                try
                {
                    string directory = Path.GetDirectoryName(process.MainModule.FileName);
                    if (File.Exists(Path.Combine(directory, "tool", "fx_server.py"))) roots.Add(ResolvedDirectory(directory));
                }
                catch (Exception error) { if (!(error is System.ComponentModel.Win32Exception || error is InvalidOperationException || error is ArgumentException)) throw; }
            }
        }
        for (int port = 48754; port <= 48774; port++)
        {
            try
            {
                var request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/api/status");
                request.Proxy = null; request.Timeout = 250; request.ReadWriteTimeout = 250;
                using (var response = request.GetResponse()) using (var reader = new StreamReader(response.GetResponseStream()))
                {
                    var data = Json.Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
                    object app, root;
                    if (data.TryGetValue("app", out app) && (string)app == "Dataky FX Studio" && data.TryGetValue("library", out root) && root is string)
                        roots.Add(ResolvedDirectory((string)root));
                }
            }
            catch (Exception error) { if (!(error is WebException || error is ArgumentException || error is InvalidCastException || error is IOException)) throw; }
        }
        return roots;
    }

    private static bool RegularPath(string path)
    {
        return (File.GetAttributes(path) & FileAttributes.ReparsePoint) == 0;
    }

    private static bool NoReparseUnder(string root, string path)
    {
        string fullRoot = Path.GetFullPath(root).TrimEnd('\\'), full = Path.GetFullPath(path);
        if (!full.StartsWith(fullRoot + "\\", StringComparison.OrdinalIgnoreCase)) return false;
        string current = fullRoot;
        if (!RegularPath(current)) return false;
        foreach (string part in full.Substring(fullRoot.Length + 1).Split('\\'))
        {
            current = Path.Combine(current, part);
            if ((File.Exists(current) || Directory.Exists(current)) && !RegularPath(current)) return false;
        }
        return true;
    }

    private static bool ReadySibling(string path, string parent)
    {
        string name = Path.GetFileName(path);
        if (name.Length != 24 || !String.Equals(Path.GetDirectoryName(Path.GetFullPath(path)), Path.GetFullPath(parent).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)) return false;
        foreach (char value in name) if (!Uri.IsHexDigit(value)) return false;
        if (!RegularPath(path)) return false;
        string marker = Path.Combine(path, ".dataky-package-ready");
        if (!File.Exists(marker) || !RegularPath(marker)) return false;
        string digest = File.ReadAllText(marker, Encoding.UTF8).Trim();
        if (digest.Length != 64 || !digest.StartsWith(name, StringComparison.OrdinalIgnoreCase)) return false;
        foreach (char value in digest) if (!Uri.IsHexDigit(value)) return false;
        return true;
    }

    private static void CopyMissingTree(string source, string target)
    {
        if (!Directory.Exists(source) || !RegularPath(source)) return;
        if (Directory.Exists(target) && !RegularPath(target)) throw new IOException("Dossier personnel redirigé : copie interrompue.");
        Directory.CreateDirectory(target);
        foreach (string entry in Directory.GetFileSystemEntries(source))
        {
            if (!RegularPath(entry)) continue;
            string destination = Path.Combine(target, Path.GetFileName(entry));
            if (Directory.Exists(entry)) CopyMissingTree(entry, destination);
            else if (!File.Exists(destination) && !Directory.Exists(destination)) File.Copy(entry, destination, false);
        }
    }

    private static void CopyMissingFile(string source, string target)
    {
        if (!File.Exists(source) || !RegularPath(source) || File.Exists(target) || Directory.Exists(target)) return;
        string parent = Path.GetDirectoryName(target);
        if (Directory.Exists(parent) && !RegularPath(parent)) throw new IOException("Dossier personnel redirigé : copie interrompue.");
        Directory.CreateDirectory(parent); File.Copy(source, target, false);
    }

    // Called once for a new full bundle. Originals and existing destination files stay intact.
    internal static void MigrateUserData(string destination, string parent, IEnumerable<string> running)
    {
        string marker = Path.Combine(destination, ".dataky-user-migration.json");
        if (File.Exists(marker)) return;
        var candidates = new List<string>();
        foreach (string path in Directory.GetDirectories(parent))
            if (!String.Equals(ResolvedDirectory(path), ResolvedDirectory(destination), StringComparison.OrdinalIgnoreCase) && ReadySibling(path, parent)) candidates.Add(path);
        candidates.Sort(delegate(string a, string b) { return Directory.GetLastWriteTimeUtc(b).CompareTo(Directory.GetLastWriteTimeUtc(a)); });
        string previous = null;
        foreach (string active in running) foreach (string candidate in candidates)
            if (String.Equals(ResolvedDirectory(candidate), ResolvedDirectory(active), StringComparison.OrdinalIgnoreCase) && previous == null) previous = candidate;
        if (previous == null && candidates.Count > 0) previous = candidates[0];
        if (previous != null)
        {
            foreach (string relative in new[] { @"editor\projects", @"editor\snapshots", @"editor\artistry", @"editor\local_ai\meshes", @"editor\local_ai\video", "exports" })
                if (NoReparseUnder(previous, Path.Combine(previous, relative)) && NoReparseUnder(destination, Path.Combine(destination, relative))) CopyMissingTree(Path.Combine(previous, relative), Path.Combine(destination, relative));
            foreach (string relative in new[] { @"editor\local_ai\catalog.json", @"tool\grid_overrides.json" })
                if (NoReparseUnder(previous, Path.Combine(previous, relative)) && NoReparseUnder(destination, Path.Combine(destination, relative))) CopyMissingFile(Path.Combine(previous, relative), Path.Combine(destination, relative));
        }
        File.WriteAllText(marker, Json.Serialize(new { status = "complete", source = previous, completed_at = DateTime.UtcNow.ToString("o") }), new UTF8Encoding(false));
    }

    private void ApplyUpdates(string destination)
    {
        string script = Path.Combine(destination, "tool", "fx_update.py");
        string python = Path.Combine(destination, "_runtime", "python", "python.exe");
        if (!File.Exists(python)) python = Path.Combine(destination, "_runtime", "python", "pythonw.exe");
        if (!File.Exists(script) || !File.Exists(python)) return;
        Status(100, "Vérification des mises à jour…");
        var start = new ProcessStartInfo(python, Quote(script) + " --root " + Quote(destination) + " --apply");
        start.WorkingDirectory = destination; start.UseShellExecute = false; start.CreateNoWindow = true; start.WindowStyle = ProcessWindowStyle.Hidden;
        start.RedirectStandardOutput = true; start.RedirectStandardError = true;
        start.EnvironmentVariables["PYTHONUTF8"] = "1";
        start.EnvironmentVariables.Remove("PYTHONHOME"); start.EnvironmentVariables.Remove("PYTHONPATH");
        var output = new StringBuilder(); var error = new StringBuilder();
        using (var process = new Process())
        {
            process.StartInfo = start;
            process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs line) { if (line.Data != null) lock (output) { if (output.Length < 65536) output.AppendLine(line.Data); } };
            process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs line) { if (line.Data != null) lock (error) { if (error.Length < 65536) error.AppendLine(line.Data); } };
            process.Start(); process.BeginOutputReadLine(); process.BeginErrorReadLine();
            // The helper bounds all network operations. Never kill a transactional apply halfway through.
            process.WaitForExit();
            if (process.ExitCode != 0) WriteStartupLog(destination, "La mise à jour n’a pas été appliquée ; ouverture de la version conservée.");
        }
    }

    private void TryApplyUpdates(string destination)
    {
        try { ApplyUpdates(destination); }
        catch (Exception error) { WriteStartupLog(destination, "Vérification indisponible : " + error.GetType().Name + ". Ouverture de la version installée."); }
    }

    internal static bool ShouldApplyUpdates(string destination, IEnumerable<string> running)
    {
        foreach (string path in running) if (String.Equals(ResolvedDirectory(path), ResolvedDirectory(destination), StringComparison.OrdinalIgnoreCase)) return false;
        return true;
    }

    private static void WriteStartupLog(string destination, string message)
    {
        try { string directory = Path.Combine(destination, "editor", "desktoplogs"); Directory.CreateDirectory(directory); File.AppendAllText(Path.Combine(directory, "demarrage.log"), DateTime.UtcNow.ToString("o") + " " + message + Environment.NewLine, Encoding.UTF8); }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    private void RunPackage()
    {
        string staging = null, installParent = null, bundleId = null;
        try
        {
            string executable = Application.ExecutablePath;
            long offset, size; byte[] digest;
            using (var file = new FileStream(executable, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (file.Length < 64) throw new InvalidDataException("Paquet incomplet.");
                file.Position = file.Length - 64;
                using (var reader = new BinaryReader(file, Encoding.UTF8))
                {
                    if (Encoding.ASCII.GetString(reader.ReadBytes(16)) != Magic) throw new InvalidDataException("Format de paquet invalide.");
                    ulong rawOffset = reader.ReadUInt64(), rawSize = reader.ReadUInt64();
                    if (rawOffset > Int64.MaxValue || rawSize > Int64.MaxValue) throw new InvalidDataException("Taille de paquet invalide.");
                    offset = (long)rawOffset; size = (long)rawSize; digest = reader.ReadBytes(32);
                    if (offset < 1024 || size <= 0 || offset > file.Length - 64 || size != file.Length - 64 - offset || digest.Length != 32)
                        throw new InvalidDataException("Le paquet est tronqué.");
                }
            }
            string payloadHash = Hex(digest); bundleId = payloadHash.Substring(0, 24);
            installParent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DatakyFXStudio", "Standalone");
            Directory.CreateDirectory(installParent);
            string destination = Path.Combine(installParent, bundleId);
            string readyPath = Path.Combine(destination, ".dataky-package-ready");
            using (var extractionLock = new Mutex(false, "Local\\DatakyFX-Package-" + bundleId))
            {
                bool acquired;
                Status(0, "Préparation de l’application…");
                try { acquired = extractionLock.WaitOne(TimeSpan.FromMinutes(10)); }
                catch (AbandonedMutexException) { acquired = true; }
                if (!acquired) throw new IOException("Une autre préparation est encore en cours.");
                try
                {
                    bool ready = File.Exists(readyPath) && File.ReadAllText(readyPath, Encoding.UTF8).Trim() == payloadHash &&
                        File.Exists(Path.Combine(destination, "Dataky FX Studio.exe")) && File.Exists(Path.Combine(destination, "_runtime", "python", "pythonw.exe"));
                    if (!ready)
                    {
                        if (Directory.Exists(destination)) throw new IOException("Le dossier de préparation existe mais semble incomplet. Vos fichiers ont été conservés : " + destination);
                        VerifyPayload(executable, offset, size, payloadHash);
                        staging = Path.Combine(installParent, bundleId + ".tmp-" + Guid.NewGuid().ToString("N").Substring(0, 8));
                        Directory.CreateDirectory(staging);
                        Extract(executable, offset, size, staging);
                        if (!File.Exists(Path.Combine(staging, "Dataky FX Studio.exe")) || !File.Exists(Path.Combine(staging, "tool", "fx_server.py")) || !File.Exists(Path.Combine(staging, "_runtime", "python", "pythonw.exe")))
                            throw new InvalidDataException("Le paquet ne contient pas tous les composants nécessaires.");
                        File.WriteAllText(Path.Combine(staging, ".dataky-package-ready"), payloadHash, new UTF8Encoding(false));
                        Directory.Move(staging, destination); staging = null;
                    }
                }
                finally { extractionLock.ReleaseMutex(); }
            }
            if (!selfTest)
            {
                using (var startup = new Mutex(false, StartupKey(destination)))
                {
                    bool acquired;
                    try { acquired = startup.WaitOne(TimeSpan.FromMinutes(3)); }
                    catch (AbandonedMutexException) { acquired = true; }
                    if (!acquired) throw new IOException("Un autre démarrage est encore en cours. Relancez dans un instant.");
                    try
                    {
                        var running = RunningLibraries();
                        if (ShouldApplyUpdates(destination, running))
                        {
                            try { MigrateUserData(destination, installParent, running); }
                            catch (IOException) { WriteStartupLog(destination, "Certaines données personnelles n’ont pas pu être recopiées ; les originaux sont conservés."); }
                            catch (UnauthorizedAccessException) { WriteStartupLog(destination, "Certaines données personnelles ne sont pas accessibles ; les originaux sont conservés."); }
                            TryApplyUpdates(destination);
                        }
                        Status(100, "Ouverture de l’atelier…");
                        var launch = new ProcessStartInfo(Path.Combine(destination, "Dataky FX Studio.exe"));
                        launch.WorkingDirectory = destination; launch.UseShellExecute = false; launch.CreateNoWindow = true; launch.WindowStyle = ProcessWindowStyle.Hidden;
                        launch.EnvironmentVariables["DATAKY_PACKAGE_PATH"] = executable;
                        launch.EnvironmentVariables["DATAKY_UPDATE_CHECKED"] = "1";
                        Process.Start(launch);
                    }
                    finally { startup.ReleaseMutex(); }
                }
                result = 0; return;
            }
            Status(100, "Ouverture de l’atelier…");
            var start = new ProcessStartInfo(Path.Combine(destination, "Dataky FX Studio.exe"));
            start.WorkingDirectory = destination; start.UseShellExecute = false; start.CreateNoWindow = true;
            if (selfTest)
            {
                if (arguments.Length < 2) throw new ArgumentException("--self-test attend le chemin du rapport.");
                string reportPath = Path.GetFullPath(arguments[1]);
                start.Arguments = "--self-test " + Quote(reportPath);
                using (var child = Process.Start(start))
                {
                    if (!child.WaitForExit(120000)) { child.Kill(); throw new IOException("Le test de démarrage a dépassé son délai."); }
                    if (child.ExitCode != 0 || !File.Exists(reportPath)) throw new IOException("Le lanceur extrait a échoué au test de démarrage.");
                }
                var report = Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(reportPath, Encoding.UTF8));
                report["single_file_package"] = true; report["bundle_id"] = bundleId; report["extracted_root"] = destination;
                report["payload_sha256"] = payloadHash; report["bootstrap_status"] = "ok";
                File.WriteAllText(reportPath, Json.Serialize(report), new UTF8Encoding(false));
            }
            else Process.Start(start);
            result = 0;
        }
        catch (Exception error)
        {
            if (staging != null) TryRemoveStaging(staging, installParent, bundleId);
            if (selfTest && arguments.Length > 1)
            {
                try { string reportPath = Path.GetFullPath(arguments[1]); Directory.CreateDirectory(Path.GetDirectoryName(reportPath)); File.WriteAllText(reportPath, Json.Serialize(new { bootstrap_status = "error", error = error.Message }), new UTF8Encoding(false)); }
                catch (Exception) { }
            }
            else BeginInvoke((MethodInvoker)delegate { MessageBox.Show(this, error.Message, "Dataky FX Studio", MessageBoxButtons.OK, MessageBoxIcon.Error); });
        }
        finally { BeginInvoke((MethodInvoker)delegate { finished = true; Close(); }); }
    }

    private void VerifyPayload(string path, long offset, long size, string expected)
    {
        Status(1, "Vérification du paquet complet…");
        using (var file = new PayloadStream(path, offset, size)) using (var hash = SHA256.Create())
        {
            byte[] buffer = new byte[1024 * 1024]; int count; long processed = 0;
            while ((count = file.Read(buffer, 0, buffer.Length)) > 0)
            { hash.TransformBlock(buffer, 0, count, buffer, 0); processed += count; Status((int)(processed * 8 / size), "Vérification du paquet complet…"); }
            hash.TransformFinalBlock(new byte[0], 0, 0);
            if (Hex(hash.Hash) != expected) throw new InvalidDataException("Le fichier du paquet est endommagé. Aucune application n’a été exécutée.");
        }
    }

    private void Extract(string path, long offset, long size, string destination)
    {
        using (var input = new PayloadStream(path, offset, size)) using (var archive = new ZipArchive(input, ZipArchiveMode.Read))
        {
            if (archive.Entries.Count > 100000) throw new InvalidDataException("Trop de fichiers dans le paquet.");
            long total = 0;
            foreach (var entry in archive.Entries) { total = checked(total + entry.Length); if (total > MaxExpandedBytes) throw new InvalidDataException("Paquet trop volumineux."); }
            var drive = new DriveInfo(Path.GetPathRoot(destination));
            if (drive.AvailableFreeSpace < total + 64L * 1024 * 1024) throw new IOException("Espace disque insuffisant pour préparer l’application.");
            string prefix = Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            long written = 0; byte[] buffer = new byte[1024 * 1024];
            foreach (var entry in archive.Entries)
            {
                string name = entry.FullName.Replace('\\', '/');
                if (name.StartsWith("/") || name.Contains(":") || ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000) throw new InvalidDataException("Chemin de paquet invalide.");
                foreach (string segment in name.Split('/')) if (segment == ".." || segment == ".") throw new InvalidDataException("Chemin de paquet invalide.");
                string target = Path.GetFullPath(Path.Combine(destination, name.Replace('/', Path.DirectorySeparatorChar)));
                if (!target.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) || !names.Add(target)) throw new InvalidDataException("Chemin de paquet ambigu.");
                if (name.EndsWith("/")) { Directory.CreateDirectory(target); continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                using (var source = entry.Open()) using (var output = new FileStream(target, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    int count; long entryBytes = 0;
                    while ((count = source.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        output.Write(buffer, 0, count); entryBytes += count; written += count;
                        if (entryBytes > entry.Length) throw new InvalidDataException("Taille de fichier incohérente.");
                        Status(8 + (int)(written * 90 / Math.Max(1, total)), "Préparation de l’atelier et de son catalogue…");
                    }
                    if (entryBytes != entry.Length) throw new InvalidDataException("Fichier du paquet incomplet.");
                }
            }
        }
    }

    private static void TryRemoveStaging(string path, string parent, string id)
    {
        try
        {
            string full = Path.GetFullPath(path), prefix = Path.GetFullPath(parent).TrimEnd('\\') + "\\";
            if (full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) && Path.GetFileName(full).StartsWith(id + ".tmp-", StringComparison.Ordinal) && Directory.Exists(full)) Directory.Delete(full, true);
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        using (var app = new PortableBootstrap(args)) { Application.Run(app); return app.result; }
    }
}
