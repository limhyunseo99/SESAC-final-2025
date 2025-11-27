# Retriever 결과 → 섹션별 매핑 규칙 (섹션 분류 + 요약)
# src/section_mapper.py

from typing import List, Dict
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI


SECTION_KEYS = {
    "market": ["시장", "market", "overview", "규모", "성장률", "growth"],
    "trend": ["트렌드", "trend", "소비", "consumer", "수요", "lifestyle"],
    "distribution": ["유통", "distribution", "channel", "도매", "소매", "온라인몰"],
    "regulation": ["규제", "regulation", "법", "법규", "compliance", "인증"],
    "competitor": ["경쟁", "competitor", "경쟁사", "경쟁 구도", "brand"],
    "strategy": ["전략", "strategy", "진출", "recommendation", "기회", "risk"],
}


def guess_section(text: str) -> str:
    """
    단순 키워드 매칭으로 섹션 분류.
    추후 KATI/KOTRA 데이터에 맞게 키워드만 추가/수정하면 됨.
    """
    t = text.lower()

    for section, keywords in SECTION_KEYS.items():
        for kw in keywords:
            if kw.lower() in t:
                return section

    return "etc"


def map_docs_to_sections(docs: List[Document]) -> Dict[str, List[Document]]:
    """
    Retriever로부터 나온 Document 리스트를
    섹션별(dict)로 묶는 함수.
    """
    section_map: Dict[str, List[Document]] = {
        "market": [],
        "trend": [],
        "distribution": [],
        "regulation": [],
        "competitor": [],
        "strategy": [],
        "etc": [],
    }

    for d in docs:
        sec = guess_section(d.page_content)
        section_map[sec].append(d)

    return section_map


def summarize_section(
    title: str,
    docs: List[Document],
    llm: ChatOpenAI,
    max_lines: int = 7,
) -> str:
    """
    섹션별로 모아진 문서들을 하나로 합쳐서
    LLM에게 요약시키는 함수.
    """
    if not docs:
        return f"### {title}\n자료 없음.\n"

    merged = "\n\n".join([d.page_content for d in docs])

    prompt = f"""
    아래는 '{title}' 섹션에 해당하는 텍스트 조각들입니다.
    핵심 내용만 뽑아서 {max_lines}줄 이내로 한국어로 요약하세요.

    ---
    {merged}
    ---
    """

    res = llm.invoke(prompt)
    return f"### {title}\n{res.content.strip()}\n"


def build_final_report(section_map: Dict[str, List[Document]]) -> str:
    """
    섹션별 Document 묶음(section_map)을 받아
    LLM 요약을 거쳐 최종 보고서 형태의 문자열로 합치는 함수.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

    title_map = {
        "market": "시장 개요",
        "trend": "소비 트렌드 및 수요 특성",
        "distribution": "유통 구조",
        "regulation": "규제 및 인증",
        "competitor": "경쟁 환경",
        "strategy": "진출 전략 및 시사점",
        "etc": "기타 참고사항",
    }

    final_report = ""

    for sec_key, title in title_map.items():
        docs = section_map.get(sec_key, [])
        section_text = summarize_section(title, docs, llm)
        final_report += section_text + "\n"

    return final_report


if __name__ == "__main__":
    # 간단 테스트용: 가짜 Document 2~3개를 만들어서 섹션 분류/요약해보기
    fake_docs = [
        Document(
            page_content="미국 음료 시장의 규모와 성장률은 최근 5년간 꾸준히 증가하였다.",
            metadata={},
        ),
        Document(
            page_content="온라인 채널 중심의 유통 구조가 강화되고 있으며, 대형마트 비중은 감소 추세이다.",
            metadata={},
        ),
        Document(
            page_content="식품 안전 관련 규제가 강화되면서 수입 인증 절차가 복잡해졌다.",
            metadata={},
        ),
    ]

    section_map = map_docs_to_sections(fake_docs)
    report = build_final_report(section_map)
    print(report)
