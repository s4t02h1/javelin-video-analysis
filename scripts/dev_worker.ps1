# scripts/dev_worker.ps1 — バックグラウンドワーカーを起動する (Phase 8)
# 使用方法: .\scripts\dev_worker.ps1

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# .env が存在すれば読み込む
if (Test-Path ".env") {
    Get-Content ".env" | Where-Object { $_ -match "^[A-Z_]+=.*" -and $_ -notmatch "^#" } | ForEach-Object {
        $k, $v = $_ -split "=", 2
        [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
    }
    Write-Host "[INFO] .env を読み込みました。"
}

$PollInterval = if ($env:JVA_WORKER_POLL_INTERVAL_SECONDS) { $env:JVA_WORKER_POLL_INTERVAL_SECONDS } else { "5" }

Write-Host "[INFO] ワーカー起動中 (poll-interval=${PollInterval}秒) ..."
Write-Host "[INFO] Ctrl+C で停止"
Write-Host ""

python worker.py --poll-interval $PollInterval
