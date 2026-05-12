import streamlit as st
import pandas as pd
import calendar
import os
import random
import io
import time
from datetime import date, timedelta
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="ジョイフル シフト管理PRO", layout="wide")

# --- 1. スプレッドシート設定 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1dDyKAXYsHZg1ta4l7te84uSbhSea-FoyVgTeo4-kgkI/edit?gid=0#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet(worksheet_name, default_df):
    """スプレッドシートから読み込む。失敗しても勝手に保存はしない。"""
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        if df is not None and not df.empty:
            # 重複と空白の掃除
            df = df.dropna(how='all', axis=0)
            first_col = df.columns[0]
            df = df.drop_duplicates(subset=first_col, keep='first')
            df = df.set_index(first_col)
            df.index = df.index.astype(str).str.strip()
            return df
        return default_df
    except Exception:
        return default_df

def save_sheet(df, worksheet_name):
    """データを保存する。スタイル情報を完全に排除して保存。"""
    try:
        # スタイル付きデータ(Styler)の場合は生データを取り出す
        if hasattr(df, 'data'):
            df = df.data
        
        save_df = df.copy()
        # インデックス名を固定
        save_df.index.name = "名前"
        # 全ての値を確実に保存可能な形式にする
        save_df = save_df.reset_index()
        
        # 保存実行
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=save_df)
        st.cache_data.clear()
        time.sleep(2) # Google側の反映を待つ
        return True
    except Exception as e:
        st.error(f"【保存失敗】'{worksheet_name}' への保存に失敗しました。")
        st.info("タブ名が正しいか、通信環境が良いか確認してください。")
        return False

# --- 2. 共通設定 ---
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]
SHIFT_OPTIONS = ["", "10:00-18:00", "18:00-23:00", "10:00-23:00", "10:00-15:00", "11:00-18:00", "17:00-23:00", "18:30-23:00", "19:00-23:00"]

def time_to_float(t_str):
    if not t_str or ":" not in str(t_str): return 0.0
    try:
        h, m = map(int, str(t_str).split(":"))
        return h + (0.5 if m == 30 else 0)
    except: return 0.0

def parse_range(r_str):
    try:
        parts = str(r_str).split("-")
        return float(parts[0]), float(parts[1])
    except: return 10.0, 23.0

# --- 3. データの初期化 (25名最新リスト) ---
# 初回起動時のみ使うデータ
def get_initial_data():
    return [
        {"名前": "多田（店長）", "職種": "👔社員", "レジ締め": True, "デザート": True, "週希望": 6, "傾向": "ALL"},
        {"名前": "河野", "職種": "👔社員", "レジ締め": True, "デザート": True, "週希望": 6, "傾向": "ALL"},
        {"名前": "末益", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 6, "傾向": "ALL"},
        {"名前": "扇", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 4, "傾向": "NIGHT"},
        {"名前": "高木", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 4, "傾向": "NIGHT"},
        {"名前": "笹谷", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 4, "傾向": "NIGHT"},
        {"名前": "西村", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 3, "傾向": "NIGHT"},
        {"名前": "武久", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 4, "傾向": "NIGHT"},
        {"名前": "持田", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 2, "傾向": "NIGHT"},
        {"名前": "永田", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 2, "傾向": "NIGHT"},
        {"名前": "宝村", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 3, "傾向": "NIGHT"},
        {"名前": "竹浦", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 2, "傾向": "NIGHT"},
        {"名前": "宮川", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 3, "傾向": "NIGHT"},
        {"名前": "キサン", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 4, "傾向": "NIGHT"},
        {"名前": "太田", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 3, "傾向": "NIGHT"},
        {"名前": "小田川", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 4, "傾向": "NIGHT"},
        {"名前": "内田", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 5, "傾向": "NIGHT"},
        {"名前": "十河", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 3, "傾向": "NIGHT"},
        {"名前": "井上", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 3, "傾向": "DAY"},
        {"名前": "蜂谷", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 4, "傾向": "NIGHT"},
        {"名前": "八田", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 3, "傾向": "NIGHT"},
        {"名前": "西田", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 4, "傾向": "DAY"},
        {"名前": "清水", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 4, "傾向": "NIGHT"},
        {"名前": "松村", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 5, "傾向": "DAY"},
        {"名前": "渡部", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 5, "傾向": "DAY"},
    ]

# 名簿の読み込み（失敗しても止まらない）
master_df = load_sheet("staff_master", pd.DataFrame())
if master_df.empty:
    master_df = pd.DataFrame(get_initial_data()).set_index("名前")
    st.warning("名簿が読み込めませんでした。初期データを表示します。保存ボタンでスプレッドシートに書き込まれます。")

master_df['表示名'] = master_df['職種'].astype(str).str.strip() + " " + master_df.index.astype(str).str.strip()
ALL_NAMES = master_df['表示名'].unique().tolist()
staff_info = master_df.set_index('表示名').to_dict('index')

# 曜日別設定
avail_df = load_sheet("staff_availability", pd.DataFrame())
if avail_df.empty:
    avail_df = pd.DataFrame([[n] + ["10.0-23.0"]*7 for n in ALL_NAMES], columns=["名前"] + WEEKDAYS_JP).set_index("名前")
else:
    avail_df = avail_df.reindex(ALL_NAMES).fillna("10.0-23.0")

# 必要人数設定
REQ_STAFF_FILE = "required_staff"
req_groups = load_sheet(REQ_STAFF_FILE, pd.DataFrame())
time_slots = [f"{h}:{m}" for h in range(10, 23) for m in ["00", "30"]] + ["23:00"]
if req_groups.empty:
    req_groups = pd.DataFrame(2, index=time_slots, columns=["月火水木_ホール", "月火水木_キッチン", "金土_ホール", "金土_キッチン", "日_ホール", "日_キッチン"])
    req_groups.index.name = "時間"

# --- 4. 月管理 ---
if 'view_date' not in st.session_state:
    st.session_state.view_date = date.today().replace(day=1)
year, month = st.session_state.view_date.year, st.session_state.view_date.month
num_days = calendar.monthrange(year, month)[1]
column_names = [f"{d}({WEEKDAYS_JP[calendar.weekday(year, month, d)]})" for d in range(1, num_days + 1)]

REQ_SHEET_NAME = f"req_{year}_{month:02}"
SHIFT_SHEET_NAME = f"shift_{year}_{month:02}"

# --- 5. UI設定 ---
st.sidebar.title("ジョイフル シフトWeb")
pw = st.sidebar.text_input("管理者パスワードを入力", type="password")
is_admin = (pw == "1234")
mode = st.sidebar.radio("モード選択", ["① 休み希望入力", "② 従業員基本設定", "③ 曜日別可能時間(バー)", "④ シフト案作成"])

# --- ① 休み希望 ---
if mode == "① 休み希望入力":
    st.header(f"📅 {year}年{month}月の休み希望")
    
    # セッションを使ってデータ消失を防ぐ
    if f'req_data_{year}_{month}' not in st.session_state:
        r_raw = load_sheet(REQ_SHEET_NAME, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
        st.session_state[f'req_data_{year}_{month}'] = r_raw.reindex(ALL_NAMES).fillna(False).map(lambda x: str(x).lower() in ['true', '1', 'yes'])

    edited_req = st.data_editor(st.session_state[f'req_data_{year}_{month}'], use_container_width=True, height=750)
    
    if st.button("💾 この月の希望を保存"):
        if save_sheet(edited_req, REQ_SHEET_NAME):
            st.session_state[f'req_data_{year}_{month}'] = edited_req
            st.success("スプレッドシートへ正常に保存されました！")

# --- ② 基本設定 ---
elif mode == "② 従業員基本設定":
    if not is_admin: st.error("管理者専用です")
    else:
        st.header("⚙️ 従業員名簿管理")
        edited_master = st.data_editor(master_df, use_container_width=True, num_rows="dynamic")
        if st.button("💾 名簿を保存"):
            save_sheet(edited_master, "staff_master")

# --- ③ 曜日別バー ---
elif mode == "③ 曜日別可能時間(バー)":
    if not is_admin: st.error("管理者専用です")
    else:
        target = st.selectbox("スタッフ選択", ALL_NAMES)
        new_times = {}
        for wd in WEEKDAYS_JP:
            raw_val = avail_df.at[target, wd] if target in avail_df.index else "10.0-23.0"
            s_f, e_f = parse_range(raw_val)
            res = st.slider(wd, 10.0, 23.0, (float(s_f), float(e_f)), step=0.5, key=f"s_{target}_{wd}")
            new_times[wd] = f"{res[0]}-{res[1]}"
        if st.button(f"💾 {target} の時間を保存"):
            for wd, t in new_times.items(): avail_df.at[target, wd] = t
            save_sheet(avail_df, "staff_availability")

# --- ④ シフト案作成 ---
else:
    if not is_admin: st.error("管理者用です")
    else:
        st.header(f"📝 {year}年{month}月のシフト案")
        
        # 休み希望データの読み込み
        req_load = load_sheet(REQ_SHEET_NAME, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
        req_load = req_load.reindex(ALL_NAMES).fillna(False).map(lambda x: str(x).lower() in ['true', '1', 'yes'])

        if 'shift_cache' not in st.session_state:
            s_raw = load_sheet(SHIFT_SHEET_NAME, pd.DataFrame("", index=ALL_NAMES, columns=column_names))
            st.session_state.shift_cache = s_raw.reindex(ALL_NAMES).fillna("")
        
        current_df = st.session_state.shift_cache

        col_a1, col_a2 = st.columns([2, 1])
        with col_a1:
            if st.button("🤖 自動生成実行"):
                new_s = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
                work_counts = {n: 0 for n in ALL_NAMES}; target_counts = {n: staff_info[n]['週希望']*4.3 for n in ALL_NAMES}
                for i, col in enumerate(column_names):
                    wd_jp = WEEKDAYS_JP[calendar.weekday(year, month, i+1)]
                    capable = [n for n in ALL_NAMES if not req_load.at[n, col]]
                    random.shuffle(capable); capable.sort(key=lambda n: (work_counts[n]/target_counts[n] if target_counts[n]>0 else 99, random.random()))
                    h_cnt, has_cl = 0, False
                    for n in capable:
                        sf, ef = parse_range(avail_df.at[n, wd_jp])
                        if sf >= ef: continue
                        t_st = f"{int(sf)}:00" if sf%1==0 else f"{int(sf)}:30"
                        if staff_info[n]['レジ締め'] and ef >= 23 and not has_cl:
                            new_s.at[n, col] = f"{t_st}-23:00"; work_counts[n]+=1; has_cl=True
                        elif sf <= 11 and h_cnt < 3:
                            new_s.at[n, col] = f"{t_st}-18:00"; work_counts[n]+=1; h_cnt+=1
                st.session_state.shift_cache = new_s; st.rerun()

        with col_a2:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                current_df.to_excel(writer, sheet_name='シフト')
                wb, ws = writer.book, writer.sheets['シフト']
                fmt = wb.add_format({'border':1, 'align':'center'})
                name_fmt = wb.add_format({'bold':True, 'border':1, 'bg_color':'#F2F2F2'})
                ws.set_column(0,0,25,name_fmt); ws.set_column(1,len(column_names),12,fmt)
                for c_idx, val in enumerate(current_df.columns):
                    if "(土)" in val: ws.write(0, c_idx + 1, val, wb.add_format({'bold':True, 'bg_color':'#CCE5FF', 'font_color':'#0000FF', 'border':1}))
                    elif "(日)" in val: ws.write(0, c_idx + 1, val, wb.add_format({'bold':True, 'bg_color':'#FFCCCC', 'font_color':'#FF0000', 'border':1}))
                ws.freeze_panes(1, 1)
            st.download_button("📥 Excelで保存", output.getvalue(), f"shift_{year}_{month:02}.xlsx")

        def highlight_logic(data):
            styles = pd.DataFrame('', index=data.index, columns=data.columns)
            for col in data.columns:
                try:
                    wd = WEEKDAYS_JP[calendar.weekday(year, month, int(col.split("(")[0]))]
                    for name in data.index:
                        if name in req_load.index and req_load.at[name, col]: styles.at[name, col] = 'background-color: #ffd1d1;'
                        v = data.at[name, col]
                        if v and "-" in str(v):
                            si, ei = time_to_float(v.split("-")[0]), time_to_float(v.split("-")[1])
                            sl, el = parse_range(avail_df.at[name, wd] if name in avail_df.index else "10.0-23.0")
                            if si < sl or ei > el: styles.at[name, col] = 'background-color: #ff5555; color: white;'
                except: pass
            return styles

        edited = st.data_editor(current_df.style.apply(highlight_logic, axis=None), column_config={c: st.column_config.SelectboxColumn(options=SHIFT_OPTIONS, width="medium") for c in column_names}, use_container_width=True, height=750)
        if st.button("💾 このシフトを確定保存"):
            if save_sheet(edited, SHIFT_SHEET_NAME): st.session_state.shift_cache = edited; st.success("保存完了")

# 月移動
st.sidebar.divider()
c1, c2 = st.sidebar.columns(2)
if c1.button("◀ 前月"): 
    st.session_state.view_date = (st.session_state.view_date - timedelta(days=28)).replace(day=1)
    if 'shift_cache' in st.session_state: del st.session_state.shift_cache
    st.rerun()
if c2.button("次月 ▶"): 
    st.session_state.view_date = (st.session_state.view_date + timedelta(days=32)).replace(day=1)
    if 'shift_cache' in st.session_state: del st.session_state.shift_cache
    st.rerun()