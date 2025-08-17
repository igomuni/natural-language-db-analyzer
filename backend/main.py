import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import psycopg2
import pandas as pd
import numpy as np

# --- 初期設定 ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
app = FastAPI(
    title="Secure SQL Runner API",
    description="Receives a SQL query, executes it against the database, and returns the result.",
    version="2.0.0", # Version up!
)

# --- データベース接続 ---
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"データベース接続エラー: {e}")
        raise HTTPException(status_code=500, detail=f"データベースに接続できませんでした: {e}")

# --- APIエンドポイントの定義 ---

# Pydanticモデル: フロントエンドから受け取るリクエストのデータ形式を定義
class SQLRequest(BaseModel):
    sql_query: str

@app.get("/")
def read_root():
    # Health check endpoint
    return {"message": "Secure SQL Runner is running!"}

@app.post("/execute-sql")
def execute_sql_endpoint(request: SQLRequest):
    """
    SQLクエリを受け取り、データベースで実行して結果を返す
    """
    sql_query = request.sql_query

    if not sql_query:
        raise HTTPException(status_code=400, detail="SQLクエリが空です。")
    
    # 簡単なセキュリティチェック: SELECT文以外は許可しない (簡易的なインジェクション対策)
    if not sql_query.strip().upper().startswith("SELECT"):
        raise HTTPException(status_code=403, detail="実行できるのはSELECT文のみです。")

    try:
        with get_db_connection() as conn:
            result_df = pd.read_sql_query(sql_query, conn)
        
        result_json = result_df.replace({pd.NA: None, np.nan: None}).to_dict(orient='records')

        return {
            "result": result_json
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SQLの実行に失敗しました: {e}")