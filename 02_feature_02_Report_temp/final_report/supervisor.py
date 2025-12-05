# supervisor.py
# 섹션별 최적 전략 선택

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
                "reason": str          # 전략 선택 이유
            }
        """
        
        strategies = {
            "overview": {
                "use_json": True,
                "use_kati": False,
                "use_pdf": False,
                "use_web": False,
                "reason": "📊 country_info만으로 충분 (GDP, 인구 등 공식 통계)"
            },
            
            "market_size": {
                "use_json": True,
                "use_kati": True,
                "use_pdf": True,
                "use_web": False,
                "reason": "📈 KATI 수치 데이터 중요 + KOTRA 심층 분석"
            },
            
            "distribution": {
                "use_json": True,
                "use_kati": False,
                "use_pdf": True,
                "use_web": False,
                "reason": "🚚 KOTRA 유통 구조 정보가 핵심"
            },
            
            "regulation": {
                "use_json": True,
                "use_kati": False,
                "use_pdf": True,
                "use_web": True,
                "reason": "⚖️ 최신 규제 변경 필수 확인 (웹 검색)"
            },
            
            "risk": {
                "use_json": True,
                "use_kati": False,
                "use_pdf": True,
                "use_web": True,
                "reason": "⚠️ 최신 리스크 요인 파악 (정책 변화)"
            },
            
            "price": {
                "use_json": True,
                "use_kati": True,
                "use_pdf": True,
                "use_web": False,
                "reason": "💰 KATI 가격 통계 + KOTRA 가격대 분석"
            },
            
            "demand": {
                "use_json": True,
                "use_kati": True,
                "use_pdf": True,
                "use_web": True,
                "reason": "📊 소비 트렌드는 최신 정보 필요"
            }
        }
        
        # 기본 전략 (알 수 없는 섹션)
        default_strategy = {
            "use_json": True,
            "use_kati": True,
            "use_pdf": True,
            "use_web": False,
            "reason": "🔄 기본 전략: JSON → KATI → PDF"
        }
        
        return strategies.get(section_key, default_strategy)