interface Props {
  disclaimer: string
}

export default function DisclaimerSection({ disclaimer }: Props) {
  return (
    <section className="section">
      <div className="section-header">📋 免責事項</div>
      <div className="section-body">
        <div className="disclaimer-box">{disclaimer}</div>
      </div>
    </section>
  )
}
