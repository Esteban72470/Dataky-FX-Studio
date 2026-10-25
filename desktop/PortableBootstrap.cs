// Single-file package bootstrap: appended ZIP + a 64-byte footer. No installer or network download.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

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
