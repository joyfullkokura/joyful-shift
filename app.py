import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="ジョイフル シフト管理（名簿管理）", layout="wide")

# --- 1. スプレッドシート接続設定 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1dDyKAXYsHZg1ta4l7te84uSbhSea-FoyVgTeo4-kgkI/edit?gid=0#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. データの読み書き関数 ---
def load_master():
    try:
        # スプレッドシートから読み込み。中身が空でもエラーにしない
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="staff_master", ttl=0)
        if df is not None and not df.empty:
            return df.dropna(how='all')
        # シートが空なら、器（空の表）を返す
        return pd.DataFrame(columns=["名前", "職種", "グループ", "レジ締め", "デザート", "週希望"])
    except:
        return pd.DataFrame(columns=["名前", "職種", "グループ", "レジ締め", "デザート", "週希望"])

def save_master(df):
    # 名前が入っていない行は保存しない
    df = df.dropna(subset=["名前"])
    conn.update(spreadsheet=SPREADSHEET_URL, worksheet="staff_master", data=df)
    st.cache_data.clear()

# --- 3. メイン画面 ---
st.title("👥 従業員名簿・グループ管理")

pw = st.sidebar.text_input("管理者パスワード", type="password")

# データのロード
master_df = load_master()

if pw == "1234":
    st.info("💡 表の一番下の行をクリックして、新しい従業員を入力してください。行を選んでDeleteキーで削除もできます。")
    st.caption("グループ分け：【HD:ホール昼, HN:ホール夜, KD:キッチン昼, KN:キッチン夜, W:社員】")
    
    # 自由に追加・削除・編集できるエディタ
    edited_df = st.data_editor(
        master_df,
        column_config={
            "職種": st.column_config.SelectboxColumn(options=["👔社員", "☕DF", "🍳DK"]),
            "グループ": st.column_config.SelectboxColumn(options=["HD", "HN", "KD", "KN", "W"]),
            "週希望": st.column_config.SelectboxColumn(options=[1,2,3,4,5,6,7]),
            "レジ締め": st.column_config.CheckboxColumn(),
            "デザート": st.column_config.CheckboxColumn(),
        },
        use_container_width=True,
        num_rows="dynamic"  # これで行の追加・削除が可能になります
    )
    
    if st.button("💾 スプレッドシートに保存"):
        save_master(edited_df)
        st.success("名簿を更新しました！")
else:
    st.warning("管理パスワードを入力すると、名簿の編集が可能です。")
    # 非ログイン時は表示のみ
    if not master_df.empty:
        st.dataframe(master_df, use_container_width=True)