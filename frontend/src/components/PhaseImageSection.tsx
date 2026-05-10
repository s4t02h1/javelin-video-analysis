import type { PhaseImage } from '../types'

interface Props {
  phaseImages: PhaseImage[]
}

export default function PhaseImageSection({ phaseImages }: Props) {
  const available = phaseImages.filter((p) => p.available && p.url)
  const hasAny = phaseImages.some((p) => p.available)

  return (
    <section className="section">
      <div className="section-header">📸 フェーズ別静止画</div>
      <div className="section-body">
        {!hasAny && (
          <p style={{ fontSize: '0.82rem', color: '#6c757d' }}>
            フェーズ画像は生成されていません。
          </p>
        )}
        {hasAny && (
          <>
            <div className="phase-grid">
              {phaseImages.map((p) => (
                <div key={p.phase_key} className="phase-card">
                  <div className="phase-card-header">{p.label}</div>
                  {p.available && p.url ? (
                    <img src={p.url} alt={p.label} loading="lazy" />
                  ) : (
                    <div className="phase-no-image">
                      {p.available ? 'URL 未生成' : '推定なし'}
                    </div>
                  )}
                  <div className="phase-card-tip">{p.tip}</div>
                </div>
              ))}
            </div>
            <p style={{ marginTop: 10, fontSize: '0.72rem', color: '#6c757d' }}>
              ※ フェーズ推定は自動推定です。正確な区切りではありません。
            </p>
          </>
        )}
        {!hasAny && available.length === 0 && (
          <p style={{ fontSize: '0.78rem', color: '#6c757d', marginTop: 8 }}>
            フェーズ検出が実施されていない場合、この画像は表示されません。
          </p>
        )}
      </div>
    </section>
  )
}
