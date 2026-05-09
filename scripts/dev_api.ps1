# scripts/dev_api.ps1 — FastAPI 開発サーバーを起動する (Phase 8)
# 使用方法: .\scripts\dev_api.ps1

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

Write-Host "[INFO] FastAPI 起動中 (http://127.0.0.1:8000) ..."
Write-Host "[INFO] API ドキュメント: http://127.0.0.1:8000/docs"
Write-Host "[INFO] ヘルスチェック:  http://127.0.0.1:8000/health"
Write-Host "[INFO] 準備状態確認:   http://127.0.0.1:8000/ready"
Write-Host "[INFO] Ctrl+C で停止"
Write-Host ""

uvicorn server.app:app --host 127.0.0.1 --port 8000 --reload
