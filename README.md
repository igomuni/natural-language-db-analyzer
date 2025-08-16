# 自然言語DB分析ツール プロトタイプ

行政事業レビューのCSVデータを活用し、自然言語で質問するとSQLを自動生成してデータベースを検索・分析するWebアプリケーションのプロトタイプです。

## 技術スタック

- Webフレームワーク: Streamlit
- データベース: DuckDB
- LLM: Google Gemini
- LLM SDK: google-generativeai

## セットアップ手順

### 1. リポジトリのクローンと移動

```bash
git clone <this-repository-url>
cd natural-language-db-analyzer
```

### 2. 仮想環境の構築と有効化

- Windows
  ```bash
  python -m venv venv
  .\venv\Scripts\activate
  ```
- Mac / Linux
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### 3. 必要なライブラリのインストール

```bash
pip install -r requirements.txt
```

### 4. APIキーの設定

1.  `.env.example` ファイルをコピーして、同じ階層に `.env` という名前のファイルを作成します。
2.  Google AI Studio (https://aistudio.google.com/) からご自身のAPIキーを取得します。
3.  作成した `.env` ファイルを開き、`YOUR_API_KEY_HERE` の部分を自身のAPIキーに書き換えます。

### 5. データベースの準備

以下のコマンドを実行して、政府のサイトからデータをダウンロードし、DuckDBデータベースファイルを作成します。
この処理は初回のみ必要です。

```bash
python scripts/prepare_data.py
```
実行後、`data/` フォルダ内に `review.db` ファイルが生成されます。

## 実行方法

以下のコマンドでStreamlitアプリケーションを起動します。

```bash
streamlit run app.py
```

コマンド実行後、自動的にブラウザが立ち上がり、アプリケーションの画面が表示されます。