import os
import streamlit as st
import pandas as pd
import numpy as np
import requests # バックエンドと通信するためのライブラリ
import random

# --- 初期設定 ---

# バックエンドサーバーのURLを設定
# ローカルでテストする場合: "http://127.0.0.1:8000"
# Renderにデプロイした後: Renderが提供するURL (例: "https://your-app-name.onrender.com")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

# --- バックエンドAPIを呼び出す関数 ---

def call_analyze_api(question: str):
    """
    バックエンドの /analyze エンドポイントを呼び出し、分析結果を取得する。
    """
    api_endpoint = f"{BACKEND_URL}/analyze"
    
    # バックエンドに送信するデータ（JSON形式）
    payload = {
        "question": question
    }
    
    try:
        # POSTリクエストを送信
        response = requests.post(api_endpoint, json=payload, timeout=300) # タイムアウトを5分に設定
        
        # レスポンスのステータスコードをチェック
        response.raise_for_status() # 200番台でなければエラーを発生させる
        
        # JSONレスポンスをPythonの辞書に変換して返す
        return response.json()
        
    except requests.exceptions.RequestException as e:
        # 接続エラーやタイムアウトなどのネットワーク関連のエラー
        st.error(f"バックエンドサーバーへの接続に失敗しました: {e}")
        st.info(f"バックエンドサーバー({BACKEND_URL})が正しく起動しているか確認してください。")
        return None
    except Exception as e:
        # その他の予期せぬエラー
        st.error(f"予期せぬエラーが発生しました: {e}")
        return None


# --- 表示関連の関数 (以前のものと同じ) ---

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

# --- サンプル質問生成 (以前のものと同じ) ---
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


# --- Streamlit UI 本体 ---

st.title("自然言語DB分析ツール 💬")
st.caption("行政事業レビューデータを元に、自然言語で質問できます。")

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
    with st.spinner("バックエンドサーバーに問い合わせ中..."):
        # ★★★ ここが新しい！バックエンドAPIを呼び出す ★★★
        api_response = call_analyze_api(user_question)

    if api_response:
        st.success("データの取得が完了しました！")
        
        # バックエンドから返ってきたSQLと結果を取り出す
        generated_sql = api_response.get("generated_sql", "N/A")
        result_data = api_response.get("result", [])
        
        with st.expander("バックエンドで実行されたSQLクエリ"):
            st.code(generated_sql, language="sql")
            
        # 結果をPandas DataFrameに変換
        result_df = pd.DataFrame(result_data)
        
        # --- 結果の表示ロジック (以前とほぼ同じ) ---
        if result_df.empty:
            st.warning("分析結果が0件でした。")
        elif result_df.shape == (1, 1) and pd.api.types.is_numeric_dtype(result_df.iloc[0,0]):
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