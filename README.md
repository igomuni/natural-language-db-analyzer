# 自然言語DB分析ツール (Natural Language DB Analyzer)

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)]([YOUR_STREAMLIT_APP_URL])

日本の行政事業レビュー「支出先・支出情報」のCSVデータを元に、自然言語（日本語）で質問するだけで、AIが自動的にSQLを生成し、データベースを分析して結果を返してくれるWebアプリケーションです。

SQLを直接実行してデータを探索したり、他のLLMで試すためのプロンプトを生成したりする学習機能も備えています。

## ✨ 主な機能

- **自然言語による対話**: 「〇〇省の支出額トップ5は？」のような曖昧な日本語の質問を理解します。
- **AIによるSQL自動生成**: フロントエンドで動作するGoogle Geminiが、ユーザーの質問の意図を汲み取り、PostgreSQLのクエリを動的に生成します。
- **SQL直接実行**: 生成されたSQLを編集したり、自分で書いたSQLを直接実行して、データを自由に探索できます。
- **クラウドネイティブ**: フロントエンド、バックエンド、データベースが独立してクラウド上で動作する、モダンな3層アーキテクチャを採用しています。

## 🏛️ アーキテクチャ

このアプリケーションは、メモリ使用量とセキュリティを最適化するため、以下の3層アーキテクチャで構成されています。

```
[ユーザー] <--> [Frontend (UI + AI Logic): Streamlit] <--> [Backend (Secure SQL Runner): FastAPI] <--> [Database: Supabase(PostgreSQL)]
                   (on Streamlit Cloud)                     (on Render)                              (on Supabase)
```

- **フロントエンド**がユーザーとの対話と、Google Gemini APIとの通信（SQL生成）を担当します。
- **バックエンド**は、フロントエンドから受け取ったSQLを安全に実行し、結果を返すだけのシンプルな役割に徹します。

## 🛠️ 技術スタック

| カテゴリ          | 技術 / サービス                               |
| ----------------- | ----------------------------------------------- |
| **フロントエンド**  | Streamlit                                       |
| **バックエンド**    | FastAPI, Uvicorn                                |
| **データベース**    | Supabase (PostgreSQL)                           |
| **AI / LLM**      | Google Gemini 1.5 Flash                         |
| **デプロイ (Frontend)** | Streamlit Community Cloud                     |
| **デプロイ (Backend)**  | Render                                          |
| **主要ライブラリ**    | `requests`, `psycopg2-binary`, `pandas`, `google-generativeai` |


## 🚀 セットアップとローカルでの実行

### 前提条件
- Python 3.9以上
- Git

### 1. データベースの準備 (Supabase)
1. Supabaseにサインアップし、新しいプロジェクトを作成します。
2. テーブルエディタのインポート機能を使用し、[行政事業レビューのCSVデータ](https://rssystem.go.jp/files/2024/rs/5-1_支出先_支出情報.zip) (`5-1_...`) を`main_data`というテーブル名でインポートします。（ヘッダーの長い列名は、インポート前に短い名前に変更することを推奨します）
3. `Authentication` -> `Policies` で、`main_data`テーブルの**RLSを有効**にし、「Enable read access for everyone」ポリシーを追加して、読み取り専用に設定します。
4. `Settings` -> `Database` から、**Pooler**用の接続文字列を取得します。

### 2. バックエンドのセットアップ (Secure SQL Runner)
```bash
# リポジトリをクローン
git clone https://github.com/[YOUR_GITHUB_USERNAME]/natural-language-db-analyzer.git
cd natural-language-db-analyzer/backend

# 依存ライブラリをインストール
pip install -r requirements.txt

# .envファイルを作成し、データベース接続情報を設定
# (backend/.env.exampleを参考にしてください)
# DATABASE_URL="YOUR_SUPABASE_POOLER_CONNECTION_STRING" 
# (パスワードの特殊文字はURLエンコードしてください)

# バックエンドサーバーを起動
uvicorn main:app --reload
```
サーバーは `http://127.0.0.1:8000` で起動します。

### 3. フロントエンドのセットアップ```bash
# (新しいターミナルを開き) ルートディレクトリに移動
cd .. 

# 依存ライブラリをインストール
pip install -r requirements.txt

# .envファイルを作成し、APIキーを設定
# (/.env.exampleを参考にしてください)
# GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
# BACKEND_URL="http://127.0.0.1:8000" (ローカルテスト用)

# Streamlitアプリを起動
streamlit run app.py
```
ブラウザで `http://localhost:8501` が開きます。

## 🌐 デプロイ

- **バックエンド**: `backend`ディレクトリをRenderのWeb Serviceとしてデプロイします。環境変数には`DATABASE_URL`のみ設定します。
- **フロントエンド**: ルートディレクトリをStreamlit Community Cloudにデプロイします。Secretsには`GOOGLE_API_KEY`と、Renderで公開されたバックエンドのURLを`BACKEND_URL`として設定します。

## 📄 ライセンス
このプロジェクトは [MITライセンス](LICENSE) の下で公開されています。