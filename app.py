import os
import streamlit as st
import duckdb
import google.generativeai as genai
from dotenv import load_dotenv
import numpy as np
import pandas as pd
import random

# --- 初期設定 ---
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key: st.error("エラー: Google APIキーが設定されていません。StreamlitのSecretsに設定してください。"); st.stop()
try: genai.configure(api_key=api_key)
except Exception as e: st.error(f"APIキーの設定中にエラーが発生しました: {e}"); st.stop()
DB_FILE = os.path.join("data", "review.db")
TABLE_NAME = "main_data"

# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
# 修正点: データベース接続をキャッシュするだけのシンプルな関数に変更
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
@st.cache_resource
def get_db_connection():
    """
    リポジトリに含まれるDBファイルへの接続を確立し、キャッシュする。
    """
    if not os.path.exists(DB_FILE):
        st.error(f"データベースファイル '{DB_FILE}' が見つかりません。リポジトリに含まれているか確認してください。")
        st.stop()
    
    try:
        conn = duckdb.connect(DB_FILE, read_only=True) # 読み取り専用でOK
        return conn
    except Exception as e:
        st.error(f"データベースへの接続に失敗しました: {e}")
        st.stop()

# --- Streamlit UI ---
st.title("自然言語DB分析ツール 💬")
st.caption("行政事業レビューデータを元に、自然言語で質問できます。")

conn = get_db_connection()

# (以降のコードは、get_schema_infoの呼び出し以外はほぼ同じ)
def get_schema_info(conn):
    try:
        schema_df = conn.execute(f"DESCRIBE {TABLE_NAME};").fetchdf()
        schema_str = "テーブルスキーマ:\n"
        for _, row in schema_df.iterrows(): schema_str += f"- {row['column_name']} ({row['column_type']})\n"
        return schema_str
    except Exception as e: st.error(f"データベースのスキーマ情報取得中にエラーが発生しました: {e}"); return None

schema_info = get_schema_info(conn)
if schema_info is None:
    st.error("データベーススキーマの取得に失敗しました。アプリを再起動してみてください。")
    st.stop()

# (以降、残りのすべてのコードは変更なし)
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

try: model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e: st.error(f"Geminiモデルの読み込み中にエラーが発生しました: {e}"); st.stop()

def create_prompt(user_question, schema_info):
    system_prompt = f"""
あなたは、日本の行政事業レビューデータを分析する優秀なSQLデータアナリストです。
`{TABLE_NAME}` という名前のテーブルを持つDuckDBデータベースを操作する前提で、以下のタスクを実行してください。
{schema_info}
# 主要な列の解説
- "府省庁": 事業を所管する省庁名です。
- "局・庁": 府省庁の下の組織名です。「観光庁」や「気象庁」などはこちらの列に含まれます。
- "金額": 個別の契約の支出額（円）です。
- "事業名": 実施された事業の正式名称です。
- "支出先名": 支払いを受けた法人名です。
# あなたのタスク
ユーザーからの自然言語による質問を解釈し、その答えを導き出すための**DuckDBで実行可能なSQLクエリを1つだけ**生成してください。
# 遵守すべきルール
1. 生成するSQLは、上記のスキーマ情報と解説を正確に反映させてください。
2. **SQL内の列名は、必ずダブルクォート `"` で囲んでください。**
3. ユーザーの入力には表記揺れが含まれる可能性が非常に高いです。**`LIKE` 演算子を使った部分一致検索を積極的に使用してください。**
   - **特に重要**: 「子ども家庭庁」と質問されても `WHERE "府省庁" LIKE '%こども家庭庁%'` のように、シンプルなひらがな表記で検索してください。
4. **`SUM` や `COUNT` などの集計関数を使用する場合は、`AS` を使って結果の列に分かりやすい別名（例: `AS "合計金額"`、`AS "契約件数"`）を付けてください。**
5. 回答には、SQLクエリ以外の説明、前置き、後書きを含めないでください。
6. SQLクエリは、```sql ... ``` のようにマークダウンのコードブロックで囲んで出力してください。
"""
    full_prompt = f"{system_prompt}\n\n# ユーザーの質問\n{user_question}"
    return full_prompt

def execute_sql(conn, sql_query):
    try:
        result_df = conn.execute(sql_query).fetchdf()
        return result_df
    except Exception as e:
        st.error(f"SQLの実行中にエラーが発生しました: {e}"); st.error(f"実行しようとしたSQL: \n```sql\n{sql_query}\n```"); return None

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

st.markdown("""<style>div[data-testid="stButton"] > button {text-align: left !important; width: 100%; justify-content: flex-start !important;}</style>""", unsafe_allow_html=True)

def set_question_text(question): st.session_state.user_question_input = question

with st.expander("質問のヒント (クリックして表示)"):
    st.info("以下のような質問ができます。クリックすると入力欄にコピーされます。")
    sample_questions = generate_sample_questions(5)
    for q in sample_questions: st.button(q, on_click=set_question_text, args=(q,), key=f"btn_{q}")

with st.form("question_form"):
    user_question = st.text_area("分析したいことを日本語で入力してください:", key="user_question_input", placeholder="例: こども家庭庁による支出を、金額が大きい順に5件教えて。")
    submitted = st.form_submit_button("質問する")

if submitted and user_question:
    with st.spinner("AIがSQLを生成中..."):
        prompt = create_prompt(user_question, schema_info)
        try:
            response = model.generate_content(prompt)
            generated_sql = response.text.strip().replace("```sql", "").replace("```", "").strip()
            st.success("SQLの生成が完了しました！")
            with st.expander("AIによって生成されたSQLクエリ"): st.code(generated_sql, language="sql")
        except Exception as e: st.error(f"SQLの生成中にエラーが発生しました: {e}"); st.stop()

    with st.spinner("データベースを検索中..."):
        result_df = execute_sql(conn, generated_sql)

    if result_df is not None:
        st.success("データの取得が完了しました！")
        if result_df.shape == (1, 1) and pd.api.types.is_numeric_dtype(result_df.iloc[0,0]):
            value = result_df.iloc[0, 0]
            label = result_df.columns[0]
            if pd.isna(value):
                st.metric(label=label, value="―", delta="該当するデータがありませんでした", delta_color="inverse")
            else:
                is_monetary = '金額' in generated_sql or '金額' in label
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