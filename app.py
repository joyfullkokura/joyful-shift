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
def save_config_data(df, worksheet_name="config"):
    """設定シート専用の保存関数（store_idチェックなし）"""
    return save_sheet_robust(df, worksheet_name, target_url=SPREADSHEET_URL)
def calc_work_and_break_for_pair(val1, val2):
    """2つの時間枠（前半・後半）を合算して正しい休憩を計算する"""
    net1, brk1 = calc_work_and_break(val1)
    net2, brk2 = calc_work_and_break(val2)
    
    # 総勤務時間（休憩込み）
    total_hours = (net1 + brk1) + (net2 + brk2)
    
    if total_hours == 0:
        return net1, brk1, net2, brk2
    
    # 合計勤務時間から正しい休憩を決定
    if total_hours > 8.0:
        correct_total_break = 1.0
    elif total_hours > 6.0:
        correct_total_break = 0.75
    else:
        correct_total_break = 0.0
    
    # 既存の休憩と差がある場合のみ再計算
    old_break = brk1 + brk2
    if correct_total_break != old_break:
        work1 = net1 + brk1
        work2 = net2 + brk2
        
        if total_hours > 0:
            ratio1 = work1 / total_hours
            brk1 = round(correct_total_break * ratio1, 2)
            brk2 = round(correct_total_break - brk1, 2)
            net1 = round(work1 - brk1, 1)
            net2 = round(work2 - brk2, 1)
    
    return net1, brk1, net2, brk2
# セッションステートの初期化を一元管理
def init_session_state():
    """セッションステートの初期化を一括で行う"""
    defaults = {
        'view_date': (date.today() + timedelta(days=32)).replace(day=1),
        'is_global_admin': False,
        'last_generated_df': None,
        'last_shortage_alerts': [],
        'editing_user': None,
        'daily_layout_list': None,
        'daily_calc_results': None,
        'tweet_data_cache': None,
        'data_loaded_flags': {}  # 各データの読み込み状態を管理
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

# アプリ起動時に一度だけ実行
init_session_state()

# データ読み込み関数の改善
@st.cache_data(ttl=300)  # 5分間キャッシュ
def load_shift_data_cached(spreadsheet_url, sheet_name):
    """シフトデータをキャッシュ付きで読み込む"""
    try:
        conn_temp = st.connection("gsheets", type=GSheetsConnection)
        df = conn_temp.read(spreadsheet=spreadsheet_url, worksheet=sheet_name, ttl=0)
        return df
    except:
        return None
def display_month_events(year, month):
    """当月のイベント情報を整理して表示"""
    holidays = get_month_holidays_list(year, month)
    local_events = get_kitakyushu_events(year, month)
    
    # 全日程を日付順に統合
    all_events = {}
    
    # 祝日
    for day, name in holidays:
        if day not in all_events:
            all_events[day] = []
        all_events[day].append(("祝", name))
    
    # 地域イベント
    for day, name in local_events:
        if day not in all_events:
            all_events[day] = []
        all_events[day].append(("🚩", name))
    
    # 日付順に表示
    with st.container(border=True):
        st.markdown(f"### 📅 {month}月の特別日")
        
        if not all_events:
            st.write("特別な日はありません")
        else:
            for day in sorted(all_events.keys()):
                events = all_events[day]
                event_text = " / ".join([f"{icon} {name}" for icon, name in events])
                # 曜日も表示
                w_idx = calendar.weekday(year, month, day)
                w_name = WEEKDAYS_JP[w_idx]
                st.markdown(f"**{day}日({w_name})**: {event_text}")
    
    return all_events
@st.cache_data(ttl=600)
def get_all_stores_cached():
    master_conn = st.connection("gsheets", type=GSheetsConnection)
    df = master_conn.read(spreadsheet=MASTER_DATABASE_URL, worksheet="stores", ttl=0)
    # --- 修正点：空行を削除 ---
    df = df.dropna(how='all') # 全て空の行を削除
    df = df[df['store_id'].notna()] # store_id が空の行も削除
    df.columns = df.columns.str.strip()
    return df
def get_split_shift(slot_time_str, store_info):
    """アイドルタイムを考慮してシフトを前後2つに分ける"""
    if not slot_time_str or "-" not in slot_time_str:
        return slot_time_str, ""
    
    start_str, end_str = slot_time_str.split("-")
    s = time_to_float(start_str)
    e = time_to_float(end_str)
    duration = e - s
    
    # 6時間以下なら休憩なし
    if duration <= 6.0:
        return slot_time_str, ""
    
    break_len = 1.0 if duration > 8.0 else 0.75
    
    # 休憩候補（アイドルタイム）のリスト
    idles = [
        (time_to_float(store_info.get('idle1_s', "14:00")), time_to_float(store_info.get('idle1_e', "15:00"))),
        (time_to_float(store_info.get('idle2_s', "15:00")), time_to_float(store_info.get('idle2_e', "16:00"))),
        (time_to_float(store_info.get('idle3_s', "00:00")), time_to_float(store_info.get('idle3_e', "00:00"))),
    ]
    
    for b_start, b_end in idles:
        # 開始・終了が同じ、または0の場合はスキップ
        if b_start == b_end: continue
        
        # 【重要】勤務開始から少なくとも1.5時間後、かつ終了まで1.5時間以上ある場所で切る
        if (s + 1.5 <= b_start) and (e >= b_start + break_len + 1.5):
            part1 = f"{float_to_time(s)}-{float_to_time(b_start)}"
            part2 = f"{float_to_time(b_start + break_len)}-{float_to_time(e)}"
            return part1, part2
            
    # 合致するアイドルタイムがない場合は真ん中で分割
    mid_start = s + (duration / 2) - (break_len / 2)
    # 30分単位に丸める処理を入れるとより綺麗です
    mid_start = round(mid_start * 2) / 2
    return f"{float_to_time(s)}-{float_to_time(mid_start)}", f"{float_to_time(mid_start + break_len)}-{float_to_time(e)}"
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
                'x_scale': 0.275, 
                'y_scale': 0.275,
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
    """'10:00-18:00' などの文字列から実働と休憩を計算（単体用・変更なし）"""
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

def calc_work_and_break_combined(val1, val2):
    """2つの時間枠（前半・後半）を合算して正しい休憩を計算する【新関数】"""
    # 両方の時間を個別に計算
    net1, brk1 = calc_work_and_break(val1)
    net2, brk2 = calc_work_and_break(val2)
    
    # 総勤務時間（休憩込み）= 実働 + 休憩
    total_hours = net1 + brk1 + net2 + brk2
    
    # 勤務時間が0なら終了
    if total_hours == 0:
        return net1, brk1, net2, brk2
    
    # ★ 合計勤務時間から正しい休憩を再計算
    if total_hours > 8.0:
        correct_total_break = 1.0
    elif total_hours > 6.0:
        correct_total_break = 0.75
    else:
        correct_total_break = 0.0
    
    # 休憩を前半と後半に按分（勤務時間の比率で）
    work1 = net1 + brk1  # 前半の勤務時間
    work2 = net2 + brk2  # 後半の勤務時間
    
    if total_hours > 0:
        ratio1 = work1 / total_hours
        break1 = round(correct_total_break * ratio1, 2)
        break2 = round(correct_total_break - break1, 2)
    else:
        break1, break2 = 0.0, 0.0
    
    # 実働 = 勤務時間 - 休憩
    final_net1 = round(work1 - break1, 1)
    final_net2 = round(work2 - break2, 1)
    
    return final_net1, break1, final_net2, break2
st.set_page_config(page_title="ジョイフル シフト管理", layout="wide")
# --- 30分刻みの時間リスト作成 ---
TIME_OPTIONS = [f"{h:02d}:{m:02d}" for h in range(0, 31) for m in [0, 30]]# 24:30以降は不要なので24:00までにする
TIME_OPTIONS = TIME_OPTIONS[:-1]
# --- 1. スプレッドシート接続設定 ---
# ブラウザのURLバーにある文字列をそのまま貼り付けているか確認
MASTER_DATABASE_URL = "https://docs.google.com/spreadsheets/d/1cajpaXBr6N8ecMGTR0L9-5AJ65yuRNSpdhheU6QR44U/edit?gid=0#gid=0"
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

def save_sheet_robust(df, worksheet_name, target_url=None):
    """データを保存する。target_urlが指定されればそこへ、なければ現在の店のURLへ。"""
    if target_url is None:
        target_url = SPREADSHEET_URL
        
    try:
        raw_gc = None
        if hasattr(conn, "_client"): raw_gc = conn._client
        elif hasattr(conn, "client") and hasattr(conn.client, "_client"): raw_gc = conn.client._client
        elif hasattr(conn, "client"): raw_gc = conn.client
            
        if raw_gc is None or not hasattr(raw_gc, "open_by_url"):
            st.error("Google Sheetsの接続元が見つかりませんでした。")
            return False

        sh = raw_gc.open_by_url(target_url)
        worksheet_list = [w.title for w in sh.worksheets()]
        
        if worksheet_name not in worksheet_list:
            sh.add_worksheet(title=worksheet_name, rows="100", cols="50")
            st.info(f"✨ 新しいシート「{worksheet_name}」を作成しました。")

        save_df = df.data if hasattr(df, 'data') else df.copy()
        
        # ★★★ 修正：インデックスをリセットして列として保持 ★★★
        # インデックス名がある場合、それを列として残す
        if save_df.index.name is not None:
            index_name = save_df.index.name
            save_df = save_df.reset_index()  # インデックスを列に戻す
            # インデックス列が既に存在する場合は重複を避ける
            if index_name in save_df.columns and save_df.columns.tolist().count(index_name) > 1:
                # 重複列を削除
                cols_to_keep = []
                seen = set()
                for col in save_df.columns:
                    if col not in seen:
                        cols_to_keep.append(col)
                        seen.add(col)
                save_df = save_df[cols_to_keep]
        else:
            save_df = save_df.reset_index(drop=True)
        
        # ★ 不要な列を削除
        if 'index' in save_df.columns:
            save_df = save_df.drop(columns=['index'])
        if 'level_0' in save_df.columns:
            save_df = save_df.drop(columns=['level_0'])
        
        # True/Falseを文字列に変換
        save_df = save_df.map(lambda x: "TRUE" if x is True else ("FALSE" if x is False else x))
        
        # ★★★ 保存前に列名を確認 ★★★
        # store_id などの重要な列が欠落していないか確認
        # 指定したURLとシート名に書き込む
        conn.update(spreadsheet=target_url, worksheet=worksheet_name, data=save_df)
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
f_to_t = time_to_float
def float_to_time(val):
    """10.75 -> '10:45' への変換"""
    h = int(val)
    m = int((val - h) * 60)
    return f"{h:02d}:{m:02d}"
def validate_and_fix_date_columns(df, year, month):
    """日付列を検証し、不足している日付は空列として追加する"""
    num_days = calendar.monthrange(year, month)[1]
    date_cols = []
    for d in range(1, num_days + 1):
        w_idx = calendar.weekday(year, month, d)
        date_cols.append(f"{d}({WEEKDAYS_JP[w_idx]})")
    
    # 既存の日付列を特定
    existing_dates = {}
    for col in df.columns:
        col_str = str(col)
        digits = "".join(filter(str.isdigit, col_str.split('(')[0]))
        if digits and 1 <= int(digits) <= 31:
            existing_dates[int(digits)] = col
    
    # 不足している日付列を追加
    for d in range(1, num_days + 1):
        if d not in existing_dates:
            col_name = f"{d}({WEEKDAYS_JP[calendar.weekday(year, month, d)]})"
            df[col_name] = ""  # 空列として追加
            st.warning(f"⚠️ {d}日の列が不足していたため、空列として追加しました")
    
    # 正しい順序で列を並べ替え
    ordered_cols = ["グループ", "名前"] + date_cols
    # 存在する列だけを抽出（安全策）
    final_cols = [c for c in ordered_cols if c in df.columns]
    return df[final_cols]
def validate_uploaded_shift(df, year, month):
    """アップロードされたシフトの形式を検証"""
    errors = []
    warnings = []
    
    num_days = calendar.monthrange(year, month)[1]
    
    # 1. 列数のチェック
    expected_min_cols = 2 + num_days  # グループ + 名前 + 日付列
    if len(df.columns) < expected_min_cols:
        errors.append(f"列数が不足しています（必要: {expected_min_cols}以上, 実際: {len(df.columns)}）")
    
    # 2. 名前列の存在チェック
    name_col_found = False
    for col in df.columns[:3]:  # 最初の3列をチェック
        if "名前" in str(col) or df[col].astype(str).str.contains("田中|佐藤|鈴木").any():
            name_col_found = True
            break
    
    if not name_col_found:
        warnings.append("名前列が見つかりません。1列目を名前として扱います")
    
    # 3. 日付列のカウント
    date_pattern_cols = [c for c in df.columns if "(" in str(c) and ")" in str(c)]
    if len(date_pattern_cols) < num_days:
        warnings.append(f"日付列が不足しています（{num_days}日分必要なところ{len(date_pattern_cols)}列）")
    
    # 4. 行数のチェック（偶数であるべき）
    data_rows = len(df) - 2  # ヘッダー行を除く
    if data_rows % 2 != 0:
        warnings.append("データ行数が奇数です。最終行のデータが不完全な可能性があります")
    
    return errors, warnings
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

# ==========================================
# 1. ログイン・店舗特定ロジック（修正版）
# ==========================================
query_params = st.query_params
url_store_id = query_params.get("s", None)

# 管理者フラグの初期化
if 'is_global_admin' not in st.session_state:
    st.session_state.is_global_admin = False

# まだどこにもログインしていない場合
if 'spreadsheet_url' not in st.session_state and not st.session_state.is_global_admin:
    st.title("🏪 ジョイフル シフト管理システム")
    
    # URLに店舗IDがあるかチェック（スタッフ用）
    target_id = url_store_id if url_store_id else None
    
    if not target_id:
        # ID入力画面を表示
        st.markdown("### 店舗IDを入力してください")
        input_id = st.text_input("店舗ID（または管理用ID）", placeholder="例: KOKURA").upper().strip()
        
        if input_id == "ADMIN":
            admin_pw = st.text_input("管理者パスワードを入力してください", type="password")
            if st.button("🔑 管理パネルにログイン", use_container_width=True):
                if admin_pw == "master999":
                    st.session_state.is_global_admin = True
                    st.rerun()
                else:
                    st.error("❌ パスワードが違います")
            st.stop()
            
        elif input_id != "":
            if st.button("🔍 店舗にアクセス", use_container_width=True):
                target_id = input_id
            else:
                st.stop()
        else:
            st.stop()

    # 店舗情報の検索
    try:
        # ★ キャッシュをクリアして再取得（エラー対策）
        with st.spinner("🔍 店舗情報を検索中..."):
            # キャッシュを一旦クリア
            st.cache_data.clear()
            
            # 店舗データを再取得
            df_stores = get_all_stores_cached()
            
            # デバッグ情報（問題解決後は削除可能）
            if df_stores.empty:
                st.error("⚠️ 店舗データベースが空です。システム管理者に連絡してください。")
                
                # 管理者ログインへの誘導
                st.markdown("---")
                st.markdown("システム管理者の方は、ADMIN IDでログインしてください。")
                
                with st.expander("🔧 管理者用：緊急リカバリー", expanded=False):
                    st.markdown("""
                    ### データベースが空の場合の復旧手順
                    1. **ADMIN** でログイン
                    2. 「新規店舗登録」から店舗を再登録
                    3. 各店舗のスプレッドシートURLを確認して入力
                    """)
                st.stop()
            
            # デバッグ：利用可能な店舗IDを表示
            available_ids = df_stores['store_id'].dropna().tolist()
            st.caption(f"🔍 デバッグ: 利用可能な店舗ID: {', '.join(available_ids)}")
            
            # 大文字小文字を区別せずに検索
            info = df_stores[df_stores['store_id'].str.upper() == target_id.upper()]
            
            if not info.empty:
                s_data = info.iloc[0]
                st.session_state.spreadsheet_url = s_data.get('sheet_url')
                st.session_state.store_name = s_data.get('store_name')
                st.session_state.group_options = s_data.get('group_list', "HD,HN,KD,KN,W").split(",")
                st.session_state.skill1_name = s_data.get('skill1_name', "デザート")
                st.session_state.skill2_name = s_data.get('skill2_name', "レジ締め")
                st.session_state.target_rate = float(s_data.get('target_rate', 0.7))
                st.session_state.enabled_features = s_data.get('enabled_features', '')
                
                # パスワードの小数点対策
                raw_pw = s_data.get('admin_pw')
                try: st.session_state.admin_pw_fixed = str(int(float(raw_pw))).strip()
                except: st.session_state.admin_pw_fixed = str(raw_pw).strip()
                
                # 開店・閉店時間を取得してスライダー用リストを作成
                o_time = str(s_data.get('open_time', "10:00"))
                c_time = str(s_data.get('close_time', "24:00"))
                try:
                    o_h = int(o_time.split(":")[0])
                    c_h = int(c_time.split(":")[0])
                except: o_h, c_h = 10, 24

                custom_options = []
                for h in range(o_h, c_h + 1):
                    custom_options.append(f"{h:02d}:00")
                    if h != c_h: custom_options.append(f"{h:02d}:30")
                
                st.session_state.store_time_options = custom_options
                
                st.success(f"✅ {st.session_state.store_name} に接続しました！")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ 店舗ID「{target_id}」が見つかりません。")
                st.markdown(f"利用可能な店舗ID: {', '.join(available_ids) if available_ids else 'なし'}")
                
                # 再試行ボタン
                if st.button("🔄 再検索"):
                    st.cache_data.clear()
                    st.rerun()
                
                st.stop()
    except Exception as e:
        st.error(f"⚠️ データベース接続エラーが発生しました。")
        
        with st.expander("🔍 エラー詳細", expanded=False):
            st.code(str(e))
        
        st.markdown("""
        ### 考えられる原因
        1. Google Sheets APIの接続制限に達した
        2. マスターデータベースのURLが変更された
        3. ネットワーク接続の問題
        
        ### 対処方法
        - しばらく待ってから再試行してください
        - システム管理者に連絡してください
        """)
        
        # 再試行ボタン
        if st.button("🔄 再試行", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        st.stop()
# ==========================================
# 2. システム管理者専用画面 (Global Admin) 修正版
# ==========================================
if st.session_state.is_global_admin:
    st.title("⚙️ システム総合管理パネル")
    st.sidebar.title("管理メニュー")
    if st.sidebar.button("ログアウト"):
        st.session_state.is_global_admin = False
        st.rerun()

    df_stores = get_all_stores_cached()
    tab_new, tab_edit, tab_features = st.tabs(["🆕 新規店舗登録", "⚙️ 既存店舗の編集", "🔧 機能の表示設定"])

    # ==========================================
    # 新規店舗登録タブ
    # ==========================================
    with tab_new:
        st.subheader("🆕 新しい店舗をシステムに追加")
        with st.form("add_store_form"):
            new_id = st.text_input("店舗ID (KOKURA, MOJIなど) ※必須").upper().strip()
            new_name = st.text_input("店舗名")
            new_url = st.text_input("専用シートのURL")
            new_pw = st.text_input("店長パスワード")
            
            c1, c2 = st.columns(2)
            n_open = c1.selectbox("開店時間", TIME_OPTIONS, index=20) # デフォルト10:00
            n_close = c2.selectbox("閉店時間", TIME_OPTIONS, index=48) # デフォルト24:00
            
            st.markdown("---")
            st.write("▼ アイドルタイム（休憩推奨時間）の設定")
            ci1, ci2, ci3 = st.columns(3)
            with ci1:
                n_i1s = st.selectbox("休憩1 開始", TIME_OPTIONS, index=28) # 14:00
                n_i1e = st.selectbox("休憩1 終了", TIME_OPTIONS, index=30) # 15:00
            with ci2:
                n_i2s = st.selectbox("休憩2 開始", TIME_OPTIONS, index=31) # 15:30
                n_i2e = st.selectbox("休憩2 終了", TIME_OPTIONS, index=33) # 16:30
            with ci3:
                n_i3s = st.selectbox("休憩3 開始", TIME_OPTIONS, index=0)
                n_i3e = st.selectbox("休憩3 終了", TIME_OPTIONS, index=0)

            st.markdown("---")
            st.write("▼ 店舗固有の設定")
            n_groups = st.text_input("グループ名リスト（カンマ区切り）", value="HD,HN,KD,KN,W")
            n_s1 = st.text_input("スキル1名称（昼リーダー）", value="デザート")
            n_s2 = st.text_input("スキル2名称（夜リーダー）", value="レジ締め")
            n_rate_pct = st.number_input("目標出勤率 (1〜100%)", 1, 100, 70)
            n_rate = n_rate_pct / 100.0
            
            # ★ 表示する機能の選択
            st.markdown("---")
            st.write("▼ この店舗で表示する機能")
            st.caption("チェックを入れた機能のみがサイドメニューに表示されます")
            
            # 利用可能な全機能のリスト
            all_features = [
                "確定シフト閲覧",
                "休み希望入力", 
                "清掃記録",
                "従業員名簿管理",
                "シフト自動生成（案）",
                "シフトアップロード",
                "レジ締め作業"
            ]
            
            # デフォルトで全てチェック
            n_features = {}
            for feature in all_features:
                n_features[feature] = st.checkbox(feature, value=True, key=f"new_feature_{feature}")
            
            # 選択された機能をカンマ区切りで保存
            n_enabled_features = ",".join([f for f, enabled in n_features.items() if enabled])

            if st.form_submit_button("新店舗をシステムに登録"):
                if not new_id:
                    st.error("店舗IDを入力してください。")
                else:
                    new_row = pd.DataFrame([{
                        "store_id": str(new_id), 
                        "store_name": str(new_name), 
                        "sheet_url": str(new_url), 
                        "admin_pw": str(new_pw), 
                        "open_time": str(n_open), 
                        "close_time": str(n_close),
                        "group_list": str(n_groups), 
                        "skill1_name": str(n_s1), 
                        "skill2_name": str(n_s2), 
                        "target_rate": n_rate,
                        "idle1_s": str(n_i1s), "idle1_e": str(n_i1e),
                        "idle2_s": str(n_i2s), "idle2_e": str(n_i2e),
                        "idle3_s": str(n_i3s), "idle3_e": str(n_i3e),
                        "enabled_features": n_enabled_features
                    }])

                    df_clean = df_stores.dropna(how='all').dropna(subset=['store_id'])
                    df_updated = pd.concat([df_clean, new_row], ignore_index=True)
                    
                    # ★★★ store_idをインデックスに設定してから保存 ★★★
                    df_to_save = df_updated.set_index("store_id")
                    df_to_save.index.name = "store_id"
                    
                    if save_sheet_robust(df_to_save, "stores", target_url=MASTER_DATABASE_URL):
                        st.cache_data.clear()
                        st.success(f"店舗「{new_name}」を登録しました！")
                        st.rerun()

    # ==========================================
    # 既存店舗の編集タブ
    # ==========================================
    with tab_edit:
        st.subheader("⚙️ 既存店舗の設定変更")
        if df_stores.empty:
            st.write("登録されている店舗はありません。")
        else:
            target_id = st.selectbox("編集する店舗を選択", df_stores['store_id'].tolist())
            if target_id:
                s_info = df_stores[df_stores['store_id'] == target_id].iloc[0]
                
                def get_t_idx(val):
                    try:
                        return TIME_OPTIONS.index(str(val))
                    except:
                        return 0

                with st.form(f"edit_form_{target_id}"):
                    e_name = st.text_input("店舗名", value=s_info.get('store_name', ""))
                    e_url = st.text_input("専用シートURL", value=s_info.get('sheet_url', ""))
                    e_pw = st.text_input("店長パスワード", value=s_info.get('admin_pw', ""))
                    
                    c1, c2 = st.columns(2)
                    try:
                        curr_o = int(str(s_info.get('open_time', "10:00")).split(":")[0])
                        curr_c = int(str(s_info.get('close_time', "24:00")).split(":")[0])
                    except: curr_o, curr_c = 10, 24
                    
                    e_open = c1.selectbox("開店時間", [f"{h:02d}:00" for h in range(24)], index=curr_o)
                    e_close = c2.selectbox("閉店時間", [f"{h:02d}:00" for h in range(31)], index=curr_c)
                    
                    st.markdown("---")
                    st.write("▼ アイドルタイム（休憩推奨時間）の設定")
                    ci1, ci2, ci3 = st.columns(3)
                    with ci1:
                        e_i1s = st.selectbox("休憩1 開始", TIME_OPTIONS, index=get_t_idx(s_info.get('idle1_s')), key="edit_i1s")
                        e_i1e = st.selectbox("休憩1 終了", TIME_OPTIONS, index=get_t_idx(s_info.get('idle1_e')), key="edit_i1e")
                    with ci2:
                        e_i2s = st.selectbox("休憩2 開始", TIME_OPTIONS, index=get_t_idx(s_info.get('idle2_s')), key="edit_i2s")
                        e_i2e = st.selectbox("休憩2 終了", TIME_OPTIONS, index=get_t_idx(s_info.get('idle2_e')), key="edit_i2e")
                    with ci3:
                        e_i3s = st.selectbox("休憩3 開始", TIME_OPTIONS, index=get_t_idx(s_info.get('idle3_s')), key="edit_i3s")
                        e_i3e = st.selectbox("休憩3 終了", TIME_OPTIONS, index=get_t_idx(s_info.get('idle3_e')), key="edit_i3e")

                    st.markdown("---")
                    e_groups = st.text_input("グループ名リスト", value=s_info.get('group_list', "HD,HN,KD,KN,W"))
                    e_s1 = st.text_input("スキル1名称", value=s_info.get('skill1_name', "デザート"))
                    e_s2 = st.text_input("スキル2名称", value=s_info.get('skill2_name', "レジ締め"))
                    
                    try:
                        init_rate = int(float(s_info.get('target_rate', 0.7)) * 100)
                    except:
                        init_rate = 70
                    e_rate_pct = st.number_input("目標出勤率 (1〜100%)", 1, 100, init_rate)
                    e_rate = e_rate_pct / 100.0
                    
                    # ★ 表示する機能の選択
                    st.markdown("---")
                    st.write("▼ この店舗で表示する機能")
                    st.caption("チェックを入れた機能のみがサイドメニューに表示されます")
                    
                    # 現在の設定を読み込み
                    current_features = str(s_info.get('enabled_features', '')).split(",") if pd.notna(s_info.get('enabled_features')) else []
                    
                    all_features = [
                        "確定シフト閲覧",
                        "休み希望入力", 
                        "清掃記録",
                        "従業員名簿管理",
                        "シフト自動生成（案）",
                        "シフトアップロード",
                        "レジ締め作業"
                    ]
                    
                    e_features = {}
                    for feature in all_features:
                        # 既存の設定があればそれを使い、なければTrue
                        default_val = feature in current_features if current_features else True
                        e_features[feature] = st.checkbox(feature, value=default_val, key=f"edit_feature_{target_id}_{feature}")
                    
                    e_enabled_features = ",".join([f for f, enabled in e_features.items() if enabled])

                    if st.form_submit_button("設定を更新して保存"):
                        df_to_save = df_stores.copy()
                        
                        update_columns = [
                            'store_name', 'sheet_url', 'admin_pw', 'open_time', 'close_time', 
                            'group_list', 'skill1_name', 'skill2_name', 'target_rate',
                            'idle1_s', 'idle1_e', 'idle2_s', 'idle2_e', 'idle3_s', 'idle3_e',
                            'enabled_features'
                        ]
                        
                        update_values = [
                            e_name, e_url, e_pw, e_open, e_close, 
                            e_groups, e_s1, e_s2, e_rate,
                            e_i1s, e_i1e, e_i2s, e_i2e, e_i3s, e_i3e,
                            e_enabled_features
                        ]
                        
                        df_to_save.loc[df_to_save['store_id'] == target_id, update_columns] = update_values
                        
                        # ★★★ store_idをインデックスに設定してから保存 ★★★
                        df_to_save = df_to_save.set_index("store_id")
                        df_to_save.index.name = "store_id"
                        
                        if save_sheet_robust(df_to_save, "stores", target_url=MASTER_DATABASE_URL):
                            st.cache_data.clear()
                            st.success("店舗設定を更新しました！")
                            st.rerun()

    # ==========================================
    # 機能の表示設定タブ（一括管理用）
    # ==========================================
    with tab_features:
        st.subheader("🔧 全店舗の機能表示一覧")
        st.caption("各店舗で現在有効になっている機能の一覧です")
        
        if df_stores.empty:
            st.write("登録されている店舗はありません。")
        else:
            # 表示用データ作成
            display_data = []
            all_features = [
                "確定シフト閲覧",
                "休み希望入力", 
                "清掃記録",
                "従業員名簿管理",
                "シフト自動生成（案）",
                "シフトアップロード",
                "レジ締め作業"
            ]
            
            for _, row in df_stores.iterrows():
                store_name = row.get('store_name', '不明')
                store_id = row.get('store_id', '')
                features_str = str(row.get('enabled_features', ''))
                
                if pd.notna(features_str) and features_str:
                    enabled = features_str.split(",")
                else:
                    enabled = all_features.copy()  # 未設定の場合は全機能有効
                
                row_data = {"店舗名": f"{store_name} ({store_id})"}
                for f in all_features:
                    row_data[f] = "✅" if f in enabled else "❌"
                
                display_data.append(row_data)
            
            if display_data:
                summary_df = pd.DataFrame(display_data)
                st.dataframe(
                    summary_df.set_index("店舗名"),
                    use_container_width=True,
                    height=400
                )
                
                st.caption("✅ = 表示中 / ❌ = 非表示")
                st.info("💡 各店舗の機能を変更するには「既存店舗の編集」タブから行ってください。")

    st.stop() # 管理者はここで終了。下の店舗用コードは実行させない。

# ==========================================
# 3. ここから下は「店舗用」の既存コード（インデント不要）
# ==========================================
SPREADSHEET_URL = st.session_state.spreadsheet_url
TIME_OPTIONS = st.session_state.store_time_options

# 以降のすべての機能で使うURLを決定
SPREADSHEET_URL = st.session_state.spreadsheet_url
# サイドバーの radio ボタンを更新（既存のコードを置き換え）
st.sidebar.title("メニュー")

# ★ 店舗設定から有効な機能を取得
enabled_features_str = st.session_state.get('enabled_features', '')
if enabled_features_str:
    enabled_features = enabled_features_str.split(",")
else:
    # 設定がない場合は全機能を表示（後方互換性）
    enabled_features = [
        "確定シフト閲覧",
        "休み希望入力", 
        "清掃記録",
        "従業員名簿管理",
        "シフト自動生成（案）",
        "シフトアップロード",
        "レジ締め作業"
    ]

# 利用可能な全機能の定義
all_available_modes = {
    "確定シフト閲覧": "📊 確定シフト閲覧",
    "休み希望入力": "📅 休み希望入力",
    "清掃記録": "🧹 清掃記録",
    "従業員名簿管理": "👥 従業員名簿管理",
    "シフト自動生成（案）": "🤖 シフト自動生成（案）",
    "シフトアップロード": "📤 シフトアップロード",
    "レジ締め作業": "💰 レジ締め作業"
}

# 有効な機能のみをメニューに表示
available_modes = {k: v for k, v in all_available_modes.items() if k in enabled_features}

# デフォルトで最初の有効な機能を選択
default_mode = list(available_modes.values())[0] if available_modes else "確定シフト閲覧"

mode = st.sidebar.radio(
    "機能を選択", 
    list(available_modes.values()),
    index=0
)

# 表示名から内部名に変換
mode_map_reverse = {v: k for k, v in available_modes.items()}
mode = mode_map_reverse.get(mode, "確定シフト閲覧")

pw = st.sidebar.text_input("管理者パスワード", type="password")

# --- お知らせ読み込み（決定版） ---
try:
    raw_config_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="config", ttl=0)
    
    if raw_config_df is not None:
        if not raw_config_df.empty:
            # パターンA：1行目が「message」、2行目にお知らせが書いてある場合
            # iloc[0, 0] でデータ1行目を取得
            current_notice = str(raw_config_df.iloc[0, 0])
        else:
            # パターンB：1行目からいきなりお知らせが書いてある場合
            # Pandasは1行目を見出しとして扱うので、columns[0] を取得
            header_val = str(raw_config_df.columns[0])
            if "Unnamed" not in header_val and header_val != "message":
                current_notice = header_val
            else:
                current_notice = "お知らせはありません"
    else:
        current_notice = "お知らせはありません"
except:
    current_notice = "お知らせはありません"

st.info(f" 📢 お知らせ： {current_notice}")
# データのロード
# プログラム中盤の ALL_NAMES を作る部分
master_df = load_master()
if not master_df.empty:
    # 以前は 職種 + 名前 でしたが、シンプルに「名前」だけにします
    ALL_NAMES = master_df["名前"].astype(str).str.strip().tolist()
else:
    ALL_NAMES = []
if mode == "従業員名簿管理":
    st.title("👥 従業員名簿管理")
    
    # ★ パスワード認証チェック
    is_admin = (str(pw).strip() == st.session_state.admin_pw_fixed)
    
    if is_admin:
        # ========== 管理者モード ==========
        st.success("✅ 管理者モードで編集可能です")
        
        # お知らせの編集
        with st.expander("📢 お知らせの編集", expanded=False):
            new_notice = st.text_area(
                "スタッフ全員に表示するメッセージを入力してください", 
                value=current_notice,
                height=100
            )
            if st.button("📢 お知らせを更新する", use_container_width=True):
                updated_notice_df = pd.DataFrame([[new_notice]], columns=["message"])
                if save_config_data(updated_notice_df, "config"):
                    st.success("お知らせを更新しました！全員の画面に反映されます。")
                    st.rerun()
        
        # グループ一覧
        st.caption(f"現在の登録グループ： 【{' / '.join(st.session_state.group_options)}】")
        
        # 名簿エディタ
        st.subheader("📝 名簿の編集")
        edited_df = st.data_editor(
            master_df,
            column_config={
                "名前": st.column_config.TextColumn("名前", required=True, width="medium"),
                "グループ": st.column_config.SelectboxColumn(
                    "グループ", 
                    options=st.session_state.group_options,
                    required=True,
                    width="small"
                ),
                "週希望": st.column_config.NumberColumn(
                    "週希望", 
                    min_value=1, 
                    max_value=7, 
                    step=1, 
                    default=3,
                    width="small",
                    help="1週間の希望出勤日数（自動生成の上限になります）"
                ),
                st.session_state.skill1_name: st.column_config.CheckboxColumn(
                    st.session_state.skill1_name,
                    width="small",
                    help=f"{st.session_state.skill1_name}ができるスタッフ"
                ),
                st.session_state.skill2_name: st.column_config.CheckboxColumn(
                    st.session_state.skill2_name,
                    width="small",
                    help=f"{st.session_state.skill2_name}ができるスタッフ"
                ),
            },
            column_order=["名前", "グループ", "週希望", st.session_state.skill1_name, st.session_state.skill2_name],
            use_container_width=True,
            num_rows="dynamic",
            height=500,
            key="master_editor"
        )
        
        col_save, col_info = st.columns([1, 3])
        with col_save:
            if st.button("💾 名簿を保存する", use_container_width=True, type="primary"):
                if save_master(edited_df):
                    st.success("✅ 保存しました！")
                    st.rerun()
        
        # ========== 取扱説明書（管理者用） ==========
        st.markdown("---")
        with st.expander("📖 【店長用】システム取扱説明書（マニュアル）", expanded=False):
            st.markdown("""
            ### 🛠️ 運用サイクル（毎月の流れ）
            
            1. **名簿の整備**: 新人が入ったら「+」ボタンで行を追加し、「名前」「グループ」「週希望」を登録。
            2. **休み希望の募集**: スタッフに「休み希望入力」から自分の名前を押してカレンダー形式で入力してもらう。
            3. **自動生成**: 「シフト自動生成」で必要人数・時間帯を設定し、ベース案を生成。
            4. **Excel微調整**: 生成した案をダウンロードし、店長のPCで細部を調整。
            5. **確定公開**: 「シフトアップロード」から修正したExcelをアップロードして公開。
            
            ---
            
            ### 👥 1. 従業員名簿管理
            
            * **パスワード**: 左メニューで管理者パスワードを入力すると編集可能になります。
            * **グループの役割**: 
                - `HD`: ホール昼 / `HN`: ホール夜
                - `KD`: キッチン昼 / `KN`: キッチン夜
                - `W`: 社員・共通（どの時間帯にも割り当て可能）
            * **週希望**: 自動生成時に「その週に最大何日入れるか」の基準。この数字を上限としてシフトが組まれます。
            * **スキル（{skill1_name}/{skill2_name}）**: 特定スキルが必要なポジションに優先的に割り当てられます。
            * **お知らせ機能**: 「お知らせの編集」から、全スタッフに表示されるメッセージを編集できます。
            
            ---
            
            ### 📅 2. 休み希望入力
            
            * **スタッフ用**: 左側の自分の名前ボタンを押すと、カレンダー形式で休み希望を入力できます。
            * **管理者モード**: パスワード入力時は、全員分を一括で編集できる表形式に切り替わります。
            * **保存**: 「💾 保存」ボタンで確定。複数人が同時に保存すると上書きされる可能性があるため注意。
            
            ---
            
            ### 🤖 3. シフト自動生成
            
            * **① 基本人数設定**: 平日と金土日祝で必要な人数を設定。
            * **② 特定日設定**: イベント日など、特定の日だけ人数を変更可能。
            * **③ 時間帯設定**: 各ポジションの勤務時間を30分刻みで設定。アイドルタイム（休憩時間）を考慮して自動分割されます。
            * **生成**: 「シフトを生成」ボタンで複数パターンをシミュレーションし、最適案を表示。
            * **出力**: Excelダウンロード時は「合計実働」「休憩合計」が自動計算されます。
            
            ---
            
            ### 📤 4. シフトアップロード
            
            * 店長が編集したExcelファイルをアップロード。
            * **自動計算**: 「10:00-18:00」形式の時間から労働時間・休憩時間を自動計算。
            * **休憩ルール**: 6時間超で0.75h、8時間超で1.0hの休憩を自動適用。
            * **公開**: アップロード後、全スタッフのスマホから閲覧可能になり、LINE通知が送信されます。
            
            ---
            
            ### 📊 5. 確定シフト閲覧
            
            * **本日の出勤者**: その日の出勤メンバーが時間とともに表示されます。
            * **💭つぶやき機能**: 各メンバーの横の💭アイコンをクリックして、一言メッセージを投稿可能。
            * **全体表示**: 年月を選択して月間シフトを閲覧。自分の名前を選択するとハイライト表示。
            * **Excel出力**: 表示中のシフトを印刷用Excelとしてダウンロード可能。
            
            ---
            
            ### 🧹 6. 清掃記録
            
            * **管理者専用**: パスワード入力が必要です。
            * 毎週日曜のモップ清掃を①〜⑦の区画ごとにチェックリストで記録。
            * **印刷用出力**: 4ヶ月分まとめた掲示用ワークシートを生成可能。
            
            ---
            
            ### 💡 トラブルシューティング
            
            * 画面が動かなくなったら → ブラウザの「更新（F5）」を実行
            * データが表示されない → サイドメニューのパスワードを確認
            * 保存に失敗する → しばらく待ってから再試行
            """.format(
                skill1_name=st.session_state.skill1_name,
                skill2_name=st.session_state.skill2_name
            ))
    
    else:
        # ========== 一般スタッフモード（閲覧のみ） ==========
        st.info("🔒 編集するには左側のメニューで管理者パスワードを入力してください。")
        
        # お知らせ表示
        if current_notice and current_notice != "お知らせはありません":
            st.info(f"📢 お知らせ： {current_notice}")
        
        st.subheader("📋 現在の名簿（閲覧のみ）")
        
        if master_df.empty:
            st.warning("名簿データがありません。")
        else:
            # 表示用に列を整理
            display_cols = ["名前", "グループ", "週希望"]
            if st.session_state.skill1_name in master_df.columns:
                display_cols.append(st.session_state.skill1_name)
            if st.session_state.skill2_name in master_df.columns:
                display_cols.append(st.session_state.skill2_name)
            
            # 存在する列のみを表示
            available_cols = [c for c in display_cols if c in master_df.columns]
            
            # チェックボックスを見やすく表示
            view_df = master_df[available_cols].copy()
            
            st.dataframe(
                view_df,
                use_container_width=True,
                height=500,
                hide_index=True
            )
            
            # 人数カウント
            st.caption(f"登録人数: {len(view_df)}名")
            
            # グループ別人数
            if "グループ" in view_df.columns:
                group_counts = view_df["グループ"].value_counts()
                st.write("**グループ別人数:**")
                for g, c in group_counts.items():
                    st.write(f"- {g}: {c}名")
        
        # スタッフ向け簡易マニュアル
        st.markdown("---")
        with st.expander("📖 スタッフ向け使い方ガイド", expanded=False):
            st.markdown("""
            ### 📱 スマホからの使い方
            
            #### 📅 休み希望の入力
            1. 左メニューから「休み希望入力」を選択
            2. 自分の名前のボタンをタップ
            3. カレンダーが表示されるので、休みたい日にチェックを入れる
            4. 「💾 保存」をタップして完了！
            
            #### 📊 シフトの確認
            1. 左メニューから「確定シフト閲覧」を選択
            2. 今日の出勤メンバーと時間が表示されます
            3. 💭アイコンをタップすると、ひとことメッセージを投稿できます
            4. 下にスクロールすると月間シフト全体が確認できます
            
            #### 👥 名簿の確認
            1. 左メニューから「従業員名簿管理」を選択
            2. 現在登録されているスタッフ一覧が表示されます
            
            ---
            
            ### 💡 ヒント
            * シフトは毎月25日頃に公開予定です
            * 休み希望の締切は毎月20日です
            * わからないことがあれば店長に聞いてください
            """)
            

if mode == "休み希望入力":
    st.title(f" {year}年{month}月の休み希望入力")
    
    state_key = f"req_data_{year}_{month}"

    # 1. データの読み込みと初期化
    if state_key not in st.session_state:
        with st.spinner("最新データを読み込み中..."):
            try:
                r_raw = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=REQ_SHEET, ttl=0)
                
                if r_raw is None or r_raw.empty:
                    df = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)
                else:
                    df = r_raw.drop_duplicates(subset=r_raw.columns[0]).set_index(r_raw.columns[0])
                    df.index = df.index.astype(str).str.strip()
                    df = df.reindex(index=ALL_NAMES, columns=column_names).fillna(False)
                    df = df.map(lambda x: str(x).upper().strip() in ["TRUE", "1", "1.0", "TRUE.0"])
            except Exception:
                df = pd.DataFrame(False, index=ALL_NAMES, columns=column_names)

            st.session_state[state_key] = df

    display_df = st.session_state[state_key]

    # 2. 画面レイアウト
    col_btn, col_view = st.columns([1, 6])

    # --- 右側の列：全体の状況表示・一括編集（管理者用） ---
    with col_view:
        config = {col: st.column_config.CheckboxColumn(col, width="small") for col in column_names}

        if pw == st.session_state.admin_pw_fixed:
            st.subheader("管理者モード：全員分を直接編集")
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
            st.data_editor(display_df, column_config=config, use_container_width=True, height=600, disabled=True)

    # --- 左側の列：個人入力への誘導ボタン ---
    with col_btn:
        st.write("自分の名前を押すと下の方に入力画面が現れるよ！⇩")
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

    # --- 3. 個別入力エリア（名前ボタンが押されたら出現） ---
    # ★★★ 修正：editing_user が存在し、かつ None でない、かつ display_df に存在する名前かチェック ★★★
    if "editing_user" in st.session_state and st.session_state.editing_user is not None:
        user = st.session_state.editing_user
        
        # ★★★ 追加：user が display_df のインデックスに存在するか確認 ★★★
        if user not in display_df.index:
            st.error(f"❌ {user} さんは名簿に登録されていません。")
            # 不正な状態をクリア
            del st.session_state.editing_user
            st.stop()
        
        # --- 強力なグリッドCSS ---
        st.markdown("""
            <style>
            [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
                display: grid !important;
                grid-template-columns: repeat(7, 1fr) !important;
                gap: 2px !important;
            }
            [data-testid="stForm"] [data-testid="column"] {
                width: auto !important;
                min-width: 0px !important;
            }
            .stCheckbox {
                margin-top: -10px !important;
                display: flex !important;
                justify-content: center !important;
            }
            .stCheckbox div[data-testid="stMarkdownContainer"] {
                display: none;
            }
            .cal-num {
                text-align: center;
                font-size: 0.8rem;
                font-weight: bold;
                margin-bottom: 0px;
                line-height: 1.2;
            }
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
        try:
            raw_user_data = display_df.loc[user].copy()
            user_status_clean = {k: (str(v).upper().strip() in ["TRUE", "1", "1.0", "YES"]) for k, v in raw_user_data.items()}
        except KeyError:
            st.error(f"❌ {user} さんのデータが見つかりません。")
            del st.session_state.editing_user
            st.stop()

        # 2. フォーム
        with st.form(key=f"ultra_tight_cal_{user}"):
            calendar.setfirstweekday(calendar.SUNDAY)
            cal = calendar.monthcalendar(year, month)
            weekdays_jp = ["日", "月", "火", "水", "木", "金", "土"]
            
            # 曜日ヘッダー
            h_cols = st.columns(7)
            for i, label in enumerate(weekdays_jp):
                color = "#333"
                if i == 0: color = "red"
                if i == 6: color = "blue"
                h_cols[i].markdown(f"<p style='text-align:center; color:{color}; font-size:0.7rem; font-weight:bold; margin-bottom:0;'>{label}</p>", unsafe_allow_html=True)

            new_updates = {}

            # カレンダー日付
            for week in cal:
                cols = st.columns(7)
                for i, day in enumerate(week):
                    if day == 0:
                        cols[i].write("")
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
                try:
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
                except Exception as e:
                    st.error(f"保存エラー: {e}")

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
    # --- 0. 祝日データの取得 ---
    current_holidays = get_month_holidays_list(year, month)
    holiday_days = [h[0] for h in current_holidays]
    
    # 来月の祝日計算
    next_month_date = (v_date + timedelta(days=32)).replace(day=1)
    next_year, next_month = next_month_date.year, next_month_date.month
    holidays = get_month_holidays_list(next_year, month)

    # ★★★ 保存データの読み込み ★★★
    stored_df = load_sheet_no_cache("config_times", pd.DataFrame())
    stored_times = stored_df.to_dict('index') if not stored_df.empty else {}
    
    # チェックボックスのデフォルト値
    transfer_baito_default = str(stored_times.get("transfer_baito_to_staff", {}).get("start", "True")).strip().lower() == "true"
    merge_staff_default = str(stored_times.get("merge_staff_shifts", {}).get("start", "True")).strip().lower() == "true"
    
    # 目標時間のデフォルト
    if "monthly_target_hours" in stored_times:
        monthly_target_default = float(stored_times["monthly_target_hours"].get("start", 160))
    else:
        monthly_target_default = 160.0
    
    # 個人別目標のデフォルト
    w_targets_default = {}
    for key, val in stored_times.items():
        if key.startswith("w_target_"):
            name = key.replace("w_target_", "")
            w_targets_default[name] = float(val.get("start", 160))
    
    # 必要人数のデフォルト
    def get_default_count(key, fallback):
        return int(stored_times.get(key, {}).get("start", fallback))
    
    staff_count_defaults = {
        "h_d_wd": get_default_count("staff_count_wd_hd", 2),
        "k_d_wd": get_default_count("staff_count_wd_kd", 2),
        "h_n_wd": get_default_count("staff_count_wd_hn", 3),
        "k_n_wd": get_default_count("staff_count_wd_kn", 3),
        "h_d_we": get_default_count("staff_count_we_hd", 3),
        "k_d_we": get_default_count("staff_count_we_kd", 2),
        "h_n_we": get_default_count("staff_count_we_hn", 4),
        "k_n_we": get_default_count("staff_count_we_kn", 4),
    }

    # ==========================================
    # ★ 設定エリア全体をフラグメント化 ★
    # ==========================================
    @st.fragment
    def all_settings_fragment():
        # --- ① 基本設定 ---
        st.markdown("### ① 基本の必要人数と目標時間")
        
        col_wd, col_we = st.columns(2)
        with col_wd:
            st.markdown("#### 🚃 平日 (月〜木)")
            h_d_wd = st.number_input("ホール昼", 0, 20, staff_count_defaults["h_d_wd"], key="h_d_wd")
            k_d_wd = st.number_input("キッチン昼", 0, 20, staff_count_defaults["k_d_wd"], key="k_d_wd")
            h_n_wd = st.number_input("ホール夜", 0, 20, staff_count_defaults["h_n_wd"], key="h_n_wd")
            k_n_wd = st.number_input("キッチン夜", 0, 20, staff_count_defaults["k_n_wd"], key="k_n_wd")
        with col_we:
            st.markdown("#### 🌞 金・土・日・祝")
            h_d_we = st.number_input("ホール昼 ", 0, 20, staff_count_defaults["h_d_we"], key="h_d_we")
            k_d_we = st.number_input("キッチン昼 ", 0, 20, staff_count_defaults["k_d_we"], key="k_d_we")
            h_n_we = st.number_input("ホール夜 ", 0, 20, staff_count_defaults["h_n_we"], key="h_n_we")
            k_n_we = st.number_input("キッチン夜 ", 0, 20, staff_count_defaults["k_n_we"], key="k_n_we")
        
        st.markdown("---")
        st.markdown("#### 🎯 社員（Wグループ）個人別の月間目標時間")
        
        w_members = []
        if not master_df.empty:
            w_members = master_df[master_df["グループ"] == "W"]["名前"].tolist()
        
        w_individual_targets = {}
        if w_members:
            for name in w_members:
                default_val = w_targets_default.get(name, monthly_target_default)
                w_individual_targets[name] = st.number_input(
                    f"{name}",
                    min_value=0.0, max_value=300.0, value=default_val, step=5.0,
                    key=f"w_target_{name}"
                )
        else:
            st.info("Wグループの社員がいません")
        
        st.markdown("---")
        st.markdown("#### ⚙️ 社員シフトの詳細設定")
        
        col_check1, col_check2 = st.columns(2)
        with col_check1:
            transfer_baito_to_staff = st.checkbox(
                "バイトのシフトを社員へ振り替える",
                value=transfer_baito_default,
                key="transfer_baito_to_staff"
            )
        with col_check2:
            merge_staff_shifts = st.checkbox(
                "社員の昼夜を1つに連結する",
                value=merge_staff_default,
                key="merge_staff_shifts"
            )
        
        st.markdown("---")
        st.markdown("### ② 特定日の追加設定（オプション）")
        
        selected_special_days = st.multiselect(
            "特別設定を適用する日を選択",
            range(1, num_days + 1),
            default=st.session_state.get("selected_special_days", []),
            key="special_days_select"
        )
        
        special_configs = {}
        if selected_special_days:
            for d in sorted(selected_special_days):
                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([1,2,2,2,2])
                    c1.markdown(f"#### {d}日")
                    s_hd = c2.number_input(f"H昼", 0, 20, h_d_we, key=f"sp_hd_{d}")
                    s_kd = c3.number_input(f"K昼", 0, 20, k_d_we, key=f"sp_kd_{d}")
                    s_hn = c4.number_input(f"H夜", 0, 20, h_n_we, key=f"sp_hn_{d}")
                    s_kn = c5.number_input(f"K夜", 0, 20, k_n_we, key=f"sp_kn_{d}")
                    special_configs[d] = {"h_d": s_hd, "k_d": s_kd, "h_n": s_hn, "k_n": s_kn}
        
        # --- ③ 詳細な枠時間の設定 ---
        st.markdown("---")
        st.markdown("### ③ 詳細な枠時間の設定（30分刻み）")
        st.write("各ポジションの勤務時間を設定してください。バーを動かすと下の人時が即座に更新されます。")

        # タブの作成もフラグメント内に
        tab_titles = ["🚃 平日", "🌞 金土日祝"] + [f"⭐ {d}日" for d in sorted(selected_special_days)]
        all_tabs = st.tabs(tab_titles)
        
        all_settings_to_save = []
        slot_data_map = {}

        # --- 平日 ---
        with all_tabs[0]:
            st.subheader("平日")
            wd_hd = []
            for i in range(h_d_wd):
                k = f"wd_hd_{i}"
                default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("10:00", "18:00")
                t = st.select_slider(f"H昼 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                wd_hd.append(f"{t[0]}-{t[1]}")
                all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})

            wd_kd = []
            for i in range(k_d_wd):
                k = f"wd_kd_{i}"
                default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("10:00", "18:00")
                t = st.select_slider(f"K昼 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                wd_kd.append(f"{t[0]}-{t[1]}")
                all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})

            wd_hn = []
            for i in range(h_n_wd):
                k = f"wd_hn_{i}"
                default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("18:00", "23:00")
                t = st.select_slider(f"H夜 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                wd_hn.append(f"{t[0]}-{t[1]}")
                all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})

            wd_kn = []
            for i in range(k_n_wd):
                k = f"wd_kn_{i}"
                default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("18:00", "23:00")
                t = st.select_slider(f"K夜 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                wd_kn.append(f"{t[0]}-{t[1]}")
                all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})

            slot_data_map["weekday"] = {"hd": wd_hd, "kd": wd_kd, "hn": wd_hn, "kn": wd_kn}

        # --- 金土日祝 ---
        with all_tabs[1]:
            st.subheader("金土日祝")
            we_hd = []
            for i in range(h_d_we):
                k = f"we_hd_{i}"
                default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("10:00", "18:00")
                t = st.select_slider(f"H昼 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                we_hd.append(f"{t[0]}-{t[1]}")
                all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})

            we_kd = []
            for i in range(k_d_we):
                k = f"we_kd_{i}"
                default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("10:00", "18:00")
                t = st.select_slider(f"K昼 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                we_kd.append(f"{t[0]}-{t[1]}")
                all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})

            we_hn = []
            for i in range(h_n_we):
                k = f"we_hn_{i}"
                default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("18:00", "23:00")
                t = st.select_slider(f"H夜 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                we_hn.append(f"{t[0]}-{t[1]}")
                all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})

            we_kn = []
            for i in range(k_n_we):
                k = f"we_kn_{i}"
                default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("18:00", "23:00")
                t = st.select_slider(f"K夜 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                we_kn.append(f"{t[0]}-{t[1]}")
                all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})

            slot_data_map["weekend"] = {"hd": we_hd, "kd": we_kd, "hn": we_hn, "kn": we_kn}

        # --- 特定日 ---
        for idx, d in enumerate(sorted(selected_special_days)):
            with all_tabs[idx+2]:
                st.subheader(f"{d}日")
                conf = special_configs[d]
                s_hd = []
                for i in range(conf["h_d"]):
                    k = f"sp_{d}_hd_{i}"
                    default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("10:00", "18:00")
                    t = st.select_slider(f"H昼 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                    s_hd.append(f"{t[0]}-{t[1]}")
                    all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})
                s_kd = []
                for i in range(conf["k_d"]):
                    k = f"sp_{d}_kd_{i}"
                    default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("10:00", "18:00")
                    t = st.select_slider(f"K昼 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                    s_kd.append(f"{t[0]}-{t[1]}")
                    all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})
                s_hn = []
                for i in range(conf["h_n"]):
                    k = f"sp_{d}_hn_{i}"
                    default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("18:00", "23:00")
                    t = st.select_slider(f"H夜 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                    s_hn.append(f"{t[0]}-{t[1]}")
                    all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})
                s_kn = []
                for i in range(conf["k_n"]):
                    k = f"sp_{d}_kn_{i}"
                    default_val = (stored_times[k]["start"], stored_times[k]["end"]) if k in stored_times else ("18:00", "23:00")
                    t = st.select_slider(f"K夜 {i+1}人目", options=TIME_OPTIONS, value=default_val, key=f"slider_{k}")
                    s_kn.append(f"{t[0]}-{t[1]}")
                    all_settings_to_save.append({"key": k, "start": t[0], "end": t[1]})
                slot_data_map[d] = {"hd": s_hd, "kd": s_kd, "hn": s_hn, "kn": s_kn}

# --- リアルタイム人時プレビュー（月-木 vs 金-日・祝） ---
        def get_month_stats(y, m):
            """月の日数を平日(月-木)と週末祝日(金-日・祝)に分類"""
            h_list = [h[0] for h in get_month_holidays_list(y, m)]
            cal = calendar.Calendar(firstweekday=6) # 日曜始まり
            wd_total = 0 # 月-木
            we_total = 0 # 金-日・祝
            for day_num, d_week in cal.itermonthdays2(y, m):
                if day_num == 0: continue
                # d_week: 0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
                # 4以上（金・土・日）または祝日リストにある場合を WE とする
                if d_week >= 4 or day_num in h_list:
                    we_total += 1
                else:
                    wd_total += 1
            return wd_total, we_total

        # 1. & 2. 基礎日数の算出
        wd_cnt, we_cnt = get_month_stats(year, month)
        
        # 3. 特定日を除外した「正味の日数（Ho, Ko）」を算出
        wd_special_count = 0
        we_special_count = 0
        h_list_integers = [h[0] for h in get_month_holidays_list(year, month)]
        
        for d in selected_special_days:
            # 特定日の本来の曜日を確認
            d_weekday = calendar.weekday(year, month, d)
            # 本来金〜日(4-6) または 祝日なら WE、それ以外なら WD
            if d_weekday >= 4 or d in h_list_integers:
                we_special_count += 1
            else:
                wd_special_count += 1
        
        pure_wd = wd_cnt - wd_special_count # これが Ho (特定日を除いた平日)
        pure_we = we_cnt - we_special_count # これが Ko (特定日を除いた土日祝)

        def calc_pos_hours(slots):
            """手順4 & 5: バーの長さから実働(休憩差引後)を合計算出"""
            total = 0.0
            for slot in slots:
                if "-" in slot:
                    # 拘束時間から休憩を自動で引く既存関数を使用
                    net, _ = calc_work_and_break(slot)
                    total += net
            return total

        # 4. 平日(月-木)の1日あたりの合計実働 (hb)
        wd_h = (calc_pos_hours(wd_hd) + calc_pos_hours(wd_kd) +
                calc_pos_hours(wd_hn) + calc_pos_hours(wd_kn))
        
        # 5. 土日祝(金-日・祝)の1日あたりの合計実働 (kb)
        we_h = (calc_pos_hours(we_hd) + calc_pos_hours(we_kd) +
                calc_pos_hours(we_hn) + calc_pos_hours(we_kn))

        # 特定日それぞれの実働合計 (Σ Tb)
        special_h_sum = 0.0
        for d in selected_special_days:
            if d in slot_data_map:
                sp = slot_data_map[d]
                day_total = (calc_pos_hours(sp["hd"]) + calc_pos_hours(sp["kd"]) +
                             calc_pos_hours(sp["hn"]) + calc_pos_hours(sp["kn"]))
                special_h_sum += day_total

        # 6. & 7. 総人時の合算
        total_labor = (wd_h * pure_wd) + (we_h * pure_we) + special_h_sum

        # --- UI表示 ---
        st.info(f"📊 この設定での**概算総人時（休憩差引後）**: **{total_labor:.2f} 時間**")
        st.caption(f"内訳: 月-木 {pure_wd}日 × {wd_h:.1f}h + 金土日祝 {pure_we}日 × {we_h:.1f}h + 特定日 {len(selected_special_days)}日分")

        # --- 保存リストの構築（全てのUI設定を網羅） ---
        # スライダー設定は既に all_settings_to_save に追加済みと仮定
        # それ以外のパラメータを追加
        all_settings_to_save.append({"key": "monthly_target_hours", "start": str(monthly_target_default), "end": ""})
        for name, target in w_individual_targets.items():
            all_settings_to_save.append({"key": f"w_target_{name}", "start": str(target), "end": ""})
        
        # 人数設定の保存
        counts_to_save = {
            "staff_count_wd_hd": h_d_wd, "staff_count_wd_kd": k_d_wd, "staff_count_wd_hn": h_n_wd, "staff_count_wd_kn": k_n_wd,
            "staff_count_we_hd": h_d_we, "staff_count_we_kd": k_d_we, "staff_count_we_hn": h_n_we, "staff_count_we_kn": k_n_we,
            "transfer_baito_to_staff": transfer_baito_to_staff, "merge_staff_shifts": merge_staff_shifts
        }
        for k, v in counts_to_save.items():
            all_settings_to_save.append({"key": k, "start": str(v), "end": ""})

        # --- 保存ボタン（フラグメント内） ---
        st.markdown("---")
        if st.button("💾 デフォルトとして保存", use_container_width=True, type="primary"):
            # 現在の設定を保存
            save_sheet_robust(pd.DataFrame(all_settings_to_save).set_index("key"), "config_times")
            # 特定日の構成を保存
            sp_save_data = []
            for d, c in special_configs.items():
                sp_save_data.append({"year": year, "month": month, "day": d, **c})
            if sp_save_data:
                save_sheet_robust(pd.DataFrame(sp_save_data).set_index("day"), "config_special_days")
            
            st.success("✅ 設定をスプレッドシートに保存しました！")
            time.sleep(1)
            st.rerun()

        # セッションに保存（外部の生成ボタン用）
        st.session_state["_slot_data_map"] = slot_data_map
        st.session_state["_all_settings_to_save"] = all_settings_to_save

    # フラグメントを実行
    all_settings_fragment()

    # --- フラグメントの外で、セッションから最新データを取り出す ---
    h_d_wd = st.session_state.get("h_d_wd", staff_count_defaults["h_d_wd"])
    k_d_wd = st.session_state.get("k_d_wd", staff_count_defaults["k_d_wd"])
    h_n_wd = st.session_state.get("h_n_wd", staff_count_defaults["h_n_wd"])
    k_n_wd = st.session_state.get("k_n_wd", staff_count_defaults["k_n_wd"])
    h_d_we = st.session_state.get("h_d_we", staff_count_defaults["h_d_we"])
    k_d_we = st.session_state.get("k_d_we", staff_count_defaults["k_d_we"])
    h_n_we = st.session_state.get("h_n_we", staff_count_defaults["h_n_we"])
    k_n_we = st.session_state.get("k_n_we", staff_count_defaults["k_n_we"])
    
    transfer_baito_to_staff = st.session_state.get("transfer_baito_to_staff", transfer_baito_default)
    merge_staff_shifts = st.session_state.get("merge_staff_shifts", merge_staff_default)
    selected_special_days = st.session_state.get("special_days_select", [])
    slot_data_map = st.session_state.get("_slot_data_map", {})
    
    # 社員別目標時間をセッションから復元
    w_individual_targets = {}
    if not master_df.empty:
        for name in master_df[master_df["グループ"] == "W"]["名前"].tolist():
            w_individual_targets[name] = st.session_state.get(f"w_target_{name}", monthly_target_default)

    # 特定日設定をセッションから復元
    special_configs = {}
    for d in selected_special_days:
        special_configs[d] = {
            "h_d": st.session_state.get(f"sp_hd_{d}", h_d_we),
            "k_d": st.session_state.get(f"sp_kd_{d}", k_d_we),
            "h_n": st.session_state.get(f"sp_hn_{d}", h_n_we),
            "k_n": st.session_state.get(f"sp_kn_{d}", k_n_we)
        }

    # ★★★ フォームの外 ★★★
    st.markdown("---")
    st.markdown(f"#### 📅 来月（{next_month}月）の祝日と行事")
    if holidays:
        st.warning(" / ".join([f"**{h[0]}日**: {h[1]}" for h in holidays]))
    else:
        st.write("祝日はありません。")

    local_events = get_kitakyushu_events(next_year, next_month)
    if local_events:
        event_text = " / ".join([f"🚩 **{e[0]}日**: {e[1]}" for e in local_events])
        st.info(f"【小倉周辺イベント予定】\n\n{event_text}")
        st.caption("※これらは例年の傾向です。実際の日程は最新情報を確認してください。https://rikumalog.com/event-calendar.html")
    else:
        st.write("地域の大型イベント予定はありません。")

    st.markdown("---")
    gen_button = st.button("🤖 シフトを生成（約30秒）", use_container_width=True)

    # --- 2. 生成ロジック ---
    if gen_button:
        df_stores_all = get_all_stores_cached()
        s_data = df_stores_all[df_stores_all['sheet_url'] == SPREADSHEET_URL].iloc[0]
        # (データの準備、off_req_countsなどは既存通り...)
        # --- 略: データのロード部分 ---
        progress_bar = st.progress(0)
        status_text = st.empty()
        NUM_TRIALS = 5
        best_overall_alerts = []  # ★★★ ここに追加 ★★★
        best_overall_df, min_total_shortage = None, 9999
        
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
# --- 1. 目標出勤日数の計算（最強の安全版） ---
        num_weeks = num_days / 7.0
        
        # 貯金箱から目標率を取得し、万が一空なら0.7にする
        t_rate = st.session_state.get('target_rate')
        if t_rate is None or pd.isna(t_rate) or t_rate == 0:
            t_rate = 0.7

        staff_goals = {}
        for _, row in master_df.iterrows():
            # 名前が空の行（ゴミデータ）は飛ばす
            s_name = str(row.get("名前", "")).strip()
            if not s_name or s_name == "nan":
                continue
                
            # 週希望を数値化（空なら3にする）
            v_req = pd.to_numeric(row.get("週希望"), errors='coerce')
            if pd.isna(v_req):
                v_req = 3.0
            
            # --- 計算の実行 ---
            raw_calc = v_req * num_weeks * t_rate
            
            # 【核心】計算結果が NaN になっていないか最終チェック
            if pd.isna(raw_calc):
                staff_goals[s_name] = 1 # 最悪でも1日
            else:
                # 正常な場合のみ int に変換
                staff_goals[s_name] = max(1, int(raw_calc))

        # --- 2. シフト生成の試行ループ（ここから下は同様） ---
        for trial_idx in range(NUM_TRIALS):
            status_text.text(f"シフト案 {trial_idx + 1} 枚目を計算中...")
            
            # --- 2行化のための名前リスト作成 ---
            EXTENDED_NAMES = []
            for n in ALL_NAMES:
                EXTENDED_NAMES.append(f"{n}")
                EXTENDED_NAMES.append(f"{n} ")
            st.session_state.current_extended_names = EXTENDED_NAMES # 保存！
            # ★★★ コマIDの作成（slot_memory） ★★★
            slot_memory = {}
            for day_idx, col in enumerate(column_names):
                d = day_idx + 1
                d_idx = calendar.weekday(year, month, d)
                if d in selected_special_days:
                    day_slots = slot_data_map.get(d)
                elif d_idx >= 4 or d in holiday_days:
                    day_slots = slot_data_map.get("weekend")
                else:
                    day_slots = slot_data_map.get("weekday")
                if day_slots is None:
                    continue
                for key in ["hd", "kd", "hn", "kn"]:
                    for i, slot_time in enumerate(day_slots.get(key, [])):
                        slot_id = f"{d}_{key}_{i}"
                        slot_memory[slot_id] = {
                            "time": slot_time,
                            "day": d,
                            "col": col,
                            "position": key,
                            "index": i,
                            "assigned_to": None
                        }
           # 表の初期化（EXTENDED_NAMESを使用）
            trial_df = pd.DataFrame("", index=EXTENDED_NAMES, columns=column_names)
            trial_shortage_count, trial_alerts = 0, []
            
            # 累積データ（1ヶ月通してカウント）のリセット
            cumulative_counts = {str(n).strip(): 0 for n in ALL_NAMES}
            consecutive_days = {str(n).strip(): 0 for n in ALL_NAMES}

            # 全スタッフに休み印をあらかじめ印字
            for name in ALL_NAMES:
                n_clean = str(name).strip()
                for col in column_names:
                    # 名前が一致することを確認して参照
                    if req_load.at[n_clean, col]:
                        trial_df.at[name, col] = "✖"

            # --- 3. 1日から末日まで1日ずつ累積で計算 ---
            for day_idx, col in enumerate(column_names):
                assigned_today = []
                d = day_idx + 1
                d_idx = calendar.weekday(year, month, d)
                
                # --- 動的なスロット決定ロジック（祝日・特定日対応） ---
                if d in selected_special_days:
                    target_slots = slot_data_map.get(d)
                elif d_idx >= 4 or d in holiday_days: # 金土日 or 祝日
                    target_slots = slot_data_map.get("weekend")
                else:
                    target_slots = slot_data_map.get("weekday")
                
                # 万が一スロットが取得できなかった場合のガード
                if target_slots is None:
                    continue

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
                            
                            # --- 【重要】ここで時間を分割する ---
                            # s_data はログイン時に取得した店舗情報
                            first_part, second_part = get_split_shift(slot_time, s_data)
                            
                            # 1行目（田中）に前半を書き込む
                            trial_df.at[picked, col] = first_part
                            # ★ スロットメモリに記録
                            slot_id = f"{d}_{key}_{i}"
                            if slot_id in slot_memory:
                                slot_memory[slot_id]["assigned_to"] = picked
                                slot_memory[slot_id]["part1"] = first_part
                                slot_memory[slot_id]["part2"] = second_part if second_part else ""
                            # 2行目（田中 ）に後半を書き込む（分割された場合のみ）
                            if second_part:
                                trial_df.at[f"{picked} ", col] = second_part
                            
                            assigned_today.append(picked)
                            cumulative_counts[picked] += 1
                            consecutive_days[picked] += 1
                        else:
                            trial_shortage_count += 1
                            trial_alerts.append(f"{d}日:{p_name}欠員")
                for name in ALL_NAMES:
                    if name not in assigned_today: consecutive_days[name] = 0
            trial_df.attrs['slot_memory'] = slot_memory
            if trial_shortage_count < min_total_shortage:
                min_total_shortage = trial_shortage_count
                best_overall_df, best_overall_alerts = trial_df, trial_alerts
                best_overall_df.attrs['slot_memory'] = slot_memory.copy()
            progress_bar.progress((trial_idx + 1) / NUM_TRIALS)
        # ==========================================
        # ★ 試行ループ後の処理（共通） ★
        # ==========================================
        if best_overall_df is None:
            st.error("シフト生成に失敗しました。")
            st.stop()

        # ★★★ チェックボックスの状態で分岐 ★★★
        if transfer_baito_to_staff or merge_staff_shifts:
            # --- 1. 2行シフトを1行に統合 ---
            for name in best_overall_df.index:
                if name.endswith(" "): continue
                name2 = f"{name} "
                if name2 not in best_overall_df.index: continue
                for col in column_names:
                    v1 = str(best_overall_df.at[name, col]).strip()
                    v2 = str(best_overall_df.at[name2, col]).strip()
                    if "-" in v1 and "-" in v2 and v1 != "✖" and v2 != "✖":
                        best_overall_df.at[name, col] = f"{v1.split('-')[0]}-{v2.split('-')[1]}"
                        best_overall_df.at[name2, col] = ""

        # ==========================================
        # ★★★ ステップ3：Wの短時間シフトを延長 ★★★
        # ==========================================
        w_staff_list = []
        if not master_df.empty:
            w_staff_list = master_df[master_df["グループ"] == "W"]["名前"].tolist()
        w_names = [str(n).strip() for n in w_staff_list]

        extend_log = []
        extend_count = 0

        if best_overall_df is not None and w_names:
            for w_name in w_names:
                name2 = f"{w_name} "
                for col in column_names:
                    v1 = str(best_overall_df.at[w_name, col]).strip() if w_name in best_overall_df.index else ""
                    v2 = str(best_overall_df.at[name2, col]).strip() if name2 in best_overall_df.index else ""

                    # 1行目のみシフトがある → 終了時間を延長
                    if "-" in v1 and v2 in ["", "nan", "None"]:
                        try:
                            start1 = v1.split("-")[0]
                            end1 = v1.split("-")[1]
                            e1 = time_to_float(end1)

                            # 午前シフト（17時前に終わる）→ 18時まで延長
                            if e1 < 17:
                                new_end = min(e1 + 3, 18)  # 最大3時間延長、18時まで
                                new_end_str = float_to_time(new_end)
                                extended = f"{start1}-{new_end_str}"

                                n_old, _ = calc_work_and_break(v1)
                                n_new, _ = calc_work_and_break(extended)
                                gained = n_new - n_old

                                if gained > 0:
                                    best_overall_df.at[w_name, col] = extended
                                    extend_log.append(f"⏫ {w_name} {col}: {v1} → {extended} (+{gained:.1f}h)")
                                    extend_count += 1
                        except:
                            pass

                    # 2行目のみシフトがある → 開始時間を早める
                    if v1 in ["", "nan", "None"] and "-" in v2:
                        try:
                            start2 = v2.split("-")[0]
                            end2 = v2.split("-")[1]
                            s2 = time_to_float(start2)

                            # 夜シフト（15時以降開始）→ 14時まで早める
                            if s2 > 15:
                                new_start = max(s2 - 3, 14)
                                new_start_str = float_to_time(new_start)
                                extended = f"{new_start_str}-{end2}"

                                n_old, _ = calc_work_and_break(v2)
                                n_new, _ = calc_work_and_break(extended)
                                gained = n_new - n_old

                                if gained > 0:
                                    best_overall_df.at[name2, col] = extended
                                    extend_log.append(f"⏫ {w_name} {col}: {v2} → {extended} (+{gained:.1f}h)")
                                    extend_count += 1
                        except:
                            pass
# ==========================================
        # ★★★ ステップ4：Wの合計実働 To の計算 ★★★
        # ==========================================
        # 1. 基準となる目標時間を取得（UIの入力を最優先）
        # フラグメント内の number_input の key は "f_monthly_target" などにしているか確認してください
        monthly_target_hours = st.session_state.get('monthly_target_hours', 168.0) # デフォルトを168に変更

        # 2. 個別目標の取得
        w_individual_targets = st.session_state.get('w_individual_targets', {})
        
        # 3. もし個別目標が空（初回実行など）なら、スプレッドシート(config_times)から読み込む
        if not w_individual_targets:
            stored_df = load_sheet_no_cache("config_times", pd.DataFrame())
            stored_times = stored_df.to_dict('index') if not stored_df.empty else {}
            for key, val in stored_times.items():
                if key.startswith("w_target_"):
                    name = key.replace("w_target_", "")
                    # ここでも 160 ではなく monthly_target_hours をデフォルトにする
                    w_individual_targets[name] = float(val.get("start", monthly_target_hours))

        # 万が一まだ空なら全員分を monthly_target_hours で埋める
        w_staff_list = master_df[master_df["グループ"] == "W"]["名前"].tolist()
        for name in w_staff_list:
            if name not in w_individual_targets:
                w_individual_targets[name] = monthly_target_hours

        w_names = [str(n).strip() for n in w_staff_list] if 'w_staff_list' in dir() else []

        # 実働時間計算関数
        def calc_total_hours(df, name):
            """DataFrame から1人の合計実働時間を計算する"""
            net = 0.0
            if name not in df.index:
                return 0.0
            for c in column_names:
                val = str(df.at[name, c]).strip()
                if "-" in val and val != "✖":
                    n, _ = calc_work_and_break(val)
                    net += n
                name2 = f"{name} "
                if name2 in df.index:
                    val2 = str(df.at[name2, c]).strip()
                    if "-" in val2 and val2 != "✖":
                        n2, _ = calc_work_and_break(val2)
                        net += n2
            return round(net, 1)

        # 各Wの実働時間を計算
        staff_hours = {}
        for name in w_names:
            staff_hours[name] = calc_total_hours(best_overall_df, name)

        # ==========================================
        # ★ ステップ5準備：Wの空きコマリストを作成（拡張版） ★
        # ==========================================
        staff_free_slots = {}  # { w_name: [ { "slot": "1_d", "other_filled": True, "day": 1, "part": "d" }, ... ] }

        if best_overall_df is not None and 'slot_memory' in best_overall_df.attrs:
            slot_memory = best_overall_df.attrs['slot_memory']

        for w_name in w_names:
            free = []
            for col in column_names:
                if req_load.at[w_name, col]:
                    continue

                d_num = int("".join(filter(str.isdigit, col.split('(')[0])))

                # この日の出勤状況をslot_memoryから確認
                has_day = False
                has_night = False
                for sid, sdata in slot_memory.items():
                    if sdata.get("day") == d_num and sdata.get("assigned_to") == w_name:
                        pos = sdata.get("position", "")
                        if pos in ("hd", "kd"):
                            has_day = True
                        elif pos in ("hn", "kn"):
                            has_night = True

                if not has_day:
                    free.append({
                        "slot": f"{d_num}_d",
                        "other_filled": has_night,  # 夜が埋まっていればTrue
                        "day": d_num,
                        "part": "d"
                    })
                if not has_night:
                    free.append({
                        "slot": f"{d_num}_n",
                        "other_filled": has_day,
                        "day": d_num,
                        "part": "n"
                    })

            staff_free_slots[w_name] = free

        # ==========================================
        # ★ ステップ5.2：空きコマの距離スコアリング ★
        # ==========================================
        def calculate_slot_cost(staff_name, day_num, part, other_filled, df, column_names):
            """ある空きコマに入る場合の連勤コストを計算する。低いほど良い。"""
            cost = 0

            # 該当日の列を特定
            target_col = None
            for c in column_names:
                d = int("".join(filter(str.isdigit, c.split('(')[0])))
                if d == day_num:
                    target_col = c
                    break
            if target_col is None:
                return 9999

            target_idx = column_names.index(target_col)

            # 同じ日の別時間帯が埋まっていれば -100（ロングシフト化を促進）
            if other_filled:
                cost -= 100

            # 直前・直後（±1日）に仕事があるか
            for offset in [-1, 1]:
                ni = target_idx + offset
                if 0 <= ni < len(column_names):
                    nc = column_names[ni]
                    v1 = str(df.at[staff_name, nc]).strip() if staff_name in df.index else ""
                    v2 = str(df.at[f"{staff_name} ", nc]).strip() if f"{staff_name} " in df.index else ""
                    if ("-" in v1 and v1 != "✖") or ("-" in v2 and v2 != "✖"):
                        cost += 100

            # 2日離れているか
            for offset in [-2, 2]:
                ni = target_idx + offset
                if 0 <= ni < len(column_names):
                    nc = column_names[ni]
                    v1 = str(df.at[staff_name, nc]).strip() if staff_name in df.index else ""
                    v2 = str(df.at[f"{staff_name} ", nc]).strip() if f"{staff_name} " in df.index else ""
                    if ("-" in v1 and v1 != "✖") or ("-" in v2 and v2 != "✖"):
                        cost += 30

            # 現在の連勤数に応じたペナルティ
            # 前後に連続何日働いているかカウント
            cons_before = 0
            ci = target_idx - 1
            while ci >= 0:
                nc = column_names[ci]
                v1 = str(df.at[staff_name, nc]).strip() if staff_name in df.index else ""
                v2 = str(df.at[f"{staff_name} ", nc]).strip() if f"{staff_name} " in df.index else ""
                if ("-" in v1 and v1 != "✖") or ("-" in v2 and v2 != "✖"):
                    cons_before += 1
                    ci -= 1
                else:
                    break
            cons_after = 0
            ci = target_idx + 1
            while ci < len(column_names):
                nc = column_names[ci]
                v1 = str(df.at[staff_name, nc]).strip() if staff_name in df.index else ""
                v2 = str(df.at[f"{staff_name} ", nc]).strip() if f"{staff_name} " in df.index else ""
                if ("-" in v1 and v1 != "✖") or ("-" in v2 and v2 != "✖"):
                    cons_after += 1
                    ci += 1
                else:
                    break

            new_streak = cons_before + 1 + cons_after  # この日を入れた場合の連続日数
            if new_streak >= 4:
                cost += 500
            elif new_streak == 3:
                cost += 200

            # ランダム要素 (0〜10)
            cost += random.uniform(0, 10)

            return cost

        # 各Wの空きコマのコストを計算
        staff_slot_costs = {}  # { w_name: [ { "slot": ..., "cost": ... }, ... ] }
        for w_name in w_names:
            free_list = staff_free_slots.get(w_name, [])
            cost_list = []
            for slot_info in free_list:
                cost = calculate_slot_cost(
                    w_name, slot_info["day"], slot_info["part"],
                    slot_info["other_filled"], best_overall_df, column_names
                )
                cost_list.append({
                    "slot": slot_info["slot"],
                    "day": slot_info["day"],
                    "part": slot_info["part"],
                    "other_filled": slot_info["other_filled"],
                    "cost": cost
                })
            # コストの低い順にソート
            cost_list.sort(key=lambda x: x["cost"])
            staff_slot_costs[w_name] = cost_list

        # ==========================================
        # ★ ステップ6：目標達成ループ（仕様準拠版） ★
        # ==========================================
        # Wの実働時間を再計算する関数
        def recalc_all_w_hours(df, w_names):
            hours = {}
            for name in w_names:
                net = 0.0
                for c in column_names:
                    for n in [name, f"{name} "]:
                        if n in df.index:
                            val = str(df.at[n, c]).strip()
                            if "-" in val and val != "✖":
                                n_net, _ = calc_work_and_break(val)
                                net += n_net
                hours[name] = round(net, 1)
            return hours

        # バイトの充足率（日数ベース）を返す
        def get_baito_fulfillment(df, name):
            days = 0
            for c in column_names:
                val = str(df.at[name, c]).strip() if name in df.index else ""
                if "-" in val and val != "✖":
                    days += 1
            goal = staff_goals.get(name, 1)
            return days / max(goal, 1)

        # メインループ
        loop_count = 0
        max_loops = 300
        staff_slot_costs_copy = {name: list(costs) for name, costs in staff_slot_costs.items()}

        while loop_count < max_loops:
            # 現在の実働を再計算
            current_hours = recalc_all_w_hours(best_overall_df, w_names)

            # 目標未達のWがいるか確認
            all_achieved = True
            for name in w_names:
                target = w_individual_targets.get(name, monthly_target_hours)
                if current_hours[name] < target:
                    all_achieved = False
                    break
            if all_achieved:
                st.success("🎉 全Wが目標時間に到達しました！")
                break

            # 全Wの中で最もコストが低い空きコマを1つ選ぶ
            best_overall_candidate = None
            best_w_name = None
            for w_name in w_names:
                costs = staff_slot_costs_copy.get(w_name, [])
                if not costs:
                    continue
                # このWの最優先候補（コスト最小）
                candidate = costs[0]
                if best_overall_candidate is None or candidate["cost"] < best_overall_candidate["cost"]:
                    best_overall_candidate = candidate
                    best_w_name = w_name

            if best_overall_candidate is None:
                st.warning("⚠️ 有効な空きコマがなくなりました。手動調整が必要です。")
                break

            # 選ばれた空きコマ情報
            target_slot_name = best_overall_candidate["slot"]  # 例: "17_n"
            target_day = best_overall_candidate["day"]
            target_part = best_overall_candidate["part"]

            # --- この空きコマに対応するスロットを slot_memory からリストアップ ---
            target_slot_ids = []
            for sid, sdata in slot_memory.items():
                if sdata.get("day") == target_day:
                    pos = sdata["position"]
                    if target_part == "d" and pos in ("hd", "kd"):
                        target_slot_ids.append((sid, sdata))
                    elif target_part == "n" and pos in ("hn", "kn"):
                        target_slot_ids.append((sid, sdata))

            if not target_slot_ids:
                # スロットが見つからなければこの候補を削除して次へ
                staff_slot_costs_copy[best_w_name].pop(0)
                continue

            # --- 充足率が最大のバイトを選ぶ ---
            best_slot = None
            best_baito_name = None
            best_baito_rate = -1
            for sid, sdata in target_slot_ids:
                baito_name = sdata.get("assigned_to")
                if baito_name is None or baito_name in w_names:
                    continue
                rate = get_baito_fulfillment(best_overall_df, baito_name)
                if rate > best_baito_rate:
                    best_baito_rate = rate
                    best_baito_name = baito_name
                    best_slot = (sid, sdata)

            if best_slot is None:
                # 適切なバイトがいなければこの候補を削除して次へ
                staff_slot_costs_copy[best_w_name].pop(0)
                continue

            # --- スワップ実行 ---
            baito_name = best_baito_name
            sid, sdata = best_slot
            col = sdata["col"]
            baito_val = str(best_overall_df.at[baito_name, col]).strip()
            if baito_val == "" or baito_val == "✖":
                staff_slot_costs_copy[best_w_name].pop(0)
                continue

            # Wの該当セルに書き込み（昼なら1行目、夜なら2行目優先）
            w_name = best_w_name
            name2 = f"{w_name} "
            v1 = str(best_overall_df.at[w_name, col]).strip() if w_name in best_overall_df.index else ""
            v2 = str(best_overall_df.at[name2, col]).strip() if name2 in best_overall_df.index else ""

            if target_part == "d":
                if v1 in ["", "nan"]:
                    best_overall_df.at[w_name, col] = baito_val
                else:
                    staff_slot_costs_copy[best_w_name].pop(0)
                    continue
            else:  # target_part == "n"
                if name2 in best_overall_df.index and v2 in ["", "nan"]:
                    best_overall_df.at[name2, col] = baito_val
                elif v1 in ["", "nan"]:
                    best_overall_df.at[w_name, col] = baito_val
                else:
                    staff_slot_costs_copy[best_w_name].pop(0)
                    continue

            # バイトのセルを空にする
            best_overall_df.at[baito_name, col] = ""
            # slot_memory 更新
            sdata["assigned_to"] = w_name

            # --- ロングシフト化（同じ日に昼と夜が揃ったら連結） ---
            v1 = str(best_overall_df.at[w_name, col]).strip() if w_name in best_overall_df.index else ""
            v2 = str(best_overall_df.at[name2, col]).strip() if name2 in best_overall_df.index else ""
            if "-" in v1 and "-" in v2 and v1 != "✖" and v2 != "✖":
                try:
                    merged = f"{v1.split('-')[0]}-{v2.split('-')[1]}"
                    best_overall_df.at[w_name, col] = merged
                    best_overall_df.at[name2, col] = ""
                except:
                    pass

            # --- 使用した空きコマをリストから削除 ---
            # 今回使った空きコマ（target_slot_name）を削除
            staff_slot_costs_copy[best_w_name] = [
                c for c in staff_slot_costs_copy[best_w_name] if c["slot"] != target_slot_name
            ]

            loop_count += 1

        # 最終集計
        final_hours = recalc_all_w_hours(best_overall_df, w_names)
        # ★★★ 実働時間計算関数（最終微調整用） ★★★
        def calc_hours(df, name):
            net = 0.0
            for c in column_names:
                for n in [name, f"{name} "]:
                    if n in df.index:
                        val = str(df.at[n, c]).strip()
                        if "-" in val and val != "✖":
                            n_net, _ = calc_work_and_break(val)
                            net += n_net
            return round(net, 1)
        # ==========================================
        # ★ 最終微調整（0.5h単位の不足を強制解消） ★
        # ==========================================
        for name in w_names:
            target = w_individual_targets.get(name, monthly_target_hours)
            current = calc_hours(best_overall_df, name)
            deficit = target - current

            if deficit > 0:
                # 最も短いシフトを探して延長
                shortest_col = None
                shortest_duration = 999
                for col in column_names:
                    v1 = str(best_overall_df.at[name, col]).strip() if name in best_overall_df.index else ""
                    if "-" in v1 and v1 != "✖":
                        try:
                            s = time_to_float(v1.split("-")[0])
                            e = time_to_float(v1.split("-")[1])
                            dur = e - s
                            if dur < shortest_duration:
                                shortest_duration = dur
                                shortest_col = col
                        except:
                            pass

                if shortest_col:
                    v1 = str(best_overall_df.at[name, shortest_col]).strip()
                    start1 = v1.split("-")[0]
                    end1 = v1.split("-")[1]
                    e1 = time_to_float(end1)
                    # 0.5時間単位で延長
                    new_end = float_to_time(e1 + 0.5)
                    extended = f"{start1}-{new_end}"
                    best_overall_df.at[name, shortest_col] = extended

# ==========================================
        # ★ 全スタッフ対象：最終的な2行分割処理（✖の2列目を空にする） ★
        # ==========================================
        status_text.text("全スタッフの休憩分割を適用中...")

        for name in ALL_NAMES:
            clean_name = str(name).strip()
            name2 = f"{clean_name} "
            
            # 名簿の名前が表に存在しない場合はスキップ
            if clean_name not in best_overall_df.index:
                continue

            for col in column_names:
                # 1行目の値を取得
                v1 = str(best_overall_df.at[clean_name, col]).strip()
                
                # --- A. 休み（✖）の処理 ---
                if v1 == "✖":
                    if name2 in best_overall_df.index:
                        best_overall_df.at[name2, col] = "" # 2行目は空にする
                    continue # この日の処理は終わり

                # --- B. シフト（10:00-18:00など）の処理 ---
                v2 = str(best_overall_df.at[name2, col]).strip() if name2 in best_overall_df.index else ""

                # 1行目にのみシフトがあり、2行目が空の場合のみ分割を実行
                if "-" in v1 and v2 in ["", "nan", "None"]:
                    part1, part2 = get_split_shift(v1, s_data)
                    if part2:
                        best_overall_df.at[clean_name, col] = part1
                        best_overall_df.at[name2, col] = part2

        # ==========================================
        # ★ 最終達成状況の表示（ここから下に続く） ★
        # ==========================================
        st.subheader("📊 社員の労働時間 達成状況")
        # （ここは以前の W の達成状況表示コードをそのまま入れる）
        final_all_ok = True
        for name in w_names:
            target = w_individual_targets.get(name, monthly_target_hours)
            h = calc_hours(best_overall_df, name)
            if h >= target:
                st.success(f"✅ {name}: {h:.1f}h / {target:.0f}h")
            else:
                final_all_ok = False
                st.warning(f"⚠️ {name}: {h:.1f}h / {target:.0f}h (不足 {target-h:.1f}h)")
        
        if final_all_ok:
            st.balloons()
# ==========================================
        # ★ 最終欠員集計ロジック（ここを差し替え） ★
        # ==========================================
        status_text.text("最終的な欠員状況を確認中...")
        
        final_shortage_alerts = []
        
        # slot_memory（ステップ1で作った全必要枠のリスト）をスキャンする
        if 'slot_memory' in best_overall_df.attrs:
            actual_memory = best_overall_df.attrs['slot_memory']
            
            # 日付ごとに欠員をまとめるための辞書 { 日: [欠員ポジション1, 2...] }
            day_shortages = {}
            
            for sid, data in actual_memory.items():
                # その枠に誰も割り当てられていない、または名前が空の場合
                # 注意：assigned_to はステップ3のスワップ処理でも正しく更新されている必要があります
                assigned = data.get("assigned_to")
                
                # 念のため、実際の表(best_overall_df)のその場所が本当に空かどうかも再確認
                col = data["col"]
                name = assigned if assigned else ""
                
                # 表の中でその人がその日働いているかチェック
                is_filled = False
                if name:
                    v1 = str(best_overall_df.at[name, col]).strip() if name in best_overall_df.index else ""
                    v2 = str(best_overall_df.at[f"{name} ", col]).strip() if f"{name} " in best_overall_df.index else ""
                    if "-" in v1 or "-" in v2:
                        is_filled = True
                
                if not is_filled:
                    d = data["day"]
                    pos_jp = {"hd":"H昼", "kd":"K昼", "hn":"H夜", "kn":"K夜"}.get(data["position"], data["position"])
                    if d not in day_shortages:
                        day_shortages[d] = []
                    day_shortages[d].append(pos_jp)

            # 辞書をメッセージ形式に変換
            for d in sorted(day_shortages.keys()):
                positions = day_shortages[d]
                # 同じポジションが複数ある場合は「H昼×2」のように表示
                from collections import Counter
                pos_counts = Counter(positions)
                pos_str = ", ".join([f"{p}×{count}" if count > 1 else p for p, count in pos_counts.items()])
                final_shortage_alerts.append(f"{d}日: {pos_str} 欠員")

        # ==========================================
        # ★ 最終保存 ★
        # ==========================================
        st.session_state.last_generated_df = best_overall_df
        # 修正ポイント：空にするのではなく、計算した final_shortage_alerts を入れる
        st.session_state.last_shortage_alerts = final_shortage_alerts
        
        status_text.empty()
        progress_bar.empty()
        
        if not final_shortage_alerts:
            st.balloons()
            st.success("✅ 欠員なし！全てのシフトが埋まりました。")
        else:
            st.warning(f"⚠️ シフトは生成されましたが、{len(final_shortage_alerts)}日分の欠員があります。")




    # --- 3. 結果の表示（最適化後・完全版） ---
    if st.session_state.last_generated_df is not None:
        EXT_NAMES = st.session_state.last_generated_df.index.tolist()
        st.subheader("🤖 生成されたシフト案の確認")

        display_df = st.session_state.last_generated_df.copy()
        display_df = display_df.reset_index()
        display_df.rename(columns={'index': '名前'}, inplace=True)

        for i in range(len(display_df)):
            if i % 2 != 0:
                display_df.at[i, '名前'] = ""

        # Wグループの色分け用
        w_names = []
        if not master_df.empty:
            w_names = master_df[master_df["グループ"] == "W"]["名前"].tolist()

        def style_shift_enhanced(df):
            styles = pd.DataFrame('', index=df.index, columns=df.columns)

            for r_idx in range(len(df)):
                is_second_row = (r_idx % 2 != 0)

                if is_second_row:
                    row_name = str(df.iloc[r_idx - 1]['名前']).strip() if r_idx > 0 else ""
                else:
                    row_name = str(df.iloc[r_idx]['名前']).strip()

                for c_idx, col_name in enumerate(df.columns):
                    bg_color = ""
                    if col_name == '名前':
                        bg_color = "background-color: #f8f9fa;"
                    else:
                        try:
                            d = int(col_name.split('(')[0])
                            d_idx = calendar.weekday(year, month, d)
                            is_holiday = d in holiday_days
                            if is_holiday or d_idx == 6:
                                bg_color = "background-color: #ffe6e6;"
                            elif d_idx == 5:
                                bg_color = "background-color: #e6f3ff;"

                            if row_name in w_names:
                                val = str(df.iloc[r_idx, c_idx]).strip()
                                if "-" in val and val != "✖":
                                    try:
                                        start_h = time_to_float(val.split("-")[0])
                                        if start_h >= 15:
                                            bg_color = "background-color: #FFF3E0;"
                                        else:
                                            bg_color = "background-color: #E8F5E9;"
                                    except:
                                        pass
                        except:
                            pass

                    if is_second_row:
                        border = "border-top: none !important; border-bottom: 2px solid #555 !important;"
                    else:
                        border = "border-top: 2px solid #555 !important; border-bottom: 1px dashed #ccc !important;"

                    styles.iloc[r_idx, c_idx] = bg_color + border

                    if str(df.iloc[r_idx, c_idx]).strip() == "✖":
                        styles.iloc[r_idx, c_idx] += "color: #E60012; font-weight: bold;"
            return styles

        st.dataframe(
            display_df.style.apply(style_shift_enhanced, axis=None),
            use_container_width=True,
            height=650,
            hide_index=True
        )

        st.divider()
        st.subheader("📥 シフト表をダウンロード")

# --- Excel出力（4行レイアウト・動的計算式版） ---
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
            # 1. 出力用データの準備（2行→4行セットに加工）
            export_df = st.session_state.last_generated_df.copy()
            export_df = export_df.reset_index()
            export_df.rename(columns={'index': '名前'}, inplace=True)

            # グループ列を追加
            name_to_group = {}
            if not master_df.empty and "名前" in master_df.columns and "グループ" in master_df.columns:
                name_to_group = master_df.set_index("名前")["グループ"].to_dict()
            groups = [name_to_group.get(str(n).strip(), "") for n in export_df['名前']]
            export_df.insert(0, "グループ", groups)

            # 空の合計列を追加
            export_df["合計実働"] = ""
            export_df["休憩合計"] = ""
            export_df["充足率"] = ""
            # ★ 2行ごとに計算行(2行)を挿入（4行で1セット）
            new_rows = []
            for i in range(len(export_df)):
                new_rows.append(export_df.iloc[i].to_dict())
                if i % 2 == 1:      # 後半行の直後に計算行・休憩行を追加
                    calc_row = {col: "" for col in export_df.columns}
                    break_row = {col: "" for col in export_df.columns}
                    new_rows.append(calc_row)
                    new_rows.append(break_row)
            export_df = pd.DataFrame(new_rows)

            # 2. Excelシートへ書き出し
            export_df.to_excel(writer, sheet_name='シフト表', startrow=3, index=False)
            workbook = writer.book
            worksheet = writer.sheets['シフト表']

            # 3. 印刷設定
            worksheet.set_portrait()
            worksheet.set_paper(9)
            worksheet.set_margins(0.3, 0.3, 0.3, 0.3)
            worksheet.center_horizontally()
            worksheet.fit_to_pages(1, 0)

            # 4. タイトル
            title_fmt = workbook.add_format({
                'bold': True, 'size': 22, 'align': 'center', 'valign': 'vcenter',
                'font_name': 'Meiryo UI', 'color': '#333333'
            })
            total_cols = len(export_df.columns)
            store_name = st.session_state.get("store_name", "ジョイフル")
            worksheet.merge_range(0, 0, 0, total_cols - 1,
                                  f"{year}年{month}月　{store_name}　シフト表", title_fmt)
            worksheet.set_row(0, 40)
            worksheet.set_row(1, 8)

            # 5. 書式定義
            # --- 合計行用の書式定義 ---
            fmt_total_combined = workbook.add_format({
                'bold': True,           # 太字
                'border': 2,            # 外枠を太く
                'bg_color': "#D0FFCC",  # 薄い黄色（合計とわかりやすくするため）
                'align': 'center',      # 中央揃え
                'valign': 'vcenter',    # 上下中央揃え
                'num_format': '0.0',    # 小数点第1位まで表示
                'size': 17            # 文字サイズを少し大きく
            })
            fmt_pct = workbook.add_format({
                'bold': True,
                'border': 2,
                'bg_color': '#E1F5FE',
                'align': 'center',
                'valign': 'vcenter', 
                'num_format': '0%', 
                'size': 16,
                'font_name': 'Meiryo UI'
            })
            fmt_header = workbook.add_format({
                'bold': True, 'border': 2, 'bg_color': '#D9D9D9',
                'align': 'center', 'valign': 'vcenter', 'size': 15, 'font_name': 'Meiryo UI'
            })
            fmt_merge = workbook.add_format({
                'bold': True, 'top': 2, 'bottom': 2, 'left': 1, 'right': 1,
                'bg_color': '#F2F2F2', 'align': 'center', 'valign': 'vcenter',
                'size': 17, 'font_name': 'Meiryo UI'
            })
            fmt_row1 = workbook.add_format({
                'left': 1, 'right': 1, 'top': 2, 'bottom': 7,
                'align': 'center', 'valign': 'vcenter', 'size': 14, 'font_name': 'Arial Narrow'
            })
            fmt_row2 = workbook.add_format({
                'left': 1, 'right': 1, 'top': 7, 'bottom': 2,
                'align': 'center', 'valign': 'vcenter', 'size': 14, 'font_name': 'Arial Narrow'
            })
            fmt_calc = workbook.add_format({
                'left': 1, 'right': 1, 'top': 2, 'bottom': 2,
                'bg_color': '#FFFFCC', 'align': 'center', 'valign': 'vcenter',
                'num_format': '0.00', 'size': 10, 'font_name': 'Meiryo UI'
            })
            fmt_break = workbook.add_format({
                'left': 1, 'right': 1, 'top': 2, 'bottom': 2,
                'bg_color': '#FFE0B2', 'align': 'center', 'valign': 'vcenter',
                'num_format': '0.00', 'size': 8, 'font_name': 'Meiryo UI'
            })
            fmt_total = workbook.add_format({
                'bold': True, 'top': 2, 'bottom': 2, 'left': 1, 'right': 1,
                'bg_color': '#FFFFCC', 'align': 'center', 'valign': 'vcenter',
                'num_format': '0.00', 'size': 14, 'font_name': 'Meiryo UI'
            })
        
            fmt_sat = workbook.add_format({
                'bold': True, 'border': 2, 'bg_color': '#E6F3FF', 'font_color': '#0000FF',
                'align': 'center', 'valign': 'vcenter', 'size': 16, 'font_name': 'Meiryo UI'
            })
            fmt_sun = workbook.add_format({
                'bold': True, 'border': 2, 'bg_color': '#FFE6E6', 'font_color': '#FF0000',
                'align': 'center', 'valign': 'vcenter', 'size': 16, 'font_name': 'Meiryo UI'
            })

            # 6. ヘッダー行
            header_row = 2
            worksheet.set_row(header_row, 24)
            h_list = [h[0] for h in get_month_holidays_list(year, month)]

            for c_idx, col_name in enumerate(export_df.columns):
                if col_name == "グループ":
                    worksheet.write(header_row, c_idx, "G", fmt_header)
                elif col_name == "名前":
                    worksheet.write(header_row, c_idx, "名前", fmt_header)
                elif col_name in ["合計実働", "休憩合計","充足率"]:
                    worksheet.write(header_row, c_idx, col_name, fmt_header)
                else:
                    try:
                        d_str = "".join(filter(str.isdigit, str(col_name).split('(')[0]))
                        d = int(d_str)
                        d_idx = calendar.weekday(year, month, d)
                        if d in h_list or d_idx == 6:
                            worksheet.write(header_row, c_idx, col_name, fmt_sun)
                        elif d_idx == 5:
                            worksheet.write(header_row, c_idx, col_name, fmt_sat)
                        else:
                            worksheet.write(header_row, c_idx, col_name, fmt_header)
                    except:
                        worksheet.write(header_row, c_idx, col_name, fmt_header)

# --- 7. 変数の定義と列幅の設定 ---
            # まず計算の基準となる数値を定義します（これで NameError を防ぎます）
            date_start = 2
            num_dates = len(column_names)
            total_col = date_start + num_dates
            break_col = total_col + 1
            fulfillment_col = break_col + 1 # 充足率の列番号

            # 列幅の設定
            worksheet.set_column(0, 0, 5)    # G列
            worksheet.set_column(1, 1, 18)   # 名前列
            for i in range(num_dates):
                worksheet.set_column(date_start + i, date_start + i, 11) # 日付列
            
            # 右端の集計3列（合計・休憩・充足率）の幅を一括設定
            worksheet.set_column(total_col, fulfillment_col, 10)

            # --- 8. ヘルパー関数 ---
            def col_letter(idx):
                if idx < 26: return chr(65 + idx)
                return chr(64 + idx // 26) + chr(65 + idx % 26)

            def get_dur_formula(ref):
                return (
                    f'IFERROR('
                    f'(LEFT(MID({ref},FIND("-",{ref})+1,10),FIND(":",MID({ref},FIND("-",{ref})+1,10))-1)'
                    f'+RIGHT(MID({ref},FIND("-",{ref})+1,10),2)/60)'
                    f'-'
                    f'(LEFT(LEFT({ref},FIND("-",{ref})-1),FIND(":",LEFT({ref},FIND("-",{ref})-1))-1)'
                    f'+RIGHT(LEFT({ref},FIND("-",{ref})-1),2)/60)'
                    f',0)'
                )

# --- 9. データ行（4行セット）の書き込み ---
            for i in range(0, len(export_df), 4):   # 4行ずつ処理
                base_row = header_row + 1 + i
                if i + 3 >= len(export_df):
                    continue

                name = str(export_df.iloc[i]["名前"]).strip()
                group = str(export_df.iloc[i]["グループ"]).strip()

                # Excelの行番号（1始まり）を定義
                r1 = base_row + 1      # 1行目（前半）
                r2 = base_row + 2      # 2行目（後半）
                r3 = base_row + 3      # 3行目（実働計算行）
                r4 = base_row + 4      # 4行目（休憩計算行）

                # グループ・名前・合計・休憩・充足率の各列を4行マージ
                worksheet.merge_range(base_row, 0, base_row + 3, 0, group, fmt_merge)
                worksheet.merge_range(base_row, 1, base_row + 3, 1, name, fmt_merge)

                # 行の高さ設定
                worksheet.set_row(base_row, 23)      # 1行目
                worksheet.set_row(base_row + 1, 23)  # 2行目
                worksheet.set_row(base_row + 2, 12)  # 3行目
                # 4行目（休憩詳細）はデータ集計用なので非表示にする設定
                worksheet.set_row(base_row + 3, 17, None, {'hidden': True})

                # 日付列のループ
                for c in range(date_start, date_start + num_dates):
                    cl = col_letter(c)
                    ref1 = f"{cl}{r1}"
                    ref2 = f"{cl}{r2}"

                    val1 = str(export_df.iloc[i, c]) if c < export_df.shape[1] else ""
                    val2 = str(export_df.iloc[i+1, c]) if c < export_df.shape[1] else ""

                    # シフト時間を書き込み
                    worksheet.write(base_row, c, val1 if val1 != "nan" else "", fmt_row1)
                    worksheet.write(base_row + 1, c, val2 if val2 != "nan" else "", fmt_row2)

                    # --- 3行目：日次実働計算（動的） ---
                    d1 = get_dur_formula(ref1)
                    d2 = get_dur_formula(ref2)
                    worksheet.write_formula(base_row + 2, c, f"={d1}+{d2}", fmt_calc)

                    # --- 4行目：日次休憩計算（動的） ---
                    s2 = f'LEFT(LEFT({ref2},FIND("-",{ref2})-1),FIND(":",LEFT({ref2},FIND("-",{ref2})-1))-1)+RIGHT(LEFT({ref2},FIND("-",{ref2})-1),2)/60'
                    e1 = f'LEFT(MID({ref1},FIND("-",{ref1})+1,10),FIND(":",MID({ref1},FIND("-",{ref1})+1,10))-1)+RIGHT(MID({ref1},FIND("-",{ref1})+1,10),2)/60'
                    brk_f = f'=IF(AND({ref1}<>"",{ref2}<>"",ISNUMBER(FIND("-",{ref1})),ISNUMBER(FIND("-",{ref2}))),({s2})-({e1}),0)'
                    worksheet.write_formula(base_row + 3, c, brk_f, fmt_break)

                # --- 右端：月合計（SUM数式） ---
                col_start = col_letter(date_start)
                col_end = col_letter(date_start + num_dates - 1)

                # 合計実働マージ
                worksheet.merge_range(base_row, total_col, base_row + 3, total_col, 
                                      f"=SUM({col_start}{r3}:{col_end}{r3})", fmt_total)

                # 休憩合計マージ
                worksheet.merge_range(base_row, break_col, base_row + 3, break_col,
                                      f"=SUM({col_start}{r4}:{col_end}{r4})", fmt_total)

                # --- ★★★ 充足率の【動的】計算と書き込み ★★★ ---
                # 1. 本人の「週希望」から「今月の目標出勤日数」を計算（定数として埋め込む）
                weekly_pref = 3 
                if not master_df.empty:
                    match = master_df[master_df["名前"] == name]
                    if not match.empty:
                        weekly_pref = pd.to_numeric(match.iloc[0]["週希望"], errors='coerce') or 3
                
                target_days = (weekly_pref / 7) * num_dates
                
                # 2. Excel数式の作成
                # 仕組み：3行目（実働）が0より大きい日をCOUNTIFで数え、目標日数で割る
                # 範囲は 3行目(r3) の 1日〜末日まで
                actual_days_formula = f'COUNTIF({col_start}{r3}:{col_end}{r3},">0")'
                dynamic_fulfillment_formula = f"={actual_days_formula}/{target_days}"

                # 3. 4行マージセルに数式を書き込み
                worksheet.merge_range(base_row, fulfillment_col, base_row + 3, fulfillment_col, 
                                      dynamic_fulfillment_formula, fmt_pct)

            worksheet.freeze_panes(header_row + 1, 2)
# --- 10. 最終行：日別合計（総人時）の計算 ---
            total_row_idx = header_row + 1 + len(export_df)
            worksheet.set_row(total_row_idx, 25)

            worksheet.merge_range(total_row_idx, 0, total_row_idx, 1, "日別合計人時", fmt_total_combined)

            first_data_row = header_row + 2
            last_data_row = header_row + 1 + len(export_df)

            # 各日付（C列〜）の合計：ここは3行目と4行目が混在しているので、MODを使って3行目(実働)だけを狙う
            for c in range(date_start, date_start + num_dates):
                cl = col_letter(c)
                # 日別合計は、MOD=2（実働行）だけを正確に拾う
                sum_formula = (
                    f"=SUMPRODUCT(({cl}{first_data_row}:{cl}{last_data_row}),"
                    f"(MOD(ROW({cl}{first_data_row}:{cl}{last_data_row}),4)=2)*1)"
                )
                worksheet.write_formula(total_row_idx, c, sum_formula, fmt_total_combined)

            # --- 右端：月間総合計（実働・休憩） ---
            # ここは結合セルなので、シンプルなSUMでOK（一番上の行の数値だけを自動で拾うため）
            total_work_sum_formula = f"=SUM({col_letter(total_col)}{first_data_row}:{col_letter(total_col)}{last_data_row})"
            worksheet.write_formula(total_row_idx, total_col, total_work_sum_formula, fmt_total_combined)

            total_break_sum_formula = f"=SUM({col_letter(break_col)}{first_data_row}:{col_letter(break_col)}{last_data_row})"
            worksheet.write_formula(total_row_idx, break_col, total_break_sum_formula, fmt_total_combined)

# --- 仕上げ：ウィンドウ枠の固定 ---
            worksheet.freeze_panes(header_row + 1, 2)

            # --- ★ config_timesシートから時間を取得してドロップダウンに設定 ---
            try:
                # 1. スプレッドシートから直接設定を読み込む
                conf_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="config_times", ttl=0)
                
                valid_shifts = []
                if conf_df is not None and not conf_df.empty:
                    # start列とend列が存在するか確認
                    if "start" in conf_df.columns and "end" in conf_df.columns:
                        for _, row in conf_df.iterrows():
                            s_t = str(row["start"]).strip()
                            e_t = str(row["end"]).strip()
                            # "10:00" のように時刻形式になっているものだけを抽出
                            if ":" in s_t and ":" in e_t:
                                valid_shifts.append((s_t, e_t))
                
                # 2. 重複を削除
                valid_shifts = list(set(valid_shifts))
                
                # 3. スタート時間が早い順に並べ替え（time_to_float関数を利用）
                valid_shifts.sort(key=lambda x: time_to_float(x[0]))
                
                # 4. "10:00-15:00" の形式に整形
                dropdown_list = [f"{s}-{e}" for s, e in valid_shifts]
                
                # 5. 基本の選択肢（✖や空欄）を追加
                dropdown_list.extend(['✖', ' '])

                # リストが空（または読み込み失敗）の場合のデフォルト
                if len(dropdown_list) <= 2:
                    dropdown_list = ['10:00-15:00', '16:00-23:00', '10:00-22:00', '✖', ' ']

                # 6. Excelの入力規則（ドロップダウン）を適用
                worksheet.data_validation(header_row + 1, date_start, total_row_idx - 1, date_start + num_dates - 1, {
                    'validate': 'list',
                    'source': dropdown_list,
                    'input_title': 'シフト選択',
                    'input_message': '直接入力可能',
                    'error_type': 'information', # リスト外の自由入力を許可
                    'show_error': True
                })
            except Exception as e:
                # 万が一エラーが起きてもダウンロードボタンを消さないためのガード
                st.sidebar.error(f"ドロップダウン作成エラー: {e}")

        # ↑ ここまでが with pd.ExcelWriter(...) の中身
                # エラーが起きてもエクセル作成を止めないためのガード
                pass

        # ↑ ここまでが with pd.ExcelWriter(...) as writer: の中身（インデント8つ分）

    # --- ★ここからボタン（withブロックの外に出す。インデント4つ分） ---
    st.write("") # スペース
    st.download_button(
        label="📥 このシフト表をExcelで保存",
        data=buffer.getvalue(),
        file_name=f"shift_{year}_{month:02}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="excel_download_btn" # 重複防止用のキー
    )

    # 欠員警告の表示
    st.divider()
    st.subheader("欠員状況の確認")
    if st.session_state.last_shortage_alerts:
        import re
        def extract_day(msg):
            match = re.search(r'\d+', msg)
            return int(match.group()) if match else 0
        st.warning(f"今月の合計欠員数: **{len(st.session_state.last_shortage_alerts)}枠**")
        for msg in sorted(st.session_state.last_shortage_alerts, key=extract_day):
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
        @keyframes popIn {
            0% { transform: scale(0); opacity: 0; }
            70% { transform: scale(1.3); opacity: 1; }
            100% { transform: scale(1); opacity: 1; }
        }
        .tweet-bubble {
            display: inline-block; 
            background-color: #FFF176; 
            color: #333; 
            padding: 6px 14px;
            border-radius: 18px; 
            font-size: 0.85rem; 
            margin-left: 4px; 
            position: relative;
            box-shadow: 2px 2px 5px rgba(0,0,0,0.1); 
            animation: fadeInUp 0.5s ease-out, popIn 0.3s ease-out 0.2s both; 
            border: 1px solid #FDD835;
        }
        .tweet-bubble::after {
            content: ''; 
            position: absolute; 
            left: -8px; 
            top: 50%; 
            margin-top: -5px;
            border-top: 5px solid transparent; 
            border-right: 8px solid #FFF176; 
            border-bottom: 5px solid transparent;
        }
        .worker-row { 
            display: flex; 
            align-items: center; 
            margin-bottom: 0px; 
            min-height: 35px; 
            line-height: 35px;
        }
        </style>
    """, unsafe_allow_html=True)
    

    # --- 1. 日付とつぶやきの準備 ---
    today = get_japan_today()
    date_str_today = today.strftime("%Y/%m/%d")
    t_month, t_year = today.month, today.year
    t_day_str = str(today.day)
    
    tweet_sheet = "daily_tweets"
    if "tweet_data_cache" not in st.session_state or st.session_state.tweet_data_cache is None:
        try:
            raw_tweets = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=tweet_sheet, ttl=0)
            if raw_tweets is not None and not raw_tweets.empty:
                st.session_state.tweet_data_cache = raw_tweets
            else:
                st.session_state.tweet_data_cache = pd.DataFrame(columns=["日付", "名前", "メッセージ"])
        except:
            st.session_state.tweet_data_cache = pd.DataFrame(columns=["日付", "名前", "メッセージ"])

    today_tweet_dict = {} 
    current_all_tweets = st.session_state.tweet_data_cache
    
    if current_all_tweets is not None and not current_all_tweets.empty:
        required_cols = ["日付", "名前", "メッセージ"]
        if all(col in current_all_tweets.columns for col in required_cols):
            current_all_tweets["日付"] = current_all_tweets["日付"].astype(str)
            today_mask = (
                current_all_tweets["日付"].str.contains(date_str_today.replace("/", ".")) | 
                current_all_tweets["日付"].str.contains(date_str_today)
            )
            today_only = current_all_tweets[today_mask]
            
            if not today_only.empty:
                today_tweet_dict = dict(
                    zip(
                        today_only["名前"].astype(str).str.strip(), 
                        today_only["メッセージ"]
                    )
                )

    # --- 2. シフトデータの読み込みと「超」徹底掃除 ---
    today_sheet = f"shift_{t_year}_{t_month:02}"
    confirmed_df = load_confirmed_shift(today_sheet)

    if confirmed_df.empty:
        st.warning(f"📅 {t_year}年{t_month}月の確定シフトがまだ登録されていません。")
    else:
        # インデックスを列に戻して全データをフラットにする
        display_view = confirmed_df.reset_index()
        
        # 列の役割を判定
        group_col = display_view.columns[0]
        name_col = display_view.columns[1]
        
        # もし1列目に「名前」という文字が入っていたら、列をずらす
        if "名前" in str(display_view.columns[0]):
            name_col = display_view.columns[0]
            group_col = display_view.columns[1]

        # --- ヘッダー行の除去ロジック ---
        ignore_keywords = ["名前", "グループ", "合計実働", "休憩合計", "index", "Unnamed"]
        display_view = display_view[~display_view[name_col].astype(str).str.contains("|".join(ignore_keywords), na=False)]
        display_view = display_view[~display_view[group_col].astype(str).str.contains("|".join(ignore_keywords), na=False)]
        display_view = display_view.reset_index(drop=True)

        # 今日の日付列を特定
        target_col = None
        for c in display_view.columns:
            c_digits = "".join(filter(str.isdigit, str(c).split('(')[0]))
            if c_digits == t_day_str:
                target_col = c
                break

        # ★ つぶやき入力状態の管理
        if "tweet_input_target" not in st.session_state:
            st.session_state.tweet_input_target = None

        # --- 3. 本日の出勤メンバー表示エリア ---
        with st.expander(f"🏃 本日 {t_month}月{today.day}日の出勤メンバー", expanded=True):
            if target_col is None:
                st.error(f"今日の日付「{t_day_str}」の列が見つかりません。")
            else:
                member_list = []
                for i in range(0, len(display_view), 2):
                    name_raw = str(display_view.iloc[i][name_col]).strip()
                    if name_raw in ["nan", "None", ""]: continue
                    
                    time1 = str(display_view.iloc[i][target_col]).strip()
                    time2 = ""
                    if i + 1 < len(display_view):
                        time2 = str(display_view.iloc[i+1][target_col]).strip()
                    
                    is_work1 = "-" in time1
                    is_work2 = "-" in time2
                    
                    if not is_work1 and not is_work2: continue
                    
                    final_time = f"{time1} / {time2}" if (is_work1 and is_work2) else (time1 if is_work1 else time2)
                    gp = str(display_view.iloc[i][group_col]).strip()
                    
                    member_list.append({"名前": name_raw, "時間": final_time, "グループ": gp})

                if not member_list:
                    st.write("本日の出勤予定者はいません。")
                else:
                    col_h, col_k = st.columns(2)
                    with col_h:
                        st.markdown("### 👔 ホール")
                        hall_members = [x for x in member_list if any(k in x["グループ"] for k in ["H", "W", "不明"])]
                        for idx, m in enumerate(hall_members):
                            has_tweet = m["名前"] in today_tweet_dict
                            tweet_msg = today_tweet_dict.get(m["名前"], "")
                            
                            # 1行を表示
                            sub_col1, sub_col2 = st.columns([5, 0.5])
                            
                            with sub_col1:
                                tweet_display = f' <span class="tweet-bubble">{tweet_msg}</span>' if has_tweet else ""
                                st.markdown(
                                    f'<div class="worker-row">'
                                    f'<strong>{m["時間"]}</strong> : {m["名前"]}{tweet_display}'
                                    f'</div>', 
                                    unsafe_allow_html=True
                                )
                            
                            with sub_col2:
                                # ★ st.popover を使った吹き出し入力
                                with st.popover("💭", help=f"{m['名前']}さんのつぶやきを入力"):
                                    st.markdown(f"**{m['名前']}** さんのメッセージ")
                                    
                                    # 既存のつぶやきがあれば表示
                                    if has_tweet:
                                        st.info(f"現在のつぶやき: {tweet_msg}")
                                    
                                    new_msg = st.text_area(
                                        "ひとこと（50文字以内）",
                                        max_chars=50,
                                        placeholder="今日も頑張りましょう！😊",
                                        key=f"popover_tweet_{m['名前']}",
                                        height=80
                                    )
                                    
                                    col_btn1, col_btn2 = st.columns(2)
                                    with col_btn1:
                                        if st.button("📢 投稿", key=f"submit_popover_{m['名前']}", use_container_width=True, type="primary"):
                                            if new_msg:
                                                try:
                                                    tweet_sheet_name = "daily_tweets"
                                                    try:
                                                        existing_tweets = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=tweet_sheet_name, ttl=0)
                                                        if existing_tweets is None or existing_tweets.empty:
                                                            existing_tweets = pd.DataFrame(columns=["日付", "名前", "メッセージ"])
                                                    except:
                                                        existing_tweets = pd.DataFrame(columns=["日付", "名前", "メッセージ"])
                                                    
                                                    # 同じ日付・同じ名前の古いつぶやきを削除
                                                    if not existing_tweets.empty:
                                                        existing_tweets = existing_tweets[
                                                            ~((existing_tweets["日付"].astype(str) == date_str_today) & 
                                                              (existing_tweets["名前"].astype(str) == m['名前']))
                                                        ]
                                                    
                                                    new_tweet = pd.DataFrame([{
                                                        "日付": date_str_today,
                                                        "名前": m['名前'],
                                                        "メッセージ": new_msg
                                                    }])
                                                    
                                                    updated_tweets = pd.concat([existing_tweets, new_tweet], ignore_index=True)
                                                    
                                                    if save_sheet_robust(updated_tweets, tweet_sheet_name):
                                                        st.session_state.tweet_data_cache = updated_tweets
                                                        st.success("✅ 投稿しました！")
                                                        time.sleep(0.5)
                                                        st.rerun()
                                                except Exception as e:
                                                    st.error(f"保存エラー: {e}")
                                            else:
                                                st.warning("メッセージを入力してください")
                                    
                                    with col_btn2:
                                        if st.button("🗑️ 削除", key=f"delete_popover_{m['名前']}", use_container_width=True):
                                            try:
                                                tweet_sheet_name = "daily_tweets"
                                                try:
                                                    existing_tweets = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=tweet_sheet_name, ttl=0)
                                                    if existing_tweets is None or existing_tweets.empty:
                                                        existing_tweets = pd.DataFrame(columns=["日付", "名前", "メッセージ"])
                                                except:
                                                    existing_tweets = pd.DataFrame(columns=["日付", "名前", "メッセージ"])
                                                
                                                # 該当のつぶやきを削除
                                                if not existing_tweets.empty:
                                                    existing_tweets = existing_tweets[
                                                        ~((existing_tweets["日付"].astype(str) == date_str_today) & 
                                                          (existing_tweets["名前"].astype(str) == m['名前']))
                                                    ]
                                                
                                                if save_sheet_robust(existing_tweets, tweet_sheet_name):
                                                    st.session_state.tweet_data_cache = existing_tweets
                                                    st.success("🗑️ 削除しました！")
                                                    time.sleep(0.5)
                                                    st.rerun()
                                            except Exception as e:
                                                st.error(f"削除エラー: {e}")
                    
                    with col_k:
                        st.markdown("### 🍳 キッチン")
                        kitchen_members = [x for x in member_list if "K" in x["グループ"]]
                        for idx, m in enumerate(kitchen_members):
                            has_tweet = m["名前"] in today_tweet_dict
                            tweet_msg = today_tweet_dict.get(m["名前"], "")
                            
                            sub_col1, sub_col2 = st.columns([5, 0.5])
                            
                            with sub_col1:
                                tweet_display = f' <span class="tweet-bubble">{tweet_msg}</span>' if has_tweet else ""
                                st.markdown(
                                    f'<div class="worker-row">'
                                    f'<strong>{m["時間"]}</strong> : {m["名前"]}{tweet_display}'
                                    f'</div>', 
                                    unsafe_allow_html=True
                                )
                            
                            with sub_col2:
                                # ★ st.popover を使った吹き出し入力
                                with st.popover("💭", help=f"{m['名前']}さんにつぶやきを入力"):
                                    st.markdown(f"**{m['名前']}** さんへのメッセージ")
                                    
                                    if has_tweet:
                                        st.info(f"現在のつぶやき: {tweet_msg}")
                                    
                                    new_msg = st.text_area(
                                        "ひとこと（50文字以内）",
                                        max_chars=50,
                                        placeholder="今日も頑張りましょう！😊",
                                        key=f"popover_tweet_{m['名前']}",
                                        height=80
                                    )
                                    
                                    col_btn1, col_btn2 = st.columns(2)
                                    with col_btn1:
                                        if st.button("📢 投稿", key=f"submit_popover_{m['名前']}", use_container_width=True, type="primary"):
                                            if new_msg:
                                                try:
                                                    tweet_sheet_name = "daily_tweets"
                                                    try:
                                                        existing_tweets = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=tweet_sheet_name, ttl=0)
                                                        if existing_tweets is None or existing_tweets.empty:
                                                            existing_tweets = pd.DataFrame(columns=["日付", "名前", "メッセージ"])
                                                    except:
                                                        existing_tweets = pd.DataFrame(columns=["日付", "名前", "メッセージ"])
                                                    
                                                    if not existing_tweets.empty:
                                                        existing_tweets = existing_tweets[
                                                            ~((existing_tweets["日付"].astype(str) == date_str_today) & 
                                                              (existing_tweets["名前"].astype(str) == m['名前']))
                                                        ]
                                                    
                                                    new_tweet = pd.DataFrame([{
                                                        "日付": date_str_today,
                                                        "名前": m['名前'],
                                                        "メッセージ": new_msg
                                                    }])
                                                    
                                                    updated_tweets = pd.concat([existing_tweets, new_tweet], ignore_index=True)
                                                    
                                                    if save_sheet_robust(updated_tweets, tweet_sheet_name):
                                                        st.session_state.tweet_data_cache = updated_tweets
                                                        st.success("✅ 投稿しました！")
                                                        time.sleep(0.5)
                                                        st.rerun()
                                                except Exception as e:
                                                    st.error(f"保存エラー: {e}")
                                            else:
                                                st.warning("メッセージを入力してください")
                                    
                                    with col_btn2:
                                        if st.button("🗑️ 削除", key=f"delete_popover_{m['名前']}", use_container_width=True):
                                            try:
                                                tweet_sheet_name = "daily_tweets"
                                                try:
                                                    existing_tweets = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=tweet_sheet_name, ttl=0)
                                                    if existing_tweets is None or existing_tweets.empty:
                                                        existing_tweets = pd.DataFrame(columns=["日付", "名前", "メッセージ"])
                                                except:
                                                    existing_tweets = pd.DataFrame(columns=["日付", "名前", "メッセージ"])
                                                
                                                if not existing_tweets.empty:
                                                    existing_tweets = existing_tweets[
                                                        ~((existing_tweets["日付"].astype(str) == date_str_today) & 
                                                          (existing_tweets["名前"].astype(str) == m['名前']))
                                                    ]
                                                
                                                if save_sheet_robust(existing_tweets, tweet_sheet_name):
                                                    st.session_state.tweet_data_cache = existing_tweets
                                                    st.success("🗑️ 削除しました！")
                                                    time.sleep(0.5)
                                                    st.rerun()
                                            except Exception as e:
                                                st.error(f"削除エラー: {e}")

    st.divider()

    # --- 4. 全体表示エリア (データクレンジング & 合算表示) ---
    st.subheader("📅 全体シフト閲覧")
    col_sel_y, col_sel_m = st.columns(2)
    v_year = col_sel_y.selectbox("表示年", [today.year-1, today.year, today.year+1], index=1, key="v_y")
    v_month = col_sel_m.selectbox("表示月", range(1, 13), index=today.month-1, key="v_m")
    
    v_sheet = f"shift_{v_year}_{v_month:02}"
    v_df_raw = load_confirmed_shift(v_sheet)
    
    if v_df_raw.empty:
        st.info(f"💡 {v_year}年{v_month}月の確定シフトはまだ公開されていません。")
    else:
        # --- 1. データのクレンジングと列名の修正 ---
        v_view = v_df_raw.reset_index(drop=False)  # ★ インデックスを列として残す
        
        # 列名を文字列に統一
        v_view.columns = [str(c).strip() for c in v_view.columns]
        
        # グループ列と名前列を特定
        v_group_col = None
        v_name_col = None
        
        for col in v_view.columns:
            col_str = str(col).strip()
            if col_str in ["G", "グループ", "group"]:
                v_group_col = col
            elif col_str in ["名前", "name", "Name"]:
                v_name_col = col
        
        # 見つからない場合は最初の2列を使用
        if v_group_col is None:
            v_group_col = v_view.columns[0]
        if v_name_col is None:
            v_name_col = v_view.columns[1] if len(v_view.columns) > 1 else v_view.columns[0]
        
        # ゴミ行の除去
        ignore_keywords = ["名前", "グループ", "合計実働", "休憩合計", "index", "Unnamed", "G"]
        if v_name_col in v_view.columns:
            v_view = v_view[~v_view[v_name_col].astype(str).str.contains("|".join(ignore_keywords), na=False)]
        v_view = v_view.reset_index(drop=True)
        
        # 日付列の特定
        actual_date_cols = []
        for col in v_view.columns:
            col_str = str(col).strip()
            if "(" in col_str and ")" in col_str:
                actual_date_cols.append(col)
        
        # 日付列が見つからない場合は、グループ・名前・合計列以外を日付列とみなす
        if not actual_date_cols:
            skip = [v_group_col, v_name_col, "合計実働", "休憩合計", "欠員メッセージ"]
            actual_date_cols = [c for c in v_view.columns if c not in skip]
        
        # 日付列を日付順にソート
        def extract_day(col_name):
            digits = "".join(filter(str.isdigit, str(col_name).split('(')[0]))
            return int(digits) if digits.isdigit() else 999
        
        try:
            actual_date_cols = sorted(actual_date_cols, key=extract_day)
        except:
            pass
        
        # --- 2. 実働合計・休憩合計の再計算（2行合算対応版） ---
        v_view = v_view.fillna("")
        
        recalc_totals = []
        recalc_breaks = []
        
        for i in range(0, len(v_view), 2):
            row1_net = 0.0
            row1_brk = 0.0
            row2_net = 0.0
            row2_brk = 0.0
            
            for c in actual_date_cols:
                val1 = str(v_view.iloc[i].get(c, "")) if i < len(v_view) else ""
                val2 = ""
                if i + 1 < len(v_view):
                    val2 = str(v_view.iloc[i+1].get(c, ""))
                
                net1, brk1 = calc_work_and_break(val1)
                net2, brk2 = calc_work_and_break(val2)
                
                total_hours_today = (net1 + brk1) + (net2 + brk2)
                
                if total_hours_today > 0:
                    if total_hours_today > 8.0:
                        correct_break_today = 1.0
                    elif total_hours_today > 6.0:
                        correct_break_today = 0.75
                    else:
                        correct_break_today = 0.0
                    
                    old_break_today = brk1 + brk2
                    if correct_break_today != old_break_today:
                        work1 = net1 + brk1
                        work2 = net2 + brk2
                        
                        if total_hours_today > 0:
                            ratio1 = work1 / total_hours_today
                            brk1 = round(correct_break_today * ratio1, 2)
                            brk2 = round(correct_break_today - brk1, 2)
                            net1 = round(work1 - brk1, 1)
                            net2 = round(work2 - brk2, 1)
                
                row1_net += net1
                row1_brk += brk1
                row2_net += net2
                row2_brk += brk2
            
            recalc_totals.append(round(row1_net, 1))
            recalc_breaks.append(round(row1_brk, 2))
            
            if i + 1 < len(v_view):
                recalc_totals.append(round(row2_net, 1))
                recalc_breaks.append(round(row2_brk, 2))
        
        while len(recalc_totals) < len(v_view):
            recalc_totals.append(0.0)
            recalc_breaks.append(0.0)
        
        v_view["合計実働"] = recalc_totals[:len(v_view)]
        v_view["休憩合計"] = recalc_breaks[:len(v_view)]

        # --- 3. 以降は同じ（検索用名前リスト、表示加工、スタイル適用） ---
        # --- 3. 検索用名前リスト ---
        valid_names = sorted(list(set([str(n).strip() for n in v_view[v_name_col] if str(n).strip() != ""])))
        search_name = st.selectbox(
            "自分の名前を選択してハイライト！✨", 
            ["(全員分表示)"] + valid_names,
            index=0,
            key="highlight_name_select"
        )
        
        # --- 4. ウェブ表示用の加工（2行合算・2行目の名前消去） ---
        v_display = v_view.copy()
        v_display = v_display.replace(["nan", "None"], "")

        for i in range(0, len(v_display), 2):
            if i + 1 < len(v_display):
                v_display.at[i+1, v_name_col] = ""
                v_display.at[i+1, v_group_col] = ""
                v_display.at[i, "合計実働"] = round(v_view.at[i, "合計実働"] + v_view.at[i+1, "合計実働"], 1)
                v_display.at[i, "休憩合計"] = round(v_view.at[i, "休憩合計"] + v_view.at[i+1, "休憩合計"], 1)
                v_display.at[i+1, "合計実働"] = None
                v_display.at[i+1, "休憩合計"] = None

        # --- 5. スタイル適用と表示 ---
        # --- 5. スタイル適用と表示 ---
        def style_confirmed_grid(df):
            styles = pd.DataFrame('', index=df.index, columns=df.columns)
            target = str(search_name).strip()
            h_list = [h[0] for h in get_month_holidays_list(v_year, v_month)]

            for r_idx in range(len(df)):
                is_second = (r_idx % 2 != 0)
                
                # ★ 修正：v_displayの行番号に対応するv_viewの行番号を使う
                # v_displayとv_viewは同じ行数・同じ順序なので、そのままv_viewの同じ行を参照
                row_name = str(v_view.iloc[r_idx][v_name_col]).strip()
                
                # 2行目の場合は1行目の名前を使う（ハイライト用）
                if is_second and row_name == "":
                    row_name = str(v_view.iloc[r_idx - 1][v_name_col]).strip()
                
                for c_idx, col_name in enumerate(df.columns):
                    bg_color = ""
                    
                    if col_name in [v_group_col, v_name_col]:
                        bg_color = "background-color: #f8f9fa;"
                    elif "(" in str(col_name) and ")" in str(col_name):
                        try:
                            d_str = "".join(filter(str.isdigit, str(col_name).split('(')[0]))
                            if d_str:
                                d = int(d_str)
                                d_idx = calendar.weekday(v_year, v_month, d)
                                if d in h_list or d_idx == 6:
                                    bg_color = "background-color: #ffe6e6;"
                                elif d_idx == 5:
                                    bg_color = "background-color: #e6f3ff;"
                        except:
                            pass
                    
                    if col_name in ["合計実働", "休憩合計"]:
                        bg_color = "background-color: #FFFFCC; font-weight: bold;"
                    
                    if target != "(全員分表示)" and target == row_name:
                        bg_color = "background-color: #FFF9C4; color: black;"

                    if is_second:
                        border = "border-top: none !important; border-bottom: 2px solid #555 !important;"
                    else:
                        border = "border-top: 2px solid #555 !important; border-bottom: 1px dashed #ccc !important;"
                    
                    styles.iloc[r_idx, c_idx] = bg_color + border
                    
                    val_str = str(df.iloc[r_idx, c_idx]).strip()
                    if val_str == "✖":
                        styles.iloc[r_idx, c_idx] += "color: #E60012; font-weight: bold;"
            return styles

        # 表示実行
        st.dataframe(
            v_display.style.apply(style_confirmed_grid, axis=None).format(
                {"合計実働": "{:.1f}", "休憩合計": "{:.1f}"}, 
                na_rep=""
            ),
            use_container_width=True, 
            height=600, 
            hide_index=True
        )

# --- 6. ダウンロードボタン (Excel出力) ---
        # ★ 出力用のデータを正しく作成
        # v_viewの列構成を確認
        
        # 実際の列名を使って出力
        actual_group_col = v_group_col  # "グループ"
        actual_name_col = v_name_col    # "名前"
        
        export_cols = [actual_group_col, actual_name_col] + actual_date_cols + ["合計実働", "休憩合計"]
        
        # ★ 列が実際に存在するか確認
        missing_cols = [c for c in export_cols if c not in v_view.columns]
        if missing_cols:
            st.error(f"出力に必要な列が見つかりません: {missing_cols}")
            st.write("実際の列名:", list(v_view.columns))
        else:
            v_export = v_view[export_cols].copy()
            v_export = v_export.replace(["nan", "None"], "")
            
            store_name = st.session_state.get("store_name", "ジョイフル")
            
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                workbook = writer.book
                worksheet = workbook.add_worksheet('確定シフト')
                
                # 印刷設定
                worksheet.set_portrait()
                worksheet.set_paper(9)
                worksheet.set_margins(0.3, 0.3, 0.3, 0.3)
                worksheet.center_horizontally()
                worksheet.fit_to_pages(1, 0)
                
                # タイトル行
                title_format = workbook.add_format({
                    'bold': True,
                    'size': 22,
                    'align': 'center',
                    'valign': 'vcenter',
                    'font_name': 'Meiryo UI',
                    'color': '#333333'
                })
                worksheet.set_row(0, 40)
                total_export_cols = len(export_cols)
                worksheet.merge_range(0, 0, 0, total_export_cols - 1, 
                                      f"{v_year}年{v_month}月　{store_name}　シフト表", 
                                      title_format)
                
                worksheet.set_row(1, 8)
                
                # 書式定義
                fmt_header = workbook.add_format({
                    'bold': True, 'border': 2, 'bg_color': '#D9D9D9', 
                    'align': 'center', 'valign': 'vcenter', 'size': 10, 'font_name': 'Meiryo UI'
                })
                fmt_merge = workbook.add_format({
                    'bold': True, 'top': 2, 'bottom': 2, 'left': 1, 'right': 1,
                    'bg_color': '#F2F2F2', 'align': 'center', 'valign': 'vcenter',
                    'size': 10, 'font_name': 'Meiryo UI'
                })
                fmt_row1 = workbook.add_format({
                    'left': 1, 'right': 1, 'top': 2, 'bottom': 7,
                    'align': 'center', 'valign': 'vcenter', 'size': 9, 'font_name': 'Meiryo UI'
                })
                fmt_row2 = workbook.add_format({
                    'left': 1, 'right': 1, 'top': 7, 'bottom': 2,
                    'align': 'center', 'valign': 'vcenter', 'size': 9, 'font_name': 'Meiryo UI'
                })
                fmt_total = workbook.add_format({
                    'bold': True, 'top': 2, 'bottom': 2, 'left': 1, 'right': 1,
                    'bg_color': '#FFFFCC', 'align': 'center', 'valign': 'vcenter',
                    'num_format': '0.0', 'size': 9, 'font_name': 'Meiryo UI'
                })
                fmt_sat = workbook.add_format({
                    'bold': True, 'border': 2, 'bg_color': '#E6F3FF', 'font_color': '#0000FF',
                    'align': 'center', 'valign': 'vcenter', 'size': 9, 'font_name': 'Meiryo UI'
                })
                fmt_sun = workbook.add_format({
                    'bold': True, 'border': 2, 'bg_color': '#FFE6E6', 'font_color': '#FF0000',
                    'align': 'center', 'valign': 'vcenter', 'size': 9, 'font_name': 'Meiryo UI'
                })
                
                # ヘッダー行
                header_row = 2
                worksheet.set_row(header_row, 24)
                h_list = [h[0] for h in get_month_holidays_list(v_year, v_month)]
                
                for c_idx, col_name in enumerate(export_cols):
                    if col_name == actual_group_col:
                        worksheet.write(header_row, c_idx, "G", fmt_header)
                    elif col_name == actual_name_col:
                        worksheet.write(header_row, c_idx, "名前", fmt_header)
                    elif col_name in ["合計実働", "休憩合計"]:
                        worksheet.write(header_row, c_idx, col_name, fmt_header)
                    else:
                        try:
                            d_str = "".join(filter(str.isdigit, str(col_name).split('(')[0]))
                            d = int(d_str)
                            d_idx = calendar.weekday(v_year, v_month, d)
                            if d in h_list or d_idx == 6:
                                worksheet.write(header_row, c_idx, col_name, fmt_sun)
                            elif d_idx == 5:
                                worksheet.write(header_row, c_idx, col_name, fmt_sat)
                            else:
                                worksheet.write(header_row, c_idx, col_name, fmt_header)
                        except:
                            worksheet.write(header_row, c_idx, col_name, fmt_header)
                
                # 列幅
                worksheet.set_column(0, 0, 5)   # G列
                worksheet.set_column(1, 1, 16)  # 名前列
                for i in range(2, 2 + len(actual_date_cols)):
                    worksheet.set_column(i, i, 10)
                worksheet.set_column(2 + len(actual_date_cols), 2 + len(actual_date_cols), 9)    # 合計実働
                worksheet.set_column(3 + len(actual_date_cols), 3 + len(actual_date_cols), 9)    # 休憩合計
                
                # ★ データ行の書き込み（正しい列を参照）
                t_col_idx = export_cols.index("合計実働")
                b_col_idx = export_cols.index("休憩合計")
                g_col_idx = 0  # グループ列は常に0列目
                n_col_idx = 1  # 名前列は常に1列目
                date_start_idx = 2
                date_end_idx = date_start_idx + len(actual_date_cols) - 1
                
                for i in range(0, len(v_export), 2):
                    xl_row = header_row + 1 + i
                    
                    if i + 1 < len(v_export):
                        # ★ v_exportから直接データを取得
                        name = str(v_export.iloc[i][actual_name_col]).strip()
                        group = str(v_export.iloc[i][actual_group_col]).strip()
                        sum_work = round(float(v_export.iloc[i]["合計実働"]) + float(v_export.iloc[i+1]["合計実働"]), 1)
                        sum_break = round(float(v_export.iloc[i]["休憩合計"]) + float(v_export.iloc[i+1]["休憩合計"]), 1)
                        
                        worksheet.set_row(xl_row, 22)
                        worksheet.set_row(xl_row + 1, 22)
                        
                        # グループと名前を2行マージ（正しい列位置に）
                        worksheet.merge_range(xl_row, g_col_idx, xl_row + 1, g_col_idx, group, fmt_merge)
                        worksheet.merge_range(xl_row, n_col_idx, xl_row + 1, n_col_idx, name, fmt_merge)
                        
                        # 合計列を2行マージ
                        worksheet.merge_range(xl_row, t_col_idx, xl_row + 1, t_col_idx, sum_work, fmt_total)
                        worksheet.merge_range(xl_row, b_col_idx, xl_row + 1, b_col_idx, sum_break, fmt_total)
                        
                        # 日付データを書き込み
                        for c_idx in range(date_start_idx, date_end_idx + 1):
                            col_name = export_cols[c_idx]
                            val1 = str(v_export.iloc[i][col_name]).strip() if col_name in v_export.columns else ""
                            val2 = str(v_export.iloc[i+1][col_name]).strip() if col_name in v_export.columns else ""
                            
                            worksheet.write(xl_row, c_idx, val1, fmt_row1)
                            worksheet.write(xl_row + 1, c_idx, val2, fmt_row2)
                
                worksheet.freeze_panes(header_row + 1, 2)
            
            st.write("")
            st.download_button(
                label="📥 このシフト表をExcelで保存", 
                data=buf.getvalue(), 
                file_name=f"shift_{v_year}_{v_month:02}.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                use_container_width=True
            )
if mode == "清掃記録":
    st.title("🧹 モップ清掃記録")

    # --- パスワードチェック ---
    if str(pw).strip() != st.session_state.admin_pw_fixed:
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
                    worksheet.insert_image('A11', 'cleaning_map.png', {
                        'x_scale': 0.385, # 85%まで拡大
                        'y_scale': 0.4,
                        'x_offset': 10,
                        'y_offset': 6
                    })
                except: pass

            st.download_button(
                label="📥 印刷用Excelをダウンロード",
                data=buffer_clean.getvalue(),
                file_name=f"Cleaning_Report_{c_year}_{c_month:02}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# mode == "清掃記録" の管理者用エリア（pw == "1234" の中）の最後に追加
    if str(pw).strip() == st.session_state.admin_pw_fixed:
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
if mode == "シフトアップロード":
    st.title("📤 確定シフトのアップロード・公開")

    # 店舗専用のパスワードで認証
    if str(pw).strip() != st.session_state.admin_pw_fixed:
        st.warning("店長専用メニューです。管理者パスワードを入力してください。")
    else:
        st.info(f"現在は「{st.session_state.store_name}」の確定シフトを操作しています。")
        
        with st.expander("📖 アップロードの手順", expanded=False):
            st.markdown("""
            1. 「シフト自動生成」で作成したExcelをダウンロードし、店長のPCで修正・保存します。
            2. 公開したい「年」と「月」を選択します。
            3. 修正したExcelファイルをここにドラッグ＆ドロップします。
            4. 「確定シフトを公開する」を押すと、スタッフ全員のスマホから閲覧可能になり、LINE通知が飛びます。
            """)

        # --- 1. アップロード先の年月を選択 ---
        col_up1, col_up2 = st.columns(2)
        today_up = get_japan_today()
        with col_up1:
            up_target_year = st.selectbox("アップロード先の年", [today_up.year - 1, today_up.year, today_up.year + 1], index=1)
        with col_up2:
            up_target_month = st.selectbox("アップロード先の月", range(1, 13), index=today_up.month - 1)

        up_file = st.file_uploader("修正済みExcelファイル(xlsx)を選択してください", type="xlsx")
        
        if up_file:
            # Excelを読み込む
            f_df = pd.read_excel(up_file, sheet_name=0, header=None)  # ★ ヘッダーなしで読み込み
            
            st.write("▼ アップロード内容のプレビュー（先頭6行）")
            st.dataframe(f_df.head(6), use_container_width=True)
            
            # ★★★ タイトル行・ヘッダー行を自動検出して除去 ★★★
            # 1行目はタイトル（"○年○月" を含む）
            # 2行目は空行
            # 3行目がヘッダー（"G", "名前" などを含む）
            
            header_row_idx = None
            for idx, row in f_df.iterrows():
                first_cell = str(row.iloc[0]).strip()
                second_cell = str(row.iloc[1]).strip() if len(row) > 1 else ""
                
                # "G" と "名前" が含まれる行をヘッダーとして検出
                if first_cell == "G" and ("名前" in second_cell or second_cell == "名前"):
                    header_row_idx = idx
                    break
                # または "グループ" と "名前" の組み合わせ
                if "グループ" in first_cell or "名前" in second_cell:
                    header_row_idx = idx
                    break
            
            if header_row_idx is not None:
                # ヘッダー行より前の行（タイトル行など）を削除
                f_df = f_df.iloc[header_row_idx:].reset_index(drop=True)
                # ヘッダー行を列名に設定
                f_df.columns = f_df.iloc[0]
                f_df = f_df.iloc[1:].reset_index(drop=True)
                
                st.success(f"✅ ヘッダー行を検出しました（{header_row_idx + 1}行目）")
            else:
                st.warning("ヘッダー行が見つかりませんでした。先頭行を列名として使用します。")
                f_df.columns = f_df.iloc[0]
                f_df = f_df.iloc[1:].reset_index(drop=True)
            
            # 列名を文字列に統一
            f_df.columns = [str(c).strip() for c in f_df.columns]
            
            st.write("▼ クレンジング後のプレビュー")
            st.dataframe(f_df.head(6), use_container_width=True)
            
            # ★★★ 日付列の検出と整形 ★★★
            # グループ列と名前列を特定
            group_col = None
            name_col = None
            
            for i, col in enumerate(f_df.columns):
                col_str = str(col).strip()
                if col_str in ["G", "グループ", "group"]:
                    group_col = col
                elif col_str in ["名前", "name", "Name"]:
                    name_col = col
            
            # 見つからない場合は最初の2列を使用
            if group_col is None:
                group_col = f_df.columns[0]
                st.info(f"グループ列が見つからないため、'{group_col}' 列を使用します")
            if name_col is None:
                name_col = f_df.columns[1] if len(f_df.columns) > 1 else f_df.columns[0]
                st.info(f"名前列が見つからないため、'{name_col}' 列を使用します")
            
            # 日付列を特定（カッコを含む列、または数字のみの列）
            date_cols = []
            for col in f_df.columns:
                col_str = str(col).strip()
                # 「1(月)」や「1日(月)」などのパターン
                if "(" in col_str and ")" in col_str:
                    date_cols.append(col)
                # 「合計実働」「休憩合計」「欠員」などの集計列は除外
                elif col_str in ["合計実働", "休憩合計", "欠員メッセージ", "G", "名前", "グループ"]:
                    continue
            
            # 日付列が見つからない場合は、3列目以降を日付列とみなす
            if not date_cols:
                skip_cols = [group_col, name_col, "合計実働", "休憩合計", "欠員メッセージ"]
                date_cols = [c for c in f_df.columns if c not in skip_cols]
                st.info(f"日付列を自動判定しました: {len(date_cols)}列")
            
            st.write(f"🔍 検出: グループ列='{group_col}', 名前列='{name_col}', 日付列={len(date_cols)}列")
            
            if st.button(f"🚀 {up_target_year}年{up_target_month}月の確定シフトを公開する", use_container_width=True):
                with st.spinner("労働時間を再計算して公開中..."):
                    try:
                        # 必要な列だけを抽出
                        keep_cols = [group_col, name_col] + date_cols
                        # 合計実働・休憩合計があれば保持
                        if "合計実働" in f_df.columns:
                            keep_cols.append("合計実働")
                        if "休憩合計" in f_df.columns:
                            keep_cols.append("休憩合計")
                        
                        f_clean = f_df[keep_cols].copy()
                        
                        # ゴミ行の除去
                        ignore_keywords = ["名前", "グループ", "合計実働", "休憩合計", "G", "index"]
                        if name_col in f_clean.columns:
                            f_clean = f_clean[~f_clean[name_col].astype(str).str.contains("|".join(ignore_keywords), na=False)]
                        
                        f_clean = f_clean.reset_index(drop=True)
                        
                        # ★★★ 2行1セットで休憩を正しく計算 ★★★
                        nets, brks = [], []
                        
                        for i in range(0, len(f_clean), 2):
                            row1_net, row1_brk = 0.0, 0.0
                            row2_net, row2_brk = 0.0, 0.0
                            
                            for c in date_cols:
                                val1 = str(f_clean.iloc[i][c]).strip() if i < len(f_clean) else ""
                                val2 = ""
                                if i + 1 < len(f_clean):
                                    val2 = str(f_clean.iloc[i+1][c]).strip()
                                
                                # 2行合算で休憩を計算
                                n1, b1, n2, b2 = calc_work_and_break_for_pair(val1, val2)
                                row1_net += n1
                                row1_brk += b1
                                row2_net += n2
                                row2_brk += b2
                            
                            nets.append(round(row1_net, 1))
                            brks.append(round(row1_brk, 2))
                            if i + 1 < len(f_clean):
                                nets.append(round(row2_net, 1))
                                brks.append(round(row2_brk, 2))
                        
                        # 長さを揃える
                        while len(nets) < len(f_clean):
                            nets.append(0.0)
                            brks.append(0.0)
                        
                        f_clean["合計実働"] = nets[:len(f_clean)]
                        f_clean["休憩合計"] = brks[:len(f_clean)]
                        
                        # 名前列をインデックスに設定
                        f_clean = f_clean.set_index(name_col)
                        
                        # 店舗専用のスプレッドシートへ保存
                        target_sheet = f"shift_{up_target_year}_{up_target_month:02}"
                        
                        if save_sheet_robust(f_clean, target_sheet):
                            st.cache_data.clear()
                            
                            # LINE通知
                            store_name = st.session_state.store_name
                            line_msg = (
                                f"📢 {store_name}\nシフト公開のお知らせ\n\n"
                                f"{up_target_year}年{up_target_month}月の確定シフトが公開されました！\n"
                                f"各自、アプリから確認をお願いします。✨\n\n"
                                f"URL: https://joyful-shift.streamlit.app/?s={url_store_id if url_store_id else 'KOKURA'}"
                            )
                            
                            if send_line_notification(line_msg):
                                st.success(f"✅ {target_sheet} を公開し、スタッフにLINE通知を送りました！")
                            else:
                                st.warning(f"✅ {target_sheet} は公開されましたが、LINE通知に失敗しました。")
                            
                            time.sleep(2)
                            st.rerun()
                    except Exception as e:
                        st.error(f"エラーが発生しました。Excelの形式が正しいか確認してください。\n詳細: {e}")
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