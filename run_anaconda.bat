@echo off
REM javelin-video-analysis - MediaPipe対応版実行スクリプト
REM Anaconda Python 3.8環境で実際のMediaPipeポーズ検出を使用

echo ========================================================
echo Javelin Video Analysis - Real MediaPipe Pose Detection
echo ========================================================

REM Python環境情報を表示
py -V:ContinuumAnalytics/Anaconda38-64 --version
echo MediaPipe Version: 0.10.10 (with DLL fix)

echo.
echo 🎯 使用例:
echo   run_anaconda.bat --video input.mp4 --output output.mp4
echo   run_anaconda.bat --video input.mp4 --output output.mp4 --vectors --heatmap --hud
echo   run_anaconda.bat --video aisa_javelin1.mp4 --output result.mp4 --vectors --heatmap --hud --wrist-trail --height-m 1.75
echo.
echo ⚠️ 注意: 長い動画では処理に時間がかかります。Ctrl+Cで中断しないでください。
echo 📊 進行状況は30フレームごとに表示されます。
echo.

REM 引数をAnaconda Python環境に渡して実行（MediaPipe DLL修復付き）
py -V:ContinuumAnalytics/Anaconda38-64 run.py %*