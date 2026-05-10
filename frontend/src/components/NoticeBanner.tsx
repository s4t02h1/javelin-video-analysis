interface Props {
  notices: string[]
}

export default function NoticeBanner({ notices }: Props) {
  if (!notices.length) return null
  return (
    <div className="notice-banner" role="note">
      <strong>⚠️ この解析結果を読む前に確認してください</strong>
      <ul>
        {notices.map((n, i) => (
          <li key={i}>{n}</li>
        ))}
      </ul>
    </div>
  )
}
