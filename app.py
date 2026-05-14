import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="ジョイフル シフト管理", layout="wide")

# --- 1. スプレッドシート接続設定 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1dDyKAXYsHZg1ta4l7te84uSbhSea-FoyVgTeo4-kgkI/edit?gid=0#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. データの読み書き関数 ---
def load_master():
    # 正しい種類（型）を持った空の表を準備しておく
    empty_df = pd.DataFrame({
        "名前": pd.Series(dtype='str'),
        "職種": pd.Series(dtype='str'),
        "グループ": pd.Series(dtype='str'),
        "レジ締め": pd.Series(dtype='bool'),
        "デザート": pd.Series(dtype='bool'),
        "週希望": pd.Series(dtype='int')
    })
    
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="staff_master", ttl=0)
        df['レジ締め'] = df['レジ締め'].astype(bool)
        df['デザート'] = df['デザート'].astype(bool)
        if df is not None and not df.empty:
            df = df.dropna(how='all')
            # 読み込んだデータの種類を正しく変換する
            df['レジ締め'] = df['レジ締め'].map(lambda x: str(x).upper() == 'TRUE')
            df['デザート'] = df['デザート'].map(lambda x: str(x).upper() == 'TRUE')
            df['週希望'] = pd.to_numeric(df['週希望'], errors='coerce').fillna(3).astype(int)
            return df
        return empty_df
    except:
        return empty_df

def save_master(df):
    # 名前が空の行を削除
    df = df.dropna(subset=["名前"])
    if not df.empty:
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet="staff_master", data=df)
        st.cache_data.clear()
        return True
    return False

# --- 3. メイン画面 ---
st.title("👥 従業員名簿・グループ管理")
st.info("💡 下の表に名前を打ち込んで『保存』してください。")

pw = st.sidebar.text_input("管理者パスワード", type="password")

# データのロード
master_df = load_master()

if pw == "1234":
    st.caption("グループ：【HD:ホール昼, HN:ホール夜, KD:キッチン昼, KN:キッチン夜, W:共通】")
    
    # 型エラーを防ぐためのエディタ設定
    edited_df = st.data_editor(
        master_df,
        column_config={
            "名前": st.column_config.TextColumn("名前", required=True),
            "職種": st.column_config.SelectboxColumn("職種", options=["👔社員", "☕DF", "🍳DK"]),
            "グループ": st.column_config.SelectboxColumn("グループ", options=["HD", "HN", "KD", "KN", "W"]),
            "週希望": st.column_config.NumberColumn("週希望", min_value=1, max_value=7, step=1, default=3),
            "レジ締め": st.column_config.CheckboxColumn("レジ締め"),
            "デザート": st.column_config.CheckboxColumn("デザート"),
        },
        use_container_width=True,
        num_rows="dynamic", # 行の追加削除を有効化
        key="master_editor"
    )
    
    if st.button("💾 スプレッドシートに保存"):
        if save_master(edited_df):
            st.success("スプレッドシートに保存しました！")
            st.rerun()
else:
    st.warning("左側のメニューでパスワード『1234』を入力してください。")
    if not master_df.empty:
        st.write("### 現在の名簿（閲覧のみ）")
        st.dataframe(master_df, use_container_width=True)