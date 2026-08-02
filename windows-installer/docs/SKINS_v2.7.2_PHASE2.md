# v2.7.2 工程2: 利用者別スキン設定

## 保存モデル

`user_preferences` は利用者IDを主キーとし、`skin_id` と更新日時を保存します。既存利用者はスキーマv6移行時に `library` で初期化されます。

許可値は `library`, `midnight`, `neon`, `cyberpunk`, `candy`, `monochrome` の6種類です。未知の値や任意CSSは受け付けません。

## API

`GET /api/current-user` は認証状態に加えて `skinId` を返します。未認識時は `library` です。

`PUT /api/me/skin` は現在の接続からサーバーが利用者を解決し、本文の `skinId` だけを保存します。クライアントは利用者IDを指定できません。

## 関連付け

ローカルオーナーへTailscale識別情報を関連付けた場合、識別情報はオーナーの利用者IDへ移動します。その後はローカル接続とTailscale接続で同じスキン設定を参照します。統合前の重複利用者設定は、利用者削除に伴って外部キーのCASCADEで削除されます。オーナー側の設定を優先します。

## バックアップ

v5からv6へ移行する前に `library-pre-v2.7.2-YYYYMMDD-HHMMSS.db` を作成して検証します。通常バックアップと復元検証はスキーマv6を対応形式として扱います。
