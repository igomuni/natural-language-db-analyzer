import os
import streamlit as st
import duckdb
import google.generativeai as genai
from dotenv import load_dotenv

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

# あなたのタスク
ユーザーからの自然言語による質問を解釈し、その答えを導き出すための**DuckDBで実行可能なSQLクエリを1つだけ**生成してください。

# 遵守すべきルール
1. 生成するSQLは、上記のスキーマ情報を正確に反映させてください。
2. `金額` 列がユーザーの言う「支出額」「費用」「コスト」に相当します。
3. **SQL内の列名は、必ずダブルクォート `"` で囲んでください。** これは日本語の列名を正しく扱うために非常に重要です。（例: `SELECT "事業名", "金額" FROM {TABLE_NAME};`）
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
                                 placeholder="例: こども家庭庁による支出を、金額が大きい順に5件、事業名と支出先名、金額を教えて。")
    submitted = st.form_submit_button("質問する")

if submitted and user_question:
    with st.spinner("AIがSQLを生成中..."):
        # 1. プロンプトを作成
        prompt = create_prompt(user_question, schema_info)
        
        # 2. LLMにSQLを生成させる
        try:
            response = model.generate_content(prompt)
            # レスポンスからSQLクエリを抽出
            generated_sql = response.text.strip().replace("```sql", "").replace("```", "").strip()
            st.success("SQLの生成が完了しました！")
            
            with st.expander("AIによって生成されたSQLクエリ"):
                st.code(generated_sql, language="sql")

        except Exception as e:
            st.error(f"SQLの生成中にエラーが発生しました: {e}")
            st.stop()

    with st.spinner("データベースを検索中..."):
        # 3. SQLを実行して結果を取得
        result_df = execute_sql(generated_sql)

    # 4. 結果を表示
    if result_df is not None:
        st.success("データの取得が完了しました！")
        st.write(f"**分析結果:** {len(result_df)} 件")
        st.dataframe(result_df)
