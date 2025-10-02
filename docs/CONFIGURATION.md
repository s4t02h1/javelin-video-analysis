# 設定オプション完全リファレンス

本ドキュメントは `--config` で与える YAML の主なキーをまとめたものです。

```yaml
height_m: 1.80  # 被写体の身長（m）
visuals:
  vectors:
    enabled: true
  heatmap:
    enabled: true
    show_colorbar: true
  hud:
    enabled: true
  trails:
    enabled: true
    right_wrist: true
output:
  export_landmarks: true
  landmarks_filename: output/landmarks.json
blender:
  enabled: false
backend:
  use_tasks: false  # MediaPipe Tasks を使う場合は true
```

補足:
- それぞれのキーは未指定でも動作します（既定値あり）。
- `backend.use_tasks` は将来的に MediaPipe Tasks を導入する際の切替フラグです。
