import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="ジョイフル シフト土台", layout="wide")

# --- 1. 接続設定 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1dDyKAXYsHZg1ta4l7te84uSbhSea-FoyVgTeo4-kgkI/edit?gid=0#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. 読み書き関数 ---
def load_master():
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="staff_master", ttl=0)
        if df is not None and not df.empty:
            return df.dropna(how='all').drop_duplicates(subset="名前")
        return pd.DataFrame()
    except: return pd.DataFrame()

def save_master(df):
    conn.update(spreadsheet=SPREADSHEET_URL, worksheet="staff_master", data=df)
    st.cache_data.clear()

# --- 3. 初期データ（25名） ---
def get_init_list():
    return [
        {"名前": "多田（店長）", "職種": "👔社員", "グループ": "W", "レジ締め": True, "デザート": True, "週希望": 5},
        {"名前": "河野", "職種": "👔社員", "グループ": "W", "レジ締め": True, "デザート": True, "週希望": 5},
        {"名前": "末益", "職種": "🍳DK", "グループ": "KD", "レジ締め": False, "デザート": False, "週希望": 6},
        {"名前": "扇", "職種": "☕DF", "グループ": "HN", "レジ締め": True, "デザート": True, "週希望": 4},
        {"名前": "高木", "職種": "☕DF", "グループ": "HN", "レジ締め": True, "デザート": True, "週希望": 4},
        {"名前": "笹谷", "職種": "☕DF", "グループ": "HN", "レジ締め": True, "デザート": True, "週希望": 4},
        {"名前": "西村", "職種": "☕DF", "グループ": "HN", "レジ締め": True, "デザート": True, "週希望": 3},
        {"名前": "武久", "職種": "☕DF", "グループ": "HN", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "持田", "職種": "☕DF", "グループ": "HN", "レジ締め": False, "デザート": False, "週希望": 2},
        {"名前": "永田", "職種": "☕DF", "グループ": "HN", "レジ締め": False, "デザート": False, "週希望": 2},
        {"名前": "宝村", "職種": "☕DF", "グループ": "HN", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "竹浦", "職種": "☕DF", "グループ": "HN", "レジ締め": False, "デザート": False, "週希望": 2},
        {"名前": "宮川", "職種": "☕DF", "グループ": "HN", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "キサン", "職種": "🍳DK", "グループ": "KN", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "太田", "職種": "🍳DK", "グループ": "KN", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "小田川", "職種": "🍳DK", "グループ": "KN", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "内田", "職種": "🍳DK", "グループ": "KN", "レジ締め": False, "デザート": False, "週希望": 5},
        {"名前": "十河", "職種": "🍳DK", "グループ": "KN", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "井上", "職種": "🍳DK", "グループ": "KD", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "蜂谷", "職種": "🍳DK", "グループ": "KN", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "八田", "職種": "🍳DK", "グループ": "KN", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "西田", "職種": "🍳DK", "グループ": "KD", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "清水", "職種": "🍳DK", "グループ": "KN", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "松村", "職種": "🍳DK", "グループ": "KD", "レジ締め": False, "デザート": False, "週希望": 5},
        {"名前": "渡部", "職種": "🍳DK", "グループ": "KD", "レジ締め": False, "デザート": False, "週希望": 5},
    ]

# --- 4. メイン処理 ---
st.title("🛡️ シフト管理：土台設定")
pw = st.sidebar.text_input("パスワード", type="password")

master_df = load_master()
if master_df.empty:
    master_df = pd.DataFrame(get_init_list())

if pw == "1234":
    st.header("従業員名簿とグループ分け")
    st.info("HD:ホール昼, HN:ホール夜, KD:キッチン昼, KN:キッチン夜, W:社員")
    
    edited = st.data_editor(
        master_df,
        column_config={
            "グループ": st.column_config.SelectboxColumn(options=["HD", "HN", "KD", "KN", "W"]),
            "週希望": st.column_config.SelectboxColumn(options=[1,2,3,4,5,6,7]),
            "レジ締め": st.column_config.CheckboxColumn(),
            "デザート": st.column_config.CheckboxColumn(),
        },
        use_container_width=True,
        num_rows="dynamic"
    )
    
    if st.button("💾 スプレッドシートに保存"):
        save_master(edited)
        st.success("保存しました！")
else:
    st.warning("パスワードを入力してください。")