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

def load_sheet(worksheet_name, default_df):
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

def save_sheet(df, worksheet_name):
    try:
        if hasattr(df, 'data'): df = df.data
        save_df = df.copy()
        save_df.index.name = "名前"
        save_df = save_df.reset_index()
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=save_df)
        st.cache_data.clear()
        time.sleep(1)
        return True
    except Exception as e:
        st.error(f"【保存失敗】タブ '{worksheet_name}' が見つからないか、通信エラーです。")
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

# --- 3. データの初期化 (25名フル名簿) ---
def get_initial_staff():
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

master_df = load_sheet("staff_master", pd.DataFrame(get_initial_staff()).set_index("名前"))
master_df['表示名'] = master_df['職種'].astype(str).str.strip() + " " + master_df.index.astype(str).str.strip()
ALL_NAMES = [n.strip() for n in master_df['表示名'].unique().tolist() if "末登" not in n]
staff_info = master_df.set_index('表示名').to_dict('index')

avail_df = load_sheet("staff_availability", pd.DataFrame([[n] + ["10.0-23.0"]*7 for n in ALL_NAMES], columns=["名前"] + WEEKDAYS_JP).set_index("名前"))
avail_df = avail_df.reindex(ALL_NAMES).fillna("10.0-23.0")

# 人数設定の読み込み
time_slots = [f"{h}:{m}" for h in range(10, 23) for m in ["00", "30"]] + ["23:00"]
req_groups = load_sheet("required_staff", pd.DataFrame(2, index=time_slots, columns=["月火水木_ホール", "月火水木_キッチン", "金土_ホール", "金土_キッチン", "日_ホール", "日_キッチン"]))

# --- 4. 月管理 ---
if 'view_date' not in st.session_state:
    st.session_state.view_date = date.today().replace(day=1)
year, month = st.session_state.view_date.year, st.session_state.view_date.month
num_days = calendar.monthrange(year, month)[1]
column_names = [f"{d}({WEEKDAYS_JP[calendar.weekday(year, month, d)]})" for d in range(1, num_days + 1)]

REQ_SHEET_NAME = f"req_{year}_{month:02}"
SHIFT_SHEET_NAME = f"shift_{year}_{month:02}"

# --- 5. UI ---
st.sidebar.title("ジョイフル シフトWeb")
pw = st.sidebar.text_input("管理者パスワード", type="password")
is_admin = (pw == "1234")
mode = st.sidebar.radio("モード選択", ["① 休み希望入力", "② 従業員基本設定", "③ 曜日別可能時間", "④ シフト案作成"])

if mode == "① 休み希望入力":
    st.header(f"📅 {year}年{month}月の休み希望入力")
    if f'req_cache_{year}_{month}' not in st.session_state:
        r_raw = load_sheet(REQ_SHEET_NAME, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
        st.session_state[f'req_cache_{year}_{month}'] = r_raw.reindex(ALL_NAMES).fillna(False).map(lambda x: str(x).lower() in ['true', '1', 'yes'])
    edited = st.data_editor(st.session_state[f'req_cache_{year}_{month}'], use_container_width=True, height=700)
    if st.button("💾 希望を保存"):
        if save_sheet(edited, REQ_SHEET_NAME): 
            st.session_state[f'req_cache_{year}_{month}'] = edited
            st.success("保存しました")

elif mode == "② 従業員基本設定":
    if not is_admin: st.error("管理者専用")
    else:
        edited = st.data_editor(master_df.drop(columns=['表示名']), use_container_width=True, num_rows="dynamic")
        if st.button("💾 名簿を保存"): save_sheet(edited, "staff_master")

elif mode == "③ 曜日別可能時間":
    if not is_admin: st.error("管理者専用")
    else:
        target = st.selectbox("スタッフ選択", ALL_NAMES)
        new_times = {}
        for wd in WEEKDAYS_JP:
            raw = avail_df.at[target, wd] if target in avail_df.index else "10.0-23.0"
            sf, ef = parse_range(raw)
            res = st.slider(wd, 10.0, 23.0, (float(sf), float(ef)), step=0.5, key=f"s_{target}_{wd}")
            new_times[wd] = f"{res[0]}-{res[1]}"
        if st.button("💾 設定を保存"):
            for wd, t in new_times.items(): avail_df.at[target, wd] = t
            save_sheet(avail_df, "staff_availability")

else:
    if not is_admin: st.error("管理者パスワードを入力してください")
    else:
        st.header(f"📝 {year}年{month}月のシフト案")

        # ====================== 【人数設定機能】ここから ======================
        with st.expander("🛠️ 必要人数設定（グループ別・時間帯個別調整）", expanded=False):
            groups_labels = {"月火水木": "📅 平日 (月〜木)", "金土": "🟧 週末 (金・土)", "日": "🟥 日曜日"}
            edited_req_groups = req_groups.copy()
            tabs = st.tabs(list(groups_labels.values()))
            for i, (key, label) in enumerate(groups_labels.items()):
                with tabs[i]:
                    st.write(f"#### {label} の一括設定")
                    c1, c2, c3 = st.columns(3)
                    bh = c1.number_input("ホール全員", 0, 10, 2, key=f"bh_{key}")
                    bk = c2.number_input("キッチン全員", 0, 10, 2, key=f"bk_{key}")
                    if c3.button("全時間に適用", key=f"ap_{key}"):
                        edited_req_groups[f"{key}_ホール"] = bh; edited_req_groups[f"{key}_キッチン"] = bk
                        save_sheet(edited_req_groups, "required_staff"); st.rerun()
                    st.divider(); st.write("#### 時間別調整")
                    for t in time_slots:
                        cols = st.columns([1, 2, 2])
                        cols[0].write(f"**{t}**")
                        edited_req_groups.at[t, f"{key}_ホール"] = cols[1].number_input("H", 0, 10, int(edited_req_groups.at[t, f"{key}_ホール"]), key=f"nh_{key}_{t}", label_visibility="collapsed")
                        edited_req_groups.at[t, f"{key}_キッチン"] = cols[2].number_input("K", 0, 10, int(edited_req_groups.at[t, f"{key}_キッチン"]), key=f"nk_{key}_{t}", label_visibility="collapsed")
            if st.button("💾 人数設定を保存"): save_sheet(edited_req_groups, "required_staff")
        # ====================== 【人数設定機能】ここまで ======================

        st.divider()
        req_load = load_sheet(REQ_SHEET_NAME, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
        req_load = req_load.reindex(ALL_NAMES).fillna(False).map(lambda x: str(x).lower() in ['true', '1', 'yes'])

        if 'shift_cache' not in st.session_state:
            s_raw = load_sheet(SHIFT_SHEET_NAME, pd.DataFrame("", index=ALL_NAMES, columns=column_names))
            st.session_state.shift_cache = s_raw.reindex(ALL_NAMES).fillna("")
        
        current_df = st.session_state.shift_cache

        col_a1, col_a2 = st.columns([2, 1])
        with col_a1:
            if st.button("🤖 公平自動生成実行"):
                new_s = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
                work_counts = {n: 0 for n in ALL_NAMES}; target_counts = {n: staff_info[n]['週希望']*4.3 for n in ALL_NAMES}
                for i, col in enumerate(column_names):
                    wd_jp = WEEKDAYS_JP[calendar.weekday(year, month, i+1)]
                    g_key = "月火水木" if wd_jp in ["月","火","水","木"] else ("金土" if wd_jp in ["金","土"] else "日")
                    thd, tkd = int(edited_req_groups.at["12:00", f"{g_key}_ホール"]), int(edited_req_groups.at["12:00", f"{g_key}_キッチン"])
                    thn, tkn = int(edited_req_groups.at["19:00", f"{g_key}_ホール"]), int(edited_req_groups.at["19:00", f"{g_key}_キッチン"])
                    capable = [n for n in ALL_NAMES if not req_load.at[n, col]]
                    random.shuffle(capable); capable.sort(key=lambda n: (work_counts[n]/target_counts[n] if target_counts[n]>0 else 99, random.random()))
                    h_cnt, k_cnt, has_cl = 0, 0, 0, 0, False
                    for n in capable:
                        sf, ef = parse_range(avail_df.at[n, wd_jp]); role = staff_info[n]['職種']
                        if sf >= ef: continue
                        tst = f"{int(sf)}:00" if sf%1==0 else f"{int(sf)}:30"
                        if staff_info[n]['レジ締め'] and ef >= 23 and not has_cl:
                            new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; has_cl=True
                        elif sf <= 11 and ef >= 18:
                            if ("☕" in role or "👔" in role) and h_cnt < thd: new_s.at[n, col] = f"{tst}-18:00"; work_counts[n]+=1; h_cnt+=1
                            elif ("🍳" in role or "👔" in role) and k_cnt < tkd: new_s.at[n, col] = f"{tst}-18:00"; work_counts[n]+=1; k_cnt+=1
                st.session_state.shift_cache = new_s; st.rerun()

        with col_a2:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                current_df.to_excel(writer, sheet_name='シフト')
                wb, ws = writer.book, writer.sheets['シフト']
                ws.set_column(0,0,25); ws.set_column(1,len(column_names),12)
            st.download_button("📥 Excel保存", output.getvalue(), f"shift_{year}_{month:02}.xlsx")

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
        if st.button("💾 このシフトを保存"):
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