# 自然言語DB分析ツール (Natural Language DB Analyzer)

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://natural-language-db-analyzer-20250816-2217.streamlit.app/)

日本の行政事業レビュー「支出先・支出情報」のCSVデータを元に、自然言語（日本語）で質問するだけで、AIが自動的にSQLを生成し、データベースを分析して結果を返してくれるWebアプリケーションです。

## ✨ 主な機能

- **自然言語による対話**: 「〇〇省の支出額トップ5は？」のような曖昧な日本語の質問を理解します。
- **AIによるSQL自動生成**: Google Gemini (AIモデル)が、ユーザーの質問の意図を汲み取り、PostgreSQLのクエリを動的に生成します。
- **クラウドネイティブ**: フロントエンド、バックエンド、データベースが独立してクラウド上で動作する、モダンな3層アーキテクチャを採用しています。
- **インタラクティブなUI**: Streamlitを使用し、サンプル質問の提示や、分析結果を直感的に表示する機能を備えています。

## 🏛️ アーキテクチャ

このアプリケーションは、関心の分離の原則に基づき、以下の3つのサービスで構成されています。

```
[ユーザー] <--> [Frontend: Streamlit] <--> [Backend: FastAPI] <--> [Database: Supabase(PostgreSQL)]
                   (on Streamlit Cloud)      (on Render)           (on Supabase)
```

## 🛠️ 技術スタック

| カテゴリ          | 技術 / サービス                               |
| ----------------- | ----------------------------------------------- |
| **フロントエンド**  | Streamlit                                       |
| **バックエンド**    | FastAPI, Uvicorn                                |
| **データベース**    | Supabase (PostgreSQL)                           |
| **AI / LLM**      | Google Gemini 1.5 Flash                         |
| **デプロイ (Frontend)** | Streamlit Community Cloud                     |
| **デプロイ (Backend)**  | Render                                          |
| **主要ライブラリ**    | `requests`, `psycopg2-binary`, `pandas`         |


## 🚀 セットアップとローカルでの実行

### 前提条件
- Python 3.9以上
- Git

### 1. データベースの準備 (Supabase)
このアプリケーションはSupabase上のPostgreSQLデータベースをデータソースとしています。
1. Supabaseにサインアップし、新しいプロジェクトを作成します。
2. テーブルエディタのインポート機能を使用し、[行政事業レビューのCSVデータ](https://rssystem.go.jp/download-csv/2024) (`5-1_支出先_支出情報`) を`main_data`というテーブル名でインポートします。
3. `Settings` -> `Database` から、**Pooler**用の接続文字列を取得します。

### 2. バックエンドのセットアップ
```bash
# リポジトリをクローン
git clone https://github.com/[YOUR_USERNAME]/natural-language-db-analyzer.git
cd natural-language-db-analyzer/backend

# 依存ライブラリをインストール
pip install -r requirements.txt

# .envファイルを作成し、秘密鍵を設定
# (.env.exampleを参考にしてください)
cp .env.example .env
# nano .env または vim .env などで編集
# GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
# DATABASE_URL="YOUR_SUPABASE_POOLER_CONNECTION_STRING"

# バックエンドサーバーを起動
uvicorn main:app --reload
```
サーバーは `http://127.0.0.1:8000` で起動します。

### 3. フロントエンドのセットアップ
```bash
# ルートディレクトリに移動
cd ..

# 依存ライブラリをインストール
pip install -r requirements.txt

# Streamlitアプリを起動
streamlit run app.py
```
ブラウザで `http://localhost:8501` が開きます。

## 📄 ライセンス
このプロジェクトは [MITライセンス](LICENSE) の下で公開されています。