# scripts/dev_admin.ps1 — Streamlit 管理画面を起動する (Phase 8)
# 使用方法: .\scripts\dev_admin.ps1

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

Write-Host "[INFO] Streamlit 管理画面起動中 (http://127.0.0.1:8501) ..."
Write-Host "[INFO] Ctrl+C で停止"
Write-Host ""

streamlit run admin_app.py --server.address=127.0.0.1 --server.port=8501
