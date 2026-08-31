#Requires -Version 5.1
<#
    Windows/PowerShell port of scripts/demo.sh.
    Kept behaviourally identical to the bash version; see that file for the
    canonical reference if the two drift. Two Windows-only additions:
    PYTHONUTF8=1 and `uv run --with tzdata` (see the project's Windows
    run-recipe notes) are required on every `uv run python ...` invocation
    here that the bash version does not need on macOS/Linux.
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet('serve', 'check', 'help')]
    [string]$Mode = 'serve'
)

$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

if ($Mode -eq 'help') {
    Write-Host "用法：scripts\demo.ps1 [check|serve]"
    Write-Host "正常 demo：FurKids 5、新店犬最多 60、五股犬最多 60；不建立 ORG-A／ORG-B。"
    Write-Host "check 只 bootstrap/驗證；serve（預設）另啟動 FastAPI／Next.js／Worker。"
    Write-Host "舊 fixtures 請先預覽：uv run python -m scripts.cleanup_legacy_demo_fixtures；--yes 才刪除。"
    Write-Host "測試 fixtures 請使用獨立 DB：uv run python -m scripts.seed_test_fixtures"
    exit 0
}

$env:PYTHONUTF8 = '1'

if (-not $env:UV_CACHE_DIR) { $env:UV_CACHE_DIR = Join-Path $env:TEMP 'strayhub-uv-cache' }
if (-not $env:DATABASE_URL) { $env:DATABASE_URL = 'postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/strayhub' }
if (-not $env:STRAYHUB_TEST_DATABASE_URL) { $env:STRAYHUB_TEST_DATABASE_URL = 'postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub' }
if (-not $env:API_HOST) { $env:API_HOST = '127.0.0.1' }
if (-not $env:API_PORT) { $env:API_PORT = '8001' }
if (-not $env:API_BASE_URL) { $env:API_BASE_URL = "http://$($env:API_HOST):$($env:API_PORT)" }
if (-not $env:WEB_HOST) { $env:WEB_HOST = '127.0.0.1' }
if (-not $env:WEB_PORT) { $env:WEB_PORT = '3001' }

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Error "缺少必要命令：$Name"
        exit 1
    }
}

function Require-PortAvailable {
    param([string]$Label, [int]$Port)
    $listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listening) {
        Write-Error "$Label port $Port 已被使用，請先停止舊服務後再執行 demo.ps1。"
        exit 1
    }
}

function Invoke-Checked {
    # PowerShell's $ErrorActionPreference = 'Stop' only converts terminating
    # *cmdlet* errors -- a native command (uv/docker/npm/alembic/...) that
    # exits non-zero does NOT throw and execution just continues, unlike
    # bash's `set -e`. Every step here that a real failure must abort on
    # goes through this wrapper instead of a bare native-command call.
    param([string]$FilePath, [string[]]$ArgumentList)
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        Write-Error "指令失敗（結束碼 $LASTEXITCODE）：$FilePath $($ArgumentList -join ' ')"
        exit 1
    }
}

Require-Command 'uv'
Require-Command 'npm'

# Check .env-aware settings before migrations, grants, data or storage writes.
Invoke-Checked 'uv' @('run', '--with', 'tzdata', 'python', '-m', 'scripts.local_demo')

if (-not $env:AUTH_JWT_ACTIVE_PRIVATE_KEY -or -not $env:AUTH_JWT_ACTIVE_PUBLIC_KEY) {
    Require-Command 'openssl'
    $keyDir = Join-Path $env:TEMP ([System.Guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $keyDir | Out-Null
    try {
        $privatePath = Join-Path $keyDir 'private.pem'
        $publicPath = Join-Path $keyDir 'public.pem'
        # Only stdout is redirected here, deliberately: redirecting a native
        # command's stderr in Windows PowerShell 5.1 (e.g. `*>`, `2>&1`)
        # wraps every stderr line in a NativeCommandError and fails the
        # command even on exit code 0 -- openssl's progress dots go to
        # stderr, so touching that stream would trip $ErrorActionPreference.
        openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out $privatePath 1> $null
        if ($LASTEXITCODE -ne 0) { throw "openssl genpkey failed (exit $LASTEXITCODE)" }
        openssl pkey -in $privatePath -pubout -out $publicPath 1> $null
        if ($LASTEXITCODE -ne 0) { throw "openssl pkey failed (exit $LASTEXITCODE)" }
        $env:AUTH_JWT_ACTIVE_PRIVATE_KEY = (Get-Content -Raw $privatePath).TrimEnd()
        $env:AUTH_JWT_ACTIVE_PUBLIC_KEY = (Get-Content -Raw $publicPath).TrimEnd()
    }
    finally {
        Remove-Item -Recurse -Force $keyDir
    }
}

$env:PII_ALLOW_LOCAL_PROVIDER = 'true'
if (-not $env:PII_LOCAL_KEY_BASE64) {
    Require-Command 'openssl'
    $env:PII_LOCAL_KEY_BASE64 = (openssl rand -base64 32).Trim()
    if ($LASTEXITCODE -ne 0) { Write-Error "openssl rand failed (exit $LASTEXITCODE)"; exit 1 }
}

if ($env:DEMO_SKIP_DOCKER -ne '1') {
    Require-Command 'docker'
    Invoke-Checked 'docker' @('compose', '-f', 'infra/local/docker-compose.yml', 'up', '-d', 'postgres', 'minio')
}

Write-Host '[Demo] Migration'
Invoke-Checked 'uv' @('run', '--with', 'tzdata', 'alembic', 'upgrade', 'head')
Invoke-Checked 'uv' @('run', '--with', 'tzdata', 'python', '-m', 'scripts.configure_runtime_role', '--apply')

Write-Host '[Demo] Three-shelter data bootstrap (no test fixtures)'
Invoke-Checked 'uv' @('run', '--with', 'tzdata', 'python', '-m', 'scripts.bootstrap_demo')

Write-Host '[Demo] PASS'
Write-Host 'Three-shelter manager: demo-furkids-admin / local-only-password'
Write-Host 'Platform: demo-platform-admin / local-only-password'
Write-Host 'FurKids volunteer: demo-furkids-volunteer / local-only-password'
Write-Host 'Xindian volunteer: demo-xindian-volunteer / local-only-password'
Write-Host 'Wugu volunteer: demo-wugu-volunteer / local-only-password'
Write-Host "API:          http://$($env:API_HOST):$($env:API_PORT)/healthz"
Write-Host "Web:          http://$($env:WEB_HOST):$($env:WEB_PORT)"

if ($Mode -eq 'check') {
    exit 0
}

Require-PortAvailable 'API' ([int]$env:API_PORT)
Require-PortAvailable 'Web' ([int]$env:WEB_PORT)

function Stop-ProcessTree {
    # npm on Windows is npm.cmd, not a real Win32 executable, so it has to be
    # launched through cmd.exe /c -- Start-Process calls CreateProcess
    # directly (no PATHEXT/shell resolution like typing `npm ...` at a
    # prompt does) and fails with "%1 is not a valid Win32 application" on a
    # bare .cmd file. That means the PID we track back is cmd.exe's, not the
    # actual node.exe it spawns, so a plain Stop-Process on it would orphan
    # the real dev server. Kill the whole subtree instead.
    param([int]$ProcessId)
    Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-ProcessTree -ProcessId $_.ProcessId }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

$processes = @()
try {
    Write-Host '[Demo] Starting FastAPI／Next.js／Worker; press Ctrl-C to stop'
    $processes += Start-Process -FilePath 'uv' -ArgumentList @(
        'run', '--with', 'tzdata', 'python', '-m', 'uvicorn',
        'services.api.app.main:app', '--host', $env:API_HOST, '--port', $env:API_PORT
    ) -NoNewWindow -PassThru
    $processes += Start-Process -FilePath "$env:ComSpec" -ArgumentList @(
        '/c', 'npm', '--prefix', 'apps/web', 'run', 'dev', '--',
        '--hostname', $env:WEB_HOST, '--port', $env:WEB_PORT
    ) -NoNewWindow -PassThru
    $processes += Start-Process -FilePath 'uv' -ArgumentList @(
        'run', '--with', 'tzdata', 'python', '-m', 'services.worker.worker'
    ) -NoNewWindow -PassThru

    Wait-Process -Id ($processes | Select-Object -ExpandProperty Id)
}
finally {
    foreach ($p in $processes) {
        if (-not $p.HasExited) {
            Stop-ProcessTree -ProcessId $p.Id
        }
    }
}
