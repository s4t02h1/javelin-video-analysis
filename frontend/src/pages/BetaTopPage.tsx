import React from 'react';
import { Link } from 'react-router-dom';

export default function BetaTopPage() {
  return (
    <main className="beta-top-page" style={{ maxWidth: 480, margin: '0 auto', padding: 16 }}>
      <h1>やり投げ 動作解析 β版</h1>
      <p>本サービスは、やり投げを中心とした動作解析のβ版です。スマートフォンから動画を提出し、管理者が内容を確認後、解析結果をお送りします。</p>
      <ul style={{ fontSize: '1em', margin: '1em 0' }}>
        <li>撮影条件によっては解析できない場合があります</li>
        <li>受付漏れ・動画紛失・成果物渡し間違い防止を最優先しています</li>
        <li>公式LINEは案内・通知・問い合わせ窓口です</li>
      </ul>
      <Link to="/upload" className="btn-main" style={{ display: 'block', margin: '1.5em 0', padding: '1em', background: '#1976d2', color: '#fff', borderRadius: 8, textAlign: 'center', textDecoration: 'none', fontWeight: 600 }}>
        動画を提出する
      </Link>
      <Link to="/guide" style={{ display: 'block', marginBottom: 8, color: '#1976d2', textAlign: 'center' }}>
        撮影ガイドはこちら
      </Link>
      <Link to="/privacy" style={{ display: 'block', marginBottom: 8, color: '#1976d2', textAlign: 'center' }}>
        注意事項・プライバシー方針
      </Link>
    </main>
  );
}
