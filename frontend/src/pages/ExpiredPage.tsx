export default function ExpiredPage() {
  return (
    <div className="page-wrapper">
      <div className="error-screen">
        <div className="error-icon">⏰</div>
        <h2>公開期限が切れています</h2>
        <p>
          このダッシュボードの公開期限が切れています。
          <br />
          再発行が必要な場合は、以下の情報をご連絡ください。
        </p>
        <p style={{ fontSize: '0.8rem' }}>
          ダッシュボード URL（ブラウザのアドレスバーの内容）をそのままコピーしてお送りください。
        </p>
      </div>
    </div>
  )
}
