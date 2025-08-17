import os
import streamlit as st
import pandas as pd
import numpy as np
import requests 
import random
import time
import google.generativeai as genai # AIライブラリをフロントエンドに再インポート
from dotenv import load_dotenv # ローカルテスト用にdotenvを追加

# --- 初期設定 ---
load_dotenv() # ローカルの.envを読み込む
# Streamlit CloudではSecretsから、ローカルでは.envからAPIキーを取得
api_key = os.getenv("GOOGLE_API_KEY") 
if not api_key: st.error("エラー: Google APIキーが設定されていません。"); st.stop()
try: genai.configure(api_key=api_key)
except Exception as e: st.error(f"APIキーの設定中にエラーが発生しました: {e}"); st.stop()

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
TABLE_NAME = "main_data" # プロンプトで使うので定義

# --- データベース/バックエンド関連 ---

# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
# 修正点: スキーマ情報をフロントエンドでキャッシュする
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
@st.cache_data(ttl=3600) # 1時間キャッシュ
def get_schema_from_backend():
    """バックエンドに固定のクエリを送り、スキーマ情報を取得する"""
    # この関数はバックエンドに負荷をかけないよう、結果をキャッシュする
    # バックエンド側でスキーマ取得用のエンドポイントを作るのが理想だが、今回は簡易的にSQL実行エンドポイントを使う
    sql_to_get_schema = "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'main_data';"
    
    api_endpoint = f"{BACKEND_URL}/execute-sql"
    payload = {"sql_query": sql_to_get_schema}
    
    try:
        response = requests.post(api_endpoint, json=payload, timeout=60)
        response.raise_for_status()
        schema_raw = response.json().get("result", [])
        
        schema_str = "テーブルスキーマ:\n"
        for item in schema_raw:
            schema_str += f"- {item['column_name']} ({item['data_type']})\n"
        return schema_str
    except Exception as e:
        st.error(f"バックエンドからスキーマ情報の取得に失敗しました: {e}")
        return None

def execute_sql_on_backend(sql_query: str):
    """バックエンドの /execute-sql エンドポイントを呼び出す"""
    api_endpoint = f"{BACKEND_URL}/execute-sql"
    payload = {"sql_query": sql_query}
    
    try:
        response = requests.post(api_endpoint, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"バックENDサーバーへの接続に失敗しました: {e}")
        return None

# --- LLMロジック (バックエンドからフロントエンドに移動) ---
try: model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e: st.error(f"Geminiモデルの読み込み中にエラーが発生しました: {e}"); st.stop()

def create_prompt(user_question, schema_info):
    # このプロンプトは、以前バックエンドにあったものとほぼ同じ
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
7. SQLクエリは、```sql ... ``` のようにマークダウンで囲んで出力してください。
"""
    full_prompt = f"{system_prompt}\n\n# ユーザーの質問\n{user_question}"
    return full_prompt


# --- Streamlit UI 本体 ---
st.title("自然言語DB分析ツール 💬")
st.caption("行政事業レビューデータを元に、自然言語で質問できます。")

# アプリ起動時に一度だけスキーマ情報を取得
db_schema_info = get_schema_from_backend()

if not db_schema_info:
    st.error("データベースのスキーマ情報を取得できませんでした。バックエンドが正しく動作しているか確認してください。")
    st.stop()

# (以降のUI部分は、呼び出す関数が変わる以外はほぼ同じ)
# (念のため完全なコードを記載)

def format_japanese_currency(num):
    if not isinstance(num, (int, float, np.number)) or num == 0: return "0円"
    num = int(num)
    units = {'兆': 10**12, '億': 10**8, '万': 10**4}
    if num < 10000: return f"{num:,}円"
    result = ""
    remainder = num
    for unit, value in units.items():
        if remainder >= value:
            quotient = int(remainder // value)
            result += f"{quotient}{unit}"
            remainder %= value
    if remainder > 0:
        if num >= 10000 and result != "": pass
        else: result += f"{remainder}円"
    return result + "円"

MINISTRIES = [
    'こども家庭庁', 'カジノ管理委員会', 'スポーツ庁', 'デジタル庁', '中央労働委員会',
    '個人情報保護委員会', '公安調査庁', '公害等調整委員会', '公正取引委員会', '内閣官房',
    '内閣府', '厚生労働省', '原子力規制委員会', '国土交通省', '国土交通省　気象庁',
    '国土交通省　海上保安庁', '国土交通省　観光庁', '国土交通省　運輸安全委員会',
    '国税庁', '外務省', '復興庁', '文化庁', '文部科学省', '林野庁', '水産庁',
    '法務省', '消費者庁', '消防庁', '特許庁', '環境省', '経済産業省', '総務省',
    '警察庁', '財務省', '農林水産省', '金融庁', '防衛省'
]
QUESTION_TEMPLATES = [
    "{ministry}の支出額の合計はいくらですか？",
    "{ministry}が最も多く支出している事業名トップ3を教えてください。",
    "{ministry}への支出で、契約相手が多い法人名を5つリストアップしてください。",
    "{ministry}関連の事業で、入札者数が1だった契約の件数を教えて。",
    "{ministry}による支出を、金額が大きい順に5件、事業名と支出先名、金額を教えて。",
    "支出額が10億円を超えている契約のうち、{ministry}が関わっているものをリストアップして。",
]
def generate_sample_questions(num_questions=5):
    samples = []
    for _ in range(num_questions):
        ministry = random.choice(MINISTRIES)
        template = random.choice(QUESTION_TEMPLATES)
        samples.append(template.format(ministry=ministry))
    return samples

st.markdown("""<style>div[data-testid="stButton"] > button {text-align: left !important; width: 100%; justify-content: flex-start !important;}</style>""", unsafe_allow_html=True)
def set_question_text(question):
    st.session_state.user_question_input = question
with st.expander("質問のヒント (クリックして表示)"):
    st.info("以下のような質問ができます。クリックすると入力欄にコピーされます。")
    sample_questions = generate_sample_questions(5)
    for q in sample_questions:
        st.button(q, on_click=set_question_text, args=(q,), key=f"btn_{q}")
with st.form("question_form"):
    user_question = st.text_area("分析したいことを日本語で入力してください:", 
                                 key="user_question_input",
                                 placeholder="例: こども家庭庁による支出を、金額が大きい順に5件教えて。")
    submitted = st.form_submit_button("質問する")

if submitted and user_question:
    generated_sql = ""
    with st.spinner("AIがSQLを生成中..."):
        prompt = create_prompt(user_question, db_schema_info)
        try:
            response = model.generate_content(prompt)
            generated_sql = response.text.strip().replace("```sql", "").replace("```", "").strip()
            st.success("SQLの生成が完了しました！")
        except Exception as e:
            st.error(f"SQLの生成中にエラーが発生しました: {e}")
            st.stop()
    
    with st.spinner("バックエンドサーバーでSQLを実行中..."):
        api_response = execute_sql_on_backend(generated_sql)

    if api_response:
        st.success("データの取得が完了しました！")
        
        with st.expander("AIによって生成され、バックエンドで実行されたSQLクエリ"):
            st.code(generated_sql, language="sql")
            
        result_data = api_response.get("result", [])
        result_df = pd.DataFrame(result_data)
        
        if result_df.empty:
            st.warning("分析結果が0件でした。")
        elif result_df.shape == (1, 1) and pd.api.types.is_numeric_dtype(result_df.iloc[0,0]):
            value = result_df.iloc[0, 0]
            label = result_df.columns[0]
            if pd.isna(value):
                st.metric(label=label, value="―", delta="該当するデータがありませんでした", delta_color="inverse")
            else:
                is_monetary = '金額' in label or '額' in label
                if is_monetary:
                    formatted_comma_value = f"{int(value):,} 円"
                    formatted_japanese_value = format_japanese_currency(value)
                    st.metric(label=label, value=formatted_comma_value, delta=formatted_japanese_value, delta_color="off")
                else:
                    formatted_value = f"{int(value):,} 件"
                    st.metric(label=label, value=formatted_value)
        else:
            st.write(f"**分析結果:** {len(result_df)} 件")
            st.dataframe(result_df.style.format(precision=0, thousands=","))