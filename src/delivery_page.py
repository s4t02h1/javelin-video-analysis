"""
src/delivery_page.py — Javelin Video Analysis スマホ向け納品HTMLページ生成

presigned URL をもとに、スマホ・PC両対応の1ファイル完結HTMLを生成する。

使用方法:
    from src.delivery_page import generate_delivery_page, save_delivery_page
    from pathlib import Path

    html = generate_delivery_page(
        manifest=manifest,             # artifact_manifest.py が生成した manifest dict
        customer_info={"name": "田中選手", "coach": "佐藤コーチ"},
        job_id="20260508_054525_147f",
        presigned_urls={"jobs/.../reports/report.pdf": "https://..."},
        expires_at="2026-05-15T10:00:00+09:00",
        job_label="20260508_054525",
    )
    path = save_delivery_page(Path("jobs/20260508_054525_147f/report"), html)
"""

from __future__ import annotations

import html as _html_escape
from datetime import datetime
from pathlib import Path
from typing import Optional


def generate_delivery_page(
    manifest: dict,
    customer_info: Optional[dict] = None,
    job_id: str = "",
    presigned_urls: Optional[dict[str, str]] = None,
    expires_at: str = "",
    job_label: str = "",
    site_title: str = "解析結果のお届け",
) -> str:
    """スマホ対応の1ファイル完結 HTML を生成して返す。

    Parameters
    ----------
    manifest : dict
        artifact_manifest.py の build_artifact_manifest() 出力
    customer_info : dict, optional
        {"name": str, "coach": str, "event": str} 等
    job_id : str
        ジョブID（表示用）
    presigned_urls : dict[str, str], optional
        s3_key → presigned URL のマッピング
    expires_at : str
        URL 有効期限（ISO 8601 文字列）
    job_label : str
        表示用ジョブラベル（省略時は job_id を使用）
    site_title : str
        ページタイトル
    """
    customer_info = customer_info or {}
    presigned_urls = presigned_urls or {}
    artifacts = manifest.get("artifacts", [])
    display_label = _e(job_label or job_id)

    # ── 有効期限の表示文字列 ─────────────────────────────────────────────────
    expires_display = _format_expires(expires_at)

    # ── カテゴリ別に整理 ─────────────────────────────────────────────────────
    categories: dict[str, list[dict]] = {}
    for a in artifacts:
        cat = a.get("category", "その他")
        categories.setdefault(cat, []).append(a)

    # ── カテゴリアイコン ─────────────────────────────────────────────────────
    _cat_icon = {
        "最初に読む資料":   "📋",
        "解析動画":         "🎬",
        "選手向け資料":     "📊",
        "フェーズ別資料":   "🔍",
        "グラフ":           "📈",
        "代表フレーム画像": "🖼️",
        "比較資料":         "⚖️",
        "研究・開発用データ": "🔬",
        "納品ZIP":          "📦",
        "納品ページ":       "🌐",
    }

    # ── ヘッダー情報 ─────────────────────────────────────────────────────────
    athlete_name = _e(customer_info.get("customer_name") or customer_info.get("nickname") or "")
    coach_name   = _e(customer_info.get("coach", ""))
    event_name   = _e(customer_info.get("event", ""))
    header_items = []
    if athlete_name:
        header_items.append(f"<span class='badge'>🏃 {athlete_name}</span>")
    if coach_name:
        header_items.append(f"<span class='badge'>👤 {coach_name} コーチ</span>")
    if event_name:
        header_items.append(f"<span class='badge'>🏟️ {event_name}</span>")
    header_info = "\n".join(header_items)

    # ── セクションHTML生成 ─────────────────────────────────────────────────────
    section_htmls: list[str] = []
    all_zip_links: list[str] = []

    for cat, items in categories.items():
        icon = _cat_icon.get(cat, "📄")
        items_html: list[str] = []

        for a in items:
            s3_key = a.get("s3_key", "")
            url = presigned_urls.get(s3_key, "")
            label = _e(a.get("label", ""))
            exists = a.get("exists", False)
            ct = a.get("content_type", "")

            if not url:
                items_html.append(
                    f"""<div class="file-item unavailable">
                      <span class="file-icon">{_file_icon(ct)}</span>
                      <span class="file-label">{label}</span>
                      <span class="file-status">{"（ファイルなし）" if not exists else "（URLなし）"}</span>
                    </div>"""
                )
                continue

            # ボタンスタイルと開き方を決定
            btn_class, btn_text, target = _button_style(cat, ct)

            item_html = (
                f"""<a href="{url}" target="{target}" rel="noopener noreferrer"
                      class="file-link {btn_class}">
                  <span class="file-icon">{_file_icon(ct)}</span>
                  <span class="file-label">{label}</span>
                  <span class="file-action">{btn_text}</span>
                </a>"""
            )
            items_html.append(item_html)

            # ZIP は一括ダウンロードセクションにも追加
            if ct == "application/zip":
                all_zip_links.append((label, url))

        if items_html:
            section_htmls.append(
                f"""<section class="category-section">
                  <h2 class="category-title">{icon} {_e(cat)}</h2>
                  <div class="file-list">
                    {"".join(items_html)}
                  </div>
                </section>"""
            )

    # ── 一括ダウンロードセクション ────────────────────────────────────────────
    bulk_section = ""
    if all_zip_links:
        bulk_items = "\n".join(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer" class="file-link btn-zip">'
            f'<span class="file-icon">📥</span><span class="file-label">{label}</span>'
            f'<span class="file-action">ダウンロード</span></a>'
            for label, url in all_zip_links
        )
        bulk_section = f"""<section class="category-section bulk-download">
          <h2 class="category-title">📥 一括ダウンロード</h2>
          <p class="section-note">ZIP ファイルをまとめてダウンロードできます。</p>
          <div class="file-list">{bulk_items}</div>
        </section>"""

    # ── フッター ──────────────────────────────────────────────────────────────
    generated_at = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex,nofollow">
  <title>{_e(site_title)} — {display_label}</title>
  <style>
    /* ── Reset & Base ─────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ font-size: 16px; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans",
                   "Noto Sans JP", sans-serif;
      background: #f4f6f9;
      color: #1a1a2e;
      line-height: 1.6;
      padding-bottom: 3rem;
    }}
    a {{ color: inherit; text-decoration: none; }}

    /* ── Header ───────────────────────────────────────── */
    .site-header {{
      background: linear-gradient(135deg, #1e3a5f, #2563eb);
      color: #fff;
      padding: 1.5rem 1rem 2rem;
      text-align: center;
    }}
    .site-header h1 {{
      font-size: clamp(1.2rem, 4vw, 1.8rem);
      font-weight: 700;
      margin-bottom: 0.4rem;
      letter-spacing: 0.02em;
    }}
    .site-header .subtitle {{
      font-size: 0.9rem;
      opacity: 0.85;
      margin-bottom: 0.8rem;
    }}
    .badge {{
      display: inline-block;
      background: rgba(255,255,255,0.2);
      border-radius: 20px;
      padding: 0.2rem 0.7rem;
      font-size: 0.85rem;
      margin: 0.15rem;
    }}
    .expiry-banner {{
      background: #fff3cd;
      color: #856404;
      border: 1px solid #ffc107;
      border-radius: 8px;
      padding: 0.6rem 1rem;
      font-size: 0.85rem;
      max-width: 600px;
      margin: 0.8rem auto 0;
    }}

    /* ── Main container ───────────────────────────────── */
    .main {{
      max-width: 720px;
      margin: 0 auto;
      padding: 1rem;
    }}

    /* ── Section ──────────────────────────────────────── */
    .category-section {{
      background: #fff;
      border-radius: 12px;
      padding: 1.25rem 1rem;
      margin-bottom: 1rem;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }}
    .category-title {{
      font-size: 1rem;
      font-weight: 700;
      color: #1e3a5f;
      margin-bottom: 0.75rem;
      padding-bottom: 0.5rem;
      border-bottom: 2px solid #e8edf4;
    }}
    .section-note {{
      font-size: 0.85rem;
      color: #666;
      margin-bottom: 0.7rem;
    }}

    /* ── File list ────────────────────────────────────── */
    .file-list {{
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }}
    .file-link, .file-item {{
      display: flex;
      align-items: center;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      font-size: 0.9rem;
      gap: 0.5rem;
      transition: opacity 0.15s;
    }}
    .file-link:active {{ opacity: 0.7; }}
    .file-icon {{ font-size: 1.2rem; flex-shrink: 0; width: 1.8rem; text-align: center; }}
    .file-label {{ flex: 1; font-weight: 500; }}
    .file-action {{
      font-size: 0.78rem;
      white-space: nowrap;
      background: rgba(255,255,255,0.25);
      padding: 0.15rem 0.5rem;
      border-radius: 10px;
      flex-shrink: 0;
    }}

    /* ── Button variants ─────────────────────────────── */
    .btn-primary    {{ background: #2563eb; color: #fff; }}
    .btn-video      {{ background: #7c3aed; color: #fff; }}
    .btn-pdf        {{ background: #dc2626; color: #fff; }}
    .btn-image      {{ background: #0891b2; color: #fff; }}
    .btn-data       {{ background: #059669; color: #fff; }}
    .btn-zip        {{ background: #d97706; color: #fff; }}
    .btn-default    {{ background: #475569; color: #fff; }}

    /* ── Unavailable ─────────────────────────────────── */
    .file-item.unavailable {{
      background: #f1f5f9;
      color: #94a3b8;
    }}
    .file-status {{ font-size: 0.8rem; color: #94a3b8; }}

    /* ── Bulk download ────────────────────────────────── */
    .bulk-download {{ border: 2px dashed #d97706; }}

    /* ── Notice ───────────────────────────────────────── */
    .notice-section {{
      background: #fffbeb;
      border: 1px solid #f59e0b;
      border-radius: 12px;
      padding: 1.25rem 1rem;
      margin-bottom: 1rem;
    }}
    .notice-section h2 {{ font-size: 0.95rem; color: #92400e; margin-bottom: 0.5rem; }}
    .notice-section ul {{
      font-size: 0.83rem;
      color: #78350f;
      padding-left: 1.2rem;
      line-height: 1.8;
    }}

    /* ── Footer ───────────────────────────────────────── */
    footer {{
      text-align: center;
      font-size: 0.78rem;
      color: #94a3b8;
      padding-top: 1.5rem;
    }}

    /* ── Dark mode ────────────────────────────────────── */
    @media (prefers-color-scheme: dark) {{
      body {{ background: #0f172a; color: #e2e8f0; }}
      .category-section {{ background: #1e293b; box-shadow: 0 2px 8px rgba(0,0,0,0.3); }}
      .category-title {{ color: #93c5fd; border-bottom-color: #334155; }}
      .file-item.unavailable {{ background: #0f172a; }}
      .notice-section {{ background: #1c1a11; border-color: #b45309; }}
      .notice-section h2 {{ color: #fcd34d; }}
      .notice-section ul {{ color: #fbbf24; }}
    }}
  </style>
</head>
<body>
  <header class="site-header">
    <h1>🏹 {_e(site_title)}</h1>
    <p class="subtitle">{display_label}</p>
    {header_info}
    {f'<div class="expiry-banner">⏰ URLの有効期限：{expires_display}</div>' if expires_display else ""}
  </header>

  <main class="main">
    {"".join(section_htmls)}

    {bulk_section}

    <section class="notice-section">
      <h2>⚠️ ご注意</h2>
      <ul>
        <li>このURLは{expires_display or "一定期間"}有効です。期限後はアクセスできなくなります。</li>
        <li>このURLを第三者と共有しないでください。</li>
        <li>動画・PDFは個人情報を含む場合があります。取り扱いにご注意ください。</li>
        <li>本解析は動きの可視化を目的とした参考資料です。医療診断・怪我の診断・専門的な競技指導を代替するものではありません。</li>
        <li>ご不明な点はご連絡ください。</li>
      </ul>
    </section>
  </main>

  <footer>
    <p>Javelin Video Analysis — 生成日: {generated_at}</p>
  </footer>
</body>
</html>"""

    return html


def save_delivery_page(output_dir: Path, html: str) -> Path:
    """delivery_page.html を出力ディレクトリに保存する。

    Parameters
    ----------
    output_dir : Path
        保存先ディレクトリ（存在しない場合は作成）
    html : str
        generate_delivery_page() の戻り値

    Returns
    -------
    Path
        保存したファイルのパス
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "delivery_page.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


# ── 内部ヘルパー ─────────────────────────────────────────────────────────────

def _e(text: str) -> str:
    """HTML エスケープ。"""
    return _html_escape.escape(str(text), quote=True)


def _file_icon(content_type: str) -> str:
    if content_type.startswith("video/"):
        return "🎬"
    if content_type == "application/pdf":
        return "📄"
    if content_type.startswith("image/"):
        return "🖼️"
    if content_type in ("text/csv",):
        return "📊"
    if content_type == "application/json":
        return "🔬"
    if content_type == "application/zip":
        return "📦"
    if content_type == "text/html":
        return "🌐"
    return "📎"


def _button_style(category: str, content_type: str) -> tuple[str, str, str]:
    """(CSS class, アクション文字列, target) を返す。"""
    if content_type.startswith("video/"):
        return "btn-video", "▶ 動画を開く", "_blank"
    if content_type == "application/pdf":
        if category == "最初に読む資料":
            return "btn-primary", "📋 まず読む", "_blank"
        return "btn-pdf", "📄 PDFを開く", "_blank"
    if content_type.startswith("image/"):
        return "btn-image", "🖼️ 画像を開く", "_blank"
    if content_type == "application/zip":
        return "btn-zip", "📥 ダウンロード", "_blank"
    if content_type in ("text/csv", "application/json"):
        return "btn-data", "🔬 データを開く", "_blank"
    return "btn-default", "開く", "_blank"


def _format_expires(expires_at: str) -> str:
    """ISO 8601 文字列を表示用文字列に変換する。"""
    if not expires_at:
        return ""
    try:
        # Python 3.11+ fromisoformat は +09:00 を処理可能
        dt = datetime.fromisoformat(expires_at)
        return dt.strftime("%Y年%m月%d日 %H:%M")
    except Exception:
        return expires_at
