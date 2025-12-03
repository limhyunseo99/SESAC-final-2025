import sys
import json
import os
import csv
import time
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.exceptions import RequestException, Timeout

# ------------------------------------------------------------
# 설정
# ------------------------------------------------------------
SAVE_DIR = r"C:\Users\0209a\sesac\Final Project\youtube_folder\results"
RESUME_FILE = r"C:\Users\0209a\sesac\Final Project\youtube_folder\resume.json"

THREADS = 4                 # 동시에 돌릴 스레드 수
REQUEST_TIMEOUT = 10        # 각 요청당 최대 10초 기다림
MAX_RETRIES = 3             # 한 페이지당 최대 재시도 횟수

# ------------------------------------------------------------
# 유틸: 월 범위
# ------------------------------------------------------------
def get_month_range(month: str):
    base = datetime.strptime(month, "%Y-%m")
    start = base.replace(day=1)
    end = start + relativedelta(months=1) - relativedelta(seconds=1)
    return start, end

# ------------------------------------------------------------
# 유틸: 국가별 검색어 선택
# ------------------------------------------------------------
def choose_term(country: str, kw: dict) -> str:
    if country == "JP":
        return kw["jp"]
    elif country == "VN":
        return kw["vn"]
    else:  # US 혹은 기타
        return kw["en"]

# ------------------------------------------------------------
# resume 로드/저장 (정보용)
# ------------------------------------------------------------
def load_resume():
    if not os.path.exists(RESUME_FILE):
        return {}
    with open(RESUME_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_resume(data):
    with open(RESUME_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ------------------------------------------------------------
# 기존 CSV 읽어서 완료된 조합 세트 만들기
# (CSV를 ground truth로 사용 → 중복 0%)
# ------------------------------------------------------------
def load_done_set(csv_path: str):
    done = set()
    if not os.path.exists(csv_path):
        return done

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 4:
                continue
            month, country, kr, local = row[:4]
            done.add((month, country, kr, local))
    return done

# ------------------------------------------------------------
# 유튜브 API 호출 (timeout + 재시도 + key 라운드로빈)
# ------------------------------------------------------------
def fetch_count(task, api_keys, key_state):
    month, country, kw, start_date, end_date = task

    term = choose_term(country, kw)
    url = "https://www.googleapis.com/youtube/v3/search"

    next_token = None
    total_count = 0

    while True:
        # API 키 라운드 로빈
        idx = key_state["key_index"]
        key = api_keys[idx]
        key_state["key_index"] = (idx + 1) % len(api_keys)

        params = {
            "key": key,
            "part": "snippet",
            "q": term,
            "regionCode": country,
            "type": "video",
            "maxResults": 50,
            "order": "date",
            "publishedAfter": start_date.isoformat("T") + "Z",
            "publishedBefore": end_date.isoformat("T") + "Z"
        }
        if next_token:
            params["pageToken"] = next_token

        # ---- 재시도 루프 ----
        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                data = resp.json()
                success = True
                break
            except Timeout:
                print(f"⏳ Timeout (시도 {attempt}/{MAX_RETRIES}) "
                      f"- {month}/{country}/{kw['kr']}")
                time.sleep(2)
            except RequestException as e:
                print(f"⚠️ 요청 오류 (시도 {attempt}/{MAX_RETRIES}) "
                      f"- {month}/{country}/{kw['kr']} : {e}")
                time.sleep(2)

        # 재시도 실패 → 이 task는 여기까지 카운트된 값만 반환하고 종료
        if not success:
            print(f"❌ 이 조합은 중단: {month}/{country}/{kw['kr']}")
            break

        if "error" in data:
            # API 자체 에러 → 잠깐 쉬고 다음 키로 넘어감
            print(f"⚠️ API ERROR ({month}/{country}/{kw['kr']}): {data['error']}")
            time.sleep(2)
            continue

        # publishedAt 기준 카운트
        for item in data.get("items", []):
            p = item["snippet"].get("publishedAt")
            if not p:
                continue
            dt = datetime.fromisoformat(p.replace("Z", "+00:00")).replace(tzinfo=None)
            if start_date <= dt <= end_date:
                total_count += 1

        next_token = data.get("nextPageToken")
        if not next_token:
            break

    return (month, country, kw["kr"], term, total_count)

# ------------------------------------------------------------
# main
# ------------------------------------------------------------
def main(batch_file: str):
    # 배치 로드
    with open(batch_file, "r", encoding="utf-8") as f:
        batch = json.load(f)

    api_keys = batch["api_keys"]
    months = batch["months"]
    countries = batch["countries"]
    keywords = batch["keywords"]

    os.makedirs(SAVE_DIR, exist_ok=True)
    resume = load_resume()

    batch_name = os.path.splitext(os.path.basename(batch_file))[0]
    csv_path = os.path.join(SAVE_DIR, f"{batch_name}.csv")

    # 이미 완료된 조합 로드 (CSV 기준)
    done_set = load_done_set(csv_path)

    # 작업 목록 생성
    tasks = []
    for month in months:
        start, end = get_month_range(month)
        for country in countries:
            for kw in keywords:
                term = choose_term(country, kw)
                ident = (month, country, kw["kr"], term)
                if ident in done_set:
                    continue  # 이미 CSV에 있으면 skip
                tasks.append((month, country, kw, start, end))

    print(f"총 작업 수: {len(tasks)}")

    # 키 상태 (라운드 로빈 인덱스만 관리)
    key_state = {"key_index": 0}

    # CSV append 모드로 열기 (헤더 없음: 기존 파일 형식 유지)
    with ThreadPoolExecutor(max_workers=THREADS) as executor, \
         open(csv_path, "a", encoding="utf-8", newline="") as csvfile:

        writer = csv.writer(csvfile)

        futures = {executor.submit(fetch_count, t, api_keys, key_state): t
                   for t in tasks}

        for future in as_completed(futures):
            month, country, kr, local, count = future.result()

            ident = (month, country, kr, local)
            if ident not in done_set:
                writer.writerow([month, country, kr, local, count])
                done_set.add(ident)

                # 정보용 resume (실제 중복 제어는 done_set/CSV가 맡음)
                resume["last_done"] = [month, country, kr]
                save_resume(resume)

            print(f"완료: {month}/{country}/{kr} → {count}")

    print("🎉 전체 완료!")

# ------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python youtube_trend.py batches/batch_03.json")
        sys.exit(1)
    main(sys.argv[1])
