import os
import streamlit as st
import pandas as pd
import numpy as np
import requests 
import random
import time
import google.generativeai as genai
from google.api_core import exceptions
from dotenv import load_dotenv 
import psycopg2

# --- 初期設定 ---
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY") 
if not api_key: st.error("エラー: Google APIキーが設定されていません。"); st.stop()
try: genai.configure(api_key=api_key)
except Exception as e: st.error(f"APIキーの設定中にエラーが発生しました: {e}"); st.stop()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL: st.error("エラー: DATABASE_URLが設定されていません。"); st.stop()
TABLE_NAME = "main_data"

# --- データベース関連のコア関数 ---
@st.cache_resource
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        st.error(f"データベースへの接続に失敗しました: {e}")
        st.stop()

conn = get_db_connection()

@st.cache_data(ttl=3600)
def get_schema_info(_conn):
    try:
        with _conn.cursor() as cur:
            cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{TABLE_NAME}';")
            schema_raw = cur.fetchall()
        schema_str = "テーブルスキーマ:\n"
        for item in schema_raw:
            schema_str += f"- {item[0]} ({item[1]})\n"
        return schema_str
    except Exception as e:
        st.error(f"データベースのスキーマ情報取得中にエラーが発生しました: {e}")
        return None

def execute_sql(_conn, sql_query: str):
    try:
        result_df = pd.read_sql_query(sql_query, _conn)
        return result_df
    except Exception as e:
        st.error(f"SQLの実行に失敗しました: {e}")
        return None

# --- LLMロジック ---
try: model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e: st.error(f"Geminiモデルの読み込み中にエラーが発生しました: {e}"); st.stop()

def create_prompt_for_llm(user_question, schema_info):
    system_prompt = f"""
あなたは、PostgreSQLデータベースを操作する優秀なSQLデータアナリストです。
`{TABLE_NAME}` という名前のテーブルを分析し、以下のタスクを実行してください。
{schema_info}
# 主要な列の解説
- "金額", "支出先の合計支出額": これらの金額列には、データが存在しないNULL値が含まれています。
# あなたのタスク
ユーザーからの自然言語による質問を解釈し、その答えを導き出すための**PostgreSQLで実行可能なSQLクエリを1つだけ**生成してください。
# 遵守すべきルール
1. SQL内の列名は、必ずダブルクォート `"` で囲んでください。
2. **計算の場合**: `NULL`を`0`として扱うため `COALESCE(column, 0)` を使用してください。
3. **フィルタリング/ランキングの場合**: `WHERE "列名" IS NOT NULL` を使用してください。
4. ユーザーの入力の表記揺れを吸収するため、`LIKE` 演算子を使用してください。
5. 集計関数には `AS` を使って分かりやすい別名を付けてください。
6. 回答には、SQLクエリ以外の説明を含めず、SQLクエリのみを出力してください。
7. SQLクエリは、```sql ... ``` のようにマークダウンのコードブロックで囲んで出力してください。
"""
    return f"{system_prompt}\n\n# ユーザーの質問\n{user_question}"

# --- UI補助関数とデータ ---
def format_japanese_currency(num):
    if not isinstance(num, (int, float, np.number)) or num == 0: return "0円"
    num = int(num); units = {'兆': 10**12, '億': 10**8, '万': 10**4};
    if num < 10000: return f"{num:,}円"
    result = ""; remainder = num;
    for unit, value in units.items():
        if remainder >= value: quotient = int(remainder // value); result += f"{quotient}{unit}"; remainder %= value
    if remainder > 0:
        if num >= 10000 and result != "": pass
        else: result += f"{remainder}円"
    return result + "円"

MINISTRIES = ['こども家庭庁', 'カジノ管理委員会', 'スポーツ庁', 'デジタル庁', '中央労働委員会', '個人情報保護委員会', '公安調査庁', '公害等調整委員会', '公正取引委員会', '内閣官房', '内閣府', '厚生労働省', '原子力規制委員会', '国土交通省', '国土交通省　気象庁', '国土交通省　海上保安庁', '国土交通省　観光庁', '国土交通省　運輸安全委員会', '国税庁', '外務省', '復興庁', '文化庁', '文部科学省', '林野庁', '水産庁', '法務省', '消費者庁', '消防庁', '特許庁', '環境省', '経済産業省', '総務省', '警察庁', '財務省', '農林水産省', '金融庁', '防衛省']
QUESTION_TEMPLATES = ["{ministry}の支出額の合計はいくらですか？", "{ministry}が最も多く支出している事業名トップ3を教えてください。", "{ministry}への支出で、契約相手が多い法人名を5つリストアップしてください。", "{ministry}関連の事業で、入札者数が1だった契約の件数を教えて。", "{ministry}による支出を、金額が大きい順に5件、事業名と支出先名、金額を教えて。", "支出額が10億円を超えている契約のうち、{ministry}が関わっているものをリストアップして。"]
SAMPLE_SQLS = {"全データの最初の5件を表示": 'SELECT *\nFROM "main_data"\nLIMIT 5;', "府省庁の一覧を取得": 'SELECT DISTINCT "府省庁"\nFROM "main_data"\nWHERE "府省庁" IS NOT NULL\nORDER BY "府省庁";', "デジタル庁に関連する契約トップ5 (金額)": 'SELECT "事業名", "支出先名", "金額"\nFROM "main_data"\nWHERE "府省庁" LIKE \'%デジタル庁%\'\n  AND "金額" IS NOT NULL\nORDER BY "金額" DESC\nLIMIT 5;', "支出先の合計支出額トップ10": 'SELECT "支出先名", "支出先の合計支出額"\nFROM "main_data"\nWHERE "支出先の合計支出額" IS NOT NULL\nORDER BY "支出先の合計支出額" DESC\nLIMIT 10;', "府省庁ごとの契約件数トップ10": 'SELECT "府省庁", COUNT(*) AS "契約件数"\nFROM "main_data"\nWHERE "府省庁" IS NOT NULL\nGROUP BY "府省庁"\nORDER BY "契約件数" DESC\nLIMIT 10;'}

def generate_sample_questions(num_questions=5):
    samples = []
    for _ in range(num_questions): ministry = random.choice(MINISTRIES); template = random.choice(QUESTION_TEMPLATES); samples.append(template.format(ministry=ministry))
    return samples

# --- Streamlit UI 本体 ---
st.set_page_config(layout="wide")
st.title("自然言語DB分析ツール 💬")
st.caption("行政事業レビューデータを元に、自然言語またはSQLで直接分析できます。")

db_schema_info = get_schema_info(conn)
if not db_schema_info: st.error("データベーススキーマの取得に失敗しました。アプリケーションを再起動してみてください。"); st.stop()

tab1, tab2, tab3 = st.tabs(["**自然言語で分析 (AI)**", "**SQLを直接実行**", "**他のLLM用プロンプト**"])

with tab1:
    st.header("AIに分析を依頼する")
    st.markdown("""<style>div[data-testid="stButton"] > button {text-align: left !important; width: 100%; justify-content: flex-start !important;}</style>""", unsafe_allow_html=True)
    def set_question_text(question): st.session_state.user_question_input = question
    with st.expander("質問のヒント (クリックして表示)"):
        st.info("以下のような質問ができます。クリックすると入力欄にコピーされます。")
        sample_questions = generate_sample_questions(5)
        for q in sample_questions: st.button(q, on_click=set_question_text, args=(q,), key=f"btn_q_{q}")
    with st.form("question_form"):
        user_question = st.text_area("分析したいことを日本語で入力してください:", key="user_question_input", placeholder="例: こども家庭庁による支出を、金額が大きい順に5件教えて。")
        submitted_q = st.form_submit_button("質問する")

    if submitted_q and user_question:
        generated_sql = ""
        result_df = None
        error_message = None
        
        with st.spinner("AIがSQLを生成中..."):
            prompt = create_prompt_for_llm(user_question, db_schema_info)
            try:
                response = model.generate_content(prompt)
                generated_sql = response.text.strip().replace("```sql", "").replace("```", "").strip()
            except exceptions.ResourceExhausted as e:
                error_message = {
                    "title": "AIへのリクエストが無料利用枠の上限に達しました。",
                    "body": "これはアプリの仕様です。開発者の方は、Google Cloudで請求先アカウントを有効にすることで、この制限を緩和できます。"
                }
            except Exception as e:
                error_message = {"title": f"SQLの生成中に予期せぬエラーが発生しました: {e}", "body": None}

        if not error_message and generated_sql:
            st.success("SQLの生成が完了しました！")
            with st.spinner("データベースでSQLを実行中..."):
                result_df = execute_sql(conn, generated_sql)
        
        st.subheader("分析結果")
        if error_message:
            st.error(error_message["title"])
            if error_message["body"]:
                st.info(error_message["body"])
        elif result_df is not None:
            with st.expander("AIによって生成されたSQLクエリ"): st.code(generated_sql, language="sql")
            if result_df.empty: st.warning("分析結果が0件でした。")
            elif result_df.shape == (1, 1) and pd.api.types.is_numeric_dtype(result_df.iloc[0,0]):
                value = result_df.iloc[0, 0]; label = result_df.columns[0]
                if pd.isna(value): st.metric(label=label, value="―", delta="該当なし", delta_color="inverse")
                else:
                    is_monetary = '金額' in label or '額' in label
                    if is_monetary: st.metric(label=label, value=f"{int(value):,} 円", delta=format_japanese_currency(value), delta_color="off")
                    else: st.metric(label=label, value=f"{int(value):,} 件")
            else:
                st.write(f"**分析結果:** {len(result_df)} 件"); st.dataframe(result_df.style.format(precision=0, thousands=","))
        elif submitted_q:
            st.warning("処理中にエラーが発生しました。詳細は上記のメッセージをご確認ください。")

with tab2:
    st.header("SQLを直接実行して分析する")
    def set_sql_text(sql): st.session_state.sql_input = sql
    with st.expander("サンプルSQL (クリックして表示)"):
        st.info("以下のようなSQLクエリを試せます。クリックすると入力欄にコピーされます。")
        for desc, sql in SAMPLE_SQLS.items(): st.button(desc, on_click=set_sql_text, args=(sql,), key=f"btn_sql_{desc}")
    with st.form("sql_form"):
        sql_query_input = st.text_area("実行するSELECT文を入力してください:", height=200, key="sql_input", placeholder='SELECT * FROM "main_data" LIMIT 5;')
        submitted_sql = st.form_submit_button("SQLを実行")
    if submitted_sql and sql_query_input:
        st.subheader("実行結果")
        with st.spinner("データベースでSQLを実行中..."):
            result_df = execute_sql(conn, sql_query_input)
        if result_df is not None:
            st.success("データの取得が完了しました！")
            st.write(f"**実行結果:** {len(result_df)} 件"); st.dataframe(result_df.style.format(precision=0, thousands=","))

with tab3:
    st.header("他のLLMで試すためのプロンプトを生成")
    st.info("以下のプロンプトをコピーして、ChatGPTやClaudeなどの他のLLMに貼り付けることで、このデータベースに対するSQLを生成させることができます。")
    
    prompt_for_others = create_prompt_for_llm("[ここにあなたの質問を入れてください]", db_schema_info)
    
    st.text_area("生成されたプロンプト:", prompt_for_others, height=400)
    st.caption("`[ここにあなたの質問を入れてください]` の部分を、あなたの聞きたいことに書き換えてからコピーしてください。")