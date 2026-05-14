import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import random

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
st.title(" 従業員名簿・グループ管理")
st.info("💡 下の表に名前を打ち込んで『保存』してください。")
st.sidebar.title("メニュー")
mode = st.sidebar.radio("機能を選択", ["従業員名簿管理", "シフト自動生成（案）"])

pw = st.sidebar.text_input("管理者パスワード", type="password")

# データのロード
master_df = load_master()
if mode == "従業員名簿管理":
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
else:
    # --- ここに新しい「シフト作成」のプログラムを書いていく ---
    st.title("📅 シフト自動生成（案）")
    
    # 段階的ステップ1: ジョイフルの「必要枠（スロット）」を定義する
    st.subheader("1. 本日の必要人数（スロット）の確認")
    
    # ホール夜(HN)の枠を定義
    hall_night_slots = [
        "18:00-23:00", # 1人目
        "18:00-23:00", # 2人目
        "18:00-22:00", # 3人目
        "19:00-23:00"  # 4人目
    ]
    
    # キッチン夜(KN)の枠を定義
    kitchen_night_slots = [
        "18:00-23:00",
        "18:00-23:00",
        "18:00-22:00",
        "19:00-23:00"
    ]

    col1, col2 = st.columns(2)
    with col1:
        st.write("🏃 ホール必要枠")
        st.write(hall_night_slots)
    with col2:
        st.write("🍳 キッチン必要枠")
        st.write(kitchen_night_slots)

    st.info("次のステップで、各グループ（HN, KN, W）から人をランダムに選んでこの枠に当てはめます。")
    # 段階的ステップ2: グループごとにリストを作る
    st.subheader("2. スタッフの選出と割り当て（試作）")

    # 名簿から HN（ホール夜）と W（共通）の人を抽出
    hn_candidates = master_df[master_df['グループ'] == 'HN']['名前'].tolist()
    w_candidates = master_df[master_df['グループ'] == 'W']['名前'].tolist()

    # --- 割り当ての計算（ホール夜） ---
    # 1. まずHNの人をランダムに並べ替える
    random.shuffle(hn_candidates)
    
    # 2. 足りない場合に備えてWの人も並べ替えて準備
    random.shuffle(w_candidates)

    # 3. ホールの全候補者を合体させる（HNが前、Wが後ろになるように）
    # これにより、HNから優先的に選ばれ、足りなくなったらWが選ばれるようになります
    all_hall_night_candidates = hn_candidates + w_candidates

    # 4. スロット（椅子）に順番に座らせる
    hall_assignments = {}
    for i in range(len(hall_night_slots)):
        slot_time = hall_night_slots[i]
        
        # 候補者がまだ残っていれば割り当てる
        if i < len(all_hall_night_candidates):
            assigned_name = all_hall_night_candidates[i]
        else:
            assigned_name = "⚠️ 欠員（候補者不足）"
        
        hall_assignments[f"枠 {i+1} ({slot_time})"] = assigned_name

    # 5. 結果を画面に出す
    st.write("🏃 ホール夜の割り当て結果")
    st.table(pd.DataFrame(hall_assignments.items(), columns=["スロット", "担当者"]))

    st.success("HNグループを優先し、足りない場合はWグループから選ぶロジックが動いています！")