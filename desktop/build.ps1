param([string]$OutputDirectory = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe' }
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Compilateur .NET Framework absent.' }
Add-Type -AssemblyName System.Drawing
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
[IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
$bitmap = New-Object Drawing.Bitmap 64,64
$graphics = [Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.Clear([Drawing.Color]::FromArgb(29,24,37))
$font = New-Object Drawing.Font 'Arial',44,([Drawing.FontStyle]::Bold),([Drawing.GraphicsUnit]::Pixel)
$brush = New-Object Drawing.SolidBrush ([Drawing.Color]::FromArgb(177,146,233))
$graphics.DrawString('D',$font,$brush,7,4)
$brush.Color = [Drawing.Color]::FromArgb(116,234,224)
$graphics.FillEllipse($brush,44,5,12,12)
$iconPath = Join-Path $PSScriptRoot 'DatakyFXStudio.ico'
$handle = $bitmap.GetHicon()
$icon = [Drawing.Icon]::FromHandle($handle)
$stream = [IO.File]::Create($iconPath)
try { $icon.Save($stream) } finally { $stream.Dispose(); $graphics.Dispose(); $brush.Dispose(); $font.Dispose(); $bitmap.Dispose() }
$target = Join-Path $OutputDirectory 'Dataky FX Studio.exe'
& $compiler /nologo /target:winexe /optimize+ /platform:anycpu /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll "/win32icon:$iconPath" "/out:$target" (Join-Path $PSScriptRoot 'DatakyFXStudio.cs')
if ($LASTEXITCODE -ne 0) { throw 'La compilation a échoué.' }
Write-Output $target
