#requires -Version 5.1
<#
.SYNOPSIS
Creates and opens the local-only configuration files needed for an authorized
TRINETRA AI / Sentinel camera on Windows.

.DESCRIPTION
This helper deliberately opens Notepad on the operator's own computer. It does
not ask for, transmit, print, validate, or store credentials anywhere except
in the two gitignored local environment files that the backend and local Vite
proxy need at runtime.

Run from a cloned checkout with:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\configure-official-camera.ps1
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendDirectory = Join-Path $repositoryRoot 'TRINETRAAI\backend'
$frontendDirectory = Join-Path $repositoryRoot 'trinetra-ai'
$backendEnv = Join-Path $backendDirectory '.env'
$backendTemplate = Join-Path $backendDirectory '.env.example'
$frontendEnv = Join-Path $frontendDirectory '.env.local'
$frontendTemplate = Join-Path $frontendDirectory '.env.local.example'

function Assert-LocalSecretFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    # Refuse to place a secret in a Git-tracked file. `git check-ignore` alone
    # does not detect a file already in the index, so check both conditions.
    $null = & git -C $repositoryRoot ls-files --error-unmatch -- $RelativePath 2>$null
    $trackedExitCode = $LASTEXITCODE
    if ($trackedExitCode -eq 0) {
        throw "Refusing to open $RelativePath because it is tracked by Git. Update to the current checkout before storing credentials."
    }
    if ($trackedExitCode -ne 1) {
        throw "Could not verify the Git status of $RelativePath. Do not enter credentials until Git is available and the file is ignored."
    }

    $null = & git -C $repositoryRoot check-ignore -q -- $RelativePath 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Refusing to open $RelativePath because Git does not ignore it. Do not enter credentials in a tracked file."
    }
}

function Initialize-LocalConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [Parameter(Mandatory = $true)]
        [string]$Template,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Template -PathType Leaf)) {
        throw "Missing $Label template: $Template"
    }

    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        Write-Host "Using your existing local $Label configuration; it will not be overwritten." -ForegroundColor Yellow
        return $false
    }

    Copy-Item -LiteralPath $Template -Destination $Destination -ErrorAction Stop
    Write-Host "Created local $Label configuration." -ForegroundColor Green
    return $true
}

function Open-NotepadAndWait {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $notepadPath = Join-Path $env:WINDIR 'System32\notepad.exe'
    if (-not (Test-Path -LiteralPath $notepadPath -PathType Leaf)) {
        $notepadPath = 'notepad.exe'
    }

    Write-Host ""
    Write-Host "Opening $Label in Notepad..." -ForegroundColor Cyan
    Write-Host "Save the file, then close Notepad to continue." -ForegroundColor Cyan
    $argument = '"{0}"' -f $FilePath
    $process = Start-Process -FilePath $notepadPath -ArgumentList $argument -PassThru
    $process.WaitForExit()
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is required so this helper can verify that local credential files are ignored.'
}

Write-Host ''
Write-Host 'TRINETRA AI — authorized official camera setup' -ForegroundColor Cyan
Write-Host 'Credentials stay on this computer. Do NOT paste an email, password, URL, or token into chat, Git, or a VITE_ variable.' -ForegroundColor Yellow
Write-Host ''

$backendCreated = Initialize-LocalConfig -Destination $backendEnv -Template $backendTemplate -Label 'backend'
Assert-LocalSecretFile -RelativePath 'TRINETRAAI/backend/.env'
if ($backendCreated) {
    # A failed official connection must stay OFFLINE rather than silently
    # replacing it with a synthetic feed. Preserve existing operator choices.
    $contents = Get-Content -LiteralPath $backendEnv -Raw
    $contents = $contents -replace '(?m)^DEMO_MODE=true\s*$', 'DEMO_MODE=false'
    # Keep real runs separate from any existing demo SQLite database. This is
    # applied only to a newly created file and never overwrites an operator's
    # existing database choice.
    $contents = $contents -replace '(?m)^DATABASE_URL=sqlite:///\./trinetra\.db\s*$', 'DATABASE_URL=sqlite:///./trinetra_official.db'
    # Windows PowerShell's Set-Content -Encoding utf8 writes a BOM on some
    # versions. Keep dotenv parsing portable by explicitly writing UTF-8 with
    # no BOM.
    $utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($backendEnv, $contents, $utf8WithoutBom)
    Write-Host 'Set DEMO_MODE=false in the newly created backend file so a failed official stream is shown honestly.' -ForegroundColor Green
}

Write-Host ''
Write-Host 'In the backend Notepad file, enter your approved official account only on these two lines:' -ForegroundColor Cyan
Write-Host '  SENTINEL_EMAIL=' -ForegroundColor White
Write-Host '  SENTINEL_PASSWORD=' -ForegroundColor White
Write-Host 'For a separately issued single-camera RTSP/HLS/WHEP source, use the commented LIVE_CAMERA_* fields in this same file. Do not put a private URL in the browser configuration.' -ForegroundColor DarkGray
Open-NotepadAndWait -FilePath $backendEnv -Label 'backend .env'

$frontendCreated = Initialize-LocalConfig -Destination $frontendEnv -Template $frontendTemplate -Label 'frontend proxy'
Assert-LocalSecretFile -RelativePath 'trinetra-ai/.env.local'

Write-Host ''
Write-Host 'In the frontend Notepad file, enter the same approved email and access password on the non-VITE_ SENTINEL_* lines.' -ForegroundColor Cyan
Write-Host 'Leave BACKEND_ORIGIN as http://127.0.0.1:8000 unless your backend uses another local port.' -ForegroundColor DarkGray
Write-Host 'Never create VITE_SENTINEL_EMAIL or VITE_SENTINEL_PASSWORD: VITE_ values are public in the browser bundle.' -ForegroundColor Yellow
Open-NotepadAndWait -FilePath $frontendEnv -Label 'frontend .env.local'

Write-Host ''
Write-Host 'Local configuration is complete. Restart both services after editing either file.' -ForegroundColor Green
Write-Host ''
Write-Host 'Terminal 1 — backend:' -ForegroundColor Cyan
Write-Host ("  cd `"{0}`"" -f $backendDirectory)
Write-Host '  py -3.12 -m venv .venv'
Write-Host '  .\.venv\Scripts\python.exe -m pip install -r requirements.txt'
Write-Host '  .\.venv\Scripts\python.exe -m scripts.seed_demo'
Write-Host '  .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000'
Write-Host ''
Write-Host 'Terminal 2 — frontend:' -ForegroundColor Cyan
Write-Host ("  cd `"{0}`"" -f $frontendDirectory)
Write-Host '  npm ci'
Write-Host '  npm run dev'
Write-Host ''
Write-Host 'Then open http://localhost:5173 and choose an authorized camera. This helper cannot grant access; the account and network must already be approved by the camera operator.' -ForegroundColor Yellow
