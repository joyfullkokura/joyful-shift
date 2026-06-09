import streamlit as st
import pandas as pd
import calendar
import random
import io
import time
from datetime import date, timedelta, datetime, timezone # timezoneを追加
from datetime import date, timedelta  # 
from datetime import date, timedelta, datetime
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components  # 追加
import requests
import json
import jpholiday

def get_month_holidays_list(y, m):
    """指定した年月の祝日を [(日, 名前), ...] の形式で返す"""
    # その月が何日まであるか取得
    last_day = calendar.monthrange(y, m)[1]
    start_date = date(y, m, 1)
    end_date = date(y, m, last_day)
    
    # 指定期間の祝日を取得
    h_list = jpholiday.between(start_date, end_date)
    # [(datetime.date(2026, 7, 20), '海の日'), ...] -> [(20, '海の日'), ...] に変換
    return [(h[0].day, h[1]) for h in h_list]
# 日本時間 (JST) を定義
JST = timezone(timedelta(hours=+9), 'JST')
def get_kitakyushu_events(y, m):
    """北九州市・小倉周辺の主要イベント情報を返す"""
    # 毎年恒例の大型イベント
    fixed_events = {
        1: [(10, "北九州市二十歳の記念式典（メディアドーム）")],
        2: [(15, "北九州マラソン（周辺交通規制あり）")],
        3: [(20, "小倉城桜まつり")],
        7: [(1, "北九州祇園三まつり 期間開始"), (17, "小倉祇園太鼓"), (18, "小倉祇園太鼓"), (19, "小倉祇園太鼓")],
        8: [(1, "わっしょい百万夏まつり"), (2, "わっしょい百万夏まつり")],
        10: [(15, "北九州フードフェスティバル")],
        11: [(1, "小倉城竹あかり")],
        12: [(24, "小倉イルミネーション")]
    }
    
    # 選択された年月に該当するイベントを抽出
    return fixed_events.get(m, [])
def export_cleaning_handwriting_sheet(year, period_label):
    if period_label == "1-4月": months = [1, 2, 3, 4]
    elif period_label == "5-8月": months = [5, 6, 7, 8]
    else: months = [9, 10, 11, 12]

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet(f"清掃用_{period_label}")
        
        # --- 【超重要】A4縦1枚に強制的に収める設定 ---
        worksheet.set_portrait()
        worksheet.set_paper(9) # A4
        worksheet.set_margins(0.3, 0.3, 0.3, 0.3) # 余白をさらに狭く
        worksheet.center_horizontally()
        
        # これが「1枚に収める」魔法の命令です
        worksheet.fit_to_pages(1, 1) 

        # --- 書式 ---
        fmt_title = workbook.add_format({'bold': True, 'size': 18, 'align': 'center', 'valign': 'vcenter'})
        fmt_month = workbook.add_format({'bold': True, 'size': 11, 'bg_color': '#F2F2F2', 'border': 2})
        fmt_head = workbook.add_format({'bold': True, 'bg_color': '#D9D9D9', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'size': 9})
        fmt_cell = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'size': 10})
        fmt_memo = workbook.add_format({'border': 1, 'valign': 'top', 'size': 9})

        # 1. タイトル
        worksheet.set_row(0, 30)
        worksheet.merge_range('A1:J1', f"🧹 {year}年 {period_label} モップ清掃チェック表", fmt_title)

        # 2. 画像（横幅に収まるようサイズを微調整）
        try:
            worksheet.insert_image('B2', 'cleaning_map.png', {
                'x_scale': 0.45, 
                'y_scale': 0.45,
                'x_offset': 10,
                'y_offset': 5
            })
        except: pass

        curr_row = 12 # 画像の下から開始（行間を詰める）

        # 3. 4ヶ月分のループ
        for m in months:
            worksheet.set_row(curr_row, 18)
            worksheet.merge_range(curr_row, 0, curr_row, 9, f" 【{m}月】", fmt_month)
            curr_row += 1
            
            # ヘッダー
            worksheet.set_row(curr_row, 18)
            headers = ["清掃日", "①", "②", "③", "④", "⑤", "⑥", "⑦", "担当", "補足"]
            for c, h in enumerate(headers):
                worksheet.write(curr_row, c, h, fmt_head)
            curr_row += 1

            # 日曜日
            sundays = get_sundays(year, m)
            for s in sundays:
                worksheet.set_row(curr_row, 28) # 高さを少し抑える
                worksheet.write(curr_row, 0, s.strftime("%m/%d(日)"), fmt_cell)
                for c in range(1, 8):
                    worksheet.write(curr_row, c, "", fmt_cell)
                worksheet.write(curr_row, 8, "", fmt_cell)
                worksheet.write(curr_row, 9, "", fmt_memo)
                curr_row += 1
            curr_row += 1 # 月の間の余白を1行にする

        # --- 【重要】横幅がはみ出さないように列幅をミリ単位で調整 ---
        worksheet.set_column('A:A', 11) # 日付
        worksheet.set_column('B:H', 3.2) # ①〜⑦（細く！）
        worksheet.set_column('I:I', 11) # 担当
        worksheet.set_column('J:J', 28) # 補足（ここが長すぎると2ページ目に飛ぶ）

    return buffer.getvalue()
def get_japan_today():
    return datetime.now(JST).date()
def send_line_notification(message):
    """LINE Messaging APIを使ってグループに通知を送る"""
    # ここに取得したアクセストークンを貼り付け
    LINE_ACCESS_TOKEN = "CWtJrVJ9DydSnL/meqMN5K8+9gV3j3zLWjlTFHuHbj9K7wNPgZah76+RzB77c/1ASW+IReRwpVetUSavMIitb85I7pmCp7hfJpY7931zzr6INTNzdFPBVXgnMehg5j+LN9bxO6aY1AIXM/k5cAwr0QdB04t89/1O/w1cDnyilFU="
    # ここに送信先のグループID（または自分のユーザーID）を貼り付け
    LINE_DESTINATION_ID = "U627c8971cff4e882b7f8673addc08ffa"
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    data = {
        "to": LINE_DESTINATION_ID,
        "messages": [{"type": "text", "text": message}]
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        return response.status_code == 200
    except Exception:
        return False
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
def get_sundays(year, month):
    """指定された年月のすべての日曜日の日付を取得する"""
    sundays = []
    cal = calendar.Calendar(firstweekday=calendar.MONDAY)
    for day in cal.itermonthdates(year, month):
        if day.weekday() == 6 and day.month == month: # 6は日曜日
            sundays.append(day)
    return sundays
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
# --- 30分刻みの時間リスト作成 ---
TIME_OPTIONS = [f"{h:02d}:{m:02d}" for h in range(10, 25) for m in [0, 30]]
# 24:30以降は不要なので24:00までにする
TIME_OPTIONS = TIME_OPTIONS[:-1]
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
def time_to_float(time_str):
    """'10:30' -> 10.5 への変換"""
    try:
        h, m = map(int, time_str.split(':'))
        return h + m / 60.0
    except:
        return 10.0

def float_to_time(val):
    """10.75 -> '10:45' への変換"""
    h = int(val)
    m = int((val - h) * 60)
    return f"{h:02d}:{m:02d}"

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
mode = st.sidebar.radio("機能を選択", ["確定シフト閲覧", "休み希望入力", "清掃記録", "従業員名簿管理", "シフト自動生成（案）","シフトアップロード"])
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
            # --- 従業員名簿管理モード内の最後に追加 ---
            st.markdown("---")
            with st.expander("📖 【店長用】システム取扱説明書（マニュアル）", expanded=False):
                st.markdown("""
                ### 🛠️ 運用サイクル（毎月の流れ）
                1.  **名簿の整備**: 新人が入ったら表の一番下の枠の＋ボタンを押して「名前」「グループ」「週希望」を登録。
                2.  **休み希望の募集**: スタッフに「休み希望入力」から自分の名前のボタンを押して入力してもらう。
                3.  **自動生成**: 「シフト自動生成」でベース案を作る。
                4.  **Excel微調整**: 生成した案をダウンロードし、店長のPCで細部を調整。
                5.  **確定公開**: 調整後のExcelを「シフトアップロード」から公開。ファイル名はjoyfull_shift_2026_07のような名前にする。
                
                ---

                ### 👥 1. 従業員名簿管理
                * まずパスワードを入力してください
                *   **グループの役割**: 
                    - `HD`: ホール昼 / `HN`: ホール夜 / `KD`: キッチン昼 / `KN`: キッチン夜
                    - `W`: 社員・共通
                *   **週希望**: 自動生成時に「その週に最大何日入れるか」の基準になります。この数字が上限になるので絶対に超えることはないですが少なくなることはあります。
                *   **レジ締め/デザート**: 特定のスキルが必要な時間帯に優先的に割り振られます。
                    **お知らせ機能**: お知らせの編集を開くと常に表示されるメッセージを編集することができます。休み希望の注意点などあれば入力してください。

                ### 📅 2. 休み希望入力
                *   **スタッフ用**: カレンダー形式でスマホから直感的に入力可能。
                *   **管理者モード**: 管理者パスワード入力時は、全員分を「表形式」で一括修正できます。
                *   **注意**: 複数人が同時に保存ボタンを押すと上書きされる可能性があるため、入力後の確認を推奨してください。

                ### 🤖 3. シフト自動生成
                *   **必要人数**: 平日と金土日で分けて設定可能。
                *   **生成ロジック**: 欠員が最小になるまで280回以上のシミュレーションを行います（約23秒）。
                *   **出力**: Excel形式でダウンロード。最後の列に合計実働、休憩合計、欠員情報が書いてます

                ### 📤 4. シフトアップロード（重要！）
                *   店長がExcelで編集したファイルをアップロードすると、**「10:00-18:00」といった文字を読み取って、労働時間を自動計算**します。
                *   **休憩の自動計算**: 6時間以上(0.75h)、8時間以上(1.0h)を自動で差し引きます。
                *   **端数処理**: 小数点第1位（例: 120.25h→120.3）に自動で丸めちゃいます。

                ### 💰 5. レジ締め作業
                *   **バー操作**: その日の出勤時間をスライドバーで調整。
                *   **スタッフ交代**: 名前をクリックして別の人を選ぶだけで、従業員の交代ができます。
                *   **リアルタイム集計**: レジに打ち込むための「昼合計」「夜合計」「総労働」が15分単位で算出されます。
                *   **初期表示**: 開いた瞬間に『本日のシフト』がバーに反映されます。一度保存した後は、その実績データが優先して表示されます。

                ### 🧹 6. 清掃記録
                *   パスワードを入力してください
                *   毎週日曜のモップ清掃をチェックリスト化。管理者のみ記録できます。
                *   保存すると月ごとの記録としてシートに蓄積されます。入力、エクセル出力したい月を選択して利用してください。

                ---
                **💡 トラブルかな？と思ったら**
                *   画面が動かなくなったらブラウザの「更新（リロード）」をしてください。（F5キー）
                """)
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

# --- 3. 個別入力エリア（名前ボタンが押されたら出現：カレンダー形式） ---
    if "editing_user" in st.session_state:
        user = st.session_state.editing_user
        
        # --- 強力なグリッドCSS（スマホでの縦並びを完全禁止） ---
        st.markdown("""
            <style>
            /* 1. フォーム内の全カラムを強制的に横7等分にする */
            [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: repeat(7, 1fr) !important;
                gap: 2px !important;
            }
            /* 2. Streamlit本来のレスポンシブ（縦並び）機能を無効化 */
            [data-testid="stForm"] [data-testid="column"] {
                width: auto !important;
                min-width: 0px !important;
            }
            /* 3. チェックボックスを極限までコンパクトに */
            .stCheckbox {
                margin-top: -10px !important;
                display: flex !important;
                justify-content: center !important;
            }
            /* チェックボックスの周りの余白を消す */
            .stCheckbox div[data-testid="stMarkdownContainer"] {
                display: none;
            }
            /* 4. 数字のサイズと配置 */
            .cal-num {
                text-align: center;
                font-size: 0.8rem;
                font-weight: bold;
                margin-bottom: 0px;
                line-height: 1.2;
            }
            /* 保存ボタン列は2列にする */
            .stFormSubmitButton [data-testid="stHorizontalBlock"] {
                grid-template-columns: 1fr 1fr !important;
            }
            </style>
        """, unsafe_allow_html=True)

        # 自動スクロール
        st.markdown('<div id="scroll_target"></div>', unsafe_allow_html=True)
        components.html(f"<script>window.parent.document.getElementById('scroll_target').scrollIntoView({{behavior: 'smooth', block: 'start'}});</script>", height=0)

        st.divider()
        st.subheader(f"📅 {user} さんの希望")

        # 1. データ準備
        raw_user_data = display_df.loc[user].copy()
        user_status_clean = {k: (str(v).upper().strip() in ["TRUE", "1", "1.0", "YES"]) for k, v in raw_user_data.items()}

        # 2. フォーム
        with st.form(key=f"ultra_tight_cal_{user}"):
            calendar.setfirstweekday(calendar.SUNDAY)
            cal = calendar.monthcalendar(year, month)
            weekdays_jp = ["日", "月", "火", "水", "木", "金", "土"]
            
            # --- 曜日ヘッダー ---
            h_cols = st.columns(7)
            for i, label in enumerate(weekdays_jp):
                color = "#333"
                if i == 0: color = "red"
                if i == 6: color = "blue"
                h_cols[i].markdown(f"<p style='text-align:center; color:{color}; font-size:0.7rem; font-weight:bold; margin-bottom:0;'>{label}</p>", unsafe_allow_html=True)

            new_updates = {}

            # --- カレンダー日付 ---
            for week in cal:
                cols = st.columns(7)
                for i, day in enumerate(week):
                    if day == 0:
                        cols[i].write("") # 空白
                        continue
                    
                    target_col = column_names[day-1]
                    current_val = user_status_clean.get(target_col, False)
                    num_color = "black"
                    if i == 0: num_color = "red"
                    if i == 6: num_color = "blue"

                    with cols[i]:
                        st.markdown(f"<p class='cal-num' style='color:{num_color};'>{day}</p>", unsafe_allow_html=True)
                        new_updates[target_col] = st.checkbox("", value=current_val, key=f"u_cb_{user}_{day}")

            st.write("")
            col_save, col_cancel = st.columns(2)
            with col_save:
                submit_btn = st.form_submit_button("💾 保存", use_container_width=True, type="primary")
            with col_cancel:
                cancel_btn = st.form_submit_button("✖ 閉じる", use_container_width=True)

        # 3. 保存ロジック
        if submit_btn:
            with st.spinner("保存中..."):
                latest_all_raw = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=REQ_SHEET, ttl=0)
                if latest_all_raw is not None and not latest_all_raw.empty:
                    latest_all_indexed = latest_all_raw.drop_duplicates(subset=latest_all_raw.columns[0]).set_index(latest_all_raw.columns[0])
                    latest_all_indexed.index = latest_all_indexed.index.astype(str).str.strip()
                    latest_all_indexed = latest_all_indexed.reindex(columns=column_names).fillna(False)
                    latest_all_indexed = latest_all_indexed.map(lambda x: str(x).upper().strip() in ["TRUE", "1", "1.0", "YES"])
                else:
                    latest_all_indexed = display_df.copy()

                latest_all_indexed.loc[user] = pd.Series(new_updates)

                if save_sheet_robust(latest_all_indexed, REQ_SHEET):
                    st.session_state[state_key] = latest_all_indexed 
                    del st.session_state.editing_user 
                    st.success(f"✅ 保存完了")
                    time.sleep(0.5)
                    st.rerun()

        if cancel_btn:
            del st.session_state.editing_user
            st.rerun()
elif mode == "シフト自動生成（案）":
    st.title(" シフト自動生成（案）")
    st.write("①～③の順に設定していってください")
    st.markdown("---")
    with st.expander("📖 シフト作成ガイド", expanded=False):
        st.markdown("""
                ###  ステップ 1：基本の「必要人数」を決める
                *  **🚃 平日 (月〜木)**: 通常の営業に必要な人数。
                *  **🌞 金・土・日・祝**: 週末や祝日に増員する人数。
                *POINT: ここで入力した人数分だけ、コンピュータがスタッフを必死に探します。
                
                ---

                ### ステップ 2：特別な日を追加する（＋ボタン）
                *   お盆、イベント、周辺の祭りなど、**「この日だけは基本設定と違う人数にしたい！」**という日を設定します。
                *   1.「➕ 特定日の人数を個別に設定する」の枠をクリック。
                *   2.リストから該当する日を選択。
                *   3. 出てきた入力欄に、その日だけの人数を入力します。
                
                ---

                ### ステップ 3：勤務時間を微調整する
                *   1.タブを切り替える: [平日] [金土日祝] [⭐特定日] の順に並んでいるので、それぞれ設定します。
                *   2.バーを動かす: 1人目（リーダー枠）〜N人目の時間を30分刻みで調整します。
                *   3.保存する: 「💾 デフォルトとして保存」を押すと、来月以降もこの時間が最初からセットされます。
                ---
                ### ステップ 4：シフトを生成する
                *   一番下の「シフトを生成・再生成」ボタンをポチッと押します。
                *   約10秒間、コンピュータが5パターンのシフトを作成し、その中から**「欠員が最も少なく、連勤がなくて公平な案」**を自動で1つ選び出します。
                *   画面に表示された表を見て、✖（欠員）が出ていないか確認してください。
                ---
                ### ステップ 5：Excelで仕上げ
                *   ダウンロード: 「📥 Excelを出力する」を押して、パソコンに保存します。
                *   最終調整: パソコンのExcelで開き、「新人ばかりの日」や「深夜→早朝の連続」がないか最終チェックし、手動で修正して保存します。
                *  アップロード: システムの「📤 完成版Excelをアップロード」から修正したファイルを選択し、「公開」ボタンを押します。
        """)
    if "last_generated_df" not in st.session_state:
        st.session_state.last_generated_df = None
    if "last_shortage_alerts" not in st.session_state:
        st.session_state.last_shortage_alerts = []
    # --- 0. 祝日データの取得 (修正版) ---
    current_holidays = get_month_holidays_list(year, month)
    holiday_days = [h[0] for h in current_holidays]
    
    # 来月の祝日計算
    next_month_date = (v_date + timedelta(days=32)).replace(day=1)
    next_year, next_month = next_month_date.year, next_month_date.month
    holidays = get_month_holidays_list(next_year, month)

    # --- 1. 必要人数（枠数）の設定エリア ---
    with st.expander("①基本の必要人数設定", expanded=True):
        st.write("基本の人数を設定してください。")
        col_wd, col_we = st.columns(2)
        with col_wd:
            st.markdown("### 🚃 平日 (月〜木)")
            h_d_wd = st.number_input("ホール昼", 1, 10, 2, key="h_d_wd")
            k_d_wd = st.number_input("キッチン昼", 1, 10, 2, key="k_d_wd")
            h_n_wd = st.number_input("ホール夜", 1, 10, 3, key="h_n_wd")
            k_n_wd = st.number_input("キッチン夜", 1, 10, 3, key="k_n_wd")
        with col_we:
            st.markdown("### 🌞 金・土・日・祝")
            h_d_we = st.number_input("ホール昼 ", 1, 10, 3, key="h_d_we")
            k_d_we = st.number_input("キッチン昼 ", 1, 10, 2, key="k_d_we")
            h_n_we = st.number_input("ホール夜 ", 1, 10, 4, key="h_n_we")
            k_n_we = st.number_input("キッチン夜 ", 1, 10, 4, key="k_n_we")

    # --- 1.2 特定日の追加設定 (+) ---
    with st.expander("②➕ 祝日など特定日の人数を個別に設定する"):
        st.write("イベント日など、特定の日だけ人数を増やしたい、減らしたい場合に使用します。")
        
        # 保存データの読み込み（当年月のみ）
        def load_special_configs():
            try:
                df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="config_special_days", ttl=0)
                if df is not None and not df.empty:
                    return df[(df['year'] == year) & (df['month'] == month)]
                return pd.DataFrame()
            except: return pd.DataFrame()

        special_df = load_special_configs()
        existing_days = [int(d) for d in special_df['day'].tolist()] if not special_df.empty else []
        
        # 日付選択（マルチセレクト）
        selected_special_days = st.multiselect(
            "特別設定を適用する日を選択",
            range(1, num_days + 1),
            default=existing_days,
            key="special_days_select"
        )

        special_configs = {}
        if selected_special_days:
            for d in sorted(selected_special_days):
                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([1,2,2,2,2])
                    c1.markdown(f"#### {d}日")
                    # 初期値は「金土日祝」の設定を引用
                    s_hd = c2.number_input(f"H昼", 1, 10, h_d_we, key=f"sp_hd_{d}")
                    s_kd = c3.number_input(f"K昼", 1, 10, k_d_we, key=f"sp_kd_{d}")
                    s_hn = c4.number_input(f"H夜", 1, 10, h_n_we, key=f"sp_hn_{d}")
                    s_kn = c5.number_input(f"K夜", 1, 10, k_n_we, key=f"sp_kn_{d}")
                    special_configs[d] = {"h_d": s_hd, "k_d": s_kd, "h_n": s_hn, "k_n": s_kn}

    # --- 1.5 詳細な枠時間の設定エリア（動的タブ） ---
    with st.expander("③🕒 詳細な枠時間の設定（30分刻み）"):
        st.write("各ポジションの勤務時間を設定してください。")

        # 保存されている時間の読み込み
        stored_df = load_sheet_no_cache("config_times", pd.DataFrame())
        stored_times = stored_df.to_dict('index') if not stored_df.empty else {}

        # タブの作成
        tab_titles = ["🚃 平日", "🌞 金土日祝"] + [f"⭐ {d}日" for d in sorted(selected_special_days)]
        all_tabs = st.tabs(tab_titles)
        
        all_settings_to_save = []
        slot_data_map = {}

        def render_slider_tab(label, count, key_prefix, tab_obj):
            results = []
            with tab_obj:
                cols = st.columns(2)
                for i in range(count):
                    k = f"{key_prefix}_{i}"
                    # 保存値があれば使用、なければデフォルト
                    default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else (("10:00", "18:00") if "昼" in label else ("18:00", "23:00"))
                    
                    with cols[i % 2]:
                        t = st.select_slider(f"{label} {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                        results.append(f"{t[0]}-{t[1]}")
                        all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})
            return results

        with st.form(key="time_config_form_v2"):
            # 平日
            wd_hd = render_slider_tab("ホール昼", h_d_wd, "wd_hd", all_tabs[0])
            wd_kd = render_slider_tab("キッチン昼", k_d_wd, "wd_kd", all_tabs[0])
            wd_hn = render_slider_tab("ホール夜", h_n_wd, "wd_hn", all_tabs[0])
            wd_kn = render_slider_tab("キッチン夜", k_n_wd, "wd_kn", all_tabs[0])
            slot_data_map["weekday"] = {"hd": wd_hd, "kd": wd_kd, "hn": wd_hn, "kn": wd_kn}

            # 週末/祝日
            we_hd = render_slider_tab("ホール昼", h_d_we, "we_hd", all_tabs[1])
            we_kd = render_slider_tab("キッチン昼", k_d_we, "we_kd", all_tabs[1])
            we_hn = render_slider_tab("ホール夜", h_n_we, "we_hn", all_tabs[1])
            we_kn = render_slider_tab("キッチン夜", k_n_we, "we_kn", all_tabs[1])
            slot_data_map["weekend"] = {"hd": we_hd, "kd": we_kd, "hn": we_hn, "kn": we_kn}

            # 追加の特定日
            for idx, d in enumerate(sorted(selected_special_days)):
                conf = special_configs[d]
                s_hd = render_slider_tab(f"{d}日H昼", conf["h_d"], f"sp_{d}_hd", all_tabs[idx+2])
                s_kd = render_slider_tab(f"{d}日K昼", conf["k_d"], f"sp_{d}_kd", all_tabs[idx+2])
                s_hn = render_slider_tab(f"{d}日H夜", conf["h_n"], f"sp_{d}_hn", all_tabs[idx+2])
                s_kn = render_slider_tab(f"{d}日K夜", conf["k_n"], f"sp_{d}_kn", all_tabs[idx+2])
                slot_data_map[d] = {"hd": s_hd, "kd": s_kd, "hn": s_hn, "kn": s_kn}

            st.write("")
            c1, c2 = st.columns(2)
            apply_btn = c1.form_submit_button("✅ 設定を今回の生成のみに適用", use_container_width=True)
            save_btn = c2.form_submit_button("💾 デフォルトとして保存", use_container_width=True)

            if save_btn:
                # config_times 保存
                save_sheet_robust(pd.DataFrame(all_settings_to_save).set_index("key"), "config_times")
                # config_special_days 保存
                sp_save = [{"year": year, "month": month, "day": d, **c} for d, c in special_configs.items()]
                if sp_save: save_sheet_robust(pd.DataFrame(sp_save).set_index("day"), "config_special_days")
                st.success("設定をスプレッドシートに保存しました！")

        # --- 来月の祝日表示 ---
    st.markdown(f"#### 📅 来月 ({month}月) の祝日と行事")
    if holidays:
        st.warning(" / ".join([f"**{h[0]}日**: {h[1]}" for h in holidays]))
    else:
        st.write("祝日はありません。")

        
        # 北九州のイベントを表示
    local_events = get_kitakyushu_events(next_year, next_month)
    if local_events:
        event_text = " / ".join([f"🚩 **{e[0]}日**: {e[1]}" for e in local_events])
        st.info(f"【小倉周辺イベント予定】\n\n{event_text}")
        st.caption("※これらは例年の傾向です。実際の日程は最新情報を確認してください。https://rikumalog.com/event-calendar.html")
    else:
        st.write("地域の大型イベント予定はありません。")
    

    st.markdown("---")
    gen_button = st.button("シフトを生成（約9秒）", use_container_width=True)

    # --- 2. 生成ロジック ---
    if gen_button:
        # (データの準備、off_req_countsなどは既存通り...)
        # --- 略: データのロード部分 ---
        progress_bar = st.progress(0)
        status_text = st.empty()
        NUM_TRIALS = 5
        best_overall_df, best_overall_alerts, min_total_shortage = None, [], 9999
        
# --- データの準備（ここを強化版に差し替え） ---
        req_load_raw = load_sheet_cached(REQ_SHEET)
        if req_load_raw is None or req_load_raw.empty:
            req_load = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)
        else:
            # 1. 1列目をインデックスにし、名前の空白を徹底的に消す
            req_load_raw = req_load_raw.drop_duplicates(subset=req_load_raw.columns[0])
            req_load_raw = req_load_raw.set_index(req_load_raw.columns[0])
            req_load_raw.index = req_load_raw.index.astype(str).str.strip()
            
            # 2. ALL_NAMESも掃除して再インデックス（これで名前が一致する）
            clean_names = [str(n).strip() for n in ALL_NAMES]
            req_load = req_load_raw.reindex(index=clean_names).fillna(False)
            
            # 3. True/Falseの判定
            req_load = req_load.map(lambda x: str(x).upper().strip() in ["TRUE", "1", "1.0", "TRUE.0", "YES"])
        off_req_counts = req_load.sum(axis=1).to_dict()
        num_weeks = num_days / 7.0
        staff_goals = {row["名前"]: max(1, int(row["週希望"] * num_weeks * 0.7)) for _, row in master_df.iterrows()}

        for trial_idx in range(NUM_TRIALS):
            status_text.text(f"シフト案 {trial_idx + 1} を計算中...")
            trial_df = pd.DataFrame("", index=ALL_NAMES, columns=column_names)
            trial_shortage_count, trial_alerts = 0, []
            cumulative_counts, consecutive_days = {n: 0 for n in ALL_NAMES}, {n: 0 for n in ALL_NAMES}

            for name in ALL_NAMES:
                for col in column_names:
                    if req_load.at[name, col]: trial_df.at[name, col] = "✖"

            for day_idx, col in enumerate(column_names):
                assigned_today = []
                d = day_idx + 1
                d_idx = calendar.weekday(year, month, d)
                
                # --- 動的なスロット決定ロジック ---
                if d in selected_special_days:
                    target_slots = slot_data_map[d]
                elif d_idx >= 4 or d in holiday_days: # 金土日 or 祝日
                    target_slots = slot_data_map["weekend"]
                else:
                    target_slots = slot_data_map["weekday"]

                # (スコア計算と割り当てロジックは既存通り...)
                # scoresの計算、get_priority_poolの定義
                scores = {}
                for name in ALL_NAMES:
                    goal = staff_goals.get(name, 10)
                    progress_ratio = cumulative_counts[name] / goal
                    unmet_score = (1.0 - progress_ratio) * 100
                    rarity_score = off_req_counts.get(name, 0) * 3
                    cons = consecutive_days[name]
                    penalty = 10 if cons==1 else 30 if cons==2 else 60 if cons==3 else 150 if cons>=4 else 0
                    scores[name] = unmet_score + rarity_score - penalty + random.uniform(0, 10)

                def get_priority_pool(group_name, filter_skill=None):
                    pool = []
                    for _, row in master_df.iterrows():
                        name = row["名前"]
                        if req_load.at[name, col] or name in assigned_today: continue
                        if row["グループ"] == group_name or row["グループ"] == "W":
                            if filter_skill and not row[filter_skill]: continue
                            pool.append({"名前": name, "スコア": scores[name]})
                    pool.sort(key=lambda x: x["スコア"], reverse=True)
                    return [p["名前"] for p in pool]

                # 割り当て
                for g_code, p_name, key in [("HD","H昼","hd"),("KD","K昼","kd"),("HN","H夜","hn"),("KN","K夜","kn")]:
                    skill = "デザート" if g_code=="HD" else "レジ締め" if g_code=="HN" else None
                    for i, slot_time in enumerate(target_slots[key]):
                        pool = get_priority_pool(g_code, skill if i==0 else None)
                        if pool:
                            picked = pool[0]
                            trial_df.at[picked, col] = slot_time
                            assigned_today.append(picked)
                            cumulative_counts[picked] += 1
                            consecutive_days[picked] += 1
                        else:
                            trial_shortage_count += 1
                            trial_alerts.append(f"{d}日:{p_name}欠員")

                for name in ALL_NAMES:
                    if name not in assigned_today: consecutive_days[name] = 0
            
            if trial_shortage_count < min_total_shortage:
                min_total_shortage = trial_shortage_count
                best_overall_df, best_overall_alerts = trial_df, trial_alerts
            progress_bar.progress((trial_idx + 1) / NUM_TRIALS)

        st.session_state.last_generated_df = best_overall_df
        st.session_state.last_shortage_alerts = best_overall_alerts
        status_text.empty(); progress_bar.empty()

    # --- 3. 結果の表示（色分け対応） ---
    if st.session_state.last_generated_df is not None:
        def style_shift(val, col):
            try:
                d = int(col.split('(')[0])
                d_idx = calendar.weekday(year, month, d)
                is_holiday = d in holiday_days
                if is_holiday or d_idx == 6: return "background-color: #ffe6e6" # 祝日・日
                if d_idx == 5: return "background-color: #e6f3ff" # 土
            except: pass
            if val == "✖": return
            return ""

        st.dataframe(
            st.session_state.last_generated_df.style.apply(lambda r: [style_shift(v, c) for v, c in zip(r, r.index)], axis=1),
            use_container_width=True
        )

        # Excel出力部分（祝日の赤字対応）
        # ... (既存のExcelWriter処理の中で、祝日判定をして fmt_sun を適用するロジックを追加)
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

if mode == "確定シフト閲覧":
    st.title("確定シフト閲覧")

    # --- 0. CSS設定 ---
    st.markdown("""
        <style>
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .tweet-bubble {
            display: inline-block;
            background-color: #FFF176;
            color: #333;
            padding: 4px 12px;
            border-radius: 18px;
            font-size: 0.85rem;
            margin-left: 8px;
            position: relative;
            box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
            animation: fadeInUp 0.5s ease-out;
            border: 1px solid #FDD835;
        }
        .tweet-bubble::after {
            content: '';
            position: absolute; left: -8px; top: 50%; margin-top: -5px;
            border-top: 5px solid transparent; border-right: 8px solid #FFF176; border-bottom: 5px solid transparent;
        }
        .worker-row { display: flex; align-items: center; margin-bottom: 8px; min-height: 35px; }
        </style>
    """, unsafe_allow_html=True)

    # --- 1. データの準備（つぶやき専用読み込み） ---
    today = get_japan_today()
    t_day = today.day
    date_str_today = today.strftime("%Y/%m/%d")
    tweet_sheet = "daily_tweets"
    
    # 【重要】load_sheet_no_cacheを使わず、直接読み込む（重複削除を回避）
    if "tweet_data_cache" not in st.session_state:
        with st.spinner("つぶやきを読み込み中..."):
            try:
                # 重複削除機能のない生の読み込み
                raw_tweets = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=tweet_sheet, ttl=0)
                if raw_tweets is None or raw_tweets.empty:
                    df_t = pd.DataFrame(columns=["日付", "名前", "メッセージ"])
                else:
                    # 余計な index 列などが混じっていたら削除
                    df_t = raw_tweets.loc[:, ~raw_tweets.columns.str.contains('^Unnamed|^index')]
                st.session_state.tweet_data_cache = df_t
            except:
                st.session_state.tweet_data_cache = pd.DataFrame(columns=["日付", "名前", "メッセージ"])

    # 今日のつぶやきを抽出
    current_all_tweets = st.session_state.tweet_data_cache
    today_tweet_dict = {}
    if not current_all_tweets.empty:
        # 日付の一致を判定（文字列として比較）
        current_all_tweets["日付"] = current_all_tweets["日付"].astype(str)
        # 「2026/06/01」でも「2026-06-01」でも一致するように掃除
        today_mask = current_all_tweets["日付"].str.contains(date_str_today.replace("/", ".")) | \
                     current_all_tweets["日付"].str.contains(date_str_today)
        
        today_only = current_all_tweets[today_mask]
        today_tweet_dict = dict(zip(today_only["名前"].astype(str).str.strip(), today_only["メッセージ"]))

    # --- 2. シフト表の表示 ---
    t_day, t_month, t_year = today.day, today.month, today.year
    day_prefix = f"{t_day}(" 
    today_sheet = f"shift_{t_year}_{t_month:02}"
    today_df = load_sheet_cached(today_sheet)
    if today_df is not None:
        today_df = today_df.set_index(today_df.columns[0])
    else:
        today_df = pd.DataFrame()

    with st.expander(f"🏃 本日 {t_month}月{t_day}日の出勤メンバー", expanded=True):
        if today_df.empty:
            st.write("本日のシフトは未登録です。")
        else:
            target_col = next((c for c in today_df.columns if str(c).strip().startswith(day_prefix) or str(c).strip() == str(t_day)), None)
            
            if target_col is None:
                st.write("今日の日付列が見当たりません。")
            else:
                workers = today_df[ (today_df[target_col].notna()) & (today_df[target_col].astype(str).str.strip() != "✖") ].copy()
                if workers.empty:
                    st.write("本日の出勤予定者はいません。")
                else:
                    group_col = "グループ" if "グループ" in today_df.columns else today_df.columns[0]
                    workers['gp_clean'] = workers[group_col].astype(str).str.strip()
                    
                    def draw_member(name, time_val, i_key):
                        name_s = str(name).strip()
                        tweet_html = ""
                        if name_s in today_tweet_dict:
                            tweet_html = f'<span class="tweet-bubble">{today_tweet_dict[name_s]}</span>'
                        
                        c_name, c_pop = st.columns([0.88, 0.12])
                        with c_name:
                            st.markdown(f'<div class="worker-row"><strong>{time_val}</strong> : {name_s} {tweet_html}</div>', unsafe_allow_html=True)
                        with c_pop:
                            with st.popover("💬"):
                                msg_input = st.text_input(f"ひとこと(20字)", max_chars=20, key=f"t_{i_key}")
                                if st.button("送信", key=f"b_{i_key}"):
                                    # 保存用データ作成
                                    new_data = pd.DataFrame([{"日付": date_str_today, "名前": name_s, "メッセージ": msg_input}])
                                    # 同じ人の今日の投稿があれば消して合体
                                    old_data = st.session_state.tweet_data_cache
                                    filtered_old = old_data[~((old_data["日付"].astype(str).str.contains(date_str_today)) & (old_data["名前"].astype(str).str.strip() == name_s))]
                                    updated_df = pd.concat([filtered_old, new_data], ignore_index=True)
                                    
                                    # 保存（インデックスを名前ではなく「通し番号」にするため reset_index）
                                    if save_sheet_robust(updated_df.set_index(updated_df.columns[0]), tweet_sheet):
                                        st.session_state.tweet_data_cache = updated_df
                                        st.rerun()

                    col_h, col_k = st.columns(2)
                    with col_h:
                        st.markdown("### 👔 ホール")
                        h_list = workers[workers['gp_clean'].str.contains('H|W|不明', na=False)].sort_values(by=target_col)
                        for i, (n, r) in enumerate(h_list.iterrows()): draw_member(n, r[target_col], f"h_{i}")
                    with col_k:
                        st.markdown("### 🍳 キッチン")
                        k_list = workers[workers['gp_clean'].str.contains('K', na=False)].sort_values(by=target_col)
                        for i, (n, r) in enumerate(k_list.iterrows()): draw_member(n, r[target_col], f"k_{i}")

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
if mode == "清掃記録":
    st.title("🧹 モップ清掃記録")

    # --- パスワードチェック ---
    if pw != "1234":
        st.warning("管理者用メニューです。パスワードを入力してください。")
        # スタッフ向けの案内図だけ表示
        try:
            st.image("cleaning_map.png", caption="清掃区画マップ（①〜⑦）", use_container_width=True)
        except:
            st.info("清掃マップ画像（cleaning_map.png）を準備してください。")
            
        with st.container(border=True):
            st.markdown("""
            ### 🧼 モップ清掃の手順
            毎週日曜日の21時以降に実施します。
            1. 掲示されているマップの番号に沿って清掃。
            2. 終わったら備え付けの紙マップを塗りつぶす。
            3. 店長がこのシステムに最終記録を行います。
            """)
    else:
        # --- 管理者モード ---
        # 1. 年月の選択
        col_y, col_m = st.columns(2)
        c_today = date.today()
        year_list_clean = [c_today.year - 1, c_today.year, c_today.year + 1]
        c_year = col_y.selectbox("記録年", year_list_clean, index=1)
        c_month = col_m.selectbox("記録月", range(1, 13), index=c_today.month - 1)
        
        log_sheet_name = f"cleaning_log_v2_{c_year}_{c_month:02}"
        log_state_key = f"clean_data_v2_{c_year}_{c_month}"

        # マップ画像を大きく表示
        try:
            st.image("cleaning_map.png", caption="清掃区画マップ（①〜⑦）", width=700)
        except:
            st.error("画像ファイル 'cleaning_map.png' が見つかりません。")

        # 2. データの読み込み
        if log_state_key not in st.session_state:
            with st.spinner("データを読み込み中..."):
                # 既存シートの確認
                raw_gc = None
                if hasattr(conn, "_client"): raw_gc = conn._client
                elif hasattr(conn, "client") and hasattr(conn.client, "_client"): raw_gc = conn.client._client
                elif hasattr(conn, "client"): raw_gc = conn.client

                r_raw = None
                if raw_gc:
                    sh = raw_gc.open_by_url(SPREADSHEET_URL)
                    worksheet_list = [w.title for w in sh.worksheets()]
                    if log_sheet_name in worksheet_list:
                        r_raw = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=log_sheet_name, ttl=0)

                sundays = get_sundays(c_year, c_month)
                day_labels = [s.strftime("%m/%d") for s in sundays]

                # 区画の定義 ①〜⑦
                areas = [f"{i}区画" for i in range(1, 8)]

                if r_raw is None or r_raw.empty:
                    data = {"日付": day_labels}
                    for a in areas: data[a] = [False] * len(sundays)
                    data["担当者/一言メモ"] = [""] * len(sundays)
                    df = pd.DataFrame(data).set_index("日付")
                else:
                    df = r_raw.set_index(r_raw.columns[0])
                    df = df.reindex(index=day_labels)
                    for a in areas:
                        if a in df.columns:
                            df[a] = df[a].map(lambda x: str(x).upper().strip() in ["TRUE", "1", "1.0"])
                        else:
                            df[a] = False
                    if "担当者/一言メモ" not in df.columns: df["担当者/一言メモ"] = ""

                st.session_state[log_state_key] = df

        display_log_df = st.session_state[log_state_key]

        # 3. 入力フォーム（エディタ）
        st.subheader("📝 清掃実施チェック")
        with st.form(key=f"clean_form_v2_{log_sheet_name}"):
            # ①〜⑦の列設定を一気に作る
            column_config = {f"{i}区画": st.column_config.CheckboxColumn(f"{i}", width="small") for i in range(1, 8)}
            column_config["担当者/一言メモ"] = st.column_config.TextColumn("一言メモ", width="medium")

            edited_log = st.data_editor(
                display_log_df,
                column_config=column_config,
                use_container_width=True,
                key=f"editor_v2_{log_sheet_name}"
            )

            if st.form_submit_button("💾 記録を保存する", use_container_width=True):
                if save_sheet_robust(edited_log, log_sheet_name):
                    st.session_state[log_state_key] = edited_log
                    st.success("✅ スプレッドシートに保存しました！")
                    time.sleep(1)
                    st.rerun()

        # 4. Excel出力（画像埋め込み機能付き）
        st.markdown("---")
        st.subheader("📊 印刷用Excel出力")
        
        if st.button(f"📥 {c_month}月の清掃報告書を作成"):
            export_df = edited_log.copy()
            for i in range(1, 8):
                col = f"{i}区画"
                export_df[col] = export_df[col].map({True: "済", False: "ー"})

            buffer_clean = io.BytesIO()
            with pd.ExcelWriter(buffer_clean, engine='xlsxwriter') as writer:
                # 1. 開始行を下げる
                export_df.to_excel(writer, sheet_name='清掃報告書', startrow=5, startcol=0)
                workbook  = writer.book
                worksheet = writer.sheets['清掃報告書']
                
                # A4縦・中央配置
                worksheet.set_portrait()
                worksheet.center_horizontally()
                worksheet.set_margins(0.5, 0.5, 0.5, 0.5)

                # 書式
                fmt_title = workbook.add_format({'bold': True, 'size': 22, 'align': 'center', 'valign': 'vcenter'})
                fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D9D9D9', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'size': 12})
                fmt_data = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'size': 14})
                fmt_done = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'size': 14, 'font_color': '#FF0000', 'bold': True})
                fmt_stamp = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'top', 'size': 11})

                # タイトル（1行目を高くしてドーンと出す）
                worksheet.set_row(1, 45)
                worksheet.merge_range('A2:I2', f"ジョイフル小倉店 {c_year}年{c_month}月 モップ清掃報告書", fmt_title)

                # 列幅を広げる
                worksheet.set_column('A:A', 15) # 日付
                worksheet.set_column('B:H', 7)  # ①〜⑦
                worksheet.set_column('I:I', 40) # メモ

                # ヘッダーと行の高さを大きく
                worksheet.set_row(5, 30)
                headers = ["日付", "①", "②", "③", "④", "⑤", "⑥", "⑦", "一言メモ"]
                for c_idx, val in enumerate(headers):
                    worksheet.write(5, c_idx, val, fmt_header)

                for r_idx, (date_label, row) in enumerate(export_df.iterrows()):
                    worksheet.set_row(6 + r_idx, 45) # データの行をかなり高く
                    worksheet.write(6 + r_idx, 0, date_label, fmt_data)
                    for c_idx in range(1, 8):
                        val = row[f"{c_idx}区画"]
                        fmt = fmt_done if val == "済" else fmt_data
                        worksheet.write(6 + r_idx, c_idx, val, fmt)
                    worksheet.write(6 + r_idx, 8, row["担当者/一言メモ"], fmt_data)

                # 判子欄（表の右下に大きく）
                worksheet.write('I12', '店長確認印', fmt_stamp)
                worksheet.merge_range('I13:I15', '', fmt_stamp)

                # 画像を巨大化して、下の余白を完全に埋める
                try:
                    worksheet.insert_image('A12', 'cleaning_map.png', {
                        'x_scale': 0.85, # 85%まで拡大
                        'y_scale': 0.85,
                        'x_offset': 10,
                        'y_offset': 10
                    })
                except: pass

            st.download_button(
                label="📥 印刷用Excelをダウンロード",
                data=buffer_clean.getvalue(),
                file_name=f"Cleaning_Report_{c_year}_{c_month:02}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# mode == "清掃記録" の管理者用エリア（pw == "1234" の中）の最後に追加
    if pw == "1234":
        st.markdown("---")
        st.subheader("🖨️ 掲示用ワークシート(4ヶ月分)の作成")
        st.write("A4縦1枚に4ヶ月分のチェック欄とマップをまとめます。")
        
        c_today = date.today()
        # 年と期間の選択
        col_y_clean, col_p_clean = st.columns(2)
        target_y_clean = col_y_clean.selectbox("作成年", [c_today.year, c_today.year + 1], key="y_clean_v3")
        target_p_clean = col_p_clean.selectbox("期間を選択", ["1-4月", "5-8月", "9-12月"], key="p_clean_v3")

        if st.button("📄 4ヶ月分一括シート(Excel)を生成"):
            with st.spinner("Excelを作成中..."):
                try:
                    clean_template = export_cleaning_handwriting_sheet(target_y_clean, target_p_clean)
                    st.download_button(
                        label=f"📥 {target_y_clean}年 {target_p_clean}のシートを保存",
                        data=clean_template,
                        file_name=f"Cleaning_Worksheet_{target_y_clean}_{target_p_clean}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    st.success("作成しました！")
                except Exception as e:
                    st.error(f"作成エラーが発生しました: {e}")
if mode == "レジ締め作業":
    st.title("💰 レジ締め作業")

    # --- 0. カラー設定のCSS注入 ---
    st.markdown("""
        <style>
        /* フロント用のスライダー（オレンジ） */
        .front-box { border-left: 10px solid #FF8C00; padding-left: 15px; margin-bottom: 20px; }
        /* キッチン用のスライダー（グリーン） */
        .kitchen-box { border-left: 10px solid #28A745; padding-left: 15px; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

    # 1. 準備
    today_now = get_japan_today()
    date_str = today_now.strftime("%Y/%m/%d")
    shift_sheet = f"shift_{today_now.year}_{today_now.month:02}"
    layout_sheet = "daily_layout"
    
    def f_to_t(val):
        h = int(val)
        m = int((val - h) * 60)
        return f"{h:02d}:{m:02d}"

    def get_break_time(total_h):
        if total_h >= 8.0: return 1.0
        elif total_h >= 6.0: return 0.75
        return 0.0

    # --- 2. データの初期化 ---
    if "daily_layout_list" not in st.session_state:
        with st.spinner("データを準備中..."):
            initial_list = []
            existing_data = load_sheet_no_cache(layout_sheet, pd.DataFrame())
            
            day_exists = False
            if not existing_data.empty and "日付" in existing_data.columns:
                existing_day = existing_data[existing_data["日付"] == date_str]
                if not existing_day.empty:
                    day_exists = True
                    for _, row in existing_day.iterrows():
                        initial_list.append({
                            "名前": row["名前"],
                            "部署": row.get("部署", "不明"),
                            "役割": row["役割"],
                            "時間": (time_to_float(str(row["入店"])), time_to_float(str(row["退勤"])))
                        })

            if not day_exists:
                confirmed = load_confirmed_shift(shift_sheet)
                t_day_col = f"{today_now.day}({WEEKDAYS_JP[today_now.weekday()]})"
                if not confirmed.empty and t_day_col in confirmed.columns:
                    today_workers = confirmed[confirmed[t_day_col].astype(str).str.contains("-")]
                    for name, row in today_workers.iterrows():
                        try:
                            s_str, e_str = str(row[t_day_col]).split("-")
                            match = master_df[master_df['名前'] == name]
                            gp = match['グループ'].values[0] if not match.empty else "不明"
                            role_init = "キッチン" if "K" in str(gp) else "フロント"
                            initial_list.append({
                                "名前": name, "部署": gp, "役割": role_init,
                                "時間": (time_to_float(s_str), time_to_float(e_str))
                            })
                        except: continue
            st.session_state.daily_layout_list = initial_list

    if "daily_calc_results" not in st.session_state:
        st.session_state.daily_calc_results = None

    # --- 3. スタッフの追加機能 ---
    st.subheader("👥 スタッフの追加")
    c_add1, c_add2 = st.columns([3, 1])
    with c_add1:
        new_worker = st.selectbox("新しく追加するスタッフ", ["(選択してください)"] + ALL_NAMES, label_visibility="collapsed")
    with c_add2:
        if st.button("➕ 追加", use_container_width=True) and new_worker != "(選択してください)":
            match = master_df[master_df['名前'] == new_worker]
            gp = match['グループ'].values[0] if not match.empty else "不明"
            st.session_state.daily_layout_list.append({
                "名前": new_worker, "部署": gp, "役割": "フロント", "時間": (10.0, 14.0)
            })
            st.rerun()

    # --- 4. メイン入力フォーム ---
    st.markdown("---")
    st.info("💡 名前の変更や時間の微調整が可能です。最後に「保存ボタン」で確定してください。")
    
    with st.form(key="daily_layout_form_v4"):
        temp_updated_list = []
        
        for i, item in enumerate(st.session_state.daily_layout_list):
            name = item["名前"]
            gp = item["部署"]
            role = item["役割"]
            start, end = item["時間"]
            
            # 色分け用のコンテナ
            color_class = "front-box" if role == "フロント" else "kitchen-box"
            
            st.markdown(f'<div class="{color_class}">', unsafe_allow_html=True)
            
            row_col1, row_col2, row_col3, row_col4 = st.columns([2.5, 2, 5, 1])
            
            with row_col1:
                # 【名前を選択可能に】ドロップダウンにして、変更しても時間は維持される
                try:
                    name_idx = ALL_NAMES.index(name) + 1
                except:
                    name_idx = 0
                updated_name = st.selectbox(f"名前_{i}", ["(選択なし)"] + ALL_NAMES, index=name_idx, key=f"name_sel_{i}", label_visibility="collapsed")
                
                # 休憩表示
                total_h = end - start
                brk_h = get_break_time(total_h)
                calc_text = f"({total_h:g} - {brk_h:g})" if brk_h > 0 else f"({total_h:g})"
                st.caption(f"{calc_text} ➔ 実働:{total_h - brk_h:g}h")
            
            with row_col2:
                # 役割の選択（W以外でも変更可能にして柔軟性をアップ）
                updated_role = st.selectbox(f"役割_{i}", ["フロント", "キッチン"], 
                                    index=0 if role == "フロント" else 1, key=f"role_{i}")
            
            with row_col3:
                new_range = st.slider(f"sl_{i}", 10.0, 24.0, (float(start), float(end)), 
                                    step=0.25, key=f"slider_{i}", label_visibility="collapsed")
                st.caption(f"🕙 {f_to_t(new_range[0])} 〜 {f_to_t(new_range[1])}")
            
            with row_col4:
                to_delete = st.checkbox("削", key=f"del_check_{i}")
            
            st.markdown('</div>', unsafe_allow_html=True)

            temp_updated_list.append({
                "名前": updated_name, "部署": gp, "役割": updated_role, "時間": new_range, "削除": to_delete
            })

        submit_btn = st.form_submit_button("📊 修正を反映して集計・保存する", use_container_width=True)

        if submit_btn:
            final_list = [it for it in temp_updated_list if not it["削除"] and it["名前"] != "(選択なし)"]
            st.session_state.daily_layout_list = final_list
            
            day_total_net, lunch_f_net, lunch_k_net, night_f_net, night_k_net = 0.0, 0.0, 0.0, 0.0, 0.0
            hourly_f_count = {h: 0.0 for h in range(10, 24)}
            hourly_k_count = {h: 0.0 for h in range(10, 24)}

            save_rows = []
            for item in final_list:
                s, e = item["時間"]
                total_work = e - s
                brk = get_break_time(total_work)
                net_work = total_work - brk
                day_total_net += net_work
                
                # A. 人数表計算
                ts = s
                while ts < e:
                    h_idx = int(ts)
                    if h_idx in hourly_f_count:
                        if item["役割"] == "フロント": hourly_f_count[h_idx] += 0.25
                        else: hourly_k_count[h_idx] += 0.25
                    ts += 0.25

                # B. 実働内訳計算（後ろから休憩を引く）
                rem_brk = brk
                ts = s
                while ts < e:
                    increment = 0.0 if (e - ts) <= rem_brk else 0.25
                    if increment > 0:
                        if 10.0 <= ts < 15.0:
                            if item["役割"] == "フロント": lunch_f_net += 0.25
                            else: lunch_k_net += 0.25
                        elif 15.0 <= ts < 24.0:
                            if item["役割"] == "フロント": night_f_net += 0.25
                            else: night_k_net += 0.25
                    ts += 0.25

                save_rows.append({
                    "日付": date_str, "名前": item["名前"], "役割": item["役割"], 
                    "入店": f_to_t(s), "退勤": f_to_t(e), "実働": round(net_work, 2), "休憩時間": brk
                })

            st.session_state.daily_calc_results = {
                "day_total": day_total_net,
                "lunch_total": lunch_f_net + lunch_k_net,
                "night_total": night_f_net + night_k_net,
                "lunch_f": lunch_f_net, "lunch_k": lunch_k_net,
                "night_f": night_f_net, "night_k": night_k_net,
                "hourly_f": hourly_f_count, "hourly_k": hourly_k_count
            }

            all_data = load_sheet_no_cache(layout_sheet, pd.DataFrame())
            new_day_df = pd.DataFrame(save_rows)
            if not all_data.empty and "日付" in all_data.columns:
                others = all_data[all_data["日付"] != date_str]
                final_save_df = pd.concat([others, new_day_df], ignore_index=True)
            else:
                final_save_df = new_day_df
            
            save_sheet_robust(final_save_df, layout_sheet)
            st.success(f"{date_str} の実績を保存しました！")
            st.rerun()

    # --- 5. 集計結果の表示 ---
    if st.session_state.daily_calc_results:
        res = st.session_state.daily_calc_results
        st.markdown("---")
        st.metric("📊 本日の総実働時間（休憩引き後）", f"{res['day_total']:.2f} h")
        
        c_sum1, c_sum2 = st.columns(2)
        with c_sum1: st.metric("☀️ 昼の実働合計", f"{res['lunch_total']:.2f} h")
        with c_sum2: st.metric("🌙 夜の実働合計", f"{res['night_total']:.2f} h")
        
        st.write("**👥 1時間ごとの配置人数**")
        st.write("（※休憩時間は差し引かれていません…ちょっとムズイ！！）")
        df_h = pd.DataFrame([res['hourly_f'], res['hourly_k']], index=["フロント", "キッチン"])
        df_h.columns = [f"{h}時" for h in range(10, 24)]
        st.table(df_h.style.format("{:.1f}"))

        with st.expander("詳細な内訳", expanded=True):
            d1, d2 = st.columns(2)
            with d1:
                st.write("**☀️ 昼の内訳**")
                st.write(f"フロント: {res['lunch_f']:.2f} h / キッチン: {res['lunch_k']:.2f} h")
            with d2:
                st.write("**🌙 夜の内訳**")
                st.write(f"フロント: {res['night_f']:.2f} h / キッチン: {res['night_k']:.2f} h")

if mode == "シフトアップロード":
    if pw != "1234":
        st.warning("パスワードを入力してください")
    if pw == "1234":
        st.divider()
        st.subheader("📤 完成版Excelをアップロードして公開")
        st.write("店長がExcelで微調整したファイルをアップロードして、確定シフトとして公開します。")

        # --- 1. アップロード先の年月を選択 ---
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            # 現在の年を中心に、前年・今年・来年を選択肢にする
            up_target_year = st.selectbox("アップロード先の年", [year - 1, year, year + 1], index=1, key="up_y")
        with col_up2:
            # 1〜12月を選択肢にし、デフォルトを現在の処理月に合わせる
            up_target_month = st.selectbox("アップロード先の月", range(1, 13), index=month - 1, key="up_m")

        up_file = st.file_uploader("Excelファイルを選択してください", type="xlsx")
        
        if up_file:
            # 1. Excelを読み込む
            f_df = pd.read_excel(up_file, sheet_name=0)
            st.write(f"📂 {up_target_year}年{up_target_month}月分として読み込み中... プレビュー:")
            st.dataframe(f_df.head(3))
            
            if st.button(f"{up_target_year}年{up_target_month}月の確定シフトを公開する"):
                with st.spinner("労働時間を計算してスプレッドシートを更新中..."):
                    # 日付列（カッコが含まれる列）を特定
                    date_cols = [c for c in f_df.columns if "(" in str(c) and ")" in str(c)]
                    
                    nets, brks = [], []
                    for _, row in f_df.iterrows():
                        row_net, row_brk = 0.0, 0.0
                        for c in date_cols:
                            n, b = calc_work_and_break(row[c])
                            row_net += n
                            row_brk += b
                        # 小数点第1位に丸める
                        nets.append(round(row_net, 1))
                        brks.append(round(row_brk, 1))
                    
                    f_df["合計実働"] = nets
                    f_df["休憩合計"] = brks                    
                    # 1列目（通常は名前）をインデックスに設定
                    f_df = f_df.set_index(f_df.columns[0])
                    
                    # 2. スプレッドシートへ保存（選択した年月を使用）
                    target_sheet = f"shift_{up_target_year}_{up_target_month:02}"
                    
                    if save_sheet_robust(f_df, target_sheet):
                        st.cache_data.clear()
                        
                        # --- 3. LINE通知を実行（選択した年月を使用） ---
                        line_msg = (
                            f"📢 ジョイフル小倉店 シフト公開のお知らせ\n\n"
                            f"{up_target_year}年{up_target_month}月の確定シフトが公開（更新）されました！\n"
                            f"各自で確認をお願いします！✨\n"
                            f"https://joyful-shift-jf9lwlpz2kpjovgwspgkcq.streamlit.app/"
                        )
                        
                        if send_line_notification(line_msg):
                            st.success(f"✅ {target_sheet} を更新し、LINEで通知しました！")
                        else:
                            st.warning(f"⚠️ {target_sheet} は更新されましたが、LINE通知に失敗しました。")
                        
                        time.sleep(1)
                        st.rerun()
st.sidebar.image("cafe_logo.png", width=200)