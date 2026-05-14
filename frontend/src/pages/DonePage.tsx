import React from 'react';
import { useLocation, Link } from 'react-router-dom';

function useQuery() {
  return new URLSearchParams(useLocation().search);
}

export default function DonePage() {
  const query = useQuery();
  const rid = query.get('rid') || '受付番号不明';
  return (
    <main className="done-page" style={{ maxWidth: 480, margin: '0 auto', padding: 16, textAlign: 'center' }}>
      <h2>受付完了</h2>
      <p>受付番号：<b>{rid}</b></p>
      <p>β版のため、撮影条件によっては解析できない場合があります。</p>
      <p>解析可能な動画から順次結果を作成します。</p>
      <p>結果案内は公式LINEまたは指定方法で行います。</p>
      <Link to="/" style={{ color: '#1976d2', display: 'block', marginTop: 24 }}>トップへ戻る</Link>
    </main>
  );
}
