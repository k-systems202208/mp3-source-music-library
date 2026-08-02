# v2.7.3 RC1 対象範囲

## 目的

スマートフォンのホーム画面へ追加し、Tailscale HTTPS URLからアプリに近い表示で起動できることを実機確認する。

## 対象

- Web App Manifest
- PWAアイコン一式
- standalone起動
- Service Workerによる画面資産キャッシュ
- 通信不能時画面
- 接続先URL案内とコピー
- ローカル／Tailscale／通常HTTPの表示判定
- safe-area、タップ領域、縦横レイアウト
- 6種類のスキン連動

## 対象外

- MP3のオフライン保存
- App Store／Google Play公開
- プッシュ通知
- ロック画面の高度な再生操作
- バックグラウンド再生保証

## 安全条件

API、音楽、DB、バックアップ、アートワークはService Workerのキャッシュ対象外とする。Windows版の検索・再生・利用者分離・スキン・バックアップ・新版通知を維持する。
