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
# データを読み込むための「道具（関数）」
@st.cache_data(ttl=600)
def load_sheet_cached(worksheet_name):
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        if df is not None:
            return df
        return None # 失敗時はNoneを返す
    except:
        return None

# データを保存するための「道具（関数）」
def save_sheet_robust(df, worksheet_name):
    try:
        # 保存するときに「名前」などの列を整理して書き込む
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=df)
        st.cache_data.clear() # 古い記憶を消去
        return True
    except:
        return False
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
st.info("💡 i")
st.sidebar.title("メニュー")
mode = st.sidebar.radio("機能を選択", ["休み希望入力","従業員名簿管理", "シフト自動生成（案）"])

pw = st.sidebar.text_input("管理者パスワード", type="password")

# データのロード
master_df = load_master()
# ここで ALL_NAMES を定義します！
if not master_df.empty:
    # master_df の「名前」列をリスト形式に変換して保存
    ALL_NAMES = master_df["名前"].tolist()
else:
    # もし名簿が空っぽなら、エラーにならないように空のリストを作る
    ALL_NAMES = []
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
            st.write("### 現在の名簿（閲覧のみ）")
            if not master_df.empty:
                st.dataframe(master_df, use_container_width=True)
            # --- ① 休み希望入力 ---
elif mode == "休み希望入力":
    st.title("📅 休み希望の登録")

    
elif mode == "シフト自動生成（案）":
    
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

    # --- 準備：グループごとに名簿を作る ---
        hd_pool = master_df[master_df['グループ'] == 'HD']['名前'].tolist()
        hn_pool = master_df[master_df['グループ'] == 'HN']['名前'].tolist()
        kd_pool = master_df[master_df['グループ'] == 'KD']['名前'].tolist()
        kn_pool = master_df[master_df['グループ'] == 'KN']['名前'].tolist()
        w_pool = master_df[master_df['グループ'] == 'W']['名前'].tolist()

    # 全ての名簿をシャッフル（公平にするため）
        random.shuffle(hd_pool)
        random.shuffle(hn_pool)
        random.shuffle(kd_pool)
        random.shuffle(kn_pool)
        random.shuffle(w_pool)

    # 「今日すでにどこかの枠に割り当てられた人」をメモするリスト
        assigned_today = []

    # 共通の「割り当て関数」を作るとミスが減ります
        def assign_slots(slot_list, main_pool, wildcard_pool, assigned_list):
            result = []
        # メインの担当者(HD等)と共通(W)を合体
            combined_pool = main_pool + wildcard_pool
        
            for slot_time in slot_list:
            # まだ選ばれていない人だけを抽出（ここが引き算！）
                available = [name for name in combined_pool if name not in assigned_list]
            
                if available:
                    picked = available[0] # 一番上の人を選ぶ
                    result.append({"スロット": slot_time, "担当者": picked})
                    assigned_list.append(picked) # 選ばれた人を「使用済み」に入れる
                else:
                    result.append({"スロット": slot_time, "担当者": "⚠️ 欠員"})
            return result

    # --- 1. 昼の枠（基本2名ずつ） ---
        day_slots = ["10:00-18:00", "10:00-18:00"]
        hd_results = assign_slots(day_slots, hd_pool, w_pool, assigned_today)
        kd_results = assign_slots(day_slots, kd_pool, w_pool, assigned_today)

    # --- 2. 夜の枠（基本4名ずつ） ---
        hall_night_slots = ["18:00-23:00", "18:00-23:00", "18:00-22:00", "19:00-23:00"]
        kitchen_night_slots = ["18:00-23:00", "18:00-23:00", "18:00-22:00", "19:00-23:00"]
    
        hn_results = assign_slots(hall_night_slots, hn_pool, w_pool, assigned_today)
        kn_results = assign_slots(kitchen_night_slots, kn_pool, w_pool, assigned_today)

    # --- 結果の表示 ---
    
        # 段階的ステップ3: 名簿順に並び替えた1日シフト表の作成
        st.subheader("3. 本日の確定シフト案（名簿順）")

    # 1. すべてのグループの結果を1つの辞書にまとめる
    # key: 名前, value: 時間
        daily_schedule = {name: "" for name in ALL_NAMES}

    # 各グループの計算結果（hd_resultsなど）から名前と時間を抜き出して辞書に入れる
    # ※ assign_slots関数の戻り値形式に合わせて処理
        for res in hd_results + hn_results + kd_results + kn_results:
            if res["担当者"] != "⚠️ 欠員":
                daily_schedule[res["担当者"]] = res["スロット"]

    # 2. 表示用の表（DataFrame）を作成
    # ALL_NAMES（名簿）を元に作るので、自動的に名簿順になります
        final_view_df = pd.DataFrame([
        {"名前": name, "シフト時間": daily_schedule[name]} 
        for name in ALL_NAMES
    ])

    # 3. 画面に表示
        st.write("📖 今日の全スタッフ配置一覧")
        st.table(final_view_df)

        st.info("💡 名簿の順番通りに並び、シフトがない人は空欄になっています。")
        