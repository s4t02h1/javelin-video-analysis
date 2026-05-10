import type { GraphItem } from '../types'

interface Props {
  graphs: GraphItem[]
}

export default function GraphSection({ graphs }: Props) {
  const available = graphs.filter((g) => g.available && g.url)

  if (!available.length) {
    return (
      <section className="section">
        <div className="section-header">📈 グラフ</div>
        <div className="section-body">
          <p style={{ fontSize: '0.82rem', color: '#6c757d' }}>
            グラフは現在ご利用いただけません。
          </p>
        </div>
      </section>
    )
  }

  return (
    <section className="section">
      <div className="section-header">📈 グラフ</div>
      <div className="section-body">
        <div className="graph-list">
          {available.map((g) => (
            <div key={g.key} className="graph-item">
              <div className="graph-label">{g.label}</div>
              <p className="graph-desc">{g.description}</p>
              <img src={g.url!} alt={g.label} loading="lazy" />
            </div>
          ))}
        </div>
        <p style={{ marginTop: 8, fontSize: '0.72rem', color: '#6c757d' }}>
          ※ グラフの数値はすべて参考値です。
        </p>
      </div>
    </section>
  )
}
