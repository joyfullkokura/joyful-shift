import pandas as pd
from datetime import datetime

def append_parsed_data(sh, sheet_name, user_name, ai_results_json, daily_memos_dict, monthly_rule):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        ws_list = [w.title for w in sh.worksheets()]
        if sheet_name not in ws_list:
            sh.add_worksheet(title=sheet_name, rows="5000", cols="10")
            ws = sh.worksheet(sheet_name)
            ws.update("A1", [["名前", "日付", "開始", "終了", "スコア", "理由", "原文", "保存日時"]])
        else:
            ws = sh.worksheet(sheet_name)

        rows_to_append = []
        clean_monthly = str(monthly_rule).replace('\n', ' ')

        if not ai_results_json:
            print("警告: AIの解析結果が空です。書き込みをスキップします。")
            return False

        for day, result in ai_results_json.items():
            memo = daily_memos_dict.get(day, "")
            clean_memo = str(memo).replace('\n', ' ')
            full_original_text = f"[{clean_monthly}] {clean_memo}".strip()
            
            def to_f(val):
                try: return float(val) if val is not None else ""
                except: return ""

            row = [
                user_name,
                str(day),
                to_f(result.get("start")),
                to_f(result.get("end")),
                to_f(result.get("score", 3.0)),
                str(result.get("reason", "")),
                full_original_text,
                now_str
            ]
            rows_to_append.append(row)
        
        if rows_to_append:
            ws.append_rows(rows_to_append)
            print(f"{len(rows_to_append)}件のデータを保存しました。")
            return True
        return False
    except Exception as e:
        print(f"スプレッドシート追記エラー: {e}")
        return False