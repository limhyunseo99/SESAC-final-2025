import json
import math
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

KEYWORDS_FILE = "keywords.json"
BATCH_SIZE = 2
OUTPUT_DIR = "batches"

# ⭐ 현재 날짜 기준 최근 12개월 자동 생성
def generate_last_12_months():
    months = []
    now = datetime.now()

    for i in range(12):
        m = now - relativedelta(months=i)
        months.append(m.strftime("%Y-%m"))

    return sorted(months)  # 오름차순 정렬

def create_batches():
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        keywords = json.load(f)["keywords"]

    total_batches = math.ceil(len(keywords) / BATCH_SIZE)
    months = generate_last_12_months()
    countries = ["US", "JP", "VN"]

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for i in range(total_batches):
        start = i * BATCH_SIZE
        end = start + BATCH_SIZE
        batch_keywords = keywords[start:end]

        batch_data = {
            "api_keys": ["AIzaSyAtlx-wNxwe5jZhSR_1PleAwKrqvjF5hOE","AIzaSyAxwvpew_Xcp5-a2Ah6eV--5_M1icSL-c8","AIzaSyAlLK8Oh-fEgT-h-ZtYMI0Nh3_oJt4Xg4I",
                         "AIzaSyCeSSxG0QI-S7TGFQcqSwgKCQEgl8Q_Y0w","AIzaSyCFn-TNjPFE7HMlZaIh0-aulsV8Zysx2Ck","AIzaSyDxLXOeywxrNtZ4NHSDnsZPCgDycdYQgv4",
                         "AIzaSyCpohMLo6yqTVGyDkLukneb7KDxoc9HQbQ","AIzaSyCB-6oxdfLcY2Cj2brBFTMmuaaW9pWwFTc","AIzaSyDJgtlZtSYDLeyibEqP5HuxfE9PKRIRpUg"],  
            "months": months,
            "countries": countries,
            "keywords": batch_keywords
        }

        file = os.path.join(OUTPUT_DIR, f"batch_{i+1:02d}.json")
        with open(file, "w", encoding="utf-8") as bf:
            json.dump(batch_data, bf, ensure_ascii=False, indent=2)

        print(f"생성 완료 → {file}")

    print(f"\n총 {total_batches}개 batch 생성됨.")

if __name__ == "__main__":
    create_batches()
