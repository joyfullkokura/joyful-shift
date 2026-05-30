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
    # 今月の1日を取得
    this_month_first = date.today().replace(day=1)
    # 32日後（必ず来月になる）の1日を初期値としてセットする
    st.session_state.view_date = (this_month_first + timedelta(days=32)).replace(day=1)
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
st.sidebar.title("メニュー")
# ネット上のロゴを表示する例
mode = st.sidebar.radio("機能を選択", ["休み希望入力","従業員名簿管理", "シフト自動生成（案）"])

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
            
    
            if st.button("スプレッドシートに保存"):
                if save_master(edited_df):
                    st.success("スプレッドシートに保存しました！")
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
        with st.spinner("スプレッドシートから最新データを読み込み中..."):
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
                    with st.spinner("スプレッドシートに一括保存中..."):
                        if save_sheet_robust(edited_all, REQ_SHEET):
                            st.session_state[state_key] = edited_all
                            st.success("✅ 全員分の休み希望を保存しました！")
                            time.sleep(1)
                            st.rerun()
        else:
            st.subheader("😪全体の休み状況（閲覧のみ）")
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

    # ---------------------------------------------------------
    # 3. 個別入力エリア（名前ボタンが押されたら下に出現）
    # ---------------------------------------------------------
    if "editing_user" in st.session_state:
        user = st.session_state.editing_user
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
            k_d_we = st.number_input("キッチン昼 ", 1, 10, 3, key="k_d_we")
            h_n_we = st.number_input("ホール夜 ", 1, 10, 4, key="h_n_we")
            k_n_we = st.number_input("キッチン夜 ", 1, 10, 4, key="k_n_we")

    # --- 2. データの準備（休み希望の読み込みと標準化） ---
    req_load_raw = load_sheet_cached(REQ_SHEET)
    if req_load_raw is None or req_load_raw.empty:
        req_load = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)
    else:
        req_load_raw = req_load_raw.drop_duplicates(subset=req_load_raw.columns[0])
        req_load = req_load_raw.set_index(req_load_raw.columns[0]).reindex(ALL_NAMES).fillna(False)
        req_load = req_load.map(lambda x: str(x).upper().strip() in ["TRUE", "1", "1.0"])

    # --- 3. 共通の「割り当て関数」の定義 ---
    def assign_slots(slot_list, main_pool, wildcard_pool, assigned_list):
        result = []
        combined_pool = main_pool + wildcard_pool
        for slot_time in slot_list:
            available = [name for name in combined_pool if name not in assigned_list]
            if available:
                picked = available[0] # 並び替え済みなので先頭を取る
                result.append({"スロット": slot_time, "担当者": picked})
                assigned_list.append(picked)
            else:
                result.append({"スロット": slot_time, "担当者": "⚠️ 欠員"})
        return result

    # --- 4. 生成ロジック（4ブロック × 10回試行） ---
    monthly_shift_df = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
    user_limits = {row["名前"]: row["週希望"] for _, row in master_df.iterrows()}
    # 最終的な欠員アラートを溜めるリスト
    shortage_alerts = []
    # 累積の出勤数（ブロックをまたいで保持される本番用）
    current_week_counts = {name: 0 for name in ALL_NAMES}

    # 31日を4つのブロックに分割
    ranges = [[1, 7], [8, 15], [16, 23], [24, 31]]
    
    # 全スタッフに休み印をあらかじめ印字
    for name in ALL_NAMES:
        for col in column_names:
            if req_load.at[name, col] == True:
                monthly_shift_df.at[name, col] = "✖"

    # ブロックごとのループ開始
    for start_d, end_d in ranges:
        best_block_df = None
        best_block_counts = None
        best_block_alerts = []
        min_shortage_in_block = 999
        
        # 10回試行して最も欠員の少ないパターンを探す
        for trial in range(70):
            # 試行用の一時的なコピー
            t_monthly_df = monthly_shift_df.copy()
            t_week_counts = {name: 0 for name in ALL_NAMES} # ブロック内でのリセット用カウント
            t_trial_alerts = []
            t_block_shortage = 0
            
            # このブロックに含まれる日付を取得
            block_cols = [c for c in column_names if start_d <= int(c.split('(')[0]) <= end_d]
            
            for col in block_cols:
                assigned_today = []
                d = int(col.split('(')[0])
                d_idx = calendar.weekday(year, month, d)
                
                # 曜日による人数決定
                if d_idx >= 4: # 金土日
                    n_hd, n_kd, n_hn, n_kn = h_d_we, k_d_we, h_n_we, k_n_we
                else: # 月〜木
                    n_hd, n_kd, n_hn, n_kn = h_d_wd, k_d_wd, h_n_wd, k_n_wd

                # 候補者のリストアップ（休み希望なし 且つ その週の出勤上限に達していない人）
                def get_eligible_staff(group_name, is_wildcard=False):
                    pool = [n for n in master_df[master_df['グループ'] == group_name]['名前'].tolist() 
                            if not req_load.at[n, col] and (is_wildcard or t_week_counts[n] < int(user_limits.get(n, 3)))]
                    random.shuffle(pool)
                    return pool

                hd_pool = get_eligible_staff('HD')
                hn_pool = get_eligible_staff('HN')
                kd_pool = get_eligible_staff('KD')
                kn_pool = get_eligible_staff('KN')
                w_pool = get_eligible_staff('W', is_wildcard=True) # 社員/共通は制限なし

                # --- 1. ホール昼(HD)の割り当て ---
                hd_res = []
                hd_leader = next((n for n in (hd_pool + w_pool) if n not in assigned_today and master_df.set_index('名前').at[n, 'デザート']), None)
                if hd_leader:
                    hd_res.append({"スロット": "10:00-18:00", "担当者": hd_leader})
                    assigned_today.append(hd_leader)
                hd_res += assign_slots(["10:00-18:00"] * (n_hd - len(hd_res)), hd_pool, w_pool, assigned_today)

                # --- 2. キッチン昼(KD)の割り当て ---
                kd_res = assign_slots(["10:00-18:00"] * n_kd, kd_pool, w_pool, assigned_today)

                # --- 3. ホール夜(HN)の割り当て ---
                hn_res = []
                hn_leader = next((n for n in (hn_pool + w_pool) if n not in assigned_today and master_df.set_index('名前').at[n, 'レジ締め']), None)
                if hn_leader:
                    hn_res.append({"スロット": "18:00-23:00", "担当者": hn_leader})
                    assigned_today.append(hn_leader)
                # 夜の椅子（スロット）リスト作成
                hn_slots = ["18:00-23:00", "18:00-23:00", "18:00-22:00", "19:00-23:00"] # 4人までの定義
                if n_hn > 4: hn_slots += ["18:00-23:00"] * (n_hn - 4) # 5人以上の場合は延長
                hn_res += assign_slots(hn_slots[:n_hn-len(hn_res)], hn_pool, w_pool, assigned_today)

                # --- 4. キッチン夜(KN)の割り当て ---
                kn_slots = ["18:00-23:00", "18:00-23:00", "18:00-22:00", "19:00-23:00"]
                if n_kn > 4: kn_slots += ["18:00-23:00"] * (n_kn - 4)
                kn_res = assign_slots(kn_slots[:n_kn], kn_pool, w_pool, assigned_today)

                # 今日の欠員カウントとデータ書き込み
                # ポジションごとに名前をつけてチェック
                check_list = [
                    (hd_res, "ホール昼"), (kd_res, "キッチン昼"),
                    (hn_res, "ホール夜"), (kn_res, "キッチン夜")
                ]
                for res_list, pos_name in check_list:
                    for item in res_list:
                        if item["担当者"] == "⚠️ 欠員":
                            t_block_shortage += 1
                            # ここで「1日:ホール昼に欠員」という形式にする
                            t_trial_alerts.append(f"{d}日:{pos_name}に欠員")
                        else:
                            t_monthly_df.at[item["担当者"], col] = item["スロット"]
                            t_week_counts[item["担当者"]] += 1
            # 10回試行のうち、最も欠員が少ないものをキープ
            if t_block_shortage < min_shortage_in_block:
                min_shortage_in_block = t_block_shortage
                best_block_df = t_monthly_df
                best_block_alerts = t_trial_alerts
                # この時点のカウントは次のブロックへは引き継がない(週リセットのため)
                best_block_counts = t_week_counts 

        # ブロック終了。ベストの結果を本番に反映
        monthly_shift_df = best_block_df
        shortage_alerts.extend(best_block_alerts)

    # --- 5. 結果の表示 ---
    # デザイン調整：×は赤く表示
    st.dataframe(
        monthly_shift_df.style.map(lambda x: "background-color: #ffd1d1" if x == "✖" else ""),
        use_container_width=True
    )
# --- Excel出力機能（自動計算・デザイン調整版） ---
    st.divider()
    st.subheader(" シフト表をダウンロード")

    buffer = io.BytesIO()
    # 見やすさを整えるために xlsxwriter を使用
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        monthly_shift_df.to_excel(writer, sheet_name='シフト案')
        
        workbook  = writer.book
        worksheet = writer.sheets['シフト案']
        # --- ここから追加：書式（見た目）の設定 ---
        # 合計列用の書式（太字、枠線、薄い黄色、数字は小数第一位まで）
        total_fmt = workbook.add_format({
            'bold': True, 
            'border': 1, 
            'bg_color': '#FFFFCC', 
            'align': 'center', 
            'num_format': '#,##0.0'
        })

        # ついでに他の波線も出るかもしれないので、基本の書式も定義しておきます
        fmt_base = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
        fmt_name = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2'})
        fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D9D9D9'})
        # ------------------------------------

        # --- 1. 書式（見た目）の設定 ---
        # 基本（枠線＋中央揃え）
        fmt_base = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
        # 名前列（太字＋グレー背景）
        fmt_name = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2'})
        # ヘッダー（太字＋濃いグレー）
        fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D9D9D9'})
        # 合計列（太字＋薄い黄色）
        fmt_total = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FFFFCC', 'align': 'center', 'num_format': '#,##0.0'})
        # 土曜（青）/ 日曜（赤）
        fmt_sat = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#CCE5FF', 'font_color': '#0000FF'})
        fmt_sun = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFCCCC', 'font_color': '#FF0000'})

        # --- 2. 列の幅とヘッダーの設定 ---
        worksheet.set_column(0, 0, 25, fmt_name)  # 名前列の幅
        worksheet.set_column(1, len(column_names), 12, fmt_base) # 日付列の幅

        # ヘッダーの色付け（土日判定）
        for col_num, value in enumerate(monthly_shift_df.columns):
            if "(土)" in value:
                worksheet.write(0, col_num + 1, value, fmt_sat)
            elif "(日)" in value:
                worksheet.write(0, col_num + 1, value, fmt_sun)
            else:
                worksheet.write(0, col_num + 1, value, fmt_header)

        # --- 3. 合計時間列の作成 (32日目の位置) ---
        total_col_idx = len(column_names) + 1
        worksheet.set_column(total_col_idx, total_col_idx, 15, fmt_total)
        worksheet.write(0, total_col_idx, "合計時間", fmt_header)

        # --- 4. 魔法の計算式（最新・修正版） ---
        import xlsxwriter.utility as xl_util
        
        for row_num in range(1, len(ALL_NAMES) + 1):
            excel_row = row_num + 1
            first_day_col = "B"
            # 末日の列記号を計算
            last_day_col_letter = xl_util.xl_col_to_name(len(column_names))
            range_ref = f"{first_day_col}{excel_row}:{last_day_col_letter}{excel_row}"
            
            # 【新ロジック】
            # SUBSTITUTEでハイフンを「時刻の引き算」ができる形式に整理します。
            # 数式の先頭に「{」などは入れず、xlsxwriterの標準形式で書き込みます。
            # これにより、Excel側で自動的に「@」がつくのを防ぎます。
            
            # --- 指定された数式（SUM + TIMEVALUE方式） ---
            range_ref = f"{first_day_col}{excel_row}:{last_day_col_letter}{excel_row}"
            
            formula = (
                f"=SUM(IFERROR((TIMEVALUE(MID({range_ref},FIND(\"-\",{range_ref})+1,10))"
                f"-TIMEVALUE(LEFT({range_ref},FIND(\"-\",{range_ref})-1)))*24,0))"
            )
            
            # 書き込み
            worksheet.write_array_formula(row_num, total_col_idx, row_num, total_col_idx, formula, total_fmt)
# --- 5. 欠員状況の印字 (合計時間のさらに右側に配置) ---
        shortage_col_idx = total_col_idx + 2  # 合計時間の2列右に配置
        worksheet.set_column(shortage_col_idx, shortage_col_idx, 35) # 文字が長いので幅を広く設定
        
        # 見出しの作成
        worksheet.write(0, shortage_col_idx, "欠員状況", fmt_header)
        
        # 合計人数の印字
        shortage_count_fmt = workbook.add_format({'bold': True, 'font_color': '#FF0000', 'align': 'left'})
        worksheet.write(1, shortage_col_idx, f"今月の合計欠員数: {len(shortage_alerts)}名", shortage_count_fmt)
        
        # 欠員リストを日付順に並び替えて印字
        if shortage_alerts:
            # メッセージの先頭の数字（日）で並び替え
            sorted_alerts = sorted(shortage_alerts, key=lambda x: int(x.split('日')[0]))
            
            for i, msg in enumerate(sorted_alerts):
                # 3行目から1行ずつ印字していく
                # 読みやすいように1行空けたい場合は i*2 などに調整も可能ですが、まずは詰めて印字します
                worksheet.write(i + 3, shortage_col_idx, msg)
        # ウィンドウ枠を固定（名前と日付が見えるように）
        worksheet.freeze_panes(1, 1)

    # 3. ダウンロードボタンを表示
    st.download_button(
        label=" Excelを出力する",
        data=buffer.getvalue(),
        file_name=f"joyfull_shift_{year}_{month:02}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="excel_download_with_formula" # 重複エラー防止のキー
    )
    st.divider()
    st.subheader("欠員状況")

    if shortage_alerts:
        # 1. 今月の合計欠員人数を表示
        total_missing = len(shortage_alerts)
        st.warning(f"今月の合計欠員数: **{total_missing}枠**")

        # 2. 日付順に並び替える（先頭の数字を見て並び替え）
        shortage_alerts.sort(key=lambda x: int(x.split('日')[0]))

        # 3. リストをそのまま表示（作成時に形式を整えているので、出すだけでOK）
        for msg in shortage_alerts:
            st.error(msg)
    else:
        st.success("✅ 欠員なし！全てのシフトが埋まりました。")
st.sidebar.image("cafe_logo.png", width=200)