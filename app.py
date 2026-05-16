import streamlit as st
import pandas as pd
import calendar
import random
import io
import time
from datetime import date, timedelta  # 
from streamlit_gsheets import GSheetsConnection

def load_sheet_no_cache(worksheet_name, default_df):
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        if df is not None and not df.empty:
            df = df.dropna(how='all', axis=0)
            first_col = df.columns[0]
            df = df.drop_duplicates(subset=first_col, keep='first')
            df = df.set_index(first_col)
            df.index = df.index.astype(str).str.strip()
            return df
        return default_df
    except Exception:
        return default_df

st.set_page_config(page_title="ジョイフル シフト管理", layout="wide")

# --- 1. スプレッドシート接続設定 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1dDyKAXYsHZg1ta4l7te84uSbhSea-FoyVgTeo4-kgkI/edit?gid=0#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)
# --- 準備：日付と名簿の情報を整理する ---

# 1. 今日が何年何月かを取得
if 'view_date' not in st.session_state:
    st.session_state.view_date = date.today().replace(day=1)

v_date = st.session_state.view_date
year, month = v_date.year, v_date.month

# 2. その月が何日まであるか調べて、列の名前（1(金)など）を作る
num_days = calendar.monthrange(year, month)[1]
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]
column_names = [f"{d}({WEEKDAYS_JP[calendar.weekday(year, month, d)]})" for d in range(1, num_days + 1)]

# 3. スプレッドシートの「タブ名」を決める
REQ_SHEET = f"req_{year}_{month:02}"

# 4. 従業員名簿を読み込んで、全員の名前リスト（ALL_NAMES）を作る
# ※ load_sheet_no_cache は以前作った関数を使います
master_df = load_sheet_no_cache("staff_master", pd.DataFrame())
if not master_df.empty:
    # 職種アイコンと名前を合体させた「表示名」のリストを作る
    master_df['表示名'] = master_df['職種'].astype(str).str.strip() + " " + master_df.index.astype(str).str.strip()
    ALL_NAMES = master_df['表示名'].tolist()
else:
    ALL_NAMES = []

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

# --- ① 休み希望入力（安定・部分更新版） ---
if mode == "休み希望入力":
    st.title(f"📅 {year}年{month}月の休み希望")

    # 1. データの初回読み込み（貯金箱への保管）
    state_key = f"full_req_data_{year}_{month}"
    if state_key not in st.session_state:
        with st.spinner("スプレッドシートからデータを読み込み中..."):
            # load_sheet_no_cache 関数を使用して読み込み
            r_raw = load_sheet_no_cache(REQ_SHEET, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
            df = r_raw.reindex(ALL_NAMES).fillna(False)
            df = df.map(lambda x: str(x).upper() == "TRUE" if isinstance(x, str) else bool(x))
            st.session_state[state_key] = df

    req_df = st.session_state[state_key]

    st.subheader("📊 現在の全体の休み状況（閲覧のみ）")
    st.dataframe(req_df, use_container_width=True, height=300)
    
    st.divider()

    # 2. 自分の名前を選択
    st.subheader("👤 あなたの名前をタップしてください")
    cols = st.columns(4) 
    for i, name in enumerate(ALL_NAMES):
        with cols[i % 4]:
            if st.button(f"{name}", key=f"btn_{name}"):
                st.session_state.editing_user = name

    # 3. 自分の行だけを編集・保存するエリア
    if "editing_user" in st.session_state:
        user = st.session_state.editing_user
        st.info(f"📝 **{user}** さんの休み希望を入力中...")
        
        # 貯金箱から自分の行だけ抜き出す
        user_row = req_df.loc[[user]]

        edited_user_row = st.data_editor(
            user_row,
            use_container_width=True,
            key=f"editor_{user}"
        )

        # 保存・閉じるボタン
        c_save, c_close = st.columns([1, 4])
        
        with c_save:
            if st.button(f"💾 {user}さんの分を保存", type="primary"):
                with st.spinner("最新データと合体させて保存中..."):
                    # 【ここが修正の核心】
                    # ① まず、今この瞬間のスプレッドシートの「全員分」を読み直す（他人の最新入力を含む）
                    latest_all_df = load_sheet_no_cache(REQ_SHEET, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
                    latest_all_df = latest_all_df.reindex(ALL_NAMES).fillna(False)
                    
                    # ② その最新の表の「自分の行だけ」を、今画面で入力した内容に差し替える
                    # 他の人の行は、①で読み込んだ最新の状態が維持されます
                    latest_all_df.loc[user] = edited_user_row.loc[user]
                    
                    # ③ 完成した「合体版」を、標準的な save_sheet_robust で保存する
                    # これなら open_by_url のエラーは出ません
                    if save_sheet_robust(latest_all_df, REQ_SHEET):
                        # 貯金箱も最新に更新
                        st.session_state[state_key] = latest_all_df
                        st.success(f"✅ {user}さんのデータを保存しました！")
                        time.sleep(1)
                        st.rerun()
        
        with c_close:
            if st.button("❌ 入力を閉じる"):
                del st.session_state.editing_user
                st.rerun()

    # 更新ボタン（サイドバー）
    st.sidebar.divider()
    if st.sidebar.button("🔄 全体表を最新に更新"):
        if state_key in st.session_state:
            del st.session_state[state_key]
        st.rerun()
    
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
    st.subheader("3. 本日の確定シフト案（名簿順）")

    # 1. すべてのスタッフが空欄の状態の「今日の予定表」を準備
    # ALL_NAMES（名簿）を基準にするので、順番が崩れません
    daily_schedule = {name: "" for name in ALL_NAMES}

    # 2. 算出した4つのグループの結果をひとつに合体させる
    # hd_results, hn_results などの計算結果をすべてスキャンします
    all_results = hd_results + hn_results + kd_results + kn_results

    # 3. 誰がどの枠に入ったか、予定表（daily_schedule）を埋めていく
    for res in all_results:
        # もし担当者が「欠員」でなければ、その人の名前に時間を書き込む
        if res["担当者"] != "⚠️ 欠員":
            # スロット（18:00-23:00など）をその人の予定に入れる
            daily_schedule[res["担当者"]] = res["スロット"]

    # 4. 表示用のデータ表（DataFrame）を作成
    # 辞書の中身を「名前」と「シフト時間」の列にして表にします
    final_view_data = []
    for name in ALL_NAMES:
        final_view_data.append({
            "スタッフ名": name,
            "本日のシフト時間": daily_schedule[name]
        })
    
    final_view_df = pd.DataFrame(final_view_data)

    # 5. 画面に表示
    st.write("📖 名簿の順番通りに並べた一覧表です")
    st.dataframe(final_view_df, use_container_width=True, hide_index=True)

    st.info("💡 グレーの空欄の人は、本日のシフトには割り当てられていません。")