import streamlit as st
import pandas as pd
import calendar
import os
import random
import io
import time
from datetime import date, timedelta
from streamlit_gsheets import GSheetsConnection

# ページ基本設定
st.set_page_config(page_title="ジョイフル シフト管理システムPRO", layout="wide")

# --- 1. スプレッドシート接続設定 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1dDyKAXYsHZg1ta4l7te84uSbhSea-FoyVgTeo4-kgkI/edit?gid=0#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet_no_cache(worksheet_name, default_df):
    """キャッシュを使わず最新のスプレッドシートを読み込み、重複を徹底的に掃除する"""
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        if df is not None and not df.empty:
            # 完全に空の行を除去
            df = df.dropna(how='all', axis=0)
            # 1列目(名前)の重複を削除
            df = df.drop_duplicates(subset=df.columns[0], keep='first')
            # 1列目をインデックスに設定
            df = df.set_index(df.columns[0])
            # インデックス(名前)の空白を掃除
            df.index = df.index.astype(str).str.strip()
            return df
        return default_df
    except Exception:
        return default_df

def save_sheet_robust(df, worksheet_name):
    """データを保存する。スタイル情報を排除し、タブがなければ自動作成を試みる。"""
    try:
        if hasattr(df, 'data'): df = df.data # StylerオブジェクトをDataFrameに戻す
        save_df = df.copy()
        save_df.index.name = "名前"
        save_df = save_df.reset_index()
        
        # 保存実行
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=save_df)
        st.cache_data.clear()
        time.sleep(1) # 反映待ち
        return True
    except Exception as e:
        st.error(f"【保存失敗】スプレッドシートのタブ '{worksheet_name}' が見当たらないか、通信エラーです。")
        return False

# --- 2. 補助関数 ---
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]
TIME_SLOTS = [f"{h}:{m}" for h in range(10, 23) for m in ["00", "30"]] + ["23:00"]
SHIFT_OPTIONS = ["", "10:00-18:00", "18:00-23:00", "10:00-23:00", "10:00-15:00", "11:00-18:00", "17:00-23:00", "18:30-23:00", "19:00-23:00"]

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

# --- 3. 従業員名簿の初期化 (25名固定・末登なし) ---
def get_master_data():
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

# 名簿のロード
master_df = load_sheet_no_cache("staff_master", pd.DataFrame(get_master_data()).set_index("名前"))
# 表示名アイコン付きを作成し、名前を完璧に同期させる
master_df['表示名'] = master_df['職種'].astype(str).str.strip() + " " + master_df.index.astype(str).str.strip()
ALL_NAMES = [n.strip() for n in master_df['表示名'].unique().tolist()]
staff_info = master_df.set_index('表示名').to_dict('index')

# 曜日別設定のロード
avail_df = load_sheet_no_cache("staff_availability", pd.DataFrame([[n] + ["10.0-23.0"]*7 for n in ALL_NAMES], columns=["名前"] + WEEKDAYS_JP).set_index("名前"))
avail_df = avail_df.reindex(ALL_NAMES).fillna("10.0-23.0")

# 必要人数設定のロード
req_staff_config = load_sheet_no_cache("required_staff", pd.DataFrame(2, index=TIME_SLOTS, columns=[f"{g}_{p}" for g in ["月火水木","金土","日"] for p in ["ホール","キッチン"]]))

# --- 4. 月管理 ---
if 'view_date' not in st.session_state: st.session_state.view_date = date.today().replace(day=1)
year, month = st.session_state.view_date.year, st.session_state.view_date.month
num_days = calendar.monthrange(year, month)[1]
column_names = [f"{d}({WEEKDAYS_JP[calendar.weekday(year, month, d)]})" for d in range(1, num_days + 1)]

# 月別ファイル名
REQ_SHEET = f"req_{year}_{month:02}"
SHIFT_SHEET = f"shift_{year}_{month:02}"

# --- 5. サイドバー・パスワード ---
st.sidebar.title("ジョイフル シフトWeb")
pw = st.sidebar.text_input("管理者パスワード", type="password")
is_admin = (pw == "1234")

# メニュー定義
MENU_REST = "① 休み希望"
MENU_STAFF = "② 従業員設定"
MENU_AVAIL = "③ 曜日別設定"
MENU_SHIFT = "④ シフト作成"
mode = st.sidebar.radio("機能を選択", [MENU_REST, MENU_STAFF, MENU_AVAIL, MENU_SHIFT])

# --- ① 休み希望 ---
if mode == MENU_REST:
    st.header(f"📅 {year}年{month}月の休み希望入力")
    # 常に最新を読み込む(ttl=0)
    r_raw = load_sheet_no_cache(REQ_SHEET, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
    req_df = r_raw.reindex(ALL_NAMES).fillna(False)
    # 文字列の "TRUE" を確実に Bool(チェックマーク) に変換
    req_df = req_df.map(lambda x: str(x).upper() == "TRUE" if isinstance(x, str) else bool(x))
    
    st.info("休みを入れたい日にチェックを付けて保存してください。")
    edited = st.data_editor(req_df, use_container_width=True, height=750)
    if st.button("💾 この月の希望を保存"):
        if save_sheet_robust(edited, REQ_SHEET): st.success("保存完了しました。")

# --- ② 従業員設定 ---
elif mode == MENU_STAFF:
    if not is_admin: st.error("管理者用パスワードを入力してください")
    else:
        st.header("⚙️ 従業員名簿の管理")
        edited = st.data_editor(master_df.drop(columns=['表示名']), use_container_width=True, num_rows="dynamic")
        if st.button("💾 名簿を保存"):
            if save_sheet_robust(edited, "staff_master"): st.success("保存完了。ブラウザを更新して反映してください。")

# --- ③ 曜日別設定 ---
elif mode == MENU_AVAIL:
    if not is_admin: st.error("管理者用パスワードを入力してください")
    else:
        st.header("🕒 スタッフ別・曜日別可能時間設定")
        target = st.selectbox("スタッフを選択", ALL_NAMES)
        new_times = {}
        for wd in WEEKDAYS_JP:
            raw_val = avail_df.at[target, wd] if target in avail_df.index else "10.0-23.0"
            sf, ef = parse_range(raw_val)
            res = st.slider(wd, 10.0, 23.0, (float(sf), float(ef)), step=0.5, format="%g時")
            new_times[wd] = f"{res[0]}-{res[1]}"
        if st.button(f"💾 {target} の設定を保存"):
            for wd, t in new_times.items(): avail_df.at[target, wd] = t
            if save_sheet_robust(avail_df, "staff_availability"): st.success("保存しました。")

# --- ④ シフト作成 ---
elif mode == MENU_SHIFT:
    if not is_admin: st.error("管理者専用です。パスワードを入力してください。")
    else:
        st.header(f"📝 {year}年{month}月のシフト作成")
        
        # 1. 必要人数設定のUI
        with st.expander("🛠️ 時間帯別の必要人数設定（上下ボタン）", expanded=False):
            curr_req = req_staff_config.copy()
            tabs = st.tabs(["📅 月〜木", "🟧 金・土", "🟥 日曜"])
            g_keys = ["月火水木", "金土", "日"]
            for i, key in enumerate(g_keys):
                with tabs[i]:
                    c1, c2, c3 = st.columns(3)
                    bh = c1.number_input("ホール全員", 0, 10, 2, key=f"bh_{key}")
                    bk = c2.number_input("キッチン全員", 0, 10, 2, key=f"bk_{key}")
                    if c3.button("全時間帯に適用", key=f"ap_{key}"):
                        curr_req[f"{key}_ホール"] = bh; curr_req[f"{key}_キッチン"] = bk
                        save_sheet_robust(curr_req, "required_staff"); st.rerun()
                    st.divider()
                    for t in TIME_SLOTS:
                        cols = st.columns([1, 2, 2])
                        cols[0].write(f"**{t}**")
                        curr_req.at[t, f"{key}_ホール"] = cols[1].number_input("H", 0, 10, int(curr_req.at[t, f"{key}_ホール"]), key=f"nh_{key}_{t}", label_visibility="collapsed")
                        curr_req.at[t, f"{key}_キッチン"] = cols[2].number_input("K", 0, 10, int(curr_req.at[t, f"{key}_キッチン"]), key=f"nk_{key}_{t}", label_visibility="collapsed")
            if st.button("💾 全ての人数設定を保存"):
                save_sheet_robust(curr_req, "required_staff")

        st.divider()

        # 2. 休み希望の強制最新読み込み
        req_load_raw = load_sheet_no_cache(REQ_SHEET, pd.DataFrame(False, index=ALL_NAMES, columns=column_names))
        req_load = req_load_raw.reindex(ALL_NAMES).fillna(False)
        req_load = req_load.map(lambda x: str(x).upper() == "TRUE" if isinstance(x, str) else bool(x))

        # 3. シフトキャッシュ管理
        shift_key = f"shift_cache_{year}_{month}"
        if shift_key not in st.session_state:
            s_raw = load_sheet_no_cache(SHIFT_SHEET, pd.DataFrame("", index=ALL_NAMES, columns=column_names))
            st.session_state[shift_key] = s_raw.reindex(ALL_NAMES).fillna("")
        current_df = st.session_state[shift_key]

        col_a1, col_a2 = st.columns([2, 1])
        with col_a1:
            if st.button("🤖 公平性と連勤防止を考慮して自動生成実行"):
                new_s = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
                work_counts = {n: 0 for n in ALL_NAMES} # 月の累計勤務日
                consecutive_counts = {n: 0 for n in ALL_NAMES} # 現在の連勤数
                target_counts = {n: (staff_info[n]['週希望'] if staff_info[n]['週希望']>0 else 1) * 4.3 for n in ALL_NAMES}

                for i, col in enumerate(column_names):
                    wd_jp = WEEKDAYS_JP[calendar.weekday(year, month, i+1)]
                    g_key = "月火水木" if wd_jp in ["月","火","水","木"] else ("金土" if wd_jp in ["金","土"] else "日")
                    
                    # 必要人数の取得（12時と19時を代表値として採用）
                    try:
                        thd = int(curr_req.at["12:00", f"{g_key}_ホール"])
                        tkd = int(curr_req.at["12:00", f"{g_key}_キッチン"])
                        thn = int(curr_req.at["19:00", f"{g_key}_ホール"])
                        tkn = int(curr_req.at["19:00", f"{g_key}_キッチン"])
                    except: thd, tkd, thn, tkn = 2, 2, 3, 2

                    # 【重要】休み希望(True)の人と、すでに6連勤している人を候補から除外
                    capable = []
                    for n in ALL_NAMES:
                        is_on_leave = req_load.at[n, col]
                        is_overworked = consecutive_counts[n] >= 6
                        if not is_on_leave and not is_overworked:
                            capable.append(n)
                    
                    random.shuffle(capable)
                    # 働いている割合（充足率）が低い順に並べ替え
                    capable.sort(key=lambda n: (work_counts[n] / target_counts[n], random.random()))

                    hd_c, kd_c, hn_c, kn_c, has_cl = 0, 0, 0, 0, False
                    for n in capable:
                        sf, ef = parse_range(avail_df.at[n, wd_jp] if n in avail_df.index else "10.0-23.0")
                        if sf >= ef: continue
                        tst = f"{int(sf)}:00" if sf%1==0 else f"{int(sf)}:30"
                        role = staff_info[n]['職種']

                        # 1. 夜のレジ締め優先確保
                        if staff_info[n]['レジ締め'] and ef >= 23 and not has_cl:
                            new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; hn_c+=1; has_cl=True; consecutive_counts[n]+=1
                        # 2. 昼枠（18時まで入れる人）
                        elif sf <= 11 and ef >= 18:
                            if ("☕" in role or "👔" in role) and hd_c < thd: 
                                new_s.at[n, col] = f"{tst}-18:00"; work_counts[n]+=1; hd_c+=1; consecutive_counts[n]+=1
                            elif ("🍳" in role or "👔" in role) and kd_c < tkd: 
                                new_s.at[n, col] = f"{tst}-18:00"; work_counts[n]+=1; kd_c+=1; consecutive_counts[n]+=1
                        # 3. 夜枠（23時まで入れる人）
                        elif ef >= 23:
                            if ("☕" in role or "👔" in role) and hn_c < thn: 
                                new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; hn_c+=1; consecutive_counts[n]+=1
                            elif ("🍳" in role or "👔" in role) and kn_c < tkn: 
                                new_s.at[n, col] = f"{tst}-23:00"; work_counts[n]+=1; kn_c+=1; consecutive_counts[n]+=1
                    
                    # 今日入らなかった人の連勤カウントをリセット
                    for n in ALL_NAMES:
                        if new_s.at[n, col] == "": consecutive_counts[n] = 0

                st.session_state[shift_key] = new_s
                st.rerun()

        with col_a2:
            # 見やすいExcel出力
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                current_df.to_excel(writer, sheet_name='シフト')
                wb, ws = writer.book, writer.sheets['シフト']
                ws.set_column(0, 0, 25, wb.add_format({'bold':True, 'border':1, 'bg_color':'#F2F2F2'}))
                ws.set_column(1, len(column_names), 12, wb.add_format({'border':1, 'align':'center'}))
                for c_idx, val in enumerate(current_df.columns):
                    if "(土)" in val: ws.write(0, c_idx+1, val, wb.add_format({'bold':True,'bg_color':'#CCE5FF','font_color':'#0000FF','border':1}))
                    elif "(日)" in val: ws.write(0, c_idx+1, val, wb.add_format({'bold':True,'bg_color':'#FFCCCC','font_color':'#FF0000','border':1}))
                ws.freeze_panes(1, 1)
            st.download_button("📥 見やすいExcelを保存", output.getvalue(), f"joyful_shift_{year}_{month:02}.xlsx")

        # 色付けロジック
        def highlight_shift(data):
            styles = pd.DataFrame('', index=data.index, columns=data.columns)
            for col in data.columns:
                try:
                    wd = WEEKDAYS_JP[calendar.weekday(year, month, int(col.split("(")[0]))]
                    for name in data.index:
                        # 休み希望（薄ピンク）
                        if name in req_load.index and req_load.at[name, col] == True:
                            styles.at[name, col] = 'background-color: #ffd1d1; color: black;'
                            continue
                        # 時間外（濃い赤）
                        val = data.at[name, col]
                        if val and "-" in str(val):
                            si, ei = time_to_float(val.split("-")[0]), time_to_float(val.split("-")[1])
                            sl, el = parse_range(avail_df.at[name, wd] if name in avail_df.index else "10.0-23.0")
                            if si < sl or ei > el: styles.at[name, col] = 'background-color: #ff5555; color: white;'
                except: pass
            return styles

        st.info("💡 薄ピンクは休み希望、赤色は出勤不可時間（バーの設定外）です。")
        edited = st.data_editor(current_df.style.apply(highlight_shift, axis=None), column_config={c: st.column_config.SelectboxColumn(options=SHIFT_OPTIONS, width="medium") for c in column_names}, use_container_width=True, height=750, key="editor_final")
        
        if st.button("💾 このシフト案を確定保存", type="primary"):
            if save_sheet_robust(edited, SHIFT_SHEET):
                st.session_state[shift_key] = edited
                st.success("保存が完了しました！Googleスプレッドシートを確認してください。")

# 月移動（サイドバー）
st.sidebar.divider()
c1, c2 = st.sidebar.columns(2)
if c1.button("◀ 前月"): 
    st.session_state.view_date = (st.session_state.view_date - timedelta(days=28)).replace(day=1)
    if shift_key in st.session_state: del st.session_state[shift_key]
    st.rerun()
if c2.button("次月 ▶"): 
    st.session_state.view_date = (st.session_state.view_date + timedelta(days=32)).replace(day=1)
    if shift_key in st.session_state: del st.session_state[shift_key]
    st.rerun()