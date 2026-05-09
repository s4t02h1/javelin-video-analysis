# scripts/docker_up.ps1 — Docker Compose でサービスを起動する (Phase 8)
# 使用方法: .\scripts\docker_up.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# .env が存在しない場合は .env.example からコピー
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[INFO] .env.example から .env を作成しました。必要に応じて編集してください。"
    } else {
        Write-Warning ".env ファイルが見つかりません。先に .env を作成してください。"
        exit 1
    }
}

# データディレクトリの作成
foreach ($d in @("data", "data/queue", "outputs", "logs", "uploads")) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        Write-Host "[INFO] ディレクトリを作成しました: $d"
    }
}

Write-Host "[INFO] Docker イメージをビルドしています..."
docker compose build

Write-Host "[INFO] サービスを起動しています..."
docker compose up -d

Write-Host ""
Write-Host "=============================="
Write-Host "  起動完了"
Write-Host "=============================="
Write-Host "  API:    http://localhost:8000"
Write-Host "  管理画面: http://localhost:8501"
Write-Host "  ヘルス: http://localhost:8000/health"
Write-Host "  停止:   .\scripts\docker_down.ps1"
Write-Host "=============================="
