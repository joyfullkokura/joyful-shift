import streamlit as st
import pandas as pd
import calendar
import random
import io
import time
from datetime import date, timedelta
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="ジョイフル シフト管理PRO", layout="wide")

# --- 1. 定数設定（一番最初に定義してエラーを防ぐ） ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1dDyKAXYsHZg1ta4l7te84uSbhSea-FoyVgTeo4-kgkI/edit?gid=0#gid=0"
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]
TIME_SLOTS = [f"{h}:{m}" for h in range(10, 23) for m in ["00", "30"]] + ["23:00"]
SHIFT_OPTIONS = ["", "10:00-18:00", "18:00-23:00", "10:00-23:00", "10:00-15:00", "11:00-18:00", "17:00-23:00", "18:30-23:00", "19:00-23:00"]

# --- 2. 補助関数 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(sheet_name, default_df):
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=sheet_name, ttl=0)
        if df is not None and not df.empty:
            df = df.dropna(how='all', axis=0)
            df = df.drop_duplicates(subset=df.columns[0]).set_index(df.columns[0])
            df.index = df.index.astype(str).str.strip()
            return df
        return default_df
    except: return default_df

def save_data(df, sheet_name):
    try:
        if hasattr(df, 'data'): df = df.data
        save_df = df.copy()
        save_df.index.name = "名前"
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=sheet_name, data=save_df.reset_index())
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"保存失敗: {e}")
        return False

def time_to_float(t_str):
    try:
        h, m = map(int, str(t_str).split(":"))
        return h + (0.5 if m == 30 else 0)
    except: return 0.0

def parse_range(r_str):
    try:
        parts = str(r_str).split("-")
        return float(parts[0]), float(parts[1])
    except: return 10.0, 23.0

def get_initial_staff():
    return [
        {"名前": "多田（店長）", "職種": "👔社員", "レジ締め": True, "週希望": 5},
        {"名前": "河野", "職種": "👔社員", "レジ締め": True, "週希望": 5},
        {"名前": "末益", "職種": "🍳DK", "レジ締め": False, "週希望": 6},
        {"名前": "扇", "職種": "☕DF", "レジ締め": True, "週希望": 4},
        {"名前": "高木", "職種": "☕DF", "レジ締め": True, "週希望": 4},
        {"名前": "笹谷", "職種": "☕DF", "レジ締め": True, "週希望": 4},
        {"名前": "西村", "職種": "☕DF", "レジ締め": True, "週希望": 3},
        {"名前": "武久", "職種": "☕DF", "レジ締め": False, "週希望": 4},
        {"名前": "持田", "職種": "☕DF", "レジ締め": False, "週希望": 2},
        {"名前": "永田", "職種": "☕DF", "レジ締め": False, "週希望": 2},
        {"名前": "宝村", "職種": "☕DF", "レジ締め": False, "週希望": 3},
        {"名前": "竹浦", "職種": "☕DF", "レジ締め": False, "週希望": 2},
        {"名前": "宮川", "職種": "☕DF", "レジ締め": False, "週希望": 3},
        {"名前": "キサン", "職種": "🍳DK", "レジ締め": False, "週希望": 4},
        {"名前": "太田", "職種": "🍳DK", "レジ締め": False, "週希望": 3},
        {"名前": "小田川", "職種": "🍳DK", "レジ締め": False, "週希望": 4},
        {"名前": "内田", "職種": "🍳DK", "レジ締め": False, "週希望": 5},
        {"名前": "十河", "職種": "🍳DK", "レジ締め": False, "週希望": 3},
        {"名前": "井上", "職種": "🍳DK", "レジ締め": False, "週希望": 3},
        {"名前": "蜂谷", "職種": "🍳DK", "レジ締め": False, "週希望": 4},
        {"名前": "八田", "職種": "🍳DK", "レジ締め": False, "週希望": 3},
        {"名前": "西田", "職種": "🍳DK", "レジ締め": False, "週希望": 4},
        {"名前": "清水", "職種": "🍳DK", "レジ締め": False, "週希望": 4},
        {"名前": "松村", "職種": "🍳DK", "レジ締め": False, "週希望": 5},
        {"名前": "渡部", "職種": "🍳DK", "レジ締め": False, "週希望": 5},
    ]

master_df = load_sheet_cached("staff_master", pd.DataFrame(get_initial_staff()).set_index("名前"))
master_df['表示名'] = master_df['職種'].astype(str).str.strip() + " " + master_df.index.astype(str).str.strip()
ALL_NAMES = [n.strip() for n in master_df['表示名'].unique().tolist()]
staff_info = master_df.set_index('表示名').to_dict('index')

avail_df = load_sheet_cached("staff_availability", pd.DataFrame([[n] + ["10.0-23.0"]*7 for n in ALL_NAMES], columns=["名前"] + WEEKDAYS_JP).set_index("名前"))
avail_df = avail_df.reindex(ALL_NAMES).fillna("10.0-23.0")

# --- 4. 月管理 ---
if 'view_date' not in st.session_state: st.session_state.view_date = date.today().replace(day=1)
year, month = st.session_state.view_date.year, st.session_state.view_date.month
num_days = calendar.monthrange(year, month)[1]
column_names = [f"{d}({WEEKDAYS_JP[calendar.weekday(year, month, d)]})" for d in range(1, num_days + 1)]

REQ_SHEET = f"req_{year}_{month:02}"
SHIFT_SHEET = f"shift_{year}_{month:02}"

mode = st.sidebar.radio("機能を選択", ["① 休み希望", "② 従業員設定", "③ 曜日別設定", "④ シフト作成"])

# --- ① 休み希望 ---
if mode == "① 休み希望":
    st.header(f"📅 {year}年{month}月の休み希望")
    r_raw = load_sheet_cached(REQ_SHEET, pd.DataFrame(False, index=ALL_NAMES, columns=column_names), ttl_sec=0)
    req_df = r_raw.reindex(ALL_NAMES).fillna(False)
    req_df = req_df.map(lambda x: str(x).upper() == "TRUE" if isinstance(x, str) else bool(x))
    edited = st.data_editor(req_df, use_container_width=True, height=700)
    if st.button("💾 希望を保存", key="save_req"):
        if save_sheet_robust(edited, REQ_SHEET): st.success("保存完了")

# --- ② & ③ 管理者機能（前回と同じため省略可、コードは維持） ---
elif mode == "② 従業員設定":
    if not is_admin: st.error("管理者専用")
    else:
        edited = st.data_editor(master_df.drop(columns=['表示名']), use_container_width=True, num_rows="dynamic")
        if st.button("💾 名簿保存", key="save_staff"): save_sheet_robust(edited, "staff_master")

elif mode == "③ 曜日別設定":
    if not is_admin: st.error("管理者専用")
    else:
        target = st.selectbox("スタッフ", ALL_NAMES)
        new_times = {}
        for wd in WEEKDAYS_JP:
            raw = avail_df.at[target, wd] if target in avail_df.index else "10.0-23.0"
            sf, ef = parse_range(raw)
            res = st.slider(wd, 10.0, 23.0, (float(sf), float(ef)), step=0.5)
            new_times[wd] = f"{res[0]}-{res[1]}"
        if st.button("💾 曜日別保存", key="save_avail"):
            for wd, t in new_times.items(): avail_df.at[target, wd] = t
            save_sheet_robust(avail_df, "staff_availability")

# --- ④ シフト作成 (重要修正箇所) ---
else:
    if not is_admin: st.error("管理者パスワードを入力してください")
    else:
        st.header(f"📝 {year}年{month}月のシフト案")
        req_groups = load_sheet_cached("required_staff", pd.DataFrame(2, index=TIME_SLOTS, columns=[f"{g}_{p}" for g in ["月火水木","金土","日"] for p in ["ホール","キッチン"]]))
        
        # 休み希望をキャッシュなしで強制取得
        r_load_raw = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=REQ_SHEET, ttl=0)
        if r_load_raw is not None and not r_load_raw.empty:
            r_load_raw = r_load_raw.drop_duplicates(subset=r_load_raw.columns[0])
            req_load = r_load_raw.set_index(r_load_raw.columns[0]).reindex(ALL_NAMES).fillna(False)
            req_load = req_load.map(lambda x: str(x).upper() == "TRUE")
        else:
            req_load = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)

        shift_key = f"shift_cache_{year}_{month}"
        if shift_key not in st.session_state:
            s_raw = load_sheet_cached(SHIFT_SHEET, pd.DataFrame("", index=ALL_NAMES, columns=column_names))
            st.session_state[shift_key] = s_raw.reindex(ALL_NAMES).fillna("")
        current_df = st.session_state[shift_key]

        col_a1, col_a2 = st.columns([2, 1])
        with col_a1:
            if st.button("🤖 必要人数と連勤を考慮して自動生成"):
                new_s = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
                work_counts = {n: 0 for n in ALL_NAMES}
                consecutive_days = {n: 0 for n in ALL_NAMES} # 連勤数管理
                target_counts = {n: (staff_info[n]['週希望'] if staff_info[n]['週希望']>0 else 1)*4.3 for n in ALL_NAMES}
                
                for i, col in enumerate(column_names):
                    wd_jp = WEEKDAYS_JP[calendar.weekday(year, month, i+1)]
                    g_key = "月火水木" if wd_jp in ["月","火","水","木"] else ("金土" if wd_jp in ["金","土"] else "日")
                    thd, tkd = int(req_groups.at["12:00", f"{g_key}_ホール"]), int(req_groups.at["12:00", f"{g_key}_キッチン"])
                    thn, tkn = int(req_groups.at["19:00", f"{g_key}_ホール"]), int(req_groups.at["19:00", f"{g_key}_キッチン"])

                    # 候補者のフィルタリング（休み希望Trueの人と6連勤以上の人を外す）
                    capable = []
                    for n in ALL_NAMES:
                        if req_load.at[n, col] == False and consecutive_days[n] < 6:
                            # 目標日数を超えすぎている社員は一旦温存
                            if "👔" in n and work_counts[n] > target_counts[n] and i < num_days - 3:
                                continue
                            capable.append(n)
                    
                    random.shuffle(capable)
                    capable.sort(key=lambda n: (work_counts[n]/target_counts[n], random.random()))

                    hd_c, kd_c, hn_c, kn_c, has_cl = 0, 0, 0, 0, False
                    for n in capable:
                        sf, ef = parse_range(avail_df.at[n, wd_jp] if n in avail_df.index else "10.0-23.0")
                        if sf >= ef: continue
                        tst = f"{int(sf)}:00" if sf%1==0 else f"{int(sf)}:30"
                        role = staff_info[n]['職種']

                        # レジ締め
                        if staff_info[n]['レジ締め'] and ef >= 23 and not has_cl:
                            new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; hn_c+=1; has_cl=True; consecutive_days[n]+=1
                        # 昼
                        elif sf <= 11 and ef >= 18:
                            if ("☕" in role or "👔" in role) and hd_c < thd: 
                                new_s.at[n, col] = f"{tst}-18:00"; work_counts[n]+=1; hd_c+=1; consecutive_days[n]+=1
                            elif ("🍳" in role or "👔" in role) and kd_c < tkd: 
                                new_s.at[n, col] = f"{tst}-18:00"; work_counts[n]+=1; kd_c+=1; consecutive_days[n]+=1
                        # 夜
                        elif ef >= 23:
                            if ("☕" in role or "👔" in role) and hn_c < thn: 
                                new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; hn_c+=1; consecutive_days[n]+=1
                            elif ("🍳" in role or "👔" in role) and kn_c < tkn: 
                                new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; kn_c+=1; consecutive_days[n]+=1
                    
                    # 出勤しなかった人の連勤カウントをリセット
                    for n in ALL_NAMES:
                        if new_s.at[n, col] == "": consecutive_days[n] = 0

                st.session_state[shift_key] = new_s
                st.rerun()

        with col_a2:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                current_df.to_excel(writer, sheet_name='シフト')
                wb, ws = writer.book, writer.sheets['シフト']
                f_name = wb.add_format({'bold':True, 'border':1, 'bg_color':'#F2F2F2'})
                f_base = wb.add_format({'border':1, 'align':'center'})
                ws.set_column(0,0,25,f_name); ws.set_column(1,len(column_names),12,f_base)
                for c_idx, val in enumerate(current_df.columns):
                    if "(土)" in val: ws.write(0, c_idx + 1, val, wb.add_format({'bold':True, 'bg_color':'#CCE5FF', 'font_color':'#0000FF', 'border':1}))
                    elif "(日)" in val: ws.write(0, c_idx + 1, val, wb.add_format({'bold':True, 'bg_color':'#FFCCCC', 'font_color':'#FF0000', 'border':1}))
                ws.freeze_panes(1, 1)
            st.download_button("📥 見やすいExcel保存", output.getvalue(), f"shift_{year}_{month:02}.xlsx", key="dl_btn")

        def highlight_logic(data):
            styles = pd.DataFrame('', index=data.index, columns=data.columns)
            for col in data.columns:
                try:
                    wd = WEEKDAYS_JP[calendar.weekday(year, month, int(col.split("(")[0]))]
                    for name in data.index:
                        if name in req_load.index and req_load.at[name, col]:
                            styles.at[name, col] = 'background-color: #ffd1d1; color: black;'
                            continue
                        val = data.at[name, col]
                        if val and "-" in str(val):
                            si, ei = time_to_float(val.split("-")[0]), time_to_float(val.split("-")[1])
                            sl, el = parse_range(avail_df.at[name, wd] if name in avail_df.index else "10.0-23.0")
                            if si < sl or ei > el: styles.at[name, col] = 'background-color: #ff5555; color: white;'
                except: pass
            return styles

        edited = st.data_editor(current_df.style.apply(highlight_logic, axis=None), column_config={c: st.column_config.SelectboxColumn(options=SHIFT_OPTIONS, width="medium") for c in column_names}, use_container_width=True, height=750, key="editor_shift")
        if st.button("💾 このシフトを確定保存"):
            if save_sheet_robust(edited, SHIFT_SHEET):
                st.session_state[shift_key] = edited
                st.success("保存完了")
# 月移動（サイドバー）
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