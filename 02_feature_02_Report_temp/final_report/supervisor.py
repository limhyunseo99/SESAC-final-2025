# supervisor.py
# 섹션별 최적 전략 선택
# 🔧 수정사항:
# 1. 점수 계산 방식 완화 및 명확화
# 2. relevance 평가 포함
# 3. summary는 별도 점수 로직 적용

class StrategySelector:
    """섹션별 최적 연구 전략 선택"""
    
    def get_strategy(self, section_key: str) -> dict:
        """
        섹션에 따라 최적 전략 반환
        
        Returns:
            {
                "use_json": bool,      # country_info 사용 여부
                "use_kati": bool,      # KATI 검증 여부
                "use_pdf": bool,       # KOTRA PDF 보완 여부
                "use_web": bool,       # 웹 검색 여부
                "min_score": int,      # 🔧 신규: 최소 품질 점수
                "reason": str          # 전략 선택 이유
            }
        """
        
        strategies = {
            # 🔧 summary는 별도 처리 - 낮은 기준
            "summary": {
                "use_json": False,
                "use_kati": False,
                "use_pdf": False,
                "use_web": False,
                "min_score": 50,  # 🔧 summary는 기준 완화
                "reason": "📋 요약은 다른 섹션 완료 후 자동 생성"
            },
            
            "overview": {
                "use_json": True,
                "use_kati": False,
                "use_pdf": False,
                "use_web": False,
                "min_score": 70,
                "reason": "📊 country_info만으로 충분 (GDP, 인구 등 공식 통계)"
            },
            
            "market_size": {
                "use_json": True,
                "use_kati": True,
                "use_pdf": True,
                "use_web": False,
                "min_score": 70,
                "reason": "📈 KATI 수치 데이터 중요 + KOTRA 심층 분석"
            },
            
            "distribution": {
                "use_json": True,
                "use_kati": False,
                "use_pdf": True,
                "use_web": False,
                "min_score": 70,
                "reason": "🚚 KOTRA 유통 구조 정보가 핵심"
            },
            
            "regulation": {
                "use_json": True,
                "use_kati": False,
                "use_pdf": True,
                "use_web": True,
                "min_score": 70,
                "reason": "⚖️ 최신 규제 변경 필수 확인 (웹 검색)"
            },
            
            "risk": {
                "use_json": True,
                "use_kati": False,
                "use_pdf": True,
                "use_web": True,
                "min_score": 70,
                "reason": "⚠️ 최신 리스크 요인 파악 (정책 변화)"
            },
            
            "price": {
                "use_json": True,
                "use_kati": True,
                "use_pdf": True,
                "use_web": False,
                "min_score": 70,
                "reason": "💰 KATI 가격 통계 + KOTRA 가격대 분석"
            },
            
            "demand": {
                "use_json": True,
                "use_kati": True,
                "use_pdf": True,
                "use_web": True,
                "min_score": 70,
                "reason": "📊 소비 트렌드는 최신 정보 필요"
            },
            
            # 🔧 신규: SNS 해시태그 섹션
            "sns_hashtag": {
                "use_json": False,
                "use_kati": False,
                "use_pdf": False,
                "use_web": False,
                "min_score": 50,  # SNS는 데이터 기반이라 기준 완화
                "reason": "📱 SNS 데이터 기반 분석 (외부 데이터)"
            }
        }
        
        # 기본 전략 (알 수 없는 섹션)
        default_strategy = {
            "use_json": True,
            "use_kati": True,
            "use_pdf": True,
            "use_web": False,
            "min_score": 70,
            "reason": "🔄 기본 전략: JSON → KATI → PDF"
        }
        
        return strategies.get(section_key, default_strategy)
    
    def get_section_weight(self, section_key: str) -> float:
        """
        🔧 신규: 섹션별 가중치 반환
        최종 보고서 품질 계산에 사용
        """
        weights = {
            "summary": 0.15,       # Executive Summary
            "overview": 0.10,     # 국가 개요
            "market_size": 0.20,  # 시장 규모 (중요)
            "distribution": 0.15, # 유통 구조
            "regulation": 0.15,   # 규제 (중요)
            "risk": 0.10,         # 리스크
            "price": 0.10,        # 가격
            "demand": 0.05,       # 수요 (선택)
            "sns_hashtag": 0.05,  # SNS (선택)
        }
        return weights.get(section_key, 0.05)
    
    def calculate_report_quality(self, sections: dict) -> dict:
        """
        🔧 신규: 전체 보고서 품질 점수 계산
        
        Args:
            sections: {section_key: {"score": int, "passed": bool}}
            
        Returns:
            {
                "total_score": float,
                "grade": str,
                "passed_sections": int,
                "total_sections": int,
                "recommendation": str
            }
        """
        total_weighted_score = 0
        total_weight = 0
        passed_count = 0
        
        for key, section in sections.items():
            weight = self.get_section_weight(key)
            score = section.get("score", 0)
            
            total_weighted_score += score * weight
            total_weight += weight
            
            if section.get("passed", False):
                passed_count += 1
        
        # 가중 평균 점수
        if total_weight > 0:
            avg_score = total_weighted_score / total_weight
        else:
            avg_score = 0
        
        # 등급 계산
        if avg_score >= 90:
            grade = "A"
            recommendation = "출판 준비 완료"
        elif avg_score >= 80:
            grade = "B"
            recommendation = "출판 가능 (일부 검토 권장)"
        elif avg_score >= 70:
            grade = "C"
            recommendation = "출판 전 수정 필요"
        elif avg_score >= 50:
            grade = "D"
            recommendation = "대폭 수정 필요"
        else:
            grade = "F"
            recommendation = "재작성 권장"
        
        return {
            "total_score": round(avg_score, 1),
            "grade": grade,
            "passed_sections": passed_count,
            "total_sections": len(sections),
            "recommendation": recommendation
        }
    
    def validate_hs_relevance(self, content: str, hs_code: str, item: str) -> dict:
        """
        🔧 신규: HS Code 관련성 평가
        
        Args:
            content: 섹션 내용
            hs_code: HS 코드
            item: 품목명
            
        Returns:
            {
                "relevant": bool,
                "score": float (0-1),
                "keywords_found": list,
                "irrelevant_content": list
            }
        """
        import re
        
        # HS Code 카테고리별 키워드
        hs_keywords = {
            "22": ["음료", "주류", "와인", "맥주", "주스", "탄산", "beverage", "wine", "beer", "juice"],
            "09": ["커피", "차", "tea", "coffee"],
            "17": ["과자", "사탕", "설탕", "candy", "sugar"],
            "18": ["초콜릿", "코코아", "chocolate", "cocoa"],
            "19": ["빵", "비스킷", "bread", "biscuit"],
            "87": ["자동차", "차량", "car", "vehicle", "automobile"],
            "88": ["항공기", "비행기", "aircraft", "airplane"],
        }
        
        # HS 코드 2자리 추출
        hs_clean = re.sub(r'[.\s]', '', str(hs_code))
        hs_2digit = hs_clean[:2] if len(hs_clean) >= 2 else ""
        
        # 해당 카테고리 키워드
        category_keywords = hs_keywords.get(hs_2digit, [])
        category_keywords.append(item.lower())
        
        content_lower = content.lower()
        
        # 키워드 매칭
        found_keywords = [kw for kw in category_keywords if kw.lower() in content_lower]
        
        # 무관한 내용 감지 (다른 카테고리 키워드)
        irrelevant = []
        for other_hs, other_keywords in hs_keywords.items():
            if other_hs != hs_2digit:
                for kw in other_keywords:
                    if kw.lower() in content_lower and kw not in found_keywords:
                        irrelevant.append(kw)
        
        # 점수 계산
        if not category_keywords:
            score = 0.5
        else:
            score = len(found_keywords) / len(category_keywords)
        
        # 무관한 내용이 많으면 감점
        if irrelevant:
            penalty = min(len(irrelevant) * 0.1, 0.4)
            score = max(0, score - penalty)
        
        return {
            "relevant": score >= 0.3,
            "score": score,
            "keywords_found": found_keywords,
            "irrelevant_content": list(set(irrelevant))
        }