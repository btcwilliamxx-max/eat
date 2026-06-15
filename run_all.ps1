# run_all.ps1
# Meal-allowance toolchain: 3-step runner
# 1. 隐藏地址_v2.py        generate announcement txt
# 2. rename_screenshots.py  AI-rename screenshots in G:\餐补\screenshots\_inbox
# 3. build_index.py         rebuild searchable index.html
#
# Prereqs:
#   1. Python 3.8+ in PATH
#   2. mavis.cmd available (used by rename_screenshots.py)
#   3. This script sits in C:\Users\92071\Desktop\餐补\
#   4. Screenshot repo G:\餐补\screenshots\ exists with _inbox\ and by_date\

$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null
$root = $PSScriptRoot
Set-Location $root

# Force Python stdout/stderr to UTF-8 so emojis and Chinese print cleanly
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# ============================================================
# 0. Pre-flight checks
# ============================================================
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Meal-allowance toolchain runner" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# python check
try {
    $pyVer = python --version 2>&1
    Write-Host "[OK]  Python: $pyVer" -ForegroundColor Green
} catch {
    Write-Host "[X]   python not found. Install Python 3.8+ and add to PATH." -ForegroundColor Red
    pause; exit 1
}

# mavis.cmd check
try {
    $null = mavis.cmd --version 2>&1
    Write-Host "[OK]  mavis.cmd reachable" -ForegroundColor Green
} catch {
    Write-Host "[X]   mavis.cmd not found (rename_screenshots.py needs it)" -ForegroundColor Red
    Write-Host "    Expected: C:\Users\92071\.mavis\bin\mavis.cmd" -ForegroundColor Yellow
    pause; exit 1
}

# files check - find by glob pattern via cmd dir to avoid GBK decoding
$expected = @('gen_announce', 'rename_screenshots', 'build_index')
$pyFiles = Get-ChildItem $root -File -Filter '*.py' | Select-Object -ExpandProperty Name
foreach ($base in $expected) {
    $hit = $pyFiles | Where-Object { $_ -like "$base*" }
    if (-not $hit) {
        Write-Host "[X]   missing file: $base*.py" -ForegroundColor Red
        pause; exit 1
    }
}
Write-Host "[OK]  all 3 scripts present" -ForegroundColor Green

# screenshot repo check - build path with [char[]] to avoid PS5.1 GBK decoding of Chinese literals
$shotChars = @('G', ':', '\', ([char]0x9910), ([char]0x8865), '\', 's', 'c', 'r', 'e', 'e', 'n', 's', 'h', 'o', 't', 's')
$shotRoot = -join $shotChars
if (-not [System.IO.Directory]::Exists($shotRoot)) {
    Write-Host "[X]   screenshot repo not found: $shotRoot" -ForegroundColor Red
    pause; exit 1
}
Write-Host "[OK]  screenshot repo: $shotRoot" -ForegroundColor Green
Write-Host ""

# ============================================================
# 1. Generate announcement txt
# ============================================================
Write-Host "[1/3]  Generating announcement txt" -ForegroundColor Cyan
Write-Host "       (you will be asked to pick an Excel and confirm y/n)" -ForegroundColor Yellow
Write-Host ""
python -X utf8 ".\gen_announce.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X]   announcement generation failed" -ForegroundColor Red
    pause; exit 1
}
Write-Host ""
Write-Host "[OK]  announcement done" -ForegroundColor Green
Write-Host ""

# ============================================================
# 2. Rename + archive screenshots
# ============================================================
Write-Host "[2/3]  Renaming + archiving screenshots" -ForegroundColor Cyan
Write-Host "       (scans G:\餐补\screenshots\_inbox\)" -ForegroundColor Yellow
Write-Host ""
$inboxPath = [System.IO.Path]::Combine($shotRoot, '_inbox')
$inboxFiles = @(Get-ChildItem $inboxPath -File -ErrorAction SilentlyContinue)
if ($inboxFiles.Count -eq 0) {
    Write-Host "[!]   _inbox is empty, skipping rename" -ForegroundColor Yellow
} else {
    Write-Host "       found $($inboxFiles.Count) screenshot(s) to process" -ForegroundColor Yellow
    python -X utf8 ".\rename_screenshots.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X]   rename failed" -ForegroundColor Red
        pause; exit 1
    }
}
Write-Host ""
Write-Host "[OK]  rename done" -ForegroundColor Green
Write-Host ""

# ============================================================
# 3. Rebuild search index
# ============================================================
Write-Host "[3/3]  Rebuilding search index" -ForegroundColor Cyan
Write-Host ""
python -X utf8 ".\build_index.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X]   index rebuild failed" -ForegroundColor Red
    pause; exit 1
}
Write-Host ""
Write-Host "[OK]  all done" -ForegroundColor Green
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Browser should open index.html automatically." -ForegroundColor Cyan
Write-Host "  In the search box type: address prefix / amount / nick / date" -ForegroundColor Cyan
Write-Host "  Click \"screenshot\" link on the right to open the receipt." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
pause
