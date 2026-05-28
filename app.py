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
st.title(" 従業員名簿・グループ管理")
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
    
    # --- ここに新しい「シフト作成」のプログラムを書いていく ---
    st.title("📅 シフト自動生成（案）")
    
    # 段階的ステップ1: ジョイフルの「必要枠（スロット）」を定義する
    st.subheader("1. 本日の必要人数（スロット）の確認")
    
    # ホール夜(HN)の枠を定義
    hall_night_slots = [
            "18:00-23:00", # 1人目
            "18:00-23:00", # 2人目
            "18:00-22:00", # 3人目
            "19:00-23:00"  # 4人目
        ]
    
    # キッチン夜(KN)の枠を定義
    kitchen_night_slots = [
            "18:00-23:00",
            "18:00-23:00",
            "18:00-22:00",
            "19:00-23:00"
        ]

    col1, col2 = st.columns(2)
    with col1:
            st.write("🏃 ホール必要枠")
            st.write(hall_night_slots)
    with col2:
            st.write("🍳 キッチン必要枠")
            st.write(kitchen_night_slots)

    # 段階的ステップ2: グループごとにリストを作る
# --- 追加箇所 A ---
# ① スプレッドシートから休み希望（req_2026_05など）を読み込む
    req_load = load_sheet_cached(REQ_SHEET)
# 名前を基準に整理し、文字の"TRUE"を本物のチェック（真偽値）に直す
    if req_load is None or req_load.empty:
    # 読み込み失敗または空の場合、全員「出勤可能（False）」な表を準備してエラーを防ぐ
        req_load = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)
    else:
    # 名前の重複を消し、名簿順（ALL_NAMES）に並べ替え。足りない人はFalseで埋める
        req_load = req_load.drop_duplicates(subset=req_load.columns[0])
        req_load = req_load.set_index(req_load.columns[0]).reindex(ALL_NAMES).fillna(False)
    
    # 【ここが重要！】0/1 と TRUE/FALSE の両方に対応させる翻訳処理
    # 値を「文字」にしてから、"TRUE" か "1" であれば True(休み) と判定する
    req_load = req_load.map(lambda x: str(x).upper().strip() in ["TRUE", "1", "1.0"])

# ② 31日分の結果を保存するための「空の大きな表」を作る
# 縦に従業員(ALL_NAMES)、横に日付(column_names)が並ぶバケツです
    monthly_shift_df = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
    user_limits = {row["名前"]: row["週希望"] for _, row in master_df.iterrows()}
    week_counts = {name: 0 for name in ALL_NAMES}
    # --- 休み印（×）の事前印字 ---
    for name in ALL_NAMES:
        # --- 追加箇所 1 ---
        shortage_alerts = []  # 欠員情報を入れるためのリスト（空っぽのメモ帳）
        for col in column_names:
            if req_load.at[name, col] == True:
                monthly_shift_df.at[name, col] = "✖"
    # --- 準備：グループごとに名簿を作る ---
    # --- 追加箇所 B ---
    for col in column_names: 
    # 今日の日付（数字）を取り出す
        d = int(col.split('(')[0])
    
    # 1, 8, 16, 24日なら、この瞬間にカウントを0に戻す！
        if d in [1, 8, 16, 24]:
            week_counts = {name: 0 for name in ALL_NAMES}
    # (ここから下の既存の「hd_pool = ...」などは、このfor文の中に含めるため右側に4マス分ズラします)
        hd_pool = [n for n in master_df[master_df['グループ'] == 'HD']['名前'].tolist() 
                   if not req_load.at[n, col] and week_counts[n] < int(user_limits.get(n, 0))]
        
        hn_pool = [n for n in master_df[master_df['グループ'] == 'HN']['名前'].tolist() 
                   if not req_load.at[n, col] and week_counts[n] < int(user_limits.get(n, 0))]
        
        kd_pool = [n for n in master_df[master_df['グループ'] == 'KD']['名前'].tolist() 
                   if not req_load.at[n, col] and week_counts[n] < int(user_limits.get(n, 0))]
        
        kn_pool = [n for n in master_df[master_df['グループ'] == 'KN']['名前'].tolist() 
                   if not req_load.at[n, col] and week_counts[n] < int(user_limits.get(n, 0))]
        
        # 社員(W)はバイトが足りない時の調整役なので、日数の制限をかけずに常に候補に入れる
        w_pool  = [n for n in master_df[master_df['グループ'] == 'W']['名前'].tolist() if not req_load.at[n, col]]
       # 全ての名簿をシャッフル（公平にするため）
        random.shuffle(hd_pool)
        random.shuffle(hn_pool)
        random.shuffle(kd_pool)
        random.shuffle(kn_pool)
        random.shuffle(w_pool)

    # 「今日すでにどこかの枠に割り当てられた人」をメモするリスト
        assigned_today = []

    # 共通の「割り当て関数」を作るとミスが減ります
        def assign_slots(slot_list, main_pool, wildcard_pool, assigned_list):
                result = []
        # メインの担当者(HD等)と共通(W)を合体
                combined_pool = main_pool + wildcard_pool
        
                for slot_time in slot_list:
            # まだ選ばれていない人だけを抽出（ここが引き算！）
                    available = [name for name in combined_pool if name not in assigned_list]
            
                    if available:
                        picked = available[0] # 一番上の人を選ぶ
                        result.append({"スロット": slot_time, "担当者": picked})
                        assigned_list.append(picked) # 選ばれた人を「使用済み」に入れる
                    else:
                        result.append({"スロット": slot_time, "担当者": "⚠️ 欠員"})
                return result

    # --- 1. 昼の枠（基本2名ずつ） ---
        day_slots = ["10:00-18:00", "10:00-18:00"]
    
    # 【ホール昼(HD)】: 1人目はデザートができる人を優先
        hd_results = []
    # 候補（HD+W）の中から、まだ選ばれておらず、デザートができる人を一人探す
        hd_leader = next((n for n in (hd_pool + w_pool) if n not in assigned_today and master_df.set_index('名前').at[n, 'デザート']), None)
    
        if hd_leader:
            hd_results.append({"スロット": "10:00-18:00", "担当者": hd_leader})
            assigned_today.append(hd_leader)
    
    # 残りの枠（1つ）を普通に埋める
        hd_results += assign_slots(["10:00-18:00"][len(hd_results):], hd_pool, w_pool, assigned_today)

    # 【キッチン昼(KD)】: スキル制限なし（普通に埋める）
        kd_results = assign_slots(["10:00-18:00", "10:00-18:00"], kd_pool, w_pool, assigned_today)


    # --- 2. 夜の枠（基本4名ずつ） ---
        hall_night_slots = ["18:00-23:00", "18:00-23:00", "18:00-22:00", "19:00-23:00"]
        kitchen_night_slots = ["18:00-23:00", "18:00-23:00", "18:00-22:00", "19:00-23:00"]
    
    # 【ホール夜(HN)】: 1人目は「レジ締め」ができる人を優先
        hn_results = []
        hn_leader = next((n for n in (hn_pool + w_pool) if n not in assigned_today and master_df.set_index('名前').at[n, 'レジ締め']), None)
    
        if hn_leader:
            hn_results.append({"スロット": "18:00-23:00", "担当者": hn_leader})
            assigned_today.append(hn_leader)
    
    # 残りの枠（3つ）を普通に埋める
        hn_results += assign_slots(hall_night_slots[len(hn_results):], hn_pool, w_pool, assigned_today)

    # 【キッチン夜(KN)】: 普通に埋める
        kn_results = assign_slots(kitchen_night_slots, kn_pool, w_pool, assigned_today)
        # --- 追加箇所 2 ---
        # 各ポジションの欠員数を数える処理
        def count_shortage(results):
            # 結果リストの中から「⚠️ 欠員」という文字が入っている数だけをカウントする
            return sum(1 for res in results if res["担当者"] == "⚠️ 欠員")

        # ホール昼、キッチン昼、ホール夜、キッチン夜、それぞれの欠員数を取得
        hd_short = count_shortage(hd_results)
        kd_short = count_shortage(kd_results)
        hn_short = count_shortage(hn_results)
        kn_short = count_shortage(kn_results)

        # 欠員が1人以上いる場合、指定の形式の文章にしてリストに追加する
        # d は現在の日付（数字）です
        if hd_short > 0: shortage_alerts.append(f"{d}日のホールの昼に{hd_short}人の欠員")
        if kd_short > 0: shortage_alerts.append(f"{d}日のキッチンの昼に{kd_short}人の欠員")
        if hn_short > 0: shortage_alerts.append(f"{d}日のホールの夜に{hn_short}人の欠員")
        if kn_short > 0: shortage_alerts.append(f"{d}日のキッチンの夜に{kn_short}人の欠員")
# --- 追加箇所 D ---
    # 算出した今日の全結果（hd_res + hn_res...）を、1ヶ月表の「今日の列(col)」に書き込む
        for item in hd_results + kd_results + hn_results + kn_results:
            if item["担当者"] != "⚠️ 欠員":
                monthly_shift_df.at[item["担当者"], col] = item["スロット"]
            # 出勤が決まったスタッフの今週のカウントを1増やす
                week_counts[item["担当者"]] += 1
    # --- 結果の表示 ---
# --- 追加箇所 E ---
    st.subheader("3. 完成した1ヶ月分のシフト案")
    st.dataframe(monthly_shift_df, use_container_width=True)
    # --- 追加箇所 3 ---
    st.divider()  # 区切り線
    st.subheader("欠員状況")

    if len(shortage_alerts) > 0:
        # 欠員がある場合は、赤いメッセージボックスに1行ずつ表示
        for alert in shortage_alerts:
            st.error(alert)
    else:
        # 欠員がゼロなら、お祝いのメッセージを表示
        st.success("✅ 1ヶ月間、全てのシフトに欠員はありません！完璧です。")
    