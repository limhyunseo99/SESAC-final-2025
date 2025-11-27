# src/input_parser.py

from typing import List, Optional, Dict


# 국가 코드 매핑
COUNTRY_MAP = {"미국": "US", "일본": "JP", "베트남": "VN"}

# HS코드 → 대략적인 품목명 매핑 (예시)
# 실제 프로젝트에서는 CSV나 DB에서 로딩하는 형태로 확장 가능
HS_TO_PRODUCT = {
    "220299": "과실음료",
    "200990": "과일주스",
    # 필요에 따라 추가...
}


def normalize_country(country_input: str) -> Optional[str]:
    """
    드롭다운 또는 문자 입력으로 들어온 국가명을
    내부 기준 국가코드(US, JP, VN 등)로 변환.
    """
    if not country_input:
        return None

    key = country_input.strip().lower()
    return COUNTRY_MAP.get(key, country_input)  # 매핑 없으면 원본 유지


def normalize_hs_code(hs_code_input: str) -> Optional[str]:
    """
    HS코드 입력값(숫자 문자열)을 정규화.
    - 공백 제거
    - 숫자만 남기기
    - 6~10자리만 인정 (그 외는 None)
    """
    if not hs_code_input:
        return None

    raw = "".join(ch for ch in hs_code_input if ch.isdigit())
    if len(raw) < 6 or len(raw) > 10:
        return None
    return raw


def infer_product_name(
    hs_code: Optional[str], manual_product: Optional[str] = None
) -> Optional[str]:
    """
    품목명 추론 로직
    1) 사용자가 직접 입력한 품목명이 있으면 그것을 우선 사용
    2) 없으면 HS코드 앞 6자리 정도로 HS_TO_PRODUCT 딕셔너리에서 추론
    """
    if manual_product:
        return manual_product.strip()

    if not hs_code:
        return None

    # 10자리 기준으로 HS → 품목명 매핑 시도
    hs10 = hs_code[:10]
    return HS_TO_PRODUCT.get(hs10)


def build_payload(
    country_input: str,
    hs_code_input: str,
    options: List[str],
    manual_product: Optional[str] = None,
    extra_note: Optional[str] = None,
) -> Dict:
    """
    최종적으로 RAG/Deep Research 파이프라인에 넘길 표준 입력 구조(payload)를 생성.
    - country: 정규화된 국가코드 (US, JP, VN 등)
    - hs_code: 정규화된 HS코드 (숫자 문자열, 4~10자리)
    - product: HS코드 또는 수동 입력으로 추론한 품목명
    - options: 분석항목 리스트 (["market", "trend", "regulation"] 등)
    - extra_note: 사용자의 추가 메모/요청
    """
    country = normalize_country(country_input)
    hs_code = normalize_hs_code(hs_code_input)
    product = infer_product_name(hs_code, manual_product)

    payload = {
        "country": country,
        "hs_code": hs_code,
        "product": product,
        "options": options,
        "extra_note": extra_note,
    }
    return payload


if __name__ == "__main__":
    # 간단한 동작 테스트 예시
    example_country = "미국"
    example_hs = " 2202991000 "
    example_options = ["market", "trend", "regulation"]
    example_product = None  # 사용자가 직접 "과실음료"라고 입력하면 여기에 넣기

    payload = build_payload(
        country_input=example_country,
        hs_code_input=example_hs,
        options=example_options,
        manual_product=example_product,
        extra_note="온라인 채널 중심으로 분석해줘",
    )

    print("[테스트 payload]")
    print(payload)
