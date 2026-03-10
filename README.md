# denen_cs_result_bot

田園ブログ（supersolenoid.jp）の「大会結果」タグの新着記事を、毎日9時（JST）にDiscordへ自動投稿するBotです。

## 動作概要

1. 毎日9時（JST）にタグページをスクレイピング
2. 前回送信時より新しい記事を検出
3. 記事のタイトル・URL・サムネイル画像をDiscord Embedで送信

## デプロイ手順（Fly.io）

### 前提条件

- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) をインストール済みであること
- Fly.io アカウントを作成済みであること

### 1. ログイン

```bash
fly auth login
```

### 2. アプリ作成

```bash
fly launch --no-deploy
```

`fly.toml` が既に存在するため、設定の上書きを求められた場合は **上書きしない** を選択してください。

### 3. ボリューム作成（state.json 永続化用）

```bash
fly volumes create bot_data --region nrt --size 1
```

### 4. シークレット設定

```bash
fly secrets set DISCORD_TOKEN=<Discord BotトークンをDeveloper Portalから取得>
fly secrets set DISCORD_CHANNEL_ID=<送信先チャンネルID>
```

チャンネルIDはDiscordでチャンネルを右クリック →「IDをコピー」で取得できます。

### 5. デプロイ

```bash
fly deploy
```

---

## コード更新時の再デプロイ

```bash
fly deploy
```

---

## 環境変数

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `DISCORD_TOKEN` | ✅ | Discord Bot トークン |
| `DISCORD_CHANNEL_ID` | ✅ | 送信先チャンネルID |
| `BLOG_TAG_URL` | | 監視するタグページURL（省略時は大会結果タグ） |

ローカルで動かす場合は `.env.example` をコピーして `.env` を作成してください。

```bash
cp .env.example .env
```

---

## 環境変数の確認

設定済みのシークレット一覧を確認するには以下を実行します。

```bash
fly secrets list
```

シークレット名と最終更新日時が表示されます（セキュリティのため値は表示されません）。

値を変更したい場合は再度 `fly secrets set` を実行してください。

```bash
fly secrets set DISCORD_TOKEN=<新しいトークン>
```

`fly secrets set` を実行するとアプリが自動的に再起動して新しい値が反映されます。`fly deploy`（再ビルド）は不要です。

---

## 運用コマンド

| コマンド | 説明 |
|----------|------|
| `fly logs` | ログを確認する |
| `fly status` | 動作状態を確認する |
| `fly secrets list` | 設定済みシークレット一覧を確認する |
| `fly secrets set KEY=VALUE` | シークレットを追加・更新する |

---

## 初回起動の挙動

`state.json` が存在しない状態で初回起動した場合、既存の記事は送信されず現在の最新記事IDのみ保存されます。次回以降の起動から、その時点より新しい記事のみ送信されます。
