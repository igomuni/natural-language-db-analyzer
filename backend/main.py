import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
import psycopg2 
import pandas as pd
import numpy as np

# --- 初期設定 ---
load_dotenv()

try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
except Exception as e:
    print(f"APIキーの設定中にエラーが発生しました: {e}")

DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI(
    title="Natural Language DB Analyzer API",
    description="自然言語の質問を解釈し、データベースを分析して結果を返すAPIです。",
    version="1.0.0",
)

# --- データベース接続 ---
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"データベース接続エラー: {e}")
        raise HTTPException(status_code=500, detail=f"データベースに接続できませんでした: {e}")

# --- スキーマ情報（キャッシュ）---
db_schema_info = None
try:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
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
    # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
    # 修正点: 列の解説とルールを、データの構造理解に合わせて更新
    # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
    system_prompt = f"""
あなたは、PostgreSQLデータベースを操作する優秀なSQLデータアナリストです。
`main_data` という名前のテーブルを分析し、以下のタスクを実行してください。

{schema_info}

# 主要な列の解説
- "府省庁": 事業を所管する省庁名です。
- "金額": **個別の「契約」**一件あたりの支出額です。この列がNULLの場合、その行は集計行である可能性があります。
- "支出先の合計支出額": ある**「支出先名」**に対する合計支出額です。この列がNULLの場合、その行は個別の契約明細である可能性があります。
- "事業名": 実施された事業の正式名称です。
- "支出先名": 支払いを受けた法人や、集計単位となる組織名です。

# あなたのタスク
ユーザーからの自然言語による質問を解釈し、その答えを導き出すための**PostgreSQLで実行可能なSQLクエリを1つだけ**生成してください。

# 遵守すべきルール
1. SQL内の列名は、必ずダブルクォート `"` で囲んでください。
2. **支出のランキングや比較を行う場合**:
   - ユーザーが「契約」や「入札」など、**個別の取引**について尋ねている場合は、`"金額"`列を使い、`WHERE "金額" IS NOT NULL`でフィルタリングしてください。
   - ユーザーが「合計支出」や「総額」など、**全体的な支出**について尋ねている場合は、`"支出先の合計支出額"`列を使うのがより適切です。その際は`WHERE "支出先の合計支出額" IS NOT NULL`でフィルタリングしてください。
   - どちらか判断に迷う場合は、より詳細な情報を含む`"金額"`列を優先してください。
3. ユーザーの入力には表記揺れが含まれる可能性があるため、`LIKE` 演算子と `%` を使った部分一致検索を積極的に使用してください。
   - 例: `WHERE "府省庁" LIKE '%こども家庭庁%'`
4. `SUM` や `COUNT` などの集計関数を使用する場合は、`AS` を使って結果の列に分かりやすい別名（例: `AS "合計金額"`）を付けてください。
5. 回答には、SQLクエリ以外の説明、前置き、後書きを含めないでください。
6. SQLクエリは、```sql ... ``` のようにマークダウンのコードブロックで囲んで出力してください。
"""
    full_prompt = f"{system_prompt}\n\n# ユーザーの質問\n{user_question}"
    return full_prompt


# --- APIエンドポイントの定義 ---
class QuestionRequest(BaseModel):
    question: str

@app.get("/")
def read_root():
    return {"message": "Backend server is running!"}

@app.post("/analyze")
def analyze_data(request: QuestionRequest):
    user_question = request.question
    if not user_question: raise HTTPException(status_code=400, detail="質問が空です。")
    if not db_schema_info or not model: raise HTTPException(status_code=500, detail="サーバーの初期設定が完了していません。")
    prompt = create_prompt(user_question, db_schema_info)
    try:
        response = model.generate_content(prompt)
        generated_sql = response.text.strip().replace("```sql", "").replace("```", "").strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQLの生成中にエラーが発生しました: {e}")
    try:
        with get_db_connection() as conn:
            result_df = pd.read_sql_query(generated_sql, conn)
        result_json = result_df.replace({pd.NA: None, np.nan: None}).to_dict(orient='records')
        return {"generated_sql": generated_sql, "result": result_json}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SQLの実行に失敗しました: {e}\n生成されたSQL: {generated_sql}")