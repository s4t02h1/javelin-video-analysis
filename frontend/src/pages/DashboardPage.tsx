import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import type { DashboardManifest } from '../types'
import { DashboardApiError, fetchDashboard } from '../lib/api'
import Header from '../components/Header'
import NoticeBanner from '../components/NoticeBanner'
import VideoSection from '../components/VideoSection'
import PhaseImageSection from '../components/PhaseImageSection'
import MetricsSection from '../components/MetricsSection'
import GraphSection from '../components/GraphSection'
import DownloadSection from '../components/DownloadSection'
import DisclaimerSection from '../components/DisclaimerSection'

export default function DashboardPage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const [manifest, setManifest] = useState<DashboardManifest | null>(null)
  const [loading, setLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      navigate('/not-found', { replace: true })
      return
    }
    let cancelled = false
    setLoading(true)

    const load = async () => {
      try {
        const data = await fetchDashboard(token)
        if (cancelled) return
        setManifest(data)
        setLoading(false)
      } catch (error) {
        if (cancelled) return
        if (error instanceof DashboardApiError) {
          if (error.type === 'expired') {
            navigate('/expired', { replace: true })
            return
          }
          if (error.type === 'not_found') {
            navigate('/not-found', { replace: true })
            return
          }
          if (error.type === 'network') {
            setErrorMsg('ネットワークエラーが発生しました。通信状況を確認してください。')
          } else {
            setErrorMsg(`エラー: ${error.detail ?? 'サーバーエラー'}`)
          }
        } else {
          setErrorMsg('不明なエラーが発生しました。')
        }
        setLoading(false)
      }
    }

    void load()
    return () => { cancelled = true }
  }, [token, navigate])

  if (loading) {
    return (
      <div className="page-wrapper">
        <div className="loading-screen" role="status" aria-live="polite">
          <div className="loading-spinner" aria-hidden="true" />
          <p style={{ color: '#6c757d', fontSize: '0.9rem' }}>読み込み中...</p>
        </div>
      </div>
    )
  }

  if (errorMsg || !manifest) {
    return (
      <div className="page-wrapper">
        <div className="error-screen">
          <div className="error-icon">⚠️</div>
          <h2>読み込みエラー</h2>
          <p>{errorMsg ?? '不明なエラーが発生しました。'}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="page-wrapper">
      <Header manifest={manifest} />

      {/* ファーストビュー: 最初に見る順番 */}
      <div className="first-steps">
        <h3>📋 最初に見る順番</h3>
        <ol>
          <li>注意事項バナーを確認してください</li>
          {manifest.sections.videos && <li>解析動画で動作全体の流れを確認してください（参考）</li>}
          <li>フェーズ別静止画で各局面の姿勢を確認してください（参考）</li>
          {manifest.sections.metrics && <li>解析指標の参考値を確認してください</li>}
          <li>必要に応じてダウンロード資料を取得してください</li>
        </ol>
      </div>

      <NoticeBanner notices={manifest.notices} />

      {manifest.sections.videos && (
        <VideoSection videos={manifest.videos} />
      )}

      <PhaseImageSection phaseImages={manifest.phase_images} />

      {manifest.sections.metrics && (
        <MetricsSection
          keyMetrics={manifest.key_metrics}
          detailMetrics={manifest.detail_metrics}
        />
      )}

      {manifest.sections.graphs && (
        <GraphSection graphs={manifest.graphs} />
      )}

      <DownloadSection downloads={manifest.downloads} />

      {/* 問い合わせ */}
      <section className="section">
        <div className="section-header">📩 お問い合わせ</div>
        <div className="section-body">
          <div className="inquiry-box">
            <p style={{ margin: '0 0 8px', fontSize: '0.82rem' }}>
              ダウンロードリンクの期限切れ・内容に関するご質問は、以下の情報をお知らせください。
            </p>
            <dl>
              <dt>ジョブID</dt>
              <dd style={{ wordBreak: 'break-all' }}>{manifest.inquiry_info.job_id}</dd>
              <dt>解析日</dt>
              <dd>{manifest.inquiry_info.delivered_at || '—'}</dd>
              <dt>プラン</dt>
              <dd>{manifest.inquiry_info.plan_label || '—'}</dd>
            </dl>
          </div>

          {/* β版フィードバック導線 */}
          {(manifest as { feedback_form_url?: string }).feedback_form_url && (
            <div className="feedback-banner">
              <p>β版改善のため、解析結果をご確認後にフィードバックをお願いします。所要時間：3〜5分程度</p>
              <a
                href={(manifest as { feedback_form_url?: string }).feedback_form_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                フィードバックフォームを開く →
              </a>
            </div>
          )}
        </div>
      </section>

      <DisclaimerSection disclaimer={manifest.disclaimer} />

      <footer className="app-footer">
        <p>Javelin Video Analysis — 参考資料</p>
        <p>
          生成日時: {manifest.generated_at.slice(0, 16).replace('T', ' ')}&nbsp;/&nbsp;
          公開期限: {manifest.token_expires_at.slice(0, 10)}
        </p>
      </footer>
    </div>
  )
}
