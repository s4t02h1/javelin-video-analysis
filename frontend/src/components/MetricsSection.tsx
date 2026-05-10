import type { KeyMetric, DetailMetric } from '../types'
import MetricCard from './MetricCard'
import ReliabilityBadge from './ReliabilityBadge'

interface Props {
  keyMetrics: KeyMetric[]
  detailMetrics: Record<string, DetailMetric[]>
}

const CATEGORY_LABELS: Record<string, string> = {
  release:    'リリース指標',
  block:      'ブロック指標',
  trunk:      '体幹指標',
  arm:        '腕・手首指標',
  trajectory: '軌跡指標',
}

export default function MetricsSection({ keyMetrics, detailMetrics }: Props) {
  const hasKeyMetrics = keyMetrics.length > 0
  const hasDetail = Object.values(detailMetrics).some((arr) => arr.length > 0)

  if (!hasKeyMetrics && !hasDetail) {
    return (
      <section className="section">
        <div className="section-header">📊 解析指標（参考値）</div>
        <div className="section-body">
          <p style={{ fontSize: '0.82rem', color: '#6c757d' }}>
            高度解析指標は生成されていません。
          </p>
        </div>
      </section>
    )
  }

  return (
    <section className="section">
      <div className="section-header">📊 解析指標（参考値）</div>
      <div className="section-body">
        <p style={{ fontSize: '0.78rem', color: '#856404', background: '#fff3cd', padding: '8px 10px', borderRadius: 4, marginBottom: 12 }}>
          すべての指標は参考値です。断定的な判断には使用しないでください。
        </p>

        {hasKeyMetrics && (
          <>
            <h3 style={{ fontSize: '0.85rem', margin: '0 0 8px' }}>主要指標</h3>
            <div className="metric-grid">
              {keyMetrics.map((m) => (
                <MetricCard key={m.key} metric={m} />
              ))}
            </div>
          </>
        )}

        {hasDetail && (
          <>
            <h3 style={{ fontSize: '0.85rem', margin: '16px 0 8px' }}>詳細指標（カテゴリ別）</h3>
            {Object.entries(detailMetrics).map(([cat, items]) => {
              if (!items.length) return null
              return (
                <details key={cat} className="detail-section">
                  <summary>{CATEGORY_LABELS[cat] ?? cat}（{items.length}件）</summary>
                  <div className="detail-table-wrap">
                <table className="detail-table">
                    <thead>
                      <tr>
                        <th>指標</th>
                        <th>値</th>
                        <th>単位</th>
                        <th>信頼度</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((item) => (
                        <tr key={item.key}>
                          <td style={{ fontSize: '0.72rem', wordBreak: 'break-all' }}>{item.label || item.key}</td>
                          <td style={{ fontWeight: 600 }}>
                            {item.value !== null && item.value !== undefined
                              ? item.value.toLocaleString('ja-JP', { maximumFractionDigits: 4 })
                              : '—'}
                          </td>
                          <td style={{ color: '#6c757d' }}>{item.unit || '—'}</td>
                          <td>
                            <ReliabilityBadge reliability={item.reliability} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  </div>
                </details>
              )
            })}
          </>
        )}
      </div>
    </section>
  )
}
