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
    """キャッシュを一切使わずにスプレッドシートを読み込む"""
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
    """データを安全に保存する"""
    try:
        if hasattr(df, 'data'): df = df.data # スタイル解除
        save_df = df.copy()
        save_df.index.name = "名前"
        save_df = save_df.reset_index()
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=save_df)
        st.cache_data.clear() 
        time.sleep(1)
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

# --- 3. データの初期化 (25名フル名簿) ---
def get_initial_staff():
    return [
        {"名前": "多田（店長）", "職種": "👔社員", "レジ締め": True, "デザート": True, "週希望": 6},
        {"名前": "河野", "職種": "👔社員", "レジ締め": True, "デザート": True, "週希望": 6},
        {"名前": "末益", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 6},
        {"名前": "扇", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 4},
        {"名前": "高木", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 4},
        {"名前": "笹谷", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 4},
        {"名前": "西村", "職種": "☕DF", "レジ締め": True, "デザート": True, "週希望": 3},
        {"名前": "武久", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "持田", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 2},
        {"名前": "永田", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 2},
        {"名前": "宝村", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "竹浦", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 2},
        {"名前": "宮川", "職種": "☕DF", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "キサン", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "太田", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "小田川", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "内田", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 5},
        {"名前": "十河", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "井上", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "蜂谷", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "八田", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 3},
        {"名前": "西田", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "清水", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 4},
        {"名前": "松村", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 5},
        {"名前": "渡部", "職種": "🍳DK", "レジ締め": False, "デザート": False, "週希望": 5},
    ]

master_df = load_sheet("staff_master", pd.DataFrame(get_initial_staff()).set_index("名前"))
master_df['表示名'] = master_df['職種'].astype(str).str.strip() + " " + master_df.index.astype(str).str.strip()
ALL_NAMES = [n.strip() for n in master_df['表示名'].unique().tolist()]
staff_info = master_df.set_index('表示名').to_dict('index')

avail_df = load_sheet("staff_availability", pd.DataFrame([[n] + ["10.0-23.0"]*7 for n in ALL_NAMES], columns=["名前"] + WEEKDAYS_JP).set_index("名前"))
avail_df = avail_df.reindex(ALL_NAMES).fillna("10.0-23.0")

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
pw = st.sidebar.text_input("パスワード", type="password")
is_admin = (pw == "1234")
mode = st.sidebar.radio("モード選択", ["① 休み希望入力", "② 従業員基本設定", "③ 曜日別可能時間", "④ シフト案作成"])

if mode == "① 休み希望入力":
    st.header(f"📅 {year}年{month}月の休み希望")
    r_raw = load_sheet(REQ_SHEET_NAME, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
    req_df = r_raw.reindex(ALL_NAMES).fillna(False)
    # 【修正】applymap を map に変更
    req_df = req_df.map(lambda x: str(x).upper() == "TRUE" if isinstance(x, str) else bool(x))
    
    edited = st.data_editor(req_df, use_container_width=True, height=750)
    if st.button("💾 希望を保存"):
        if save_sheet(edited, REQ_SHEET_NAME):
            st.success("保存完了！")

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
        if st.button(f"💾 {target} の時間を保存"):
            for wd, t in new_times.items(): avail_df.at[target, wd] = t
            save_sheet(avail_df, "staff_availability")

# --- ④ シフト案作成 ---
else:
    if not is_admin:
        st.error("管理者パスワードを入力してください")
    else:
        st.header(f"📝 {year}年{month}月のシフト案")

        # ====================== 必要人数設定 (上下ボタン付き個別設定) ======================
        with st.expander("🛠️ 必要人数設定（グループ別・時間帯個別調整）", expanded=False):
            req_groups = load_sheet("required_staff", pd.DataFrame(2, index=time_slots, 
                                          columns=["月火水木_ホール", "月火水木_キッチン", "金土_ホール", "金土_キッチン", "日_ホール", "日_キッチン"]))
            edited_req_groups = req_groups.copy()
            groups_labels = {"月火水木": "📅 平日 (月〜木)", "金土": "🟧 週末 (金・土)", "日": "🟥 日曜日"}
            tabs = st.tabs(list(groups_labels.values()))
            
            for i, (key, label) in enumerate(groups_labels.items()):
                with tabs[i]:
                    st.write(f"#### {label} の一括設定")
                    c_bulk1, c_bulk2, c_bulk3 = st.columns(3)
                    new_h = c_bulk1.number_input("ホール全員", 0, 10, 2, key=f"bulk_h_{key}")
                    new_k = c_bulk2.number_input("キッチン全員", 0, 10, 2, key=f"bulk_k_{key}")
                    if c_bulk3.button(f"{key} 全時間に適用", key=f"btn_{key}"):
                        edited_req_groups[f"{key}_ホール"] = new_h
                        edited_req_groups[f"{key}_キッチン"] = new_k
                        save_sheet(edited_req_groups, "required_staff"); st.rerun()
                    st.divider()
                    st.write("#### 時間別調整")
                    for t in time_slots:
                        cols = st.columns([1, 2, 2])
                        cols[0].write(f"**{t}**")
                        edited_req_groups.at[t, f"{key}_ホール"] = cols[1].number_input("H", 0, 10, int(edited_req_groups.at[t, f"{key}_ホール"]), key=f"nh_{key}_{t}", label_visibility="collapsed")
                        edited_req_groups.at[t, f"{key}_キッチン"] = cols[2].number_input("K", 0, 10, int(edited_req_groups.at[t, f"{key}_キッチン"]), key=f"nk_{key}_{t}", label_visibility="collapsed")
            if st.button("💾 人数設定を保存", key="save_req_final"): save_sheet(edited_req_groups, "required_staff")

        st.divider()

        # 休み希望データの準備（重複削除・クリーニング付き）
        req_load_raw = load_sheet(REQ_SHEET_NAME, pd.DataFrame())
        if req_load_raw is not None and not req_load_raw.empty:
            req_load = req_load_raw.drop_duplicates(subset=req_load_raw.columns[0]).set_index(req_load_raw.columns[0]).reindex(ALL_NAMES).fillna(False)
            req_load = req_load.map(lambda x: str(x).lower() in ['true', '1', 'yes'])
        else:
            req_load = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)

        # シフトデータの読み込み・キャッシュ管理
        if 'shift_cache' not in st.session_state:
            s_raw = load_sheet(SHIFT_SHEET_NAME, pd.DataFrame())
            if s_raw is not None and not s_raw.empty:
                st.session_state.shift_cache = s_raw.drop_duplicates(subset=s_raw.columns[0]).set_index(s_raw.columns[0]).reindex(ALL_NAMES).fillna("")
            else:
                st.session_state.shift_cache = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
        
        current_df = st.session_state.shift_cache

        col_a1, col_a2 = st.columns([2, 1])
        with col_a1:
            if st.button("🤖 必要人数と公平性を考慮して自動生成実行"):
                new_s = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
                work_counts = {n: 0 for n in ALL_NAMES}
                target_counts = {n: (staff_info[n]['週希望'] if staff_info[n]['週希望']>0 else 1)*4.3 for n in ALL_NAMES}
                for i, col in enumerate(column_names):
                    wd_jp = WEEKDAYS_JP[calendar.weekday(year, month, i+1)]
                    g_key = "月火水木" if wd_jp in ["月","火","水","木"] else ("金土" if wd_jp in ["金","土"] else "日")
                    try:
                        thd, tkd = int(edited_req_groups.at["12:00", f"{g_key}_ホール"]), int(edited_req_groups.at["12:00", f"{g_key}_キッチン"])
                        thn, tkn = int(edited_req_groups.at["19:00", f"{g_key}_ホール"]), int(edited_req_groups.at["19:00", f"{g_key}_キッチン"])
                    except: thd, tkd, thn, tkn = 2, 2, 3, 2
                    capable = [n for n in ALL_NAMES if not req_load.get(col, pd.Series(False)).at[n]]
                    random.shuffle(capable); capable.sort(key=lambda n: (work_counts[n]/target_counts[n] if target_counts[n]>0 else 99, random.random()))
                    h_d, k_d, h_n, k_n, has_cl = 0, 0, 0, 0, False
                    for n in capable:
                        raw_avail = avail_df.at[n, wd_jp] if n in avail_df.index else "10.0-23.0"
                        sf, ef = parse_range(raw_avail)
                        if sf >= ef: continue
                        tst = f"{int(sf)}:00" if sf%1==0 else f"{int(sf)}:30"
                        role = staff_info[n]['職種']
                        if staff_info[n]['レジ締め'] and ef >= 23 and not has_cl:
                            new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; h_n+=1; has_cl=True
                        elif sf <= 11 and ef >= 18:
                            if ("☕" in role or "👔" in role) and h_d < thd: new_s.at[n, col] = f"{tst}-18:00"; work_counts[n]+=1; h_d+=1
                            elif ("🍳" in role or "👔" in role) and k_d < tkd: new_s.at[n, col] = f"{tst}-18:00"; work_counts[n]+=1; k_d+=1
                        elif ef >= 23:
                            if ("☕" in role or "👔" in role) and h_n < thn: new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; h_n+=1
                            elif ("🍳" in role or "👔" in role) and k_n < tkn: new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; k_n+=1
                st.session_state.shift_cache = new_s; st.rerun()

        with col_a2:
            # --- 見やすいExcel出力機能 ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                current_df.to_excel(writer, sheet_name='シフト表')
                wb, ws = writer.book, writer.sheets['シフト表']
                base_fmt = wb.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
                name_fmt = wb.add_format({'bold': True, 'border': 1, 'align': 'left', 'bg_color': '#F2F2F2'})
                header_fmt = wb.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D9D9D9'})
                sat_fmt = wb.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#CCE5FF', 'font_color': '#0000FF'})
                sun_fmt = wb.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFCCCC', 'font_color': '#FF0000'})
                ws.set_column(0, 0, 25, name_fmt)
                ws.set_column(1, len(column_names), 12, base_fmt)
                for col_num, value in enumerate(current_df.columns):
                    if "(土)" in value: ws.write(0, col_num + 1, value, sat_fmt)
                    elif "(日)" in value: ws.write(0, col_num + 1, value, sun_fmt)
                    else: ws.write(0, col_num + 1, value, header_fmt)
                ws.freeze_panes(1, 1)
            st.download_button(label="📥 見やすいExcelで保存", data=output.getvalue(), file_name=f"shift_{year}_{month:02}.xlsx")

        # ==================== シフト表の表示 (色付け・直接編集) ====================
        def highlight_logic(data):
            styles = pd.DataFrame('', index=data.index, columns=data.columns)
            for col in data.columns:
                try:
                    wd = WEEKDAYS_JP[calendar.weekday(year, month, int(col.split("(")[0]))]
                    for name in data.index:
                        # 1. 休み希望チェック（ピンク）
                        if name in req_load.index and req_load.at[name, col]:
                            styles.at[name, col] = 'background-color: #ffd1d1;'
                            continue
                        # 2. 時間外チェック（赤）
                        val = data.at[name, col]
                        if val and "-" in str(val):
                            si, ei = time_to_float(val.split("-")[0]), time_to_float(val.split("-")[1])
                            sl, el = parse_range(avail_df.at[name, wd] if name in avail_df.index else "10.0-23.0")
                            if si < sl or ei > el: styles.at[name, col] = 'background-color: #ff5555; color: white;'
                except: pass
            return styles

        st.info("💡 薄ピンク: 休み希望 | 赤: 可能時間外")
        config = {c: st.column_config.SelectboxColumn(options=SHIFT_OPTIONS, width="medium") for c in column_names}
        edited = st.data_editor(current_df.style.apply(highlight_logic, axis=None), column_config=config, use_container_width=True, height=750)
        
        if st.button("💾 このシフトをスプレッドシートに保存"):
            if save_sheet(edited, SHIFT_SHEET_NAME):
                st.session_state.shift_cache = pd.DataFrame(edited)
                st.success("正常に保存されました")