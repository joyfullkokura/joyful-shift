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
    """データを保存する。インデックス（名前）を確実に列に戻して保存する。"""
    try:
        # 1. スタイル設定（色）がついている場合は、純粋なデータだけを取り出す
        if hasattr(df, 'data'):
            df = df.data
        
        # 2. データのコピーを作り、インデックス（名前）を1列目に戻す
        # これをしないと、保存するたびに「名前」の列が消えて日付がズレます
        save_df = df.reset_index()
        
        # 3. True/Falseを、Googleが数字の1/0に変えないように「文字」として送る
        save_df = save_df.map(lambda x: "TRUE" if x is True else ("FALSE" if x is False else x))
        
        # 4. スプレッドシートを更新
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=save_df)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
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
st.title(" ジョイフル小倉店シフト管理")
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
            

# --- ① 休み希望入力（安定・部分更新版） ---
if mode == "休み希望入力":
    st.title(f"📅 {year}年{month}月の休み希望")
    # 1. 画面を左右の2つの列（カラム）に分割します。比率は 1対4 です。
    col_btn, col_view = st.columns([1, 6])
    with col_view:
    # 1. スプレッドシートからデータを読み込む
    # ※ load_sheet_no_cache(シート名, 読み込めなかった時の予備) を使います
        df_raw = load_sheet_no_cache(REQ_SHEET, pd.DataFrame())
        # もともとの読み込みコードのすぐ下にこれを追加
        req_df = df_raw.map(lambda x: str(x) in ["1", "1.0", "TRUE"])
    # 2. データの整形
        if df_raw.empty:
        # シートが空っぽ、または存在しない場合は全員分「空」の表を作る
            display_df = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)
        else:
        # 【重要】今の名簿順(ALL_NAMES)と日付(column_names)に強制的に揃える
        # これにより、スプレッドシートがズレていても表は綺麗に表示されます
            display_df = df_raw.reindex(index=ALL_NAMES, columns=column_names).fillna(False)

    # 3. 画面に表示
        st.info("毎月20日には入力してね ")
        
    # st.dataframe を使うことで、スマホでも見やすい閲覧専用の表になります
        # column_names（1(金)など）の列をすべてチェックボックスに設定する
        config = {col: st.column_config.CheckboxColumn(col, width="small") for col in column_names}

# 表を表示する（configを渡す）
        # --- ここから書き換え ---
        if pw == "1234":
            st.subheader(" 管理者モード：全員分を編集")
            # 1. フォームの枠で囲むことで、チェックのたびに読み込みが走るのを防ぎます
            with st.form(key="admin_bulk_edit_form"):
                edited_all = st.data_editor(
                    req_df, 
                    column_config=config,
                    use_container_width=True, 
                    height=600,
                    key="admin_bulk_editor"
                )
                # 2. 専用の保存ボタン。これを押すまでスプレッドシートへは送信されません
                if st.form_submit_button("💾 全員の変更を一括保存する"):
                    with st.spinner("スプレッドシートを更新中..."):
                        if save_sheet_robust(edited_all, REQ_SHEET):
                            st.success("✅ 全員分の休み希望を上書き保存しました！")
                            st.cache_data.clear() 
                            st.rerun()
        else:
            # パスワードを入れていない時は、今まで通り閲覧専用（または編集不可）で表示
            st.subheader("📊 全体の休み状況（閲覧のみ）")
            st.data_editor(req_df, column_config=config, use_container_width=True, height=600, disabled=True)
        # --- 書き換えここまで ---
# 2. 左側の列（col_btn）の中に、これから書くものを表示しろという指示です。
    with col_btn:
        st.write("📝 下のボタンから自分の名前を選択し休み希望を入力してください⇩") # 見出し
    # 1. st.markdown（マークダウン）を使って、HTMLの中にデザインの指示を書き込みます。
        st.markdown("""
    <style>
    /* 全てのボタンに対して強制的に適用する設定 */
    .stButton > button {
        font-size: 11px !important;   /* 文字をさらに小さく */
        height: 30px !important;     /* 高さをかなり低く */
        line-height: 24px !important; /* 文字を中央に */
        min-height: 24px !important;
        padding: 0px 5px !important;  /* 左右の余白を最小限に */
        margin: 0px !important;
        border-radius: 4px !important; /* 角の丸みを少し残す */
    }
    /* ボタンを囲んでいる枠自体の余白も削る */
    .stButton {
        margin-bottom: -10px !important; /* 下のボタンとの隙間を詰める */
    }
    </style>
""", unsafe_allow_html=True)
        # 3. 名簿（ALL_NAMES）に入っている名前を一つずつ取り出してループさせます。
        for name in ALL_NAMES:
        
        # 4. その人の名前が書かれたボタンを実際に作ります。
        # 全員のボタンを区別するために、keyにはその人の名前を入れます。
            if st.button(f" {name}", key=f"sel_{name}"):
            
            # 5. ボタンが押されたら、貯金箱（session_state）に「この人を編集中」とメモします。
                st.session_state.editing_user = name
# --- 修正版：個別入力エリアを「フォーム」で囲む ---
    if "editing_user" in st.session_state:
        user = st.session_state.editing_user
        st.divider()
        st.header(f"📝 {user} さんの入力画面")

    # 1. フォームという「ひとまとめの枠」を作ります
        with st.form(key="my_individual_form"):
        
        # 2. この枠の中にある間は、チェックを入れても「読み直し」が発生しません！
            user_row = display_df.loc[[user]]
            user_row = user_row.map(lambda x: str(x).upper() in ["TRUE", "1", "1.0"])
            config = {col: st.column_config.CheckboxColumn(col, width="small") for col in column_names}
            edited_user_df = st.data_editor(
                user_row, 
                column_config=config,
                use_container_width=True, 
                key="individual_editor"
            )

        # 3. フォーム専用の「送信ボタン」を作ります
        # これを押した瞬間だけ、プログラムが動き出します
            submit_button = st.form_submit_button(label="💾 この内容でスプレッドシートに保存")

            if submit_button:
                with st.spinner("スプレッドシートを更新中..."):
                # A. スプレッドシートから最新を読み込む
                    latest_all_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=REQ_SHEET, ttl=0)
                # B. 【重要】1列目を「名前」にしてインデックスに設定
                    first_col = latest_all_df.columns[0]
                    latest_all_df = latest_all_df.set_index(first_col)
                    latest_all_df.index = latest_all_df.index.astype(str).str.strip()

                # C. 【重要】読み込んだ表の「列の並び」を、今のカレンダー（1日, 2日...）に強制的に固定する
                # これにより、列が右にズレたり消えたりするのを防ぎます
                    latest_all_df = latest_all_df.reindex(columns=column_names).fillna("FALSE")

                # D. 自分の行だけを差し替える
                    latest_all_df.loc[user] = edited_user_df.iloc[0]

                # E. 修正した save_sheet_robust で保存！
                    if save_sheet_robust(latest_all_df, REQ_SHEET):
                    # (以下、session_stateの消去などはそのまま)
                        if f"req_data_{year}_{month}" in st.session_state:
                            del st.session_state[f"req_data_{year}_{month}"]
                        del st.session_state.editing_user
                        st.success(f"✅ {user} さんの休み希望を保存しました！")
                        time.sleep(1)
                        st.rerun()
elif mode == "シフト自動生成（案）":
    st.title("📅 シフト自動生成（案）")

    # --- 1. 必要人数（枠数）の設定エリア ---
    with st.expander("必要人数の設定", expanded=True):
        st.write("基本人数を設定してください。")
        col_wd, col_we = st.columns(2)
        with col_wd:
            st.markdown("### 📅 平日 (月〜木)")
            h_d_wd = st.number_input("ホール昼", 1, 10, 2, key="h_d_wd")
            k_d_wd = st.number_input("キッチン昼", 1, 10, 2, key="k_d_wd")
            h_n_wd = st.number_input("ホール夜", 1, 10, 3, key="h_n_wd")
            k_n_wd = st.number_input("キッチン夜", 1, 10, 3, key="k_n_wd")
        with col_we:
            st.markdown("### 🟥 金・土・日")
            h_d_we = st.number_input("ホール昼 ", 1, 10, 3, key="h_d_we")
            k_d_we = st.number_input("キッチン昼 ", 1, 10, 3, key="k_d_we")
            h_n_we = st.number_input("ホール夜 ", 1, 10, 4, key="h_n_we")
            k_n_we = st.number_input("キッチン夜 ", 1, 10, 4, key="k_n_we")

# --- 2. データの準備（休み希望の読み込み） ---
    req_load_raw = load_sheet_cached(REQ_SHEET)
    if req_load_raw is None or req_load_raw.empty:
        req_load = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)
    else:
        req_load_raw = req_load_raw.drop_duplicates(subset=req_load_raw.columns[0])
        req_load = req_load_raw.set_index(req_load_raw.columns[0]).reindex(ALL_NAMES).fillna(False)
        req_load = req_load.map(lambda x: str(x).upper().strip() in ["TRUE", "1", "1.0"])

    # --- 【新規】再生成ボタンと結果の保存場所 ---
    # 計算結果を保存するための「貯金箱」を準備
    if "gen_shift_df" not in st.session_state:
        st.session_state.gen_shift_df = None
    if "gen_alerts" not in st.session_state:
        st.session_state.gen_alerts = []

    # ★ ここにボタンを設置
    if st.button("🤖 シフトを自動生成・再作成する", type="primary", use_container_width=True):
        with st.spinner("10回×4ブロックのシミュレーション中..."):
            # --- 3. 共通の「割り当て関数」の定義 ---
            def assign_slots(slot_list, main_pool, wildcard_pool, assigned_list):
                result = []
                combined_pool = main_pool + wildcard_pool
                for slot_time in slot_list:
                    available = [name for name in combined_pool if name not in assigned_list]
                    if available:
                        picked = available[0]
                        result.append({"スロット": slot_time, "担当者": picked})
                        assigned_list.append(picked)
                    else:
                        result.append({"スロット": slot_time, "担当者": "⚠️ 欠員"})
                return result

            # --- 4. 生成ロジック本体 ---
            monthly_shift_df = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
            user_limits = {row["名前"]: row["週希望"] for _, row in master_df.iterrows()}
            shortage_alerts = []
            week_counts = {name: 0 for name in ALL_NAMES}

            # 休み印の印字
            for name in ALL_NAMES:
                for col in column_names:
                    if req_load.at[name, col] == True:
                        monthly_shift_df.at[name, col] = "✖"

            # ブロックごとの計算
            ranges = [[1, 7], [8, 15], [16, 23], [24, 31]]
            for start_d, end_d in ranges:
                best_block_df = None
                best_block_counts = None
                best_block_alerts = []
                min_shortage_in_block = 999
                
                for trial in range(10):
                    t_monthly_df = monthly_shift_df.copy()
                    t_week_counts = week_counts.copy()
                    t_trial_alerts = []
                    t_block_shortage = 0
                    
                    block_cols = [c for c in column_names if start_d <= int(c.split('(')[0]) <= end_d]
                    
                    for col in block_cols:
                        assigned_today = []
                        d = int(col.split('(')[0])
                        d_idx = calendar.weekday(year, month, d)
                        n_hd, n_kd, n_hn, n_kn = (h_d_we, k_d_we, h_n_we, k_n_we) if d_idx >= 4 else (h_d_wd, k_d_wd, h_n_wd, k_n_wd)

                        def get_eligible(group_name, is_w=False):
                            pool = [n for n in master_df[master_df['グループ'] == group_name]['名前'].tolist() 
                                    if not req_load.at[n, col] and (is_w or t_week_counts[n] < int(user_limits.get(n, 3)))]
                            random.shuffle(pool)
                            return pool

                        hd_p, hn_p, kd_p, kn_p, w_p = get_eligible('HD'), get_eligible('HN'), get_eligible('KD'), get_eligible('KN'), get_eligible('W', True)

                        # ホール昼
                        hd_res = []
                        hd_l = next((n for n in (hd_p + w_p) if n not in assigned_today and master_df.set_index('名前').at[n, 'デザート']), None)
                        if hd_l: hd_res.append({"スロット": "10:00-18:00", "担当者": hd_l}); assigned_today.append(hd_l)
                        hd_res += assign_slots(["10:00-18:00"] * (n_hd - len(hd_res)), hd_p, w_p, assigned_today)
                        # キッチン昼
                        kd_res = assign_slots(["10:00-18:00"] * n_kd, kd_p, w_p, assigned_today)
                        # ホール夜
                        hn_res = []
                        hn_l = next((n for n in (hn_p + w_p) if n not in assigned_today and master_df.set_index('名前').at[n, 'レジ締め']), None)
                        if hn_l: hn_res.append({"スロット": "18:00-23:00", "担当者": hn_l}); assigned_today.append(hn_l)
                        h_s = ["18:00-23:00","18:00-23:00","18:00-22:00","19:00-23:00"] + ["18:00-23:00"]*10
                        hn_res += assign_slots(h_s[:n_hn-len(hn_res)], hn_p, w_p, assigned_today)
                        # キッチン夜
                        kn_res = assign_slots(h_s[:n_kn], kn_p, w_p, assigned_today)

                        for res_list, pos_name in [(hd_res, "ホール昼"), (kd_res, "キッチン昼"), (hn_res, "ホール夜"), (kn_res, "キッチン夜")]:
                            for item in res_list:
                                if item["担当者"] == "⚠️ 欠員":
                                    t_block_shortage += 1
                                    t_trial_alerts.append(f"{d}日:{pos_name}に欠員")
                                else:
                                    t_monthly_df.at[item["担当者"], col] = item["スロット"]
                                    t_week_counts[item["担当者"]] += 1

                    if t_block_shortage < min_shortage_in_block:
                        min_shortage_in_block = t_block_shortage
                        best_block_df = t_monthly_df
                        best_block_alerts = t_trial_alerts
                        best_block_counts = t_week_counts 

                monthly_shift_df = best_block_df
                week_counts = best_block_counts
                shortage_alerts.extend(best_block_alerts)

            # 結果を貯金箱（session_state）に保存
            st.session_state.gen_shift_df = monthly_shift_df
            st.session_state.gen_alerts = shortage_alerts
            st.rerun()

    # --- 5. 結果の表示（貯金箱に中身があるときだけ出す） ---
    if st.session_state.gen_shift_df is not None:
        res_df = st.session_state.gen_shift_df
        st.dataframe(res_df.style.map(lambda x: "background-color: #ffd1d1" if x == "✖" else ""), use_container_width=True)

        # Excel出力
        st.divider()
        st.subheader("📥 シフト表をダウンロード")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            res_df.to_excel(writer, sheet_name='シフト案')
            workbook, worksheet = writer.book, writer.sheets['シフト案']
            # (Excelの書式設定部分はそのまま使用)
            fmt_base = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
            fmt_name = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2'})
            fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D9D9D9'})
            fmt_total = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FFFFCC', 'align': 'center', 'num_format': '#,##0.0'})
            worksheet.set_column(0, 0, 25, fmt_name)
            worksheet.set_column(1, len(column_names), 12, fmt_base)
            total_col_idx = len(column_names) + 1
            worksheet.set_column(total_col_idx, total_col_idx, 15, fmt_total)
            worksheet.write(0, total_col_idx, "合計時間", fmt_header)
            
            import xlsxwriter.utility as xl_util
            for row_num in range(1, len(ALL_NAMES) + 1):
                excel_row = row_num + 1
                last_day_letter = xl_util.xl_col_to_name(len(column_names))
                range_ref = f"B{excel_row}:{last_day_letter}{excel_row}"
                formula = f"=SUMPRODUCT(IFERROR((TRIM(RIGHT(SUBSTITUTE({range_ref},\"-\",REPT(\" \",100)),100))-TRIM(LEFT(SUBSTITUTE({range_ref},\"-\",REPT(\" \",100)),100)))*24,0))"
                worksheet.write_formula(row_num, total_col_idx, formula, fmt_total)
            worksheet.freeze_panes(1, 1)

        st.download_button(label="📥 Excelを出力する", data=buffer.getvalue(), file_name=f"shift_{year}_{month:02}.xlsx", key="dl_btn")

        # 欠員状況の表示
        st.divider()
        st.subheader("欠員状況")
        if st.session_state.gen_alerts:
            st.warning(f"今月の合計欠員数: **{len(st.session_state.gen_alerts)}枠**")
            st.session_state.gen_alerts.sort(key=lambda x: int(x.split('日')[0]))
            for msg in st.session_state.gen_alerts: st.error(msg)
        else:
            st.success("✅ 欠員なし！")