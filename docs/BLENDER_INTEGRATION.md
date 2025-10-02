# Blender 連携チュートリアル

本プロジェクトで出力したランドマーク JSON と動画を Blender に読み込み、3D 合成を行う手順です。

## 前提
- Blender をローカルにインストール済み
- `blender_bridge/scripts/` がパスとして参照可能

## コマンド例
README の実行後に、以下のようなコマンドを表示しています。

```bash
blender --background --python blender_bridge/scripts/setup_scene.py -- \
  --video output/analysis_*.mp4 \
  --landmarks output/landmarks.json \
  --output output/3d_overlay.mp4
```

## トラブルシュート
- `bpy` が見つからない: Blender の Python から実行する必要があります。
- 出力が真っ黒: `setup_scene.py` のカメラ/ライト設定を確認してください。
