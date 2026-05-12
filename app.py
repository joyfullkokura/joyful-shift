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

# --- 1. スプレッドシート接続設定 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1dDyKAXYsHZg1ta4l7te84uSbhSea-FoyVgTeo4-kgkI/edit?gid=0#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet(worksheet_name, default_df=None):
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        if df is None or df.empty:
            return default_df
        df = df.dropna(how='all', axis=0)
        first_col = df.columns[0]
        df = df.drop_duplicates(subset=first_col, keep='first')
        df = df.set_index(first_col)
        df.index = df.index.astype(str).str.strip()
        return df
    except Exception:
        return default_df

def save_sheet(df, worksheet_name):
    try:
        client = conn.client
        sh = client.open_by_url(SPREADSHEET_URL)
        try: sh.worksheet(worksheet_name)
        except Exception: sh.add_worksheet(title=worksheet_name, rows=100, cols=40)
        
        if hasattr(df, 'data'): df = df.data
        df.index.name = "名前"
        save_df = df.reset_index()
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=save_df)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

# --- 2. 補助関数 ---
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

# --- 3. データの初期化 (完全に修正された25名名簿) ---
def init_system_data():
    master_df_raw = load_sheet("staff_master")
    
    # 削除したい名前のリスト（ガード用）
    DELETE_TARGETS = ["扇（一）", "西村（成）", "笹谷（祐）", "末登"]

    if master_df_raw is None:
        st.info("正しい名簿をセットアップ中...")
        # 【修正】重複を排除した純粋な25名リスト
        data = [
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
        master_df = pd.DataFrame(data).set_index("名前")
        save_sheet(master_df, "staff_master")
    else:
        # スプレッドシートから読み込んだ場合も、指定した名前を強制削除
        master_df = master_df_raw.copy()
        master_df = master_df[~master_df.index.isin(DELETE_TARGETS)]

    master_df['表示名'] = master_df['職種'].astype(str).str.strip() + " " + master_df.index.astype(str).str.strip()
    all_names = master_df['表示名'].tolist()
    staff_info_dict = master_df.set_index('表示名').to_dict('index')

    return master_df, all_names, staff_info_dict

master_df, ALL_NAMES, staff_info = init_system_data()

# 曜日別設定の読み込み
avail_df = load_sheet("staff_availability")
if avail_df is None:
    avail_rows = [[n] + ["10.0-23.0"]*7 for n in ALL_NAMES]
    avail_df = pd.DataFrame(avail_rows, columns=["名前"] + WEEKDAYS_JP).set_index("名前")
    save_sheet(avail_df, "staff_availability")
else:
    avail_df = avail_df.reindex(ALL_NAMES).fillna("10.0-23.0")

# 必要人数設定
req_groups = load_sheet("required_staff")
time_slots = [f"{h}:{m}" for h in range(10, 23) for m in ["00", "30"]] + ["23:00"]
if req_groups is None:
    req_groups = pd.DataFrame(2, index=time_slots, columns=["月火水木_ホール", "月火水木_キッチン", "金土_ホール", "金土_キッチン", "日_ホール", "日_キッチン"])
    req_groups.index.name = "時間"
    save_sheet(req_groups, "required_staff")

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
    r_raw = load_sheet(REQ_SHEET_NAME)
    if r_raw is None:
        req_df = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)
    else:
        req_df = r_raw.reindex(ALL_NAMES).fillna(False)
        req_df = req_df.map(lambda x: str(x).lower() in ['true', '1', 'yes'])
    
    edited_req = st.data_editor(req_df, use_container_width=True, height=600)
    if st.button("💾 希望を保存"):
        if save_sheet(edited_req, REQ_SHEET_NAME): st.success("保存しました")

# --- ② 基本設定 ---
elif mode == "② 従業員基本設定":
    if not is_admin: st.error("パスワードを入力してください")
    else:
        st.header("⚙️ 名簿の管理")
        edited_master = st.data_editor(master_df, use_container_width=True, num_rows="dynamic")
        if st.button("💾 名簿を保存"):
            if save_sheet(edited_master, "staff_master"):
                st.success("保存完了！自動で最新の名簿に更新されます。")
                st.rerun()

# --- ③ 曜日別バー ---
elif mode == "③ 曜日別可能時間(バー)":
    if not is_admin: st.error("パスワードが必要です")
    else:
        st.header("🕒 出勤可能時間設定")
        target = st.selectbox("スタッフを選択", ALL_NAMES)
        new_times = {}
        for wd in WEEKDAYS_JP:
            raw_val = avail_df.at[target, wd] if target in avail_df.index else "10.0-23.0"
            s_f, e_f = parse_range(raw_val)
            res = st.slider(f"{wd}曜日", 10.0, 23.0, (float(s_f), float(e_f)), step=0.5, format="%g時", key=f"s_{target}_{wd}")
            new_times[wd] = f"{res[0]}-{res[1]}"
        if st.button(f"💾 {target} の時間を保存"):
            for wd, t in new_times.items(): avail_df.at[target, wd] = t
            save_sheet(avail_df, "staff_availability")
            st.success("保存しました")

# --- ④ シフト案作成 ---
else:
    if not is_admin: st.error("パスワードを入力してください")
    else:
        st.header(f"📝 {year}年{month}月のシフト案")

        with st.expander("🛠️ 必要人数設定（上下ボタン）"):
            edited_req_groups = req_groups.copy()
            g_tabs = st.tabs(["📅 月〜木", "🟧 金・土", "🟥 日曜"])
            g_keys = ["月火水木", "金土", "日"]
            for i, key in enumerate(g_keys):
                with g_tabs[i]:
                    c1, c2, c3 = st.columns(3)
                    bh = c1.number_input("ホール全員", 0, 10, 2, key=f"bh_{key}")
                    bk = c2.number_input("キッチン全員", 0, 10, 2, key=f"bk_{key}")
                    if c3.button("適用", key=f"ap_{key}"):
                        edited_req_groups[f"{key}_ホール"] = bh
                        edited_req_groups[f"{key}_キッチン"] = bk
                        save_sheet(edited_req_groups, "required_staff"); st.rerun()
                    for t in time_slots:
                        cols = st.columns([1, 2, 2])
                        cols[0].write(f"**{t}**")
                        edited_req_groups.at[t, f"{key}_ホール"] = cols[1].number_input("H", 0, 10, int(edited_req_groups.at[t, f"{key}_ホール"]), key=f"nh_{key}_{t}", label_visibility="collapsed")
                        edited_req_groups.at[t, f"{key}_キッチン"] = cols[2].number_input("K", 0, 10, int(edited_req_groups.at[t, f"{key}_キッチン"]), key=f"nk_{key}_{t}", label_visibility="collapsed")
            if st.button("💾 人数設定を保存"): save_sheet(edited_req_groups, "required_staff")

        st.divider()

        req_load = load_sheet(REQ_SHEET_NAME)
        if req_load is not None:
            req_load = req_load.reindex(ALL_NAMES).fillna(False).map(lambda x: str(x).lower() in ['true', '1', 'yes'])
        else:
            req_load = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)

        if 'shift_cache' not in st.session_state:
            s_raw = load_sheet(SHIFT_SHEET_NAME)
            st.session_state.shift_cache = s_raw.reindex(ALL_NAMES).fillna("") if s_raw is not None else pd.DataFrame("", index=ALL_NAMES, columns=column_names)
        
        current_df = st.session_state.shift_cache

        col_a1, col_a2 = st.columns([2, 1])
        with col_a1:
            if st.button("🤖 公平自動生成実行"):
                new_s = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
                work_counts = {n: 0 for n in ALL_NAMES}
                target_counts = {n: staff_info[n]['週希望'] * 4.3 for n in ALL_NAMES}
                for i, col in enumerate(column_names):
                    wd_jp = WEEKDAYS_JP[calendar.weekday(year, month, i+1)]
                    g_key = "月火水木" if wd_jp in ["月","火","水","木"] else ("金土" if wd_jp in ["金","土"] else "日")
                    t_h_d = int(edited_req_groups.at["12:00", f"{g_key}_ホール"] if "12:00" in edited_req_groups.index else 2)
                    t_k_d = int(edited_req_groups.at["12:00", f"{g_key}_キッチン"] if "12:00" in edited_req_groups.index else 2)
                    t_h_n = int(edited_req_groups.at["19:00", f"{g_key}_ホール"] if "19:00" in edited_req_groups.index else 2)
                    t_k_n = int(edited_req_groups.at["19:00", f"{g_key}_キッチン"] if "19:00" in edited_req_groups.index else 2)

                    capable = [n for n in ALL_NAMES if not req_load.at[n, col]]
                    random.shuffle(capable)
                    capable.sort(key=lambda n: (work_counts[n]/target_counts[n] if target_counts[n]>0 else 99, random.random()))
                    h_c, k_c, has_cl = 0, 0, False
                    for n in capable:
                        sf, ef = parse_range(avail_df.at[n, wd_jp])
                        if sf >= ef: continue
                        t_st = f"{int(sf)}:00" if sf%1==0 else f"{int(sf)}:30"
                        role = staff_info[n]['職種']
                        if staff_info[n]['レジ締め'] and ef >= 23 and not has_cl:
                            new_s.at[n, col] = f"{t_st}-23:00"; work_counts[n]+=1; has_cl=True
                        elif sf <= 11 and h_c < t_h_d:
                            new_s.at[n, col] = f"{t_st}-18:00"; work_counts[n]+=1; h_c+=1
                st.session_state.shift_cache = new_s; st.rerun()

        with col_a2:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                current_df.to_excel(writer, sheet_name='シフト表')
                wb, ws = writer.book, writer.sheets['シフト表']
                base_f = wb.add_format({'border': 1, 'align': 'center'})
                name_f = wb.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2'})
                ws.set_column(0, 0, 25, name_f)
                ws.set_column(1, len(column_names), 12, base_f)
                ws.freeze_panes(1, 1)
            st.download_button(label="📥 見やすいExcelで保存", data=output.getvalue(), file_name=f"shift_{year}_{month:02}.xlsx")

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

        edited = st.data_editor(current_df.style.apply(highlight_logic, axis=None), column_config={c: st.column_config.SelectboxColumn(options=SHIFT_OPTIONS, width="medium") for c in column_names}, use_container_width=True, height=700)
        if st.button("💾 このシフトを確定保存"):
            if save_sheet(edited, SHIFT_SHEET_NAME): st.session_state.shift_cache = edited; st.success("保存完了")

# 月移動
st.sidebar.divider()
c1, c2 = st.sidebar.columns(2)
if c1.button("◀ 前月"): 
    st.session_state.view_date = (st.session_state.view_date - timedelta(days=28)).replace(day=1)
    st.session_state.pop('shift_cache', None); st.rerun()
if c2.button("次月 ▶"): 
    st.session_state.view_date = (st.session_state.view_date + timedelta(days=32)).replace(day=1)
    st.session_state.pop('shift_cache', None); st.rerun()