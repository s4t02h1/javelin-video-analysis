import type { VideoItem } from '../types'

interface Props {
  videos: VideoItem[]
}

export default function VideoSection({ videos }: Props) {
  const available = videos.filter((v) => v.available && v.url)

  if (!available.length) {
    return (
      <section className="section">
        <div className="section-header">🎬 解析動画</div>
        <div className="section-body">
          <p style={{ fontSize: '0.82rem', color: '#6c757d' }}>
            動画は現在ご利用いただけません（S3 未設定またはリンク期限切れ）。
          </p>
        </div>
      </section>
    )
  }

  return (
    <section className="section">
      <div className="section-header">🎬 解析動画</div>
      <div className="section-body">
        <div className="video-grid">
          {available.map((v) => (
            <div key={v.key} className="video-item">
              <div className="video-label">{v.label}</div>
              <p className="video-desc">{v.description}</p>
              <div className="video-container">
                <video
                  controls
                  playsInline
                  preload="metadata"
                  aria-label={v.label}
                >
                  <source src={v.url!} type={v.content_type} />
                  お使いのブラウザは動画再生に対応していません。
                </video>
              </div>
            </div>
          ))}
        </div>
        <p style={{ marginTop: 10, fontSize: '0.72rem', color: '#6c757d' }}>
          ※ 骨格線・HUD は推定値です。正確な位置・速度ではありません。
        </p>
      </div>
    </section>
  )
}
