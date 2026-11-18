# Generate thumbnails for course word images.
#
# Originals are usually 1024px wide (largest 3061px) but the card only shows
# 148px tall, so fetching full images means ~16MB per chapter and frequent
# timeouts. This script shrinks them to a 480px long edge at JPEG quality 80,
# which cuts the total size to roughly a quarter.
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts/gen-thumbs.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/gen-thumbs.ps1 -Course EnglishWord -LongEdge 480 -Quality 80
#
# Idempotent: existing thumbnails that are not older than the source are
# skipped, so re-running only handles new or changed images.
#
# NOTE: keep this file ASCII-only. PowerShell 5.1 decodes BOM-less .ps1 as
# ANSI, which mangles any non-ASCII text.

param(
    [string] $Course = 'EnglishWord',
    [int] $LongEdge = 480,
    [int] $Quality = 80
)

Add-Type -AssemblyName System.Drawing

$srcDir = Join-Path $PSScriptRoot "..\openEDU\$Course\content"
if (-not (Test-Path $srcDir)) {
    Write-Output "Directory not found: $srcDir"
    exit 1
}
$dstDir = Join-Path $srcDir 'thumb'
New-Item -ItemType Directory -Force -Path $dstDir | Out-Null

$jpegCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
    Where-Object { $_.MimeType -eq 'image/jpeg' } | Select-Object -First 1

$files = Get-ChildItem -LiteralPath $srcDir -File -Filter *.jpg
$srcTotalMB = [math]::Round((($files | Measure-Object Length -Sum).Sum) / 1MB, 2)

Write-Output "Course : $Course"
Write-Output "Source : $($files.Count) images, $srcTotalMB MB"
Write-Output "Output : $dstDir (long edge $LongEdge px, quality $Quality)"
Write-Output ''

$done = 0
$skipped = 0
$failed = 0
$srcBytes = 0
$dstBytes = 0

foreach ($f in $files) {
    $srcBytes += $f.Length
    $out = Join-Path $dstDir $f.Name

    # Already generated and source not newer -> skip
    if ((Test-Path $out) -and ((Get-Item $out).LastWriteTime -ge $f.LastWriteTime)) {
        $skipped++
        $dstBytes += (Get-Item $out).Length
        continue
    }

    $img = $null
    $fs = $null
    try {
        # Read via stream so the source file is not locked for the whole run
        $fs = [System.IO.File]::Open($f.FullName, 'Open', 'Read', 'Read')
        $img = [System.Drawing.Image]::FromStream($fs)

        $w = $img.Width
        $h = $img.Height
        $scale = [double]$LongEdge / [Math]::Max($w, $h)
        if ($scale -ge 1) { $scale = 1 }   # never upscale
        $nw = [int][Math]::Round($w * $scale)
        $nh = [int][Math]::Round($h * $scale)

        $bmp = New-Object System.Drawing.Bitmap $nw, $nh
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $g.DrawImage($img, 0, 0, $nw, $nh)
        $g.Dispose()

        $ep = New-Object System.Drawing.Imaging.EncoderParameters 1
        $qualParam = New-Object System.Drawing.Imaging.EncoderParameter(
            [System.Drawing.Imaging.Encoder]::Quality, [long]$Quality)
        $ep.Param[0] = $qualParam
        $bmp.Save($out, $jpegCodec, $ep)

        $ep.Dispose()
        $bmp.Dispose()
        $img.Dispose()
        $img = $null
        $fs.Close()
        $fs = $null

        $done++
        $dstBytes += (Get-Item $out).Length
        if ($done % 100 -eq 0) { Write-Output "  processed $done / $($files.Count) ..." }
    }
    catch {
        $failed++
        Write-Output "  FAILED: $($f.Name) -- $($_.Exception.Message)"
        try { if ($img -ne $null) { $img.Dispose() } } catch {}
        try { if ($fs -ne $null) { $fs.Close() } } catch {}
    }
}

Write-Output ''
Write-Output '=== done ==='
Write-Output "  generated: $done   skipped: $skipped   failed: $failed"
$dstTotalMB = [math]::Round($dstBytes / 1MB, 2)
Write-Output "  thumbnails total: $dstTotalMB MB"
if ($srcBytes -gt 0) {
    $pct = [math]::Round(100 * $dstBytes / $srcBytes, 1)
    Write-Output "  share of original: $pct%"
}
