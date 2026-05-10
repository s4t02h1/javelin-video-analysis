export default function NotFoundPage() {
  return (
    <div className="page-wrapper">
      <div className="error-screen">
        <div className="error-icon">🔍</div>
        <h2>ページが見つかりません</h2>
        <p>
          ダッシュボードが見つかりませんでした。
          <br />
          URL が正しいか確認してください。
        </p>
        <p style={{ fontSize: '0.8rem' }}>
          URLをお届けした担当者に再度ご確認ください。
        </p>
      </div>
    </div>
  )
}
