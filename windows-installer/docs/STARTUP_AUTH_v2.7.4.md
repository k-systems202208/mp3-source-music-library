# v2.7.4 起動時ローカルオーナー認証

## 現象

RC1のWindows実機確認で、アプリ起動直後にランチャーが自動で開く`/api/local-auth/exchange?token=...`が、Chrome上で黒い読み込み画面のまま停止しました。

タブを閉じ、管理画面の「ブラウザで開く」を押し直すと正常に表示できたため、ライブラリやDBではなく、最初の認証完了レスポンスの遷移方式を修正対象としました。

## RC2の変更

ワンタイムトークンをHttpOnly Cookieへ交換した後、本文なしの303リダイレクトではなく、小さなHTMLハンドオフページを返します。

- `window.location.replace`による即時遷移
- JavaScriptが使えない場合のmeta refresh
- 画面が切り替わらない場合の手動リンク
- `Connection: close`による接続完了
- Content Security PolicyとX-Frame-Options
- ワンタイムトークンをHTML本文へ含めない
- 不正・期限切れ・再利用済みトークンは従来どおり拒否

CookieのHttpOnly、SameSite=Strict、有効期限などの既存安全条件は維持します。

## 実機確認

アプリを完全終了して再起動する操作を3回連続で行い、3回すべてで最初の自動ブラウザ表示がライブラリ画面まで正常に進みました。

## 自動試験

- 認証Cookieの発行
- HTMLハンドオフ本文
- JavaScript遷移
- meta refresh
- 手動リンク
- Connection: close
- トークン非表示
- 3回連続の認証ハンドオフ
