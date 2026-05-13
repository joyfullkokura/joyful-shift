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

# --- 2. 補助関数（安定化・高速化） ---
def load_sheet_cached(worksheet_name, default_df):
    """キャッシュを使って読み込み、Googleへの負荷を減らす"""
    try:
        # ttl=10（10秒）程度に設定し、編集後の反映を早めつつ負荷を抑える
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=10)
        if df is not None and not df.empty:
            df = df.dropna(how='all', axis=0)
            df = df.drop_duplicates(subset=df.columns[0]).set_index(df.columns[0])
            df.index = df.index.astype(str).str.strip()
            return df
        return default_df
    except:
        return default_df

def save_sheet_robust(df, worksheet_name):
    """保存時にスタイルを解除し、確実に書き込む"""
    try:
        if hasattr(df, 'data'): df = df.data
        save_df = df.copy()
        save_df.index.name = "名前"
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=save_df.reset_index())
        st.cache_data.clear() # 保存後は最新を読み込めるようにする
        time.sleep(1)
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

# --- 3. データの初期化 (25名フル名簿) ---
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]
TIME_SLOTS = [f"{h}:{m}" for h in range(10, 23) for m in ["00", "30"]] + ["23:00"]
SHIFT_OPTIONS = ["", "10:00-18:00", "18:00-23:00", "10:00-23:00", "10:00-15:00", "11:00-18:00", "17:00-23:00", "18:30-23:00", "19:00-23:00"]

# 名簿の読み込み
master_df = load_sheet_cached("staff_master", pd.DataFrame())
if master_df.empty:
    st.error("名簿が読み込めません。スプレッドシートのタブ名『staff_master』を確認してください。")
    st.stop()

master_df['表示名'] = master_df['職種'].astype(str).str.strip() + " " + master_df.index.astype(str).str.strip()
ALL_NAMES = [n.strip() for n in master_df['表示名'].unique().tolist()]
staff_info = master_df.set_index('表示名').to_dict('index')

# 曜日別・必要人数設定
avail_df = load_sheet_cached("staff_availability", pd.DataFrame())
avail_df = avail_df.reindex(ALL_NAMES).fillna("10.0-23.0")
req_staff_config = load_sheet_cached("required_staff", pd.DataFrame(2, index=TIME_SLOTS, columns=[f"{g}_{p}" for g in ["月火水木","金土","日"] for p in ["ホール","キッチン"]]))

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

# メニュー文字定義
MENU_REST = "① 休み希望"
MENU_STAFF = "② 従業員設定"
MENU_AVAIL = "③ 曜日別設定"
MENU_SHIFT = "④ シフト作成"

mode = st.sidebar.radio("機能を選択", [MENU_REST, MENU_STAFF, MENU_AVAIL, MENU_SHIFT])

# --- ① 休み希望 ---
if mode == MENU_REST:
    st.header(f"📅 {year}年{month}月の休み希望入力")
    state_key = f"req_data_{year}_{month}"
    if state_key not in st.session_state:
        r_raw = load_sheet_cached(REQ_SHEET, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
        df = r_raw.reindex(ALL_NAMES).fillna(False)
        st.session_state[state_key] = df.map(lambda x: str(x).upper() == "TRUE" if isinstance(x, str) else bool(x))
    
    edited = st.data_editor(st.session_state[state_key], use_container_width=True, height=700)
    if st.button("💾 この月の希望を保存"):
        if save_sheet_robust(edited, REQ_SHEET):
            st.session_state[state_key] = edited
            st.success("保存完了！")

# --- ② 従業員設定 ---
elif mode == MENU_STAFF:
    if not is_admin: st.error("管理者用パスワードが必要です")
    else:
        st.header("⚙️ 従業員名簿の管理")
        edited = st.data_editor(master_df.drop(columns=['表示名']), use_container_width=True, num_rows="dynamic")
        if st.button("💾 名簿を保存"):
            if save_sheet_robust(edited, "staff_master"): st.success("保存完了。ブラウザを更新して反映してください。")

# --- ③ 曜日別設定 ---
elif mode == MENU_AVAIL:
    if not is_admin: st.error("管理者用パスワードが必要です")
    else:
        st.header("🕒 スタッフ別・曜日別可能時間")
        target = st.selectbox("スタッフを選択", ALL_NAMES)
        new_times = {}
        for wd in WEEKDAYS_JP:
            raw_val = avail_df.at[target, wd] if target in avail_df.index else "10.0-23.0"
            sf, ef = parse_range(raw_val)
            res = st.slider(f"{wd}曜日", 10.0, 23.0, (float(sf), float(ef)), step=0.5, format="%g時")
            new_times[wd] = f"{res[0]}-{res[1]}"
        if st.button(f"💾 {target} の設定を保存"):
            for wd, t in new_times.items(): avail_df.at[target, wd] = t
            if save_sheet_robust(avail_df, "staff_availability"): st.success("保存完了")

# --- ④ シフト作成 ---
elif mode == MENU_SHIFT:
    if not is_admin: st.error("管理者パスワードを入力してください")
    else:
        st.header(f"📝 {year}年{month}月のシフト案")
        
        # 人数設定
        with st.expander("🛠️ 時間帯別の必要人数設定"):
            curr_req = req_staff_config.copy()
            tabs = st.tabs(["月〜木", "金土", "日"])
            g_keys = ["月火水木", "金土", "日"]
            for i, key in enumerate(g_keys):
                with tabs[i]:
                    c1, c2, c3 = st.columns(3)
                    bh = c1.number_input("ホール一括", 0, 10, 2, key=f"bh_{key}")
                    bk = c2.number_input("キッチン一括", 0, 10, 2, key=f"bk_{key}")
                    if c3.button("全時間に適用", key=f"ap_{key}"):
                        curr_req[f"{key}_ホール"] = bh; curr_req[f"{key}_キッチン"] = bk
                        save_sheet_robust(curr_req, "required_staff"); st.rerun()
                    for t in TIME_SLOTS:
                        cols = st.columns([1, 2, 2])
                        cols[0].write(f"**{t}**")
                        curr_req.at[t,f"{key}_ホール"] = cols[1].number_input("H", 0, 10, int(curr_req.at[t,f"{key}_ホール"]), key=f"nh_{key}_{t}", label_visibility="collapsed")
                        curr_req.at[t,f"{key}_キッチン"] = cols[2].number_input("K", 0, 10, int(curr_req.at[t,f"{key}_キッチン"]), key=f"nk_{key}_{t}", label_visibility="collapsed")
            if st.button("💾 人数設定を保存"): save_sheet_robust(curr_req, "required_staff")

        st.divider()
        # ==================== 【修正版】休み希望読み込み ====================
        # ttl=0 にして、キャッシュを無視して今すぐスプレッドシートの最新状態を取りに行く
        r_load_raw = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=REQ_SHEET, ttl=0)
        
        if r_load_raw is not None and not r_load_raw.empty:
            # 重複削除と名前の掃除
            r_load_raw = r_load_raw.drop_duplicates(subset=r_load_raw.columns[0])
            req_load = r_load_raw.set_index(r_load_raw.columns[0])
            req_load.index = req_load.index.astype(str).str.strip()
            # 名簿と合体させ、空白は「休みじゃない(False)」で埋める
            req_load = req_load.reindex(ALL_NAMES).fillna(False)
            # 文字列の "TRUE" も、チェックボックスの True も、確実に「休み(True)」として判定する
            req_load = req_load.map(lambda x: str(x).upper() == "TRUE")
        else:
            req_load = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)

        # ==================== シフトデータ保持 ====================
        shift_key = f"shift_cache_{year}_{month}"
        if shift_key not in st.session_state:
            s_raw = load_sheet_cached(SHIFT_SHEET, pd.DataFrame("", index=ALL_NAMES, columns=column_names))
            st.session_state[shift_key] = s_raw.reindex(ALL_NAMES).fillna("")
        
        current_df = st.session_state[shift_key]

        col_a1, col_a2 = st.columns([2, 1])
        with col_a1:
            if st.button("🤖 公平自動生成実行"):
                new_s = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
                work_counts = {n: 0 for n in ALL_NAMES}
                target_counts = {n: (staff_info[n]['週希望'] if staff_info[n]['週希望']>0 else 1)*4.3 for n in ALL_NAMES}
                
                for i, col in enumerate(column_names):
                    wd_jp = WEEKDAYS_JP[calendar.weekday(year, month, i+1)]
                    g_key = "月火水木" if wd_jp in ["月","火","水","木"] else ("金土" if wd_jp in ["金","土"] else "日")
                    
                    try:
                        thd = int(curr_req.at["12:00", f"{g_key}_ホール"])
                        tkd = int(curr_req.at["12:00", f"{g_key}_キッチン"])
                        thn = int(curr_req.at["19:00", f"{g_key}_ホール"])
                        tkn = int(curr_req.at["19:00", f"{g_key}_キッチン"])
                    except: thd, tkd, thn, tkn = 2, 2, 3, 2
                    
                    # 【重要】ここを req_load（最新の休み希望）を使って判定するように修正
                    capable = [n for n in ALL_NAMES if req_load.at[n, col] == False]
                    
                    random.shuffle(capable)
                    capable.sort(key=lambda n: (work_counts[n]/target_counts[n] if target_counts[n]>0 else 99, random.random()))
                    
                    hd_c, kd_c, hn_c, kn_c, has_cl = 0, 0, 0, 0, False
                    for n in capable:
                        sf, ef = parse_range(avail_df.at[n, wd_jp] if n in avail_df.index else "10.0-23.0")
                        if sf >= ef: continue
                        tst = f"{int(sf)}:00" if sf%1==0 else f"{int(sf)}:30"
                        role = staff_info[n]['職種']

                        if staff_info[n]['レジ締め'] and ef >= 23 and not has_cl:
                            new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; hn_c+=1; has_cl=True
                        elif sf <= 11 and ef >= 18:
                            if ("☕" in role or "👔" in role) and hd_c < thd: new_s.at[n, col] = f"{tst}-18:00"; work_counts[n]+=1; hd_c+=1
                            elif ("🍳" in role or "👔" in role) and kd_c < tkd: new_s.at[n, col] = f"{tst}-18:00"; work_counts[n]+=1; kd_c+=1
                        elif ef >= 23:
                            if ("☕" in role or "👔" in role) and hn_c < thn: new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; hn_c+=1
                            elif ("🍳" in role or "👔" in role) and kn_c < tkn: new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; kn_c+=1
                
                st.session_state[shift_key] = new_s
                st.rerun()

        with col_a2:
            # Excel出力 (スタイルの競合を防ぐため current_df.copy() を使用)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                current_df.to_excel(writer, sheet_name='シフト')
                wb, ws = writer.book, writer.sheets['シフト']
                ws.set_column(0,0,25); ws.set_column(1,len(column_names),12)
            st.download_button("📥 Excel保存", output.getvalue(), f"shift_{year}_{month:02}.xlsx")

        # ==================== 【修正版】色付けロジック ====================
        def highlight_logic(data):
            # 表と同じ大きさの、色の設定を書くための空っぽの表を作る
            styles = pd.DataFrame('', index=data.index, columns=data.columns)
            for col in data.columns:
                try:
                    wd_name = WEEKDAYS_JP[calendar.weekday(year, month, int(col.split("(")[0]))]
                    for name in data.index:
                        # 1. 休み希望のチェック（最新の req_load を使う）
                        # もし req_load が True なら背景をピンクにする
                        if name in req_load.index and req_load.at[name, col] == True:
                            styles.at[name, col] = 'background-color: #ffd1d1; color: black;'
                            continue # 休みなら次の人の判定へ

                        # 2. 時間外チェック（赤色）
                        val = data.at[name, col]
                        if val and "-" in str(val):
                            si, ei = time_to_float(val.split("-")[0]), time_to_float(val.split("-")[1])
                            sl, el = parse_range(avail_df.at[name, wd_name] if name in avail_df.index else "10.0-23.0")
                            if si < sl or ei > el:
                                styles.at[name, col] = 'background-color: #ff5555; color: white;'
                except: pass
            return styles

        st.info("💡 ピンク色は休み希望、赤色は出勤不可時間です。")
        # style.apply を使って最新の req_load を反映させる
        edited = st.data_editor(
            current_df.style.apply(highlight_logic, axis=None), 
            column_config={c: st.column_config.SelectboxColumn(options=SHIFT_OPTIONS, width="medium") for c in column_names}, 
            use_container_width=True, 
            height=750
        )
        
        if st.button("💾 このシフトを確定保存"):
            if save_sheet_robust(edited, SHIFT_SHEET): 
                st.session_state[shift_key] = edited
                st.success("保存完了しました。")

        with col_a2:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                current_df.to_excel(writer, sheet_name='シフト')
                wb, ws = writer.book, writer.sheets['シフト']
                fmt = wb.add_format({'border':1, 'align':'center'})
                name_f = wb.add_format({'bold':True, 'border':1, 'bg_color':'#F2F2F2'})
                ws.set_column(0,0,25,name_f); ws.set_column(1,len(column_names),12,fmt)
                for c_idx, val in enumerate(current_df.columns):
                    if "(土)" in val: ws.write(0, c_idx + 1, val, wb.add_format({'bold':True, 'bg_color':'#CCE5FF', 'font_color':'#0000FF', 'border':1}))
                    elif "(日)" in val: ws.write(0, c_idx + 1, val, wb.add_format({'bold':True, 'bg_color':'#FFCCCC', 'font_color':'#FF0000', 'border':1}))
                ws.freeze_panes(1, 1)
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

        edited = st.data_editor(current_df.style.apply(highlight_logic, axis=None), column_config={c: st.column_config.SelectboxColumn(options=SHIFT_OPTIONS, width="medium") for c in column_names}, use_container_width=True, height=700)
        if st.button("💾 このシフトを保存"):
            if save_sheet_robust(edited, SHIFT_SHEET): 
                st.session_state[shift_key] = edited
                st.success("保存完了")

# 月移動（サイドバー）
st.sidebar.divider()
c1, c2 = st.sidebar.columns(2)
if c1.button("◀ 前月"): 
    st.session_state.view_date = (st.session_state.view_date - timedelta(days=28)).replace(day=1)
    st.rerun()
if c2.button("次月 ▶"): 
    st.session_state.view_date = (st.session_state.view_date + timedelta(days=32)).replace(day=1)
    st.rerun()