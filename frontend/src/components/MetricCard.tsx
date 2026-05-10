import type { KeyMetric } from '../types'
import ReliabilityBadge from './ReliabilityBadge'

interface Props {
  metric: KeyMetric
}

export default function MetricCard({ metric }: Props) {
  const displayValue =
    metric.value !== null && metric.value !== undefined
      ? metric.value.toLocaleString('ja-JP', { maximumFractionDigits: 3 })
      : '—'

  return (
    <div className="metric-card">
      <div className="metric-label">{metric.label}</div>
      <div className="metric-value">
        {displayValue}
        {metric.unit && <span className="metric-unit">{metric.unit}</span>}
      </div>
      <div className="metric-badge-wrap">
        <ReliabilityBadge reliability={metric.reliability} />
      </div>
      {metric.caution && (
        <div className="metric-caution">{metric.caution}</div>
      )}
    </div>
  )
}
