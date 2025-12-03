import os
import logging
from core import VectorDB, DataLoader, Config
from research import RAGSearch, DeepResearch
from generator import ReportGenerator

logger = logging.getLogger(__name__)


def run_pipeline(user_input=None):
    """보고서 생성 파이프라인 실행"""
    
    logger.info("=== Report Generation Pipeline Start ===")
    
    try:
        # 1) 사용자 입력 검증
        if user_input is None:
            user_input = {
                "country": "일본",
                "hs_code": "2008190000",
                "item": "바나나우유",
                "extra_analysis": ["시장 리스크", "가격 추세"],
            }
        
        # 입력 검증
        required_fields = ["country", "hs_code", "item"]
        for field in required_fields:
            if field not in user_input:
                raise ValueError(f"필수 입력 누락: {field}")
        
        logger.info(f"사용자 입력: {user_input}")
        
        # 2) VectorDB 로드
        logger.info("Step 1: Loading VectorDB...")
        vectordb = VectorDB()
        vectordb.load()
        
        # 3) RAG Search
        logger.info("Step 2: Running RAG Search...")
        rag_search = RAGSearch(vectordb)
        rag_result = rag_search.search(
            country=user_input["country"],
            hs_code=user_input["hs_code"],
            extra=user_input.get("extra_analysis", []),
        )
        
        # 4) Deep Research
        logger.info("Step 3: Running Deep Research...")
        deep_research = DeepResearch()
        deep_result = deep_research.run_all(
            country=user_input["country"],
            product=user_input.get("item", "제품"),
            hs_code=user_input["hs_code"],
            extra=user_input.get("extra_analysis", []),
            country_code=rag_result["country_code"],
        )
        
        # 5) Draft 생성 + Deep Research 통합 + Finalize
        logger.info("Step 4: Generating Report Draft...")
        generator = ReportGenerator()
        
        # RAG 결과를 생성기에 전달
        generator.set_rag_sources(rag_result)
        
        draft = generator.generate_draft(rag_result, user_input)
        
        logger.info("Step 5: Integrating Deep Research...")
        updated = generator.integrate_deep_research(draft, deep_result)
        
        logger.info("Step 6: Finalizing Report...")
        final_report, validation = generator.finalize(updated, user_input)
        
        # 6) 출력 디렉토리 준비
        os.makedirs("output", exist_ok=True)
        
        # 텍스트 파일 저장
        text_path = "output/final_report.txt"
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(final_report)
        logger.info(f"텍스트 보고서 저장: {text_path}")
        
        # 7) PDF 생성
        logger.info("Step 7: Exporting PDF...")
        pdf_path = "output/final_report.pdf"
        generator.export_pdf(
            final_report,
            output_path=pdf_path,
            metadata={
                "country": user_input["country"],
                "hs_code": user_input["hs_code"],
                "item": user_input.get("item", "제품"),
            },
        )
        
        logger.info("=== Report Generation Completed ===")
        logger.info(f"PDF 출력: {pdf_path}")
        logger.info(f"텍스트 출력: {text_path}")
        logger.info(f"Executive Summary 검증 점수: {validation['score']}")
        
        return final_report, validation
        
    except ValueError as e:
        logger.error(f"입력 오류: {e}")
        raise
    except FileNotFoundError as e:
        logger.error(f"파일 없음: {e}")
        raise
    except Exception as e:
        logger.error(f"파이프라인 실행 실패: {e}")
        raise


def initialize_vectordb():
    """VectorDB 초기 구축 함수 (최초 1회만 실행)"""
    
    logger.info("=== VectorDB 초기 구축 시작 ===")
    
    try:
        vectordb = VectorDB()
        loader = DataLoader()
        
        # KATI & KOTRA PDF에서 청킹
        logger.info("KATI PDF 처리 중...")
        kati_docs = loader.process_all_pdfs(os.path.join(Config.DATA_DIR, "kati"))
        
        logger.info("KOTRA PDF 처리 중...")
        kotra_docs = loader.process_all_pdfs(os.path.join(Config.DATA_DIR, "kotra"))
        
        # 국가별 JSON 정보
        logger.info("국가 정보 JSON 처리 중...")
        country_docs = []
        for code in ["JP", "US", "VN", "CN", "KR"]:
            try:
                country_docs.extend(loader.process_country_json(code))
            except Exception as e:
                logger.warning(f"국가 정보 처리 실패 ({code}): {e}")
                continue
        
        all_docs = kati_docs + kotra_docs + country_docs
        
        if not all_docs:
            raise ValueError("처리된 문서가 없습니다")
        
        logger.info(f"총 {len(all_docs)}개 문서 청크 생성")
        
        vectordb.insert(all_docs)
        vectordb.save()
        
        logger.info(f"=== VectorDB 구축 완료: {len(all_docs)}개 문서 ===")
        
    except Exception as e:
        logger.error(f"VectorDB 구축 실패: {e}")
        raise


if __name__ == "__main__":
    # VectorDB 초기 구축 (최초 1회만 실행)
    # 이미 구축되어 있다면 주석 처리
    """
    try:
        initialize_vectordb()
    except Exception as e:
        logger.error(f"VectorDB 구축 중 오류: {e}")
        exit(1)
    """
    
    # 보고서 생성 파이프라인 실행
    try:
        final_report, validation = run_pipeline()
        
        # 결과 출력
        print("\n" + "="*60)
        print("보고서 생성 완료")
        print("="*60)
        print(f"Executive Summary 검증 점수: {validation['score']}/100")
        print(f"검증 메시지: {validation['message']}")
        print(f"텍스트 길이: {validation['length']}자")
        print(f"수치 포함: {validation['number_count']}개")
        print("="*60)
        
    except Exception as e:
        logger.error(f"프로그램 실행 실패: {e}")
        print(f"\n오류 발생: {e}")
        exit(1)