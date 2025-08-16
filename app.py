import os
import streamlit as st
import duckdb
import google.generativeai as genai
from dotenv import load_dotenv
import numpy as np # numpyをインポート
import pandas as pd # pandasをインポート

# --- 初期設定 ---

# .envファイルから環境変数を読み込む
load_dotenv()

# Google Gemini APIキーの設定
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    st.error("エラー: Google APIキーが設定されていません。.envファイルを確認してください。")
    st.stop()

try:
    genai.configure(api_key=api_key)
except Exception as e:
    st.error(f"APIキーの設定中にエラーが発生しました: {e}")
    st.stop()


# データベースファイルのパス
DB_FILE = os.path.join("data", "review.db")
TABLE_NAME = "main_data"

# --- LLMとプロンプトの設定 ---

# Geminiモデルの初期化
try:
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"Geminiモデルの読み込み中にエラーが発生しました: {e}")
    st.stop()


def get_schema_info():
    """データベースからスキーマ情報を取得する"""
    if not os.path.exists(DB_FILE):
        return None
    try:
        conn = duckdb.connect(DB_FILE)
        schema_df = conn.execute(f"DESCRIBE {TABLE_NAME};").fetchdf()
        conn.close()
        # プロンプト用にスキーマ情報を整形
        schema_str = "テーブルスキーマ:\n"
        for _, row in schema_df.iterrows():
            schema_str += f"- {row['column_name']} ({row['column_type']})\n"
        return schema_str
    except Exception as e:
        st.error(f"データベースのスキーマ情報取得中にエラーが発生しました: {e}")
        return None

def create_prompt(user_question, schema_info):
    """LLMに投げるためのプロンプトを生成する"""
    system_prompt = f"""
あなたは、日本の行政事業レビューデータを分析する優秀なSQLデータアナリストです。
`{TABLE_NAME}` という名前のテーブルを持つDuckDBデータベースを操作する前提で、以下のタスクを実行してください。

{schema_info}

# 主要な列の解説
- "府省庁": 事業を所管する省庁名です。ユーザーが「〇〇省の〜」「〇〇庁が〜」と言及した場合は、この列を `WHERE` 句で使ってください。
- "金額": 個別の契約の支出額（円）です。ユーザーが「支出額」「費用」「コスト」「予算」について尋ねた場合は、この列を `SUM()` や `AVG()` などの集計対象としてください。
- "事業名": 実施された事業の正式名称です。
- "支出先名": 支払いを受けた法人名です。

# あなたのタスク
ユーザーからの自然言語による質問を解釈し、その答えを導き出すための**DuckDBで実行可能なSQLクエリを1つだけ**生成してください。

# 遵守すべきルール
1. 生成するSQLは、上記のスキーマ情報と解説を正確に反映させてください。
2. **SQL内の列名は、必ずダブルクォート `"` で囲んでください。**
3. ユーザーの入力には表記揺れが含まれる可能性が非常に高いです。**完全一致(`=`)ではなく、`LIKE` 演算子を使った部分一致検索を積極的に使用してください。**
   - **特に重要**: ユーザーが「子ども家庭庁」や「子供家庭庁」と入力した場合でも、データベース内の正式名称は「こども家庭庁」である可能性が高いです。このような場合は `WHERE "府省庁" LIKE '%こども家庭庁%'` のように、最も一般的でシンプルなひらがな表記を使って検索するクエリを生成してください。
4. 回答には、SQLクエリ以外の説明、前置き、後書きを含めないでください。
5. SQLクエリは、```sql ... ``` のようにマークダウンのコードブロックで囲んで出力してください。
"""
    
    full_prompt = f"{system_prompt}\n\n# ユーザーの質問\n{user_question}"
    return full_prompt

def execute_sql(sql_query):
    """DuckDBでSQLクエリを実行し、結果をDataFrameで返す"""
    try:
        conn = duckdb.connect(DB_FILE)
        result_df = conn.execute(sql_query).fetchdf()
        conn.close()
        return result_df
    except Exception as e:
        st.error(f"SQLの実行中にエラーが発生しました: {e}")
        st.error(f"実行しようとしたSQL: \n```sql\n{sql_query}\n```")
        return None

# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
# 新機能: 数値を日本語の通貨単位（兆・億・万）に変換する関数
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
def format_japanese_currency(num):
    """数値を「X兆Y億Z万円」の形式にフォーマットする"""
    if not isinstance(num, (int, float, np.number)) or num == 0:
        return "0円"
    
    num = int(num)
    
    units = {
        '兆': 10**12,
        '億': 10**8,
        '万': 10**4,
    }
    
    if num < 10000:
        return f"{num:,}円"

    result = ""
    remainder = num
    
    for unit, value in units.items():
        if remainder >= value:
            quotient = int(remainder // value)
            result += f"{quotient}{unit}"
            remainder %= value
            
    if remainder > 0:
        # 兆や億の下に万円以下の端数がある場合
        if num >= 10000 and result != "":
             pass # 例: 1兆1円のような表示は複雑なので、大きな単位を優先
        else:
             result += f"{remainder}円"

    return result + "円"


# --- Streamlit UI ---

st.title("自然言語DB分析ツール 💬")
st.caption("行政事業レビューデータを元に、自然言語で質問できます。")

# データベースの存在チェック
schema_info = get_schema_info()
if schema_info is None:
    st.error(f"データベースファイル '{DB_FILE}' が見つかりません。")
    st.warning("`scripts/prepare_data.py` を実行して、データベースを準備してください。")
    st.stop()

# 質問の入力フォーム
with st.form("question_form"):
    user_question = st.text_area("分析したいことを日本語で入力してください:", 
                                 placeholder="例: こども家庭庁による支出を、金額が大きい順に5件教えて。")
    submitted = st.form_submit_button("質問する")

if submitted and user_question:
    with st.spinner("AIがSQLを生成中..."):
        prompt = create_prompt(user_question, schema_info)
        try:
            response = model.generate_content(prompt)
            generated_sql = response.text.strip().replace("```sql", "").replace("```", "").strip()
            st.success("SQLの生成が完了しました！")
            
            with st.expander("AIによって生成されたSQLクエリ"):
                st.code(generated_sql, language="sql")
        except Exception as e:
            st.error(f"SQLの生成中にエラーが発生しました: {e}")
            st.stop()

    with st.spinner("データベースを検索中..."):
        result_df = execute_sql(generated_sql)

    if result_df is not None:
        st.success("データの取得が完了しました！")

        # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
        # 新機能: 結果の表示方法を、件数に応じて変更
        # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
        
        # ケース1: 結果が単一の数値の場合 (例: 合計金額)
        if result_df.shape == (1, 1) and pd.api.types.is_numeric_dtype(result_df.iloc[0,0]):
            value = result_df.iloc[0, 0]
            label = result_df.columns[0]
            
            # カンマ区切りと日本語単位の両方を表示
            formatted_comma_value = f"{int(value):,} 円"
            formatted_japanese_value = format_japanese_currency(value)
            
            st.metric(label=label, value=formatted_comma_value, delta=formatted_japanese_value, delta_color="off")

        # ケース2: 結果が表形式の場合
        else:
            st.write(f"**分析結果:** {len(result_df)} 件")
            # DataFrameの数値列にカンマ区切りを適用して表示
            st.dataframe(result_df.style.format(precision=0, thousands=","))