import type { DownloadCategories, DownloadItem } from '../types'

interface Props {
  downloads: DownloadCategories
}

const CATEGORY_NAMES: Record<string, string> = {
  intro:      '📌 最初に読む資料',
  athlete:    '🏃 選手向け資料',
  advanced:   '🔬 高度解析資料',
  coach:      '👩‍🏫 コーチ向け資料',
  packages:   '📦 一括ダウンロード',
  research:   '🔢 研究・開発用データ',
}

function DownloadItemRow({ item }: { item: DownloadItem }) {
  return (
    <li className="dl-item">
      {item.available && item.url ? (
        <>
          <a href={item.url} target="_blank" rel="noopener noreferrer" download>
            {item.label}
          </a>
          <span className="dl-badge-available">DL可</span>
        </>
      ) : (
        <>
          <span className="dl-unavailable">{item.label}</span>
          <span className="dl-badge-unavailable">未生成</span>
        </>
      )}
    </li>
  )
}

export default function DownloadSection({ downloads }: Props) {
  const ORDER = ['intro', 'athlete', 'advanced', 'coach', 'packages', 'research']

  return (
    <section className="section">
      <div className="section-header">📥 ダウンロード</div>
      <div className="section-body">
        {ORDER.map((cat) => {
          const items = downloads[cat]
          if (!items?.length) return null
          return (
            <div key={cat}>
              <div className="dl-section-title">{CATEGORY_NAMES[cat] ?? cat}</div>
              <ul className="dl-list">
                {items.map((item) => (
                  <DownloadItemRow key={item.filename ?? item.label} item={item} />
                ))}
              </ul>
            </div>
          )
        })}
        <p style={{ marginTop: 10, fontSize: '0.72rem', color: '#6c757d' }}>
          ※ ダウンロードリンクには有効期限があります。期限切れの場合はご連絡ください。
        </p>
      </div>
    </section>
  )
}
