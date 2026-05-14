import React from 'react';

export default function ShootingGuidePage() {
  return (
    <main className="shooting-guide-page" style={{ maxWidth: 480, margin: '0 auto', padding: 16 }}>
      <h2>撮影ガイド</h2>
      <ul style={{ fontSize: '1em', margin: '1em 0' }}>
        <li>横向き撮影を推奨します</li>
        <li>被写体が大きく映る距離で撮影してください</li>
        <li>投てき動作全体が画面に入るようにしてください</li>
        <li>カメラは固定を推奨します</li>
        <li>明るい場所で撮影してください</li>
        <li>逆光を避けてください</li>
        <li>縦撮りは現状非推奨です</li>
        <li>被写体が遠すぎる、暗い、ブレが大きい、身体が画面外に出る動画は解析できない場合があります</li>
      </ul>
    </main>
  );
}
