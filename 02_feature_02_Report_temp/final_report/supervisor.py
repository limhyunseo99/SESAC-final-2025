# supervisor_upgraded.py
# 섹션별 최적 전략 선택 v2.0
# 신규: summary, risk, regulation, price 섹션 전략 추가

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
                "require_source": bool, # 출처 필수 여부 (신규)
                "reason": str          # 전략 선택 이유
            }
        """
        
        strategies = {
            # ============================================================
            # 신규: Executive Summary
            # ============================================================
            "summary": {
                "use_json": False,  # 다른 섹션에서 생성
                "use_kati": False,
                "use_pdf": False,
                "use_web": False,
                "require_source": True,
                "reason": "📋 다른 섹션 완료 후 자동 생성"
            },
            
            # ============================================================
            # 기본 섹션
            # ============================================================
            "overview": {
                "use_json": True,
                "use_kati": False,
                "use_pdf": False,
                "use_web": False,
                "require_source": True,
                "reason": "📊 country_info만으로 충분 (GDP, 인구 등 공식 통계)"
            },
            
            "market_size": {
                "use_json": True,
                "use_kati": True,
                "use_pdf": True,
                "use_web": False,
                "require_source": True,
                "reason": "📈 KATI 수치 데이터 중요 + KOTRA 심층 분석"
            },
            
            "distribution": {
                "use_json": True,
                "use_kati": False,
                "use_pdf": True,
                "use_web": False,
                "require_source": True,
                "reason": "🚚 KOTRA 유통 구조 정보가 핵심"
            },
            
            # ============================================================
            # 분석 섹션 (출처 필수 강화)
            # ============================================================
            "regulation": {
                "use_json": True,
                "use_kati": True,
                "use_pdf": True,
                "use_web": True,  # 최신 규제 변경 확인
                "require_source": True,  # 🔴 출처 필수
                "reason": "⚖️ 최신 규제 변경 필수 확인 (웹 검색) - 출처 필수"
            },
            
            "risk": {
                "use_json": True,
                "use_kati": True,
                "use_pdf": True,
                "use_web": True,  # 최신 리스크 확인
                "require_source": True,  # 🔴 출처 필수
                "reason": "⚠️ 최신 리스크 요인 파악 (정책 변화) - 출처 필수"
            },
            
            "price": {
                "use_json": True,
                "use_kati": True,
                "use_pdf": True,
                "use_web": False,
                "require_source": True,  # 🔴 출처 필수
                "reason": "💰 KATI 가격 통계 + KOTRA 가격대 분석 - 출처 필수"
            },
            
            "demand": {
                "use_json": True,
                "use_kati": True,
                "use_pdf": True,
                "use_web": True,
                "require_source": True,
                "reason": "📊 소비 트렌드는 최신 정보 필요"
            }
        }
        
        # 기본 전략 (알 수 없는 섹션)
        default_strategy = {
            "use_json": True,
            "use_kati": True,
            "use_pdf": True,
            "use_web": False,
            "require_source": True,
            "reason": "🔄 기본 전략: JSON → KATI → PDF (출처 필수)"
        }
        
        return strategies.get(section_key, default_strategy)
    
    def get_section_order(self) -> list:
        """섹션 생성 순서 반환"""
        return [
            "overview",      # 1. 국가 및 시장 개요
            "market_size",   # 2. 시장 규모
            "distribution",  # 3. 유통 구조
            "risk",          # 4. 시장 리스크
            "regulation",    # 5. 규제 검토
            "price",         # 6. 가격 추세
            "demand",        # 7. 수요 전망 (선택)
            "summary",       # 8. 요약 (마지막에 생성)
        ]
    
    def get_mandatory_sections(self) -> list:
        """필수 섹션 목록"""
        return [
            "summary",       # Executive Summary
            "overview",      # 국가 개요
            "market_size",   # 시장 규모
            "distribution",  # 유통 구조
            "risk",          # 시장 리스크
            "regulation",    # 규제 검토
            "price",         # 가격 추세
        ]
    
    def get_optional_sections(self) -> list:
        """선택 섹션 목록"""
        return [
            "demand",        # 수요 전망
        ]
    
    def validate_section_output(self, section_key: str, content: str) -> dict:
        """
        섹션 출력 검증
        
        Returns:
            {
                "valid": bool,
                "issues": list,
                "score_penalty": int
            }
        """
        strategy = self.get_strategy(section_key)
        issues = []
        penalty = 0
        
        # 1. 출처 검증 (require_source가 True인 경우)
        if strategy.get("require_source", True):
            if "[출처:" not in content and "출처:" not in content:
                issues.append("출처 표기 누락")
                penalty += 30  # 심각한 감점
            else:
                # 출처 개수 확인
                source_count = content.count("[출처:")
                if source_count < 3:
                    issues.append(f"출처 부족 ({source_count}개)")
                    penalty += 10
        
        # 2. 길이 검증
        if len(content) < 300:
            issues.append("내용 길이 부족 (최소 300자)")
            penalty += 15
        
        # 3. 일반론 표현 검사
        general_phrases = [
            "유망하다", "경쟁이 심하다", "성장 가능성이 높다",
            "증가할 것", "예상된다", "전망이다", "~하는 경향"
        ]
        found_general = [p for p in general_phrases if p in content]
        if found_general:
            issues.append(f"일반론 표현 감지: {found_general[:3]}")
            penalty += len(found_general) * 5
        
        # 4. 섹션별 특수 검증
        if section_key == "market_size":
            # 시장 규모는 수치가 필수
            import re
            numbers = re.findall(r'\d+[,.]?\d*[%억만달러원]', content)
            if len(numbers) < 3:
                issues.append("수치 데이터 부족")
                penalty += 10
        
        if section_key == "regulation":
            # 규제는 관세율 필수
            if "관세" not in content and "%" not in content:
                issues.append("관세율 정보 누락")
                penalty += 15
        
        if section_key == "price":
            # 가격은 구체적 금액 필수
            if "$" not in content and "달러" not in content and "원" not in content:
                issues.append("가격 정보 누락")
                penalty += 15
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "score_penalty": min(penalty, 50)  # 최대 50점 감점
        }