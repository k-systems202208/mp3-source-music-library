# 要件追跡表

| 要件 | 実装 | 確認 |
|---|---|---|
| MP3を正本にする | generator、server | MP3を変更しない複製DB試験 |
| 検索・索引 | browse API、HTML | browse／UI回帰 |
| 再生・シーク | Range配信、Audio | Range試験、実機再生 |
| アートワーク | artworks、cache | generator・UI試験 |
| 文字補正 | metadata parser、override | generator・補正API |
| アルバム表示名補正 | album_override、アルバム補正API | オーナー権限・同一アルバム一括反映試験 |
| 移動・改名検出 | content signature | scan regression |
| 利用者識別 | local auth、Tailscale identity | 認証試験 |
| 利用者別状態 | user_track_state | playback／favorites |
| 利用者別スキン | user_preferences | skin persistence |
| 自分の表示名管理 | users.display_name、profile API | 本人限定更新・識別情報再取得後の維持試験 |
| プレイリスト | playlists、playlist_tracks | DB／API／UI／実機 |
| プレイリスト複製・並べ替え | duplicate API、order API、drag UI | 曲順複製・所有権・UI契約試験 |
| 管理・診断 | diagnostics API、オーナーUI | 権限・DB整合性・保存先・JSON試験 |
| バックアップ・復元 | backup_restore | schema 5/6/7試験 |
| 長いパス | long_paths | 201曲・最大364文字 |
| PWA | manifest、Service Worker | PWA回帰・iPhone実機 |
| 新版通知 | update_check | prerelease含む版比較 |
| 所有権分離 | API所有者検査 | playlist user isolation |
| 音源非キャッシュ | Service Worker除外 | cache safety |
| 更新安全性 | 移行前バックアップ | schema 6→7試験 |
| 公開版整合性 | version files、installer | RC consistency、build report |

## 未実装・対象外

| 項目 | 状態 |
|---|---|
| MP3オフライン再生 | 対象外 |
| プレイリスト共有 | 未実装 |
| M3U入出力 | 未実装 |
| 自動選曲 | 未実装 |
| 評価操作UI | 未実装。DB列は存在 |
| インターネット一般公開 | 対象外 |
