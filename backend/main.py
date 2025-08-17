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
    description="Receives a SQL query, executes it, and returns the result.",
    version="2.0.0",
)

# --- データベース接続 ---
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"データベース接続エラー: {e}")
        raise HTTPException(status_code=500, detail="データベースに接続できませんでした。")

# --- APIエンドポイントの定義 ---
class SQLRequest(BaseModel):
    sql_query: str

@app.get("/")
def read_root():
    return {"message": "Secure SQL Runner is running!"}

@app.post("/execute-sql")
def execute_sql_endpoint(request: SQLRequest):
    sql_query = request.sql_query
    if not sql_query:
        raise HTTPException(status_code=400, detail="SQLクエリが空です。")
    
    # セキュリティ: SELECT文以外は基本許可しない
    if not sql_query.strip().upper().startswith("SELECT"):
        raise HTTPException(status_code=403, detail="実行できるのはSELECT文のみです。")

    try:
        with get_db_connection() as conn:
            result_df = pd.read_sql_query(sql_query, conn)
        result_json = result_df.replace({pd.NA: None, np.nan: None}).to_dict(orient='records')
        return {"result": result_json}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SQLの実行に失敗しました: {e}")