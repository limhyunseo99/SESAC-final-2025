# supervisor.py
"""
통합 Supervisor 모듈
- 검색 품질 평가
- 출처 검증 (URL 필터링)
- 환각 탐지
- 보고서 품질 체크
"""

import re
import json
from typing import List, Dict
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage


class Supervisor:
    """통합 검증 및 품질 관리"""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model, temperature=0)

        # 국가별 공공기관 도메인
        self.gov_whitelist = {
            "JP": ["go.jp"],
            "VN": ["gov.vn"],
            "US": [".gov"],
            "CN": ["gov.cn"],
            "KR": ["go.kr"],
        }

        # 한국 공공/준공공기관
        self.kr_whitelist = [
            "kotra.or.kr",
            "koti.re.kr",
            "kati.net",
            "customs.go.kr",
            "unipass.customs.go.kr",
            "mafra.go.kr",
            "moef.go.kr",
            "trade.go.kr",
        ]

        # 국제기구
        self.intl_whitelist = [
            "oecd.org",
            "fao.org",
            "un.org",
            "wto.org",
            "worldbank.org",
            "imf.org",
        ]

        self.validation_log = []

    def _extract_domain(self, url: str) -> str:
        """URL에서 도메인 추출"""
        match = re.search(r"https?://([^/]+)", url)
        return match.group(1).lower() if match else ""

    def validate_source(
        self, urls: List[str], country_code: str, source_type: str = "regulation"
    ) -> Dict:

        country_code = country_code.upper()
        gov_domains = self.gov_whitelist.get(country_code, [])

        valid_urls = []
        rejected_urls = []
        warnings = []

        for url in urls:
            if not url:
                continue

            domain = self._extract_domain(url)

            # 국가 공공기관
            is_gov = any(domain.endswith(g) for g in gov_domains)

            # 한국 공공기관
            is_kr = any(domain.endswith(k) for k in self.kr_whitelist)

            # 국제기구
            is_intl = any(domain.endswith(i) for i in self.intl_whitelist)

            if source_type == "regulation":
                if is_gov or is_kr:
                    valid_urls.append(url)
                else:
                    rejected_urls.append(url)
                    warnings.append(f"규제 출처 부적합: {url}")

            elif source_type == "price_risk":
                if is_gov or is_kr or is_intl:
                    valid_urls.append(url)
                else:
                    rejected_urls.append(url)

            else:
                rejected_urls.append(url)

        is_valid = len(valid_urls) > 0

        if not is_valid and source_type == "regulation":
            warnings.append(f"{country_code}: 규제 정보에 공공기관 출처 없음")

        self.validation_log.append(
            {
                "type": "source_validation",
                "source_type": source_type,
                "country_code": country_code,
                "valid_count": len(valid_urls),
                "rejected_count": len(rejected_urls),
            }
        )

        return {
            "is_valid": is_valid,
            "valid_urls": valid_urls,
            "rejected_urls": rejected_urls,
            "warnings": warnings,
        }

    def evaluate_search_quality(
        self, results: List[Dict], query: str, research_type: str, country_code: str
    ) -> Dict:

        urls = [r.get("url", "") for r in results if isinstance(r, dict)]

        source_type = "regulation" if "규제" in research_type else "price_risk"
        validation = self.validate_source(urls, country_code, source_type)

        if not validation["is_valid"]:
            return {
                "quality_score": 30,
                "is_sufficient": False,
                "confidence": "low",
                "missing_aspects": ["공공기관 출처 없음"],
                "next_query_suggestions": [
                    f"{query} site:{self.gov_whitelist.get(country_code, ['gov'])[0]}",
                    f"{query} 공식 발표",
                    f"{query} official report",
                ],
                "source_validation": validation,
            }

        prompt = f"""
다음 검색 결과의 품질을 평가하세요.

평가 대상: {research_type}
국가: {country_code}
검색어: {query}
결과 수: {len(results)}

JSON만 출력:
{{
    "quality_score": 80,
    "is_sufficient": true,
    "confidence": "high",
    "missing_aspects": []
}}
"""

        try:
            response = self.llm.invoke(prompt)
            content = response.content if isinstance(response, AIMessage) else str(response)

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                eval_result = json.loads(json_match.group(0))
            else:
                eval_result = {
                    "quality_score": 60,
                    "is_sufficient": True,
                    "confidence": "medium",
                    "missing_aspects": [],
                }

            eval_result["source_validation"] = validation

            self.validation_log.append(
                {
                    "type": "search_quality",
                    "research_type": research_type,
                    "score": eval_result.get("quality_score", 0),
                }
            )

            return eval_result

        except Exception as e:
            return {
                "quality_score": 50,
                "is_sufficient": False,
                "confidence": "low",
                "missing_aspects": [f"평가 오류: {str(e)}"],
                "source_validation": validation,
            }

    def detect_hallucination(self, generated_text: str, source_docs: List[str]) -> Dict:

        number_pattern = r'\d+[,.]?\d*\s*(?:억|조|만|천|%|달러|USD|원)'
        generated_numbers = re.findall(number_pattern, generated_text)

        source_numbers = []
        for doc in source_docs:
            source_numbers.extend(re.findall(number_pattern, doc))

        suspicious = [n for n in generated_numbers if n not in source_numbers]

        has_hallucination = len(suspicious) > 3

        self.validation_log.append(
            {
                "type": "hallucination_check",
                "suspicious_count": len(suspicious),
                "has_hallucination": has_hallucination,
            }
        )

        return {
            "has_hallucination": has_hallucination,
            "suspicious_claims": suspicious[:5],
            "confidence": 1.0 - (len(suspicious) / max(len(generated_numbers), 1)),
        }

    def validate_section(self, section_text: str, section_name: str) -> Dict:

        issues = []
        stats = {
            "length": len(section_text),
            "numbers_count": 0,
            "has_source": False,
            "forbidden_phrases": [],
        }

        min_length = 300 if "Executive" in section_name else 200
        if len(section_text) < min_length:
            issues.append(f"길이 부족: {len(section_text)}자 (최소 {min_length}자)")

        numbers = re.findall(r'\d+[,.]?\d*', section_text)
        stats["numbers_count"] = len(numbers)
        if stats["numbers_count"] < 2:
            issues.append("구체적 수치 부족 (최소 2개)")

        has_citation = bool(re.search(r'\[.*?\]|출처:|source:', section_text, re.IGNORECASE))
        stats["has_source"] = has_citation
        if not has_citation and "Executive" not in section_name:
            issues.append("출처 표기 없음")

        forbidden = ["약간", "다소", "어느 정도", "~것으로 보인다", "추정"]
        found_forbidden = [f for f in forbidden if f in section_text]
        stats["forbidden_phrases"] = found_forbidden
        if found_forbidden:
            issues.append(f"모호한 표현: {', '.join(found_forbidden)}")

        score = 100 - (len(issues) * 15)
        score = max(0, score)

        return {
            "passed": len(issues) == 0,
            "score": score,
            "issues": issues,
            "stats": stats,
        }

    def validate_executive_summary(self, summary_text: str) -> Dict:

        issues = []
        stats = {
            "length": len(summary_text),
            "numbers_count": 0,
            "specific_metrics": [],
        }

        if len(summary_text) < 300:
            issues.append(f"길이 부족: {len(summary_text)}자 (최소 300자)")

        number_patterns = [
            r"\d+,?\d*\.?\d*억",
            r"\d+,?\d*\.?\d*조",
            r"\d+,?\d*\.?\d*%",
            r"\$\d+,?\d*\.?\d*[MB]?",
            r"\d{1,3}(?:,\d{3})*",
        ]

        all_numbers = []
        for pattern in number_patterns:
            matches = re.findall(pattern, summary_text)
            all_numbers.extend(matches)

        stats["numbers_count"] = len(set(all_numbers))
        stats["specific_metrics"] = list(set(all_numbers))[:5]

        if stats["numbers_count"] < 3:
            issues.append(f"구체적 수치 부족: {stats['numbers_count']}개 (최소 3개)")

        required_keywords = ["시장", "규모", "전략", "기회", "리스크"]
        missing_keywords = [kw for kw in required_keywords if kw not in summary_text]
        if missing_keywords:
            issues.append(f"필수 키워드 누락: {', '.join(missing_keywords)}")

        score = 100 - (len(issues) * 10)
        score = max(0, score)

        return {
            "passed": len(issues) == 0,
            "score": score,
            "issues": issues,
            "stats": stats,
        }

    def get_validation_summary(self) -> Dict:
        return {
            "total_validations": len(self.validation_log),
            "details": self.validation_log,
        }
