import type { Reliability } from '../types'

interface Props {
  reliability: Reliability
  showDescription?: boolean
}

const LABELS: Record<Reliability, { label: string; description: string }> = {
  high:    { label: '信頼度：高め',   description: '動画内の姿勢推定点が比較的安定している指標です。' },
  medium:  { label: '信頼度：中程度', description: '参考として確認できますが、撮影角度や推定誤差の影響を受ける可能性があります。' },
  low:     { label: '信頼度：低め',   description: '参考候補として確認してください。断定的な判断には向きません。' },
  unknown: { label: '信頼度：未判定', description: '十分な情報がないため、信頼度を判定できません。' },
}

export default function ReliabilityBadge({ reliability, showDescription = false }: Props) {
  const info = LABELS[reliability] ?? LABELS.unknown
  return (
    <span>
      <span className={`badge badge-${reliability}`}>{info.label}</span>
      {showDescription && (
        <span style={{ display: 'block', fontSize: '0.7rem', color: '#6c757d', marginTop: 3 }}>
          {info.description}
        </span>
      )}
    </span>
  )
}
