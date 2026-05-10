import type { DashboardManifest } from '../types'

interface Props {
  manifest: DashboardManifest
}

export default function Header({ manifest }: Props) {
  const expiryDate = manifest.token_expires_at
    ? manifest.token_expires_at.slice(0, 10)
    : ''

  return (
    <header className="app-header">
      <h1>
        {import.meta.env.VITE_APP_NAME ?? 'Javelin Video Analysis'}
        {manifest.display_name && ` — ${manifest.display_name}`}
      </h1>
      <p className="subtitle">
        やり投げ動画解析レポート（参考資料）
      </p>
      <div className="header-meta">
        {manifest.plan_label && (
          <span className="badge badge-plan">{manifest.plan_label}</span>
        )}
        {manifest.delivered_at && (
          <span className="badge badge-plan">解析日: {manifest.delivered_at}</span>
        )}
        {expiryDate && (
          <span className="badge badge-plan">公開期限: {expiryDate}</span>
        )}
        {manifest.metrics_version && manifest.metrics_version !== '—' && (
          <span className="badge badge-plan">v{manifest.metrics_version}</span>
        )}
      </div>
    </header>
  )
}
