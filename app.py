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
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name,ttl=0)
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
st.info("💡 ")
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

    # 1. 貯金箱（session_state）にデータが入っているか確認
    # 入っていなければ、スプレッドシートから初回読み込みを行う
    if "temp_req_df" not in st.session_state:
        raw_data = load_sheet_cached("req_2026_05")
        days_cols = [f"{d}日" for d in range(1, 32)]
        
        if raw_data.empty:
            df = pd.DataFrame(False, index=range(len(ALL_NAMES)), columns=["名前"] + days_cols)
            df["名前"] = ALL_NAMES
            st.session_state.temp_req_df = df
        else:
            # 名簿と同期して貯金箱に入れる
            df = raw_data.set_index('名前').reindex(ALL_NAMES).reset_index().fillna(False)
            st.session_state.temp_req_df = df

    st.info("💡 作業中は自動保存されません。最後に必ず下の『確定保存』を押してください。")

    # 2. 画面に表示（貯金箱の中身を編集する）
    # 日付列の設定
    days_cols = [f"{d}日" for d in range(1, 32)]
    column_config = {"名前": st.column_config.TextColumn("名前", disabled=True)}
    for col in days_cols:
        column_config[col] = st.column_config.CheckboxColumn(col, width="small")

    # edited_df は「今画面で見ている最新の状態」
    edited_df = st.data_editor(
        st.session_state.temp_req_df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=700,
        key="editor"
    )

    # 3. 保存ボタンが押されたときだけ、一気にスプレッドシートへ送る
    if st.button("💾 休み希望をスプレッドシートに一括保存"):
        if save_sheet_robust(edited_df, "req_2026_05"):
            # 保存に成功したら、貯金箱を最新の状態に更新し、キャッシュをクリアする
            st.session_state.temp_req_df = edited_df
            st.cache_data.clear() 
            st.success("スプレッドシートへの一括書き込みが完了しました！")
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
        st.subheader("2. スタッフの選出と割り当て（試作）")

        st.subheader("2. 全ポジションの自動割り当て")

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
        c1, c2 = st.columns(2)
        with c1:
            st.write("🏃 ホール昼(HD)")
            st.table(pd.DataFrame(hd_results))
            st.write("🏃 ホール夜(HN)")
            st.table(pd.DataFrame(hn_results))
        with c2:
            st.write("🍳 キッチン昼(KD)")
            st.table(pd.DataFrame(kd_results))
            st.write("🍳 キッチン夜(KN)")
            st.table(pd.DataFrame(kn_results))

        st.success("全てのポジションで『自グループ優先 ＞ 空いていればWから補充 ＞ 1人1ポジションのみ』のルールが適用されました！")
        