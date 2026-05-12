import streamlit as st
import pandas as pd
import calendar
import os
import random
import io
from datetime import date, timedelta
from streamlit_gsheets import GSheetsConnection
# ----------------------------
st.set_page_config(page_title="ジョイフル シフト管理PRO(Web版)", layout="wide")

# --- 1. スプレッドシート接続設定 ---
# あなたのスプレッドシートURL
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1dDyKAXYsHZg1ta4l7te84uSbhSea-FoyVgTeo4-kgkI/edit?gid=0#gid=0"

# 接続の作成
conn = st.connection("gsheets", type=GSheetsConnection)

# --- データ読み書き用関数 ---
def load_sheet(worksheet_name, default_df=None):
    """指定したシートを読み込む。なければデフォルトを返す"""
    try:
        # ttl=0でキャッシュを無効化し、常に最新を取得
        return conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
    except Exception:
        return default_df

def save_sheet(df, worksheet_name):
    """指定したシートに保存する"""
    # インデックスが含まれている場合はリセットして保存
    save_df = df.reset_index() if df.index.name else df
    conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=save_df)
    st.cache_data.clear() # キャッシュをクリア

# --- 2. 共通設定と補助関数 ---
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]
SHIFT_OPTIONS = [""]
for h in range(10, 23):
    for m in ["00", "30"]:
        SHIFT_OPTIONS.append(f"{h}:{m}-18:00")
        SHIFT_OPTIONS.append(f"{h}:{m}-23:00")
SHIFT_OPTIONS = sorted(list(set(SHIFT_OPTIONS + ["10:00-15:00", "11:00-18:00", "18:00-23:00", "10:00-23:00"])))

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

# --- 3. データの初期化 (スプレッドシート連動) ---
# 名簿の読み込み
master_df = load_sheet("staff_master")
if master_df is None or master_df.empty:
    st.warning("スプレッドシートのstaff_masterが空です。初期データを書き込みます...")
    data = [
            {"名前": "多田（店長）", "職種": "👔社員", "レジ締め": True, "デザート": True, "週希望": 6, "傾向": "ALL"},
            {"名前": "河野", "職種": "👔社員", "レジ締め": True, "デザート": True, "週希望": 6, "傾向": "ALL"},
            {"名前": "末益", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 6, "傾向": "ALL"},
            {"名前": "扇", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 4, "傾向": "NIGHT"},
            {"名前": "高木", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 4, "傾向": "NIGHT"},
            {"名前": "笹谷", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 4, "傾向": "NIGHT"},
            {"名前": "西村", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 3, "傾向": "NIGHT"},
            {"名前": "武久", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 4, "傾向": "NIGHT"},
            {"名前": "西村（成）", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 2, "傾向": "NIGHT"},
            {"名前": "扇（一）", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 3, "傾向": "NIGHT"},
            {"名前": "持田", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 2, "傾向": "NIGHT"},
            {"名前": "永田", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 2, "傾向": "NIGHT"},
            {"名前": "宝村", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 3, "傾向": "NIGHT"},
            {"名前": "笹谷（祐）", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 4, "傾向": "DAY"},
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
    master_df = pd.DataFrame(data)
    save_sheet(master_df, "staff_master")

master_df['表示名'] = master_df['職種'].astype(str).str.strip() + " " + master_df['名前'].astype(str).str.strip()
ALL_NAMES = [name.strip() for name in master_df['表示名'].tolist()]
staff_info = master_df.set_index('表示名').to_dict('index')

# 曜日設定の読み込み
avail_df = load_sheet("staff_availability")
if avail_df is None or avail_df.empty:
    avail_rows = []
    for _, row in master_df.iterrows():
        d_name = f"{row['職種']} {row['名前']}".strip()
        t = "10.0-18.0" if row['傾向'] == "DAY" else ("18.0-23.0" if row['傾向'] == "NIGHT" else "10.0-23.0")
        avail_rows.append([d_name] + [t]*7)
    avail_df = pd.DataFrame(avail_rows, columns=["名前"] + WEEKDAYS_JP).set_index("名前")
    save_sheet(avail_df.reset_index(), "staff_availability")
else:
    avail_df = avail_df.set_index(avail_df.columns[0])
    avail_df.index = avail_df.index.str.strip()
    # 名簿と同期
    avail_df = avail_df.reindex(ALL_NAMES).fillna("10.0-23.0")

# 必要人数設定の読み込み
req_groups = load_sheet("required_staff")
if req_groups is None or req_groups.empty:
    time_slots = [f"{h}:{m}" for h in range(10, 23) for m in ["00", "30"]] + ["23:00"]
    req_groups = pd.DataFrame(2, index=time_slots, columns=["月火水木_ホール", "月火水木_キッチン", "金土_ホール", "金土_キッチン", "日_ホール", "日_キッチン"])
    save_sheet(req_groups.reset_index().rename(columns={'index':'時間'}), "required_staff")
else:
    req_groups = req_groups.set_index(req_groups.columns[0])

# --- 4. 月管理 ---
if 'view_date' not in st.session_state:
    st.session_state.view_date = date.today().replace(day=1)
year, month = st.session_state.view_date.year, st.session_state.view_date.month
num_days = calendar.monthrange(year, month)[1]
column_names = [f"{d}({WEEKDAYS_JP[calendar.weekday(year, month, d)]})" for d in range(1, num_days + 1)]

# スプレッドシートのシート名（月別）
REQ_SHEET_NAME = f"req_{year}_{month:02}"
SHIFT_SHEET_NAME = f"shift_{year}_{month:02}"

# --- 5. パスワードロックとメニュー ---
st.sidebar.title("ジョイフル シフトWeb")
pw = st.sidebar.text_input("管理者パスワードを入力", type="password")
is_admin = (pw == "1234")
mode = st.sidebar.radio("モード選択", ["① 休み希望入力", "② 従業員基本設定", "③ 曜日別可能時間(バー)", "④ シフト案作成"])

# --- ① 休み希望 ---
if mode == "① 休み希望入力":
    st.header(f"📅 {year}年{month}月の休み希望入力")
    req_df = load_sheet(REQ_SHEET_NAME)
    if req_df is None or req_df.empty:
        req_df = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)
    else:
        req_df = req_df.set_index(req_df.columns[0]).reindex(ALL_NAMES).fillna(False)
    
    edited_req = st.data_editor(req_df, use_container_width=True, height=600)
    if st.button("💾 この月の希望を保存"):
        save_sheet(edited_req, REQ_SHEET_NAME)
        st.success("スプレッドシートに保存しました")

# --- ② 基本設定 (管理者) ---
elif mode == "② 従業員基本設定":
    if not is_admin: st.error("管理者専用です")
    else:
        st.header("⚙️ 従業員基本設定")
        edited_master = st.data_editor(master_df.drop(columns=['表示名']), 
                                        column_config={"週希望": st.column_config.SelectboxColumn(options=[1,2,3,4,5,6,7])},
                                        use_container_width=True, num_rows="dynamic")
        if st.button("💾 名簿を保存"):
            save_sheet(edited_master, "staff_master")
            st.success("保存しました。リロードして反映してください。")

# --- ③ 曜日別バー (管理者) ---
elif mode == "③ 曜日別可能時間(バー)":
    if not is_admin: st.error("管理者専用です")
    else:
        st.header("🕒 出勤可能時間（バー）")
        target = st.selectbox("スタッフを選択", ALL_NAMES)
        new_times = {}
        for wd in WEEKDAYS_JP:
            raw_val = avail_df.at[target, wd] if target in avail_df.index else "10.0-23.0"
            s_f, e_f = parse_range(raw_val)
            res = st.slider(f"{wd}曜日", 10.0, 23.0, (float(s_f), float(e_f)), step=0.5, format="%g時", key=f"{target}_{wd}")
            new_times[wd] = f"{res[0]}-{res[1]}"
        if st.button(f"💾 {target} の時間を保存"):
            for wd, t in new_times.items(): avail_df.at[target, wd] = t
            save_sheet(avail_df, "staff_availability")
            st.success("保存完了")

# --- ④ シフト案作成 (管理者) ---
else:
    if not is_admin: st.error("管理者専用です")
    else:
        st.header(f"📝 {year}年{month}月のシフト案")
        
        # 必要人数設定（上下ボタン付き）
        with st.expander("🛠️ 必要人数設定（グループ別調整）"):
            edited_req_groups = req_groups.copy()
            g_tabs = st.tabs(["📅 月〜木", "🟧 金・土", "🟥 日曜"])
            g_keys = ["月火水木", "金土", "日"]
            for i, key in enumerate(g_keys):
                with g_tabs[i]:
                    st.write(f"**{key} の一括設定**")
                    c_b1, c_b2, c_b3 = st.columns(3)
                    new_h = c_b1.number_input("ホール全員", 0, 10, 2, key=f"b_h_{key}")
                    new_k = c_b2.number_input("キッチン全員", 0, 10, 2, key=f"b_k_{key}")
                    if c_b3.button("全時間に適用", key=f"apply_{key}"):
                        edited_req_groups[f"{key}_ホール"] = new_h
                        edited_req_groups[f"{key}_キッチン"] = new_k
                        save_sheet(edited_req_groups, "required_staff")
                        st.rerun()
                    
                    st.divider()
                    st.write("個別時間帯調整")
                    for t in edited_req_groups.index:
                        c_t = st.columns([1, 2, 2])
                        c_t[0].write(f"**{t}**")
                        edited_req_groups.at[t, f"{key}_ホール"] = c_t[1].number_input("H", 0, 10, int(edited_req_groups.at[t, f"{key}_ホール"]), key=f"n_h_{key}_{t}", label_visibility="collapsed")
                        edited_req_groups.at[t, f"{key}_キッチン"] = c_t[2].number_input("K", 0, 10, int(edited_req_groups.at[t, f"{key}_キッチン"]), key=f"n_k_{key}_{t}", label_visibility="collapsed")

            if st.button("💾 全ての人数設定を保存", type="primary"):
                save_sheet(edited_req_groups, "required_staff")
                st.success("保存完了")

        st.divider()

        # 休み希望の読み込み
        req_load = load_sheet(REQ_SHEET_NAME, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
        if not req_load.empty:
            req_load = req_load.set_index(req_load.columns[0]).reindex(ALL_NAMES).fillna(False)
            req_load = req_load.map(lambda x: str(x).lower() in ['true', '1', 'yes', 'y'])

        # シフトデータのキャッシュ管理
        if 'shift_data_cache' not in st.session_state:
            sdf = load_sheet(SHIFT_SHEET_NAME)
            if sdf is not None and not sdf.empty:
                st.session_state.shift_data_cache = sdf.set_index(sdf.columns[0]).reindex(ALL_NAMES).fillna("")
            else:
                st.session_state.shift_data_cache = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
        
        current_df = st.session_state.shift_data_cache

        col_a1, col_a2 = st.columns([2, 1])
        with col_a1:
            if st.button("🤖 必要人数と公平性を考慮して自動生成"):
                new_s = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
                work_counts = {n: 0 for n in ALL_NAMES}
                target_counts = {n: staff_info[n]['週希望'] * 4.3 for n in ALL_NAMES}

                for i, col in enumerate(column_names):
                    wd_idx = calendar.weekday(year, month, i+1)
                    wd_jp = WEEKDAYS_JP[wd_idx]
                    g_key = "月火水木" if wd_jp in ["月","火","水","木"] else ("金土" if wd_jp in ["金","土"] else "日")
                    
                    # 必要人数の取得（12時と19時を代表値に）
                    t_h_d = int(edited_req_groups.at["12:00", f"{g_key}_ホール"])
                    t_k_d = int(edited_req_groups.at["12:00", f"{g_key}_キッチン"])
                    t_h_n = int(edited_req_groups.at["19:00", f"{g_key}_ホール"])
                    t_k_n = int(edited_req_groups.at["19:00", f"{g_key}_キッチン"])

                    capable = [n for n in ALL_NAMES if not req_load.at[n, col]]
                    capable.sort(key=lambda n: (work_counts[n]/target_counts[n] if target_counts[n]>0 else 99, random.random()))

                    h_d, k_d, h_n, k_n, has_cl = 0, 0, 0, 0, False
                    for n in capable:
                        sf, ef = parse_range(avail_df.at[n, wd_jp])
                        if sf >= ef: continue
                        t_st = f"{int(sf)}:00" if sf%1==0 else f"{int(sf)}:30"
                        role = staff_info[n]['職種']

                        if staff_info[n]['レジ締め'] and ef >= 23 and not has_cl:
                            new_s.at[n, col] = f"{t_st}-23:00"; work_counts[n]+=1; h_n+=1; has_cl=True
                        elif sf <= 11 and ef >= 18:
                            if ("☕" in role or "👔" in role) and h_d < t_h_d:
                                new_s.at[n, col] = f"{t_st}-18:00"; work_counts[n]+=1; h_d+=1
                            elif ("🍳" in role or "👔" in role) and k_d < t_k_d:
                                new_s.at[n, col] = f"{t_st}-18:00"; work_counts[n]+=1; k_d+=1
                        elif ef >= 23:
                            if ("☕" in role or "👔" in role) and h_n < t_h_n:
                                new_s.at[n, col] = f"{t_st}-23:00"; work_counts[n]+=1; h_n+=1
                            elif ("🍳" in role or "👔" in role) and k_n < t_k_n:
                                new_s.at[n, col] = f"{t_st}-23:00"; work_counts[n]+=1; k_n+=1
                
                st.session_state.shift_data_cache = new_s
                st.rerun()

        with col_a2:
            # Excel出力
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                current_df.to_excel(writer, sheet_name='シフト表')
                workbook, worksheet = writer.book, writer.sheets['シフト表']
                fmt = workbook.add_format({'border': 1, 'align': 'center'})
                name_fmt = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2'})
                worksheet.set_column(0, 0, 25, name_fmt)
                worksheet.set_column(1, len(column_names), 12, fmt)
                worksheet.freeze_panes(1, 1)
            st.download_button(label="📥 見やすいExcelで保存", data=output.getvalue(), file_name=f"joyful_shift_{year}_{month:02}.xlsx")

        def highlight_logic(data):
            styles = pd.DataFrame('', index=data.index, columns=data.columns)
            for col in data.columns:
                try:
                    d_num = int(col.split("(")[0]); wd_jp = WEEKDAYS_JP[calendar.weekday(year, month, d_num)]
                    for name in data.index:
                        if name in req_load.index and req_load.at[name, col]:
                            styles.at[name, col] = 'background-color: #ffd1d1;'
                        val = data.at[name, col]
                        if val and "-" in str(val):
                            si, ei = time_to_float(val.split("-")[0]), time_to_float(val.split("-")[1])
                            sl, el = parse_range(avail_df.at[name, wd_jp] if name in avail_df.index else "10.0-23.0")
                            if si < sl or ei > el: styles.at[name, col] = 'background-color: #ff5555; color: white;'
                except: pass
            return styles

        config = {c: st.column_config.SelectboxColumn(options=SHIFT_OPTIONS, width="medium") for c in column_names}
        edited = st.data_editor(current_df.style.apply(highlight_logic, axis=None), column_config=config, use_container_width=True, height=600)
        
        if st.button("💾 このシフトをスプレッドシートに保存"):
            save_sheet(edited, SHIFT_SHEET_NAME)
            st.session_state.shift_data_cache = edited
            st.success("保存完了")

# 月移動
st.sidebar.divider()
c1, c2 = st.sidebar.columns(2)
if c1.button("◀ 前月"): 
    st.session_state.view_date = (st.session_state.view_date - timedelta(days=28)).replace(day=1)
    st.session_state.pop('shift_data_cache', None)
    st.rerun()
if c2.button("次月 ▶"): 
    st.session_state.view_date = (st.session_state.view_date + timedelta(days=32)).replace(day=1)
    st.session_state.pop('shift_data_cache', None)
    st.rerun()