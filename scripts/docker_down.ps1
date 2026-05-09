# scripts/docker_down.ps1 — Docker Compose でサービスを停止する (Phase 8)
# 使用方法: .\scripts\docker_down.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "[INFO] サービスを停止しています..."
docker compose down

Write-Host "[INFO] 停止完了。データ・ログは保持されています。"
Write-Host "[INFO] ボリュームごと削除する場合: docker compose down -v"
