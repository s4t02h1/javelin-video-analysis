# 可視化プラグイン開発ガイド

このドキュメントは `jva_visuals` に新しい可視化パス（エフェクト）を追加するための最小ガイドです。

## 作成手順（最小）
1. `jva_visuals/` にファイルを追加（例: `my_effect.py`）。
2. 既存のパスを参考にクラスを定義（`apply(frame, state, fps, height_m)` を実装）。
3. `registry.py` に登録処理を追加し、YAML もしくは CLI から有効化できるようにする。

## 入力/出力の約束
- 入力: 
  - `frame`: BGR (H, W, 3) np.ndarray
  - `state`: `PoseAnalyzer` が生成する辞書（`points` など）
- 出力: 加工後の `frame` を返却
- 例外: 落ちても致命的にはしない方針（内部で握りつぶす or ログ出力）

## 参考
- `jva_visuals/vectors.py`
- `jva_visuals/heatmap.py`
