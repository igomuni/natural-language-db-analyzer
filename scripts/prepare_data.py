import os
import requests
import zipfile
import io
import pandas as pd
import duckdb

# --- 設定項目 ---
# TODO: 対象のZIPファイルのURLと、中に入っているCSVのファイル名を指定してください
DATA_URL = "https://rssystem.go.jp/files/2024/rs/5-1_RS_2024_%E6%94%AF%E5%87%BA%E5%85%88_%E6%94%AF%E5%87%BA%E6%83%85%E5%A0%B1.zip"
# ZIPファイル内のCSVファイル名（実際のファイル名に合わせて変更が必要な場合があります）
CSV_FILE_NAME = "5-1_RS_2024_支出先_支出情報.csv" 
DB_DIR = "data"
DB_FILE = os.path.join(DB_DIR, "review.db")
TABLE_NAME = "main_data"

def prepare_database():
    """
    データのダウンロード、展開、DuckDBへのインポートを行うメイン関数
    """
    print("データベースの準備を開始します...")

    # dataディレクトリが存在しない場合は作成
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
        print(f"ディレクトリ '{DB_DIR}' を作成しました。")

    # 1. データをダウンロード
    print(f"データのダウンロード中... URL: {DATA_URL}")
    try:
        response = requests.get(DATA_URL, stream=True)
        response.raise_for_status()  # HTTPエラーがあれば例外を発生させる
        zip_content = response.content
        print("ダウンロードが完了しました。")
    except requests.exceptions.RequestException as e:
        print(f"エラー: データのダウンロードに失敗しました。 {e}")
        return

    # 2. ZIPファイルをメモリ上で展開し、CSVをPandas DataFrameとして読み込む
    print(f"ZIPファイルを展開し、'{CSV_FILE_NAME}' を読み込んでいます...")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_content)) as z:
            with z.open(CSV_FILE_NAME) as f:
                # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
                # 変更点: 文字コードを 'cp932' から 'utf-8-sig' に変更
                # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
                df = pd.read_csv(f, encoding='utf-8-sig', low_memory=False)
        print("CSVファイルの読み込みが完了しました。")
        print("データの一部:")
        print(df.head())
    except KeyError:
        print(f"エラー: ZIPファイル内に '{CSV_FILE_NAME}' が見つかりません。ファイル名を確認してください。")
        return
    except Exception as e:
        print(f"エラー: CSVファイルの読み込み中に問題が発生しました。 {e}")
        return

    # 3. DuckDBにデータをインポート
    print(f"DuckDBデータベース '{DB_FILE}' にデータをインポートしています...")
    try:
        # データベースファイルが既に存在する場合は削除
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
            print(f"既存のデータベースファイル '{DB_FILE}' を削除しました。")

        con = duckdb.connect(database=DB_FILE, read_only=False)
        # Pandas DataFrameからテーブルを作成
        con.execute(f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM df")
        
        # データの確認
        record_count = con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
        print(f"インポートが完了しました。テーブル '{TABLE_NAME}' に {record_count} 件のレコードが登録されました。")
        
        con.close()
    except Exception as e:
        print(f"エラー: DuckDBへのインポート中に問題が発生しました。 {e}")
        return
    
    print("データベースの準備がすべて完了しました。")

if __name__ == "__main__":
    prepare_database()