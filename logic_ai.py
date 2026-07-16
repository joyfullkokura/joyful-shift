import google.genai as genai
from google.genai import types
import json
import re
import time

def parse_requests_bundled(monthly_rule, daily_memos_dict, column_names):
    API_KEY = "AQ.Ab8RN6LR4nlYqvyja5XjmFSDWG7cuN903p43SH71RmXIJgLdSQ"
    client = genai.Client(api_key=API_KEY)

    daily_info = "\n".join([f"{d}: {msg}" for d, msg in daily_memos_dict.items() if str(msg).strip() != ""])
    days_list = ", ".join(column_names)

    prompt = f"""
    Return employee shift requests as a JSON object for ALL dates listed.
    Target Dates: {days_list}
    Monthly Rule: "{monthly_rule}"
    Daily Requests: {daily_info}
    Rules: 1. JSON only. 2. Every date is a key. 3. Time as float or null. 4. Score 1.0-5.0. 
    Reason in Japanese.
    """

    model_priority = [
        "models/gemini-2.0-flash",    
        "models/gemini-flash-latest", 
        "models/gemini-1.5-flash-8b",  
        "models/gemini-3.5-flash"     
    ]

    for model_name in model_priority:
        try:
            print(f"Trying model: {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                )
            )
            
            clean_text = re.sub(r'```json\s*|\s*```', '', response.text).strip()
            return json.loads(clean_text)

        except Exception as e:
            if "429" in str(e):
                print(f"Model {model_name} exhausted (429). Switching to next...")
                continue
            elif "503" in str(e):
                time.sleep(2)
                try:
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    return json.loads(response.text)
                except:
                    continue
            else:
                print(f"Error with {model_name}: {e}")
                continue
    
    return {"error_detail": "すべての利用可能なAIモデルが制限に達しました。数分待ってからお試しください。"}