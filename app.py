import streamlit as st
import pandas as pd
import calendar
import random
import io
import time
from datetime import date, timedelta  # 
from datetime import date, timedelta, datetime
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components  # 追加

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
def calc_work_and_break(val):
    """'10:00-18:00' などの文字列から実働と休憩を計算（最強版）"""
    # 文字列でない、または空の場合は0
    val_str = str(val).strip()
    if val_str == "" or val_str in ["nan", "None", "✖", "FALSE", "False"]:
        return 0.0, 0.0
    
    # 記号の揺れを修正（全角～や長音をハイフンに統一）
    val_str = val_str.replace("～", "-").replace("〜", "-").replace("ー", "-").replace(" ", "")
    
    if "-" not in val_str:
        return 0.0, 0.0
        
    try:
        start_str, end_str = val_str.split("-")
        # 時刻形式を整える (10:0 -> 10:00)
        def fix_time(t):
            if ":" not in t: return t + ":00"
            return t
            
        fmt = "%H:%M"
        start_dt = datetime.strptime(fix_time(start_str), fmt)
        end_dt = datetime.strptime(fix_time(end_str), fmt)
        
        diff = (end_dt - start_dt).total_seconds() / 3600
        if diff < 0: diff += 24 # 深夜跨ぎ対応
        
        # 休憩ルール：6h超で0.75h、8h超で1.0h
        brk = 0.0
        if diff > 8: brk = 1.0
        elif diff > 6: brk = 0.75
        
        return round(diff - brk, 2), brk
    except:
        return 0.0, 0.0
st.set_page_config(page_title="ジョイフル シフト管理", layout="wide")

# --- 1. スプレッドシート接続設定 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1dDyKAXYsHZg1ta4l7te84uSbhSea-FoyVgTeo4-kgkI/edit?gid=0#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)
# --- 準備：日付と名簿の情報を整理する ---

# --- 1. 今日が何年何月かを取得（修正版） ---
if 'view_date' not in st.session_state:
    # 今月の1日を取得
    today_first = date.today().replace(day=1)
    # 32日後（＝必ず来月）の1日を初期値とする
    st.session_state.view_date = (today_first + timedelta(days=32)).replace(day=1)

# この v_date.year, v_date.month を使うことで、
# 2027年になれば自動的に 2027, 2028 という数字が使われます。
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

def save_sheet_robust(df, worksheet_name):
    """データを保存する。シートがない場合は自動で作成する。"""
    try:
        # --- 内部の gspread クライアントを力ずくで探す ---
        raw_gc = None
        
        # パターン1: conn 直下に _client がある場合
        if hasattr(conn, "_client"):
            raw_gc = conn._client
        # パターン2: conn.client の中に _client がある場合 (多くのバージョンがこれ)
        elif hasattr(conn, "client") and hasattr(conn.client, "_client"):
            raw_gc = conn.client._client
        # パターン3: conn.client 自体がクライアントの場合
        elif hasattr(conn, "client"):
            raw_gc = conn.client
            
        # 最終チェック: open_by_url を持っているか
        if raw_gc is None or not hasattr(raw_gc, "open_by_url"):
            st.error("Google Sheetsの接続元が見つかりませんでした。手動でシートを作成してください。")
            return False

        # --- シートの存在確認と作成 ---
        sh = raw_gc.open_by_url(SPREADSHEET_URL)
        worksheet_list = [w.title for w in sh.worksheets()]
        
        if worksheet_name not in worksheet_list:
            # シートが存在しない場合、新規作成（100行50列）
            sh.add_worksheet(title=worksheet_name, rows="100", cols="50")
            st.info(f"✨ 新しいシート「{worksheet_name}」を自動作成しました。")

        # --- データの整形と書き込み ---
        # 1. スタイル設定などがある場合は純粋なデータだけを取り出す
        save_df = df.data if hasattr(df, 'data') else df.copy()
        
        # 2. インデックス（名前）を1列目に戻す
        save_df = save_df.reset_index()
        
        # 3. Googleが勝手に日付や数字に変えるのを防ぐため、文字に変換
        save_df = save_df.map(lambda x: "TRUE" if x is True else ("FALSE" if x is False else x))
        
        # 4. 書き込み実行 (ライブラリ標準の機能を使用)
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=save_df)
        
        # キャッシュをクリア
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
def load_confirmed_shift(sheet_name):
    try:
        # ttl=0 で常に最新を取りに行く
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=sheet_name, ttl=0)
        if df is not None and not df.empty:
            # 1列目が何であれインデックスにする（名前やグループ）
            df = df.set_index(df.columns[0])
            return df
        return pd.DataFrame()
    except Exception:
        # シートが存在しない場合は空のDFを返す
        return pd.DataFrame()


# --- 3. メイン画面 ---
# ジョイフル風カスタムCSS
st.markdown("""
    <style>
    /* メイン背景色 */
    .stApp {
        background-color: #FFFDF0;
    }
    /* ボタンをジョイフルオレンジに */
    div.stButton > button:first-child {
        background-color: #FF8C00;
        color: white;
        border-radius: 20px;
        border: none;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    /* ヘッダーの装飾 */
    h1 {
        color: #E60012; /* ジョイフルレッド */
        border-bottom: 3px solid #FF8C00;
    }
    /* サイドバーの調整 */
    section[data-testid="stSidebar"] {
        background-color: #F8F8F8;
    }
    </style>
    """, unsafe_allow_html=True)
st.title(" ジョイフル小倉店シフト管理")
st.sidebar.title("メニュー")
# ネット上のロゴを表示する例
# サイドバーの radio ボタンを更新
mode = st.sidebar.radio("機能を選択", ["確定シフト閲覧", "休み希望入力", "従業員名簿管理", "シフト自動生成（案）"])
pw = st.sidebar.text_input("管理者パスワード", type="password")
# --- お知らせの読み込みを追加 ---
# configシートからデータを読み込む
notice_df = load_sheet_no_cache("config", pd.DataFrame([["お知らせはありません"]], columns=["message"]))
# 1行目のデータ（実際のメッセージ）を取り出す
current_notice = notice_df.iloc[0, 0] if not notice_df.empty else "お知らせはありません"
st.info(f" お知らせ： {current_notice}")
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
            with st.expander("お知らせの編集"):
            # 今のお知らせを表示した状態で入力欄を作る
                new_notice = st.text_area("スタッフ全員に表示するメッセージを入力してください", value=current_notice)
                if st.button("お知らせを更新する"):
                # 新しいメッセージをDataFrameの形にする
                    updated_notice_df = pd.DataFrame([[new_notice]], columns=["message"])
                # configシートに上書き保存
                    if save_sheet_robust(updated_notice_df, "config"):
                        st.success("お知らせを更新しました！全員の画面に反映されます。")
                        st.rerun() # 画面を更新して即座に反映
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
            
    
            if st.button("保存"):
                if save_master(edited_df):
                    st.success("保存しました！")
                    st.rerun()
        else:
            st.warning("左側のメニューでパスワードを入力してください。")
            st.write("### 現在の名簿（閲覧のみ）")
            if not master_df.empty:
                st.dataframe(master_df, use_container_width=True)
            

if mode == "休み希望入力":
    st.title(f" {year}年{month}月の休み希望入力")
    
    state_key = f"req_data_{year}_{month}"

    # 1. データの読み込みと初期化
    # リロード（F5）された場合や、まだ貯金箱にデータがない場合のみ実行
    if state_key not in st.session_state:
        with st.spinner("最新データを読み込み中..."):
            # キャッシュを無視(ttl=0)して、スプレッドシートの「生の事実」を取りに行く
            r_raw = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=REQ_SHEET, ttl=0)
            
            if r_raw is None or r_raw.empty:
                # シートが完全に空なら、真っ白な表を新規作成
                df = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)
            else:
                # 【重要】重複を消し、名前を基準にする
                df = r_raw.drop_duplicates(subset=r_raw.columns[0]).set_index(r_raw.columns[0])
                df.index = df.index.astype(str).str.strip()
                # 名簿と日付の列をカッチリ固定（これでズレがなくなります）
                df = df.reindex(index=ALL_NAMES, columns=column_names).fillna(False)
                
                # 【★ここが修正の核心★】
                # リロード時に消えてしまうのは、ここでの判定が厳しすぎたからです。
                # スプレッドシートの「1」「1.0」「TRUE」「文字のTrue」すべてを
                # 漏らさず本物のチェックマーク（True）に変換します。
                df = df.map(lambda x: str(x).upper().strip() in ["TRUE", "1", "1.0", "TRUE.0"])
            
            # 整形が終わったデータを貯金箱に入れる
            st.session_state[state_key] = df

    # 現在編集中のデータ（貯金箱の中身）を表示用に使う
    display_df = st.session_state[state_key]

    # ---------------------------------------------------------
    # 2. 画面レイアウト（左：名前ボタン、右：全体状況）
    # ---------------------------------------------------------
    col_btn, col_view = st.columns([1, 6])

    # --- 右側の列：全体の状況表示・一括編集（管理者用） ---
    with col_view:
        config = {col: st.column_config.CheckboxColumn(col, width="small") for col in column_names}

        if pw == "1234":
            st.subheader("管理者モード：全員分を直接編集")
            # 管理者専用の一括編集フォーム
            with st.form(key="admin_bulk_edit_form"):
                edited_all = st.data_editor(
                    display_df, 
                    column_config=config,
                    use_container_width=True, 
                    height=600,
                    key="admin_bulk_editor"
                )
                if st.form_submit_button("全員の変更を一括保存する"):
                    with st.spinner("一括保存中..."):
                        if save_sheet_robust(edited_all, REQ_SHEET):
                            st.session_state[state_key] = edited_all
                            st.success("✅ 全員分の休み希望を保存しました！")
                            time.sleep(1)
                            st.rerun()
        else:
            st.subheader("😪全体の休み状況")
            # 一般スタッフには編集不可（disabled=True）として表示
            st.data_editor(display_df, column_config=config, use_container_width=True, height=600, disabled=True)

    # --- 左側の列：個人入力への誘導ボタン ---
    with col_btn:
        st.write("自分の名前を押すと下の方に入力画面が現れるよ！⇩")
        # ボタンを小さくするCSSを適用
        st.markdown("""
            <style>
            .stButton > button {
                font-size: 11px !important;
                height: 20px !important;
                padding: 0px 5px !important;
                margin-bottom: 2px !important;
                border-radius: 4px !important;
            }
            </style>
        """, unsafe_allow_html=True)

        for name in ALL_NAMES:
            if st.button(f"{name}", key=f"sel_{name}", use_container_width=True):
                st.session_state.editing_user = name

# --- 3. 個別入力エリア（名前ボタンが押されたら下に出現） ---
    if "editing_user" in st.session_state:
        user = st.session_state.editing_user
        
        # 【重要】ここから追加：自動スクロール用の目印とスクリプト
        st.markdown('<div id="edit_section"></div>', unsafe_allow_html=True)
        components.html(
            f"""
            <script>
                var element = window.parent.document.getElementById('edit_section');
                if (element) {{
                    element.scrollIntoView({{behavior: 'smooth'}});
                }}
            </script>
            """,
            height=0,
        )
        st.divider()
        st.header(f" {user} さんの入力画面")

        # フォームを使って、ポチポチ中の読み込み（重さ）を防止
        with st.form(key=f"individual_form_{user}"):
            # 貯金箱から自分の行だけ取り出す
            user_row = display_df.loc[[user]]
            
            edited_user_row = st.data_editor(
                user_row, 
                column_config=config,
                use_container_width=True, 
                key=f"editor_{user}"
            )

            col_s1, col_s2 = st.columns([1, 4])
            with col_s1:
                submit_button = st.form_submit_button(label=f"💾 {user}さんの分を保存")
            with col_s2:
                # 閉じるためのボタン（フォーム内なので、何もしないボタンとして置く）
                if st.form_submit_button("閉じる"):
                    del st.session_state.editing_user
                    st.rerun()

            if submit_button:
                with st.spinner("スプレッドシートを更新中..."):
                    # 他人の入力を消さないためのマージ（合体）保存処理
                    # ① まず、今この瞬間のスプレッドシートの「全員分」を読み直す
                    latest_all_raw = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=REQ_SHEET, ttl=0)
                    
                    if latest_all_raw is None or latest_all_raw.empty:
                        # シートが空なら、今の画面のデータをベースにする
                        latest_all_indexed = display_df.copy()
                    else:
                        # シートがあるなら、名前を軸にして掃除する
                        latest_all_indexed = latest_all_raw.drop_duplicates(subset=latest_all_raw.columns[0]).set_index(latest_all_raw.columns[0])
                        latest_all_indexed.index = latest_all_indexed.index.astype(str).str.strip()
                        # 日付列をカレンダー通りに強制固定（列消失対策）
                        latest_all_indexed = latest_all_indexed.reindex(columns=column_names).fillna(False)
                        # 型を True/False に揃える
                        latest_all_indexed = latest_all_indexed.map(lambda x: str(x).upper() in ["TRUE", "1", "1.0", "YES"])

                    # ② 最新の全員表の「自分の行だけ」を、今入力した1行に差し替える
                    latest_all_indexed.loc[user] = edited_user_row.iloc[0]

                    # ③ 完成した最新合体版をスプレッドシートに保存
                    if save_sheet_robust(latest_all_indexed, REQ_SHEET):
                        # 成功したら手元の貯金箱も更新
                        st.session_state[state_key] = latest_all_indexed
                        # 編集モードを終了
                        del st.session_state.editing_user
                        st.success(f"✅ {user} さんの休み希望を保存しました！")
                        time.sleep(1)
                        st.rerun()
elif mode == "シフト自動生成（案）":
    st.title(" シフト自動生成（案）")

    # --- 1. 必要人数（枠数）の設定エリア ---
    with st.expander("必要人数の設定", expanded=True):
        st.write("基本人数を設定してください。")
        col_wd, col_we = st.columns(2)
        with col_wd:
            st.markdown("### 🚃 平日 (月〜木)")
            h_d_wd = st.number_input("ホール昼", 1, 10, 2, key="h_d_wd")
            k_d_wd = st.number_input("キッチン昼", 1, 10, 2, key="k_d_wd")
            h_n_wd = st.number_input("ホール夜", 1, 10, 3, key="h_n_wd")
            k_n_wd = st.number_input("キッチン夜", 1, 10, 3, key="k_n_wd")
        with col_we:
            st.markdown("### 🌞 金・土・日")
            h_d_we = st.number_input("ホール昼 ", 1, 10, 3, key="h_d_we")
            k_d_we = st.number_input("キッチン昼 ", 1, 10, 2, key="k_d_we")
            h_n_we = st.number_input("ホール夜 ", 1, 10, 4, key="h_n_we")
            k_n_we = st.number_input("キッチン夜 ", 1, 10, 4, key="k_n_we")

    st.markdown("---")
    st.write("設定が完了したら、下のボタンを押してシフトを生成してください。")
    # 生成実行ボタン
    gen_button = st.button("シフトを生成・再生成（約23秒）", use_container_width=True)

    # セッション状態（貯金箱）の初期化
    if "last_generated_df" not in st.session_state:
        st.session_state.last_generated_df = None
    if "last_shortage_alerts" not in st.session_state:
        st.session_state.last_shortage_alerts = []

    # --- 2. 生成ロジック（ボタンが押されたときだけ実行） ---
    if gen_button:
        progress_bar = st.progress(0)
        status_text = st.empty() # テキスト表示用
    
    # 全ステップ数 (4ブロック * 70回)
        total_steps = 4 * 70
        current_step = 0
        with st.spinner("計算中...なんとかなれッ。"):
            # データの準備（休み希望の読み込み）
            req_load_raw = load_sheet_cached(REQ_SHEET)
            if req_load_raw is None or req_load_raw.empty:
                req_load = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)
            else:
                req_load_raw = req_load_raw.drop_duplicates(subset=req_load_raw.columns[0])
                req_load = req_load_raw.set_index(req_load_raw.columns[0]).reindex(ALL_NAMES).fillna(False)
                req_load = req_load.map(lambda x: str(x).upper().strip() in ["TRUE", "1", "1.0"])

            # 共通の「割り当て関数」の定義
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

            # 生成用の一時変数
            t_monthly_shift_df = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
            user_limits = {row["名前"]: row["週希望"] for _, row in master_df.iterrows()}
            t_shortage_alerts = []

            # 31日を4つのブロックに分割
            ranges = [[1, 7], [8, 15], [16, 23], [24, 31]]
            
            # 全スタッフに休み印をあらかじめ印字
            for name in ALL_NAMES:
                for col in column_names:
                    if req_load.at[name, col] == True:
                        t_monthly_shift_df.at[name, col] = "✖"

            # ブロックごとのループ
            for start_d, end_d in ranges:
                best_block_df = None
                best_block_alerts = []
                min_shortage_in_block = 999
                
                # 指定回数試行して最も欠員の少ないパターンを探す
                for trial in range(70):
                    trial_df = t_monthly_shift_df.copy()
                    t_week_counts = {name: 0 for name in ALL_NAMES}
                    trial_alerts = []
                    trial_shortage = 0
                    
                    block_cols = [c for c in column_names if start_d <= int(c.split('(')[0]) <= end_d]
                    
                    for col in block_cols:
                        assigned_today = []
                        d = int(col.split('(')[0])
                        d_idx = calendar.weekday(year, month, d)
                        
                        if d_idx >= 4: # 金土日
                            n_hd, n_kd, n_hn, n_kn = h_d_we, k_d_we, h_n_we, k_n_we
                        else: # 月〜木
                            n_hd, n_kd, n_hn, n_kn = h_d_wd, k_d_wd, h_n_wd, k_n_wd

                        def get_eligible_staff(group_name, is_wildcard=False):
                            pool = [n for n in master_df[master_df['グループ'] == group_name]['名前'].tolist() 
                                    if not req_load.at[n, col] and (is_wildcard or t_week_counts[n] < int(user_limits.get(n, 3)))]
                            random.shuffle(pool)
                            return pool

                        hd_pool = get_eligible_staff('HD')
                        hn_pool = get_eligible_staff('HN')
                        kd_pool = get_eligible_staff('KD')
                        kn_pool = get_eligible_staff('KN')
                        w_pool = get_eligible_staff('W', is_wildcard=True)

                        # ホール昼
                        hd_res = []
                        hd_leader = next((n for n in (hd_pool + w_pool) if n not in assigned_today and master_df.set_index('名前').at[n, 'デザート']), None)
                        if hd_leader:
                            hd_res.append({"スロット": "10:00-18:00", "担当者": hd_leader})
                            assigned_today.append(hd_leader)
                        hd_res += assign_slots(["10:00-18:00"] * (n_hd - len(hd_res)), hd_pool, w_pool, assigned_today)

                        # キッチン昼
                        kd_res = assign_slots(["10:00-18:00"] * n_kd, kd_pool, w_pool, assigned_today)

                        # ホール夜
                        hn_res = []
                        hn_leader = next((n for n in (hn_pool + w_pool) if n not in assigned_today and master_df.set_index('名前').at[n, 'レジ締め']), None)
                        if hn_leader:
                            hn_res.append({"スロット": "18:00-23:00", "担当者": hn_leader})
                            assigned_today.append(hn_leader)
                        hn_slots = ["18:00-23:00", "18:00-23:00", "18:00-22:00", "19:00-23:00"]
                        if n_hn > 4: hn_slots += ["18:00-23:00"] * (n_hn - 4)
                        hn_res += assign_slots(hn_slots[:n_hn-len(hn_res)], hn_pool, w_pool, assigned_today)

                        # キッチン夜
                        kn_slots = ["18:00-23:00", "18:00-23:00", "18:00-22:00", "19:00-23:00"]
                        if n_kn > 4: kn_slots += ["18:00-23:00"] * (n_kn - 4)
                        kn_res = assign_slots(kn_slots[:n_kn], kn_pool, w_pool, assigned_today)

                        for res_list, pos_name in [(hd_res, "ホール昼"), (kd_res, "キッチン昼"), (hn_res, "ホール夜"), (kn_res, "キッチン夜")]:
                            for item in res_list:
                                if item["担当者"] == "⚠️ 欠員":
                                    trial_shortage += 1
                                    trial_alerts.append(f"{d}日:{pos_name}に欠員")
                                else:
                                    trial_df.at[item["担当者"], col] = item["スロット"]
                                    t_week_counts[item["担当者"]] += 1

                    if trial_shortage < min_shortage_in_block:
                        min_shortage_in_block = trial_shortage
                        best_block_df = trial_df
                        best_block_alerts = trial_alerts
                
                t_monthly_shift_df = best_block_df
                t_shortage_alerts.extend(best_block_alerts)

            # 結果を貯金箱に保存
            st.session_state.last_generated_df = t_monthly_shift_df
            st.session_state.last_shortage_alerts = t_shortage_alerts
            progress_bar.progress(1.0)
            status_text.text("🎉 生成が完了しました！")
            time.sleep(1)
            status_text.empty() # メッセージを消す
            progress_bar.empty() # バーを消す

    # --- 3. 結果の表示（貯金箱にデータがある場合のみ表示） ---
    if st.session_state.last_generated_df is not None:
        # スタイル適用して表示
        st.dataframe(
            st.session_state.last_generated_df.style.map(lambda x: "background-color: #ffd1d1" if x == "✖" else ""),
            use_container_width=True
        )

        st.divider()
        st.subheader(" シフト表をダウンロード")

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            # 名前とグループの対応辞書
            name_to_group = master_df.set_index("名前")["グループ"].to_dict()
            excel_df = st.session_state.last_generated_df.copy()
            excel_df.insert(0, "グループ", [name_to_group.get(name, "") for name in excel_df.index])
            excel_df.to_excel(writer, sheet_name='シフト案')
            
            workbook  = writer.book
            worksheet = writer.sheets['シフト案']

            # 書式
            fmt_base = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
            fmt_name = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2'})
            fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D9D9D9'})
            total_fmt = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FFFFCC', 'align': 'center', 'num_format': '#,##0.0'})
            fmt_sat = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#CCE5FF', 'font_color': '#0000FF'})
            fmt_sun = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFCCCC', 'font_color': '#FF0000'})

            worksheet.set_column(0, 0, 10, fmt_base)
            worksheet.set_column(1, 1, 20, fmt_name)
            
            date_start_col_idx = 2
            num_date_cols = len(column_names)
            worksheet.set_column(date_start_col_idx, date_start_col_idx + num_date_cols - 1, 12, fmt_base)

            total_col_idx = date_start_col_idx + num_date_cols
            break_col_idx = date_start_col_idx + num_date_cols + 1
            
            worksheet.set_column(total_col_idx, break_col_idx, 12, total_fmt)
            worksheet.write(0, total_col_idx, "合計実働", fmt_header)
            worksheet.write(0, break_col_idx, "休憩合計", fmt_header)

            for i, value in enumerate(column_names):
                col_pos = date_start_col_idx + i
                if "(土)" in value:
                    worksheet.write(0, col_pos, value, fmt_sat)
                elif "(日)" in value:
                    worksheet.write(0, col_pos, value, fmt_sun)
                else:
                    worksheet.write(0, col_pos, value, fmt_header)

            import xlsxwriter.utility as xl_util
            for row_num in range(1, len(ALL_NAMES) + 1):
                excel_row = row_num + 1
                first_day_letter = "C"
                last_day_letter = xl_util.xl_col_to_name(date_start_col_idx + num_date_cols - 1)
                range_ref = f"{first_day_letter}{excel_row}:{last_day_letter}{excel_row}"
                
                break_formula = (
                    f"=SUM(IFERROR("
                    f"IF((TIMEVALUE(MID({range_ref},FIND(\"-\",{range_ref})+1,10))-TIMEVALUE(LEFT({range_ref},FIND(\"-\",{range_ref})-1)))*24>8, 1, "
                    f"IF((TIMEVALUE(MID({range_ref},FIND(\"-\",{range_ref})+1,10))-TIMEVALUE(LEFT({range_ref},FIND(\"-\",{range_ref})-1)))*24>6, 0.75, 0))"
                    f", 0))"
                )
                net_total_formula = (
                    f"=SUM(IFERROR("
                    f"((TIMEVALUE(MID({range_ref},FIND(\"-\",{range_ref})+1,10))-TIMEVALUE(LEFT({range_ref},FIND(\"-\",{range_ref})-1)))*24) - "
                    f"IF((TIMEVALUE(MID({range_ref},FIND(\"-\",{range_ref})+1,10))-TIMEVALUE(LEFT({range_ref},FIND(\"-\",{range_ref})-1)))*24>8, 1, "
                    f"IF((TIMEVALUE(MID({range_ref},FIND(\"-\",{range_ref})+1,10))-TIMEVALUE(LEFT({range_ref},FIND(\"-\",{range_ref})-1)))*24>6, 0.75, 0))"
                    f", 0))"
                )
                worksheet.write_array_formula(row_num, total_col_idx, row_num, total_col_idx, net_total_formula, total_fmt)
                worksheet.write_array_formula(row_num, break_col_idx, row_num, break_col_idx, break_formula, total_fmt)

            worksheet.freeze_panes(1, 2)
            
            shortage_col_idx = total_col_idx + 2
            worksheet.set_column(shortage_col_idx, shortage_col_idx, 35)
            worksheet.write(0, shortage_col_idx, "欠員状況", fmt_header)
            shortage_count_fmt = workbook.add_format({'bold': True, 'font_color': '#FF0000', 'align': 'left'})
            worksheet.write(1, shortage_col_idx, f"今月の合計欠員数: {len(st.session_state.last_shortage_alerts)}名", shortage_count_fmt)
            
            if st.session_state.last_shortage_alerts:
                sorted_alerts = sorted(st.session_state.last_shortage_alerts, key=lambda x: int(x.split('日')[0]))
                for i, msg in enumerate(sorted_alerts):
                    worksheet.write(i + 3, shortage_col_idx, msg)

        st.download_button(
            label=" Excelを出力する",
            data=buffer.getvalue(),
            file_name=f"joyfull_shift_{year}_{month:02}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="excel_download_after_gen"
        )

        st.divider()
        st.subheader("欠員状況")
        if st.session_state.last_shortage_alerts:
            st.warning(f"今月の合計欠員数: **{len(st.session_state.last_shortage_alerts)}枠**")
            sorted_alerts_view = sorted(st.session_state.last_shortage_alerts, key=lambda x: int(x.split('日')[0]))
            for msg in sorted_alerts_view:
                st.error(msg)
        else:
            st.success("✅ 欠員なし！全てのシフトが埋まりました。")
    if pw == "1234":
        st.divider()
        st.subheader("📤 完成版Excelをアップロードして公開")
        up_file = st.file_uploader("Excelファイルを選択してください", type="xlsx")
        
        if up_file:
            # 1. Excelを読み込む
            f_df = pd.read_excel(up_file, sheet_name=0)
            st.write("読み込み中... プレビュー:")
            st.dataframe(f_df.head(3))
            
            if st.button("公開する"):
                with st.spinner("計算中..."):
                    date_cols = [c for c in f_df.columns if "(" in str(c) and ")" in str(c)]
                    
                    nets, brks = [], []
                    for _, row in f_df.iterrows():
                        row_net, row_brk = 0.0, 0.0
                        for c in date_cols:
                            n, b = calc_work_and_break(row[c])
                            row_net += n
                            row_brk += b
                        # ★ ここで 1（小数点第1位）に丸める
                        nets.append(round(row_net, 1))
                        brks.append(round(row_brk, 1))
                    
                    f_df["合計実働"] = nets
                    f_df["休憩合計"] = brks                    
                    # インデックス（名前）を設定
                    f_df = f_df.set_index(f_df.columns[0])
                    
                    # スプレッドシートへ保存
                    target_sheet = f"shift_{year}_{month:02}"
                    if save_sheet_robust(f_df, target_sheet):
                        st.cache_data.clear()
                        st.success(f"再計算完了！ {target_sheet} を公開しました。")
                        time.sleep(1)
                        st.rerun()
st.sidebar.image("cafe_logo.png", width=200)
if mode == "確定シフト閲覧":
    st.title("確定シフト閲覧")

    # --- 今日の出勤メンバー（強化版） ---
    today = date.today()
    t_day = today.day
    t_month = today.month
    t_year = today.year

    # 今日の日付（例: "30"）で始まる列を自動で探す
    day_prefix = f"{t_day}(" 
    
    today_sheet = f"shift_{t_year}_{t_month:02}"
    today_df = load_sheet_no_cache(today_sheet, pd.DataFrame())
    
    with st.expander(f"🏃 本日 {t_month}月{t_day}日の出勤メンバー", expanded=True):
        if today_df.empty:
            st.write(f"シート「{today_sheet}」が見つからないか、空っぽです。")
        else:
            # 1. 今日の日付列を探す
            target_col = None
            for col in today_df.columns:
                c_str = str(col).strip()
                if c_str.startswith(day_prefix) or c_str == str(t_day):
                    target_col = col
                    break
            
            # 2. グループ列を特定する
            group_col = None
            if "グループ" in today_df.columns:
                group_col = "グループ"
            elif not today_df.empty:
                group_col = today_df.columns[0] # インデックスの次の1列目をグループ列とみなす

            if target_col is None:
                st.write(f"今日の日付「{t_day}日」の列が見当たりません。")
            else:
                # 3. 出勤者を抽出
                workers = today_df[ (today_df[target_col].notna()) & 
                                    (today_df[target_col].astype(str).str.strip() != "✖") & 
                                    (today_df[target_col].astype(str).str.strip() != "") ].copy()
                
                if workers.empty:
                    st.write("本日の出勤予定者はいません。")
                else:
                    # 4. 表示用に整理（Excelのグループ列をそのまま使用）
                    col_hall, col_kitchen = st.columns(2)
                    
                    # グループ列の値を掃除
                    workers['gp_clean'] = workers[group_col].astype(str).str.strip() if group_col else "不明"
                    
                    with col_hall:
                        st.markdown("### 👔 ホール")
                        # グループ名に H または W が入っている人（HD, HN, W, または不明）
                        hall_list = workers[workers['gp_clean'].str.contains('H|W|不明', na=False)]
                        if not hall_list.empty:
                            for name, row in hall_list.sort_values(by=target_col).iterrows():
                                st.write(f"**{row[target_col]}** ： {name}")
                        else: st.caption("なし")

                    with col_kitchen:
                        st.markdown("### 🍳 キッチン")
                        # グループ名に K が入っている人（KD, KN）
                        kit_list = workers[workers['gp_clean'].str.contains('K', na=False)]
                        if not kit_list.empty:
                            for name, row in kit_list.sort_values(by=target_col).iterrows():
                                st.write(f"**{row[target_col]}** ： {name}")
                        else: st.caption("なし")
    
    st.divider()

    # --- 全体表示の年月選択（デフォルトを現在に設定） ---
    col_y, col_m = st.columns(2)
    
    # 年のデフォルト設定
# --- 確定シフト閲覧の年リスト修正 ---
        # 今年を中心に、去年・今年・来年・再来年を自動でリストにする
    year_list = [today.year - 1, today.year, today.year + 1, today.year + 2]
        
    try:
        default_year_idx = year_list.index(today.year)
    except ValueError:
        default_year_idx = 1 # 万が一見つからなければ今年のインデックス(1)にする
            
    target_year = col_y.selectbox("年", year_list, index=default_year_idx)
    # 月のデフォルト設定（index=現在の月-1）
    target_month = col_m.selectbox("月", range(1, 13), index=t_month - 1)
    
    sheet_name = f"shift_{target_year}_{target_month:02}"
    
    # 管理者用メモ
    if pw == "1234":
        st.caption(f"（管理者用メモ：シート名「{sheet_name}」を探しています）")

    confirmed_df = load_confirmed_shift(sheet_name)
    
    if confirmed_df.empty:
        st.info(f"💡 {target_year}年{target_month}月の確定シフトはまだ公開されていません。")
    else:
        st.write("---")
        # 選択肢もきれいに掃除
        search_name = st.selectbox("自分の名前を選択してね！✨", ["(全員分表示)"] + [str(n).strip() for n in ALL_NAMES])
        
        def apply_styling(row):
            # 1. 判定用のターゲット（選択された名前）を掃除
            target = str(search_name).strip()
            
            # 2. 行の「名前」を特定する
            row_index_name = str(row.name).strip()
            row_first_cell = str(row.iloc[0]).strip() if len(row) > 0 else ""
            
            # インデックス、または1列目が選択された名前と一致するか？
            if target != "(全員分表示)" and (target == row_index_name or target == row_first_cell):
                # 一致したら行全体を強調
                return ['background-color: #FFF9C4; color: black; font-weight: bold; border: 2px solid #FFD700'] * len(row)
            return [''] * len(row)

        # スタイル適用
        styled_df = confirmed_df.style.apply(apply_styling, axis=1).map(
            lambda x: "color: #E60012; font-weight: bold;" if str(x).strip() == "✖" else ""
        )
        
        # 表示
        st.dataframe(
            styled_df,
            use_container_width=True,
            height=600
        )
