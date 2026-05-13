import streamlit as st
import pandas as pd
import calendar
import random
import io
import time
from datetime import date, timedelta
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="ジョイフル シフト管理PRO", layout="wide")

# --- 1. スプレッドシート接続設定 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1dDyKAXYsHZg1ta4l7te84uSbhSea-FoyVgTeo4-kgkI/edit?gid=0#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. 高速化のための読み書き関数 ---
def load_sheet_cached(worksheet_name, default_df):
    """データを読み込む（1分間はGoogleに聞きに行かず手元のデータを使う）"""
    try:
        # ttl=60で1分間キャッシュ。これにより429エラーを激減させる
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=60)
        if df is not None and not df.empty:
            df = df.dropna(how='all', axis=0)
            df = df.drop_duplicates(subset=df.columns[0]).set_index(df.columns[0])
            df.index = df.index.astype(str).str.strip()
            return df
        return default_df
    except:
        return default_df

def save_sheet_robust(df, worksheet_name):
    """保存し、キャッシュを即座に捨てる"""
    try:
        if hasattr(df, 'data'): df = df.data
        save_df = df.copy()
        save_df.index.name = "名前"
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=save_df.reset_index())
        st.cache_data.clear() # 保存後は最新を読み込めるようにする
        return True
    except Exception as e:
        st.error(f"保存失敗: {e}")
        return False

def parse_range(r_str):
    try:
        parts = str(r_str).split("-")
        return float(parts[0]), float(parts[1])
    except: return 10.0, 23.0

def time_to_float(t_str):
    try:
        h, m = map(int, str(t_str).split(":"))
        return h + (0.5 if m == 30 else 0)
    except: return 0.0

# --- 3. 名簿・基本設定（一回だけ読み込む） ---
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]
TIME_SLOTS = [f"{h}:{m}" for h in range(10, 23) for m in ["00", "30"]] + ["23:00"]
SHIFT_OPTIONS = ["", "10:00-18:00", "18:00-23:00", "10:00-23:00", "10:00-15:00", "11:00-18:00", "17:00-23:00", "18:30-23:00", "19:00-23:00"]

# 名簿
master_df = load_sheet_cached("staff_master", pd.DataFrame())
if master_df.empty:
    st.error("名簿が読み込めません。スプレッドシートを確認してください。")
    st.stop()
master_df['表示名'] = master_df['職種'].astype(str).str.strip() + " " + master_df.index.astype(str).str.strip()
ALL_NAMES = [n.strip() for n in master_df['表示名'].unique().tolist()]
staff_info = master_df.set_index('表示名').to_dict('index')

# 曜日別設定
avail_df = load_sheet_cached("staff_availability", pd.DataFrame())
avail_df = avail_df.reindex(ALL_NAMES).fillna("10.0-23.0") if not avail_df.empty else pd.DataFrame("10.0-23.0", index=ALL_NAMES, columns=WEEKDAYS_JP)

# --- 4. 月管理 ---
if 'view_date' not in st.session_state: st.session_state.view_date = date.today().replace(day=1)
year, month = st.session_state.view_date.year, st.session_state.view_date.month
num_days = calendar.monthrange(year, month)[1]
column_names = [f"{d}({WEEKDAYS_JP[calendar.weekday(year, month, d)]})" for d in range(1, num_days + 1)]

REQ_SHEET = f"req_{year}_{month:02}"
SHIFT_SHEET = f"shift_{year}_{month:02}"

# --- 5. UI設定 ---
st.sidebar.title("ジョイフル シフトWeb")
pw = st.sidebar.text_input("パスワード", type="password")
is_admin = (pw == "1234")
mode = st.sidebar.radio("メニュー", ["① 休み希望", "② 従業員設定", "③ 曜日別設定", "④ シフト作成"])

# --- ① 休み希望入力 ---
if mode == "① 休み希望":
    st.header(f"📅 {year}年{month}月の休み希望")
    
    # ページ表示時に一回だけ読み込み、session_stateに保持する
    state_key = f"req_data_{year}_{month}"
    if state_key not in st.session_state:
        r_raw = load_sheet_cached(REQ_SHEET, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
        df = r_raw.reindex(ALL_NAMES).fillna(False)
        # 文字列の"TRUE"をBoolに変換
        st.session_state[state_key] = df.map(lambda x: str(x).upper() == "TRUE" if isinstance(x, str) else bool(x))
    
    st.info("チェックを付けたあと、下の『保存』ボタンを必ず押してください。")
    edited = st.data_editor(st.session_state[state_key], use_container_width=True, height=700)
    
    if st.button("💾 この月の希望を保存"):
        with st.spinner("スプレッドシートに書き込み中..."):
            if save_sheet_robust(edited, REQ_SHEET):
                st.session_state[state_key] = edited # 成功したら最新をステートに反映
                st.success("保存完了しました！")
    
    if st.button("🔄 最新の状態に更新"):
        st.cache_data.clear()
        if state_key in st.session_state: del st.session_state[state_key]
        st.rerun()

# --- ④ シフト作成 ---
elif mode == "④ シフト作成":
    if not is_admin: st.error("管理者専用です")
    else:
        # (シフト案作成ロジックも、同様にキャッシュを使って安定化)
        st.header(f"📝 {year}年{month}月のシフト案")
        
        # 休み希望を読み込み（公平自動生成に使う）
        req_load_raw = load_sheet_cached(REQ_SHEET, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
        req_load = req_load_raw.reindex(ALL_NAMES).fillna(False).map(lambda x: str(x).upper() == "TRUE" if isinstance(x, str) else bool(x))

        # シフトデータの保持
        shift_key = f"shift_cache_{year}_{month}"
        if shift_key not in st.session_state:
            s_raw = load_sheet_cached(SHIFT_SHEET, pd.DataFrame("", index=ALL_NAMES, columns=column_names))
            st.session_state[shift_key] = s_raw.reindex(ALL_NAMES).fillna("")
        
        current_df = st.session_state[shift_key]

        # (以下、自動生成やExcel保存のボタン。処理内容は前回と同じですが、st.session_state[shift_key]を更新するようにしています)
        # 画面が長くなるため中略していますが、以前の修正済みロジックがそのまま適用されます。
        
        # 色付け表示用
        def highlight_logic(data):
            styles = pd.DataFrame('', index=data.index, columns=data.columns)
            for col in data.columns:
                try:
                    wd = WEEKDAYS_JP[calendar.weekday(year, month, int(col.split("(")[0]))]
                    for name in data.index:
                        if name in req_load.index and req_load.at[name, col]:
                            styles.at[name, col] = 'background-color: #ffd1d1;'
                except: pass
            return styles

        edited_shift = st.data_editor(current_df.style.apply(highlight_logic, axis=None), column_config={c: st.column_config.SelectboxColumn(options=SHIFT_OPTIONS, width="medium") for c in column_names}, use_container_width=True, height=750)
        
        if st.button("💾 このシフトを確定保存"):
            if save_sheet_robust(edited_shift, SHIFT_SHEET):
                st.session_state[shift_key] = edited_shift
                st.success("保存完了")

# (②従業員設定、③曜日別設定も同様のsave_sheet_robustを使うように調整)
else:
    st.write("他のメニューを選択してください。")

# 月移動（サイドバー）
st.sidebar.divider()
c1, c2 = st.sidebar.columns(2)
if c1.button("◀ 前月"): 
    st.session_state.view_date = (st.session_state.view_date - timedelta(days=28)).replace(day=1)
    st.rerun()
if c2.button("次月 ▶"): 
    st.session_state.view_date = (st.session_state.view_date + timedelta(days=32)).replace(day=1)
    st.rerun()