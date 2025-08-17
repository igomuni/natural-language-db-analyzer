import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
import psycopg2 # PostgreSQLに接続するためのライブラリ (DBドライバ)
import pandas as pd
import numpy as np

# --- 初期設定 ---

# .envファイルから環境変数を読み込む (ローカル開発用)
# Renderのような本番環境では、環境変数はダッシュボードから設定される
load_dotenv()

# Google Gemini APIキーの設定
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
except Exception as e:
    print(f"APIキーの設定中にエラーが発生しました: {e}")

# SupabaseのデータベースURLを取得
DATABASE_URL = os.getenv("DATABASE_URL")

# FastAPIアプリケーションのインスタンスを作成
# titleやdescriptionは、自動生成されるAPIドキュメント(/docs)に表示される
app = FastAPI(
    title="Natural Language DB Analyzer API",
    description="自然言語の質問を解釈し、データベースを分析して結果を返すAPIです。",
    version="1.0.0",
)

# --- データベース関連のロジック ---

def get_db_connection():
    """Supabase(PostgreSQL)へのデータベース接続を確立する"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"データベース接続エラー: {e}")
        raise HTTPException(status_code=500, detail=f"データベースに接続できませんでした: {e}")

# サーバー起動時に一度だけスキーマ情報を取得し、メモリにキャッシュしておく
# これにより、リクエスト毎にDBに問い合わせる必要がなくなり、パフォーマンスが向上する
db_schema_info = None
try:
    # withステートメントを使うことで、接続が自動的にクローズされる
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # information_schemaは、DBのメタデータ(列名、型など)を格納する標準的なテーブル
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'main_data';
            """)
            schema_info_raw = cur.fetchall()
            schema_str = "テーブルスキーマ:\n"
            for col_name, data_type in schema_info_raw:
                schema_str += f"- {col_name} ({data_type})\n"
            db_schema_info = schema_str
except Exception as e:
    print(f"起動時のスキーマ情報取得に失敗しました: {e}")


# --- LLM関連のロジック ---

try:
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"Geminiモデルの読み込み中にエラーが発生しました: {e}")

def create_prompt(user_question, schema_info):
    """ユーザーの質問とスキーマ情報から、LLMに投げるプロンプトを生成する"""
    system_prompt = f"""
あなたは、PostgreSQLデータベースを操作する優秀なSQLデータアナリストです。
`main_data` という名前のテーブルを分析し、以下のタスクを実行してください。

{schema_info}

# 主要な列の解説
- "府省庁": 事業を所管する省庁名です。
- "金額": 個別の契約の支出額（円）です。
- "事業名": 実施された事業の正式名称です。
- "支出先名": 支払いを受けた法人名です。

# あなたのタスク
ユーザーからの自然言語による質問を解釈し、その答えを導き出すための**PostgreSQLで実行可能なSQLクエリを1つだけ**生成してください。

# 遵守すべきルール
1. SQL内の列名は、必ずダブルクォート `"` で囲んでください。
2. ユーザーの入力には表記揺れが含まれる可能性があるため、`LIKE` 演算子と `%` を使った部分一致検索を積極的に使用してください。
   - 例: ユーザーが「子ども家庭庁」と尋ねた場合、`WHERE "府省庁" LIKE '%こども家庭庁%'` のように記述します。
3. `SUM` や `COUNT` などの集計関数を使用する場合は、`AS` を使って結果の列に分かりやすい別名（例: `AS "合計金額"`）を付けてください。
4. 回答には、SQLクエリ以外の説明、前置き、後書きを含めないでください。
5. SQLクエリは、```sql ... ``` のようにマークダウンのコードブロックで囲んで出力してください。
"""
    full_prompt = f"{system_prompt}\n\n# ユーザーの質問\n{user_question}"
    return full_prompt


# --- APIエンドポイントの定義 ---

# Pydanticモデル: フロントエンドから受け取るリクエストのデータ形式を定義
class QuestionRequest(BaseModel):
    question: str

@app.get("/")
def read_root():
    """サーバーが正常に起動しているか確認するためのルートエンドポイント"""
    return {"message": "Backend server is running!"}

@app.post("/analyze")
def analyze_data(request: QuestionRequest):
    """
    自然言語の質問を受け取り、分析結果を返すメインのエンドポイント
    """
    user_question = request.question

    if not user_question:
        raise HTTPException(status_code=400, detail="質問が空です。")
    
    if not db_schema_info or not model:
        raise HTTPException(status_code=500, detail="サーバーの初期設定(スキーマ or モデル)が完了していません。")

    # 1. プロンプトを作成
    prompt = create_prompt(user_question, db_schema_info)

    # 2. LLMにSQLを生成させる
    try:
        response = model.generate_content(prompt)
        generated_sql = response.text.strip().replace("```sql", "").replace("```", "").strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQLの生成中にエラーが発生しました: {e}")

    # 3. データベースでSQLを実行
    try:
        with get_db_connection() as conn:
            # PandasはDB接続とSQL文を渡すだけで、結果を直接DataFrameに変換できる
            result_df = pd.read_sql_query(generated_sql, conn)
        
        # DataFrameをJSON形式(レコードのリスト)に変換して返す
        # JSONではNaN(Not a Number)は扱えないため、None(null)に置換する
        result_json = result_df.replace({pd.NA: None, np.nan: None}).to_dict(orient='records')

        # 成功した場合は、生成されたSQLと結果のJSONを返す
        return {
            "generated_sql": generated_sql,
            "result": result_json
        }
    except Exception as e:
        # SQL実行エラーの場合は、どのSQLで失敗したか分かるように情報を付加して返す
        raise HTTPException(status_code=400, detail=f"SQLの実行に失敗しました: {e}\n生成されたSQL: {generated_sql}")