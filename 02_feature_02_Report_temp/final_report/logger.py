# logger.py
# 상세 로깅 시스템 - 사용자 활동 및 Supervisor 의사결정 추적

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path
from enum import Enum


LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


class PipelineStage(Enum):
    """파이프라인 단계 정의"""
    INPUT_PARSING = "input_parsing"
    QUERY_GENERATION = "query_generation"
    DRAFT_GENERATION = "draft_generation"
    RAG_SEARCH = "rag_search"
    KATI_VERIFICATION = "kati_verification"
    PDF_ENHANCEMENT = "pdf_enhancement"
    WEB_SEARCH = "web_search"
    SUPERVISOR_EVALUATION = "supervisor_evaluation"
    REPORT_GENERATION = "report_generation"
    PDF_EXPORT = "pdf_export"
    COMPLETED = "completed"


class SupervisorAction(Enum):
    """Supervisor 액션 타입"""
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"
    MERGE = "merge"
    FILTER = "filter"


@dataclass
class UserActivityLog:
    """사용자 활동 로그"""
    timestamp: str
    stage: str
    action: str
    input_data: Dict = field(default_factory=dict)
    output_data: Dict = field(default_factory=dict)
    duration_ms: float = 0
    success: bool = True
    error_message: str = ""


@dataclass
class CandidateResult:
    """Supervisor가 평가한 후보 결과"""
    candidate_id: str
    source: str
    content_preview: str
    content_length: int
    scores: Dict[str, int] = field(default_factory=dict)
    total_score: int = 0
    grade: str = ""
    passed: bool = False
    filter_reasons: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class SupervisorDecisionLog:
    """Supervisor 의사결정 로그"""
    decision_id: str
    timestamp: str
    section: str
    stage: str
    candidates: List[CandidateResult] = field(default_factory=list)
    total_candidates: int = 0
    action: str = ""
    selected_candidate_ids: List[str] = field(default_factory=list)
    rejected_candidate_ids: List[str] = field(default_factory=list)
    selection_reason: str = ""
    selection_criteria: Dict = field(default_factory=dict)
    before_content: str = ""
    before_length: int = 0
    after_content: str = ""
    after_length: int = 0
    improvement_delta: int = 0
    processing_time_ms: float = 0


@dataclass
class SectionProcessingLog:
    """섹션별 처리 로그"""
    section_key: str
    section_title: str
    started_at: str = ""
    ended_at: str = ""
    stage_snapshots: Dict[str, Dict] = field(default_factory=dict)
    supervisor_decisions: List[SupervisorDecisionLog] = field(default_factory=list)
    final_score: int = 0
    final_grade: str = ""
    included_in_report: bool = False
    sources_used: List[str] = field(default_factory=list)
    content_evolution: List[Dict] = field(default_factory=list)


@dataclass
class SessionLog:
    """세션 전체 로그"""
    session_id: str
    started_at: str
    ended_at: str = ""
    user_input: Dict = field(default_factory=dict)
    selected_options: List[str] = field(default_factory=list)
    user_activities: List[UserActivityLog] = field(default_factory=list)
    sections: Dict[str, SectionProcessingLog] = field(default_factory=dict)
    stats: Dict = field(default_factory=dict)
    errors: List[Dict] = field(default_factory=list)


class ResearchLogger:
    """연구 파이프라인 로거"""
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.session = SessionLog(
            session_id=self.session_id,
            started_at=datetime.now().isoformat()
        )
        self._decision_counter = 0
        self._candidate_counter = 0
        
        self.log_file = LOG_DIR / f"session_{self.session_id}.log"
        self.json_file = LOG_DIR / f"session_{self.session_id}.json"
        
        self._setup_file_logger()
    
    def _setup_file_logger(self):
        """파일 로거 설정"""
        self.file_logger = logging.getLogger(f"research_{self.session_id}")
        self.file_logger.setLevel(logging.DEBUG)
        self.file_logger.handlers = []
        
        handler = logging.FileHandler(self.log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        self.file_logger.addHandler(handler)
        
        self.file_logger.info(f"세션 시작: {self.session_id}")
    
    def log_user_input(self, payload: Dict):
        """사용자 입력 기록"""
        self.session.user_input = payload.copy()
        self.session.selected_options = payload.get("options", [])
        
        activity = UserActivityLog(
            timestamp=datetime.now().isoformat(),
            stage=PipelineStage.INPUT_PARSING.value,
            action="user_input_received",
            input_data=payload
        )
        self.session.user_activities.append(activity)
        
        self.file_logger.info(f"USER_INPUT: country={payload.get('country')}, "
                              f"hs_code={payload.get('hs_code')}, "
                              f"item={payload.get('item')}, "
                              f"options={payload.get('options')}")
    
    def log_stage_start(self, stage: PipelineStage, details: Dict = None):
        """단계 시작 기록"""
        activity = UserActivityLog(
            timestamp=datetime.now().isoformat(),
            stage=stage.value,
            action="stage_started",
            input_data=details or {}
        )
        self.session.user_activities.append(activity)
        
        self.file_logger.info(f"STAGE_START: {stage.value} | {details or ''}")
    
    def log_stage_end(self, stage: PipelineStage, result: Dict = None, 
                      duration_ms: float = 0, success: bool = True, error: str = ""):
        """단계 종료 기록"""
        activity = UserActivityLog(
            timestamp=datetime.now().isoformat(),
            stage=stage.value,
            action="stage_completed" if success else "stage_failed",
            output_data=result or {},
            duration_ms=duration_ms,
            success=success,
            error_message=error
        )
        self.session.user_activities.append(activity)
        
        status = "SUCCESS" if success else "FAILED"
        self.file_logger.info(f"STAGE_END: {stage.value} | {status} | {duration_ms:.1f}ms")
        if error:
            self.file_logger.error(f"  ERROR: {error}")
    
    def start_section(self, section_key: str, section_title: str):
        """섹션 처리 시작"""
        self.session.sections[section_key] = SectionProcessingLog(
            section_key=section_key,
            section_title=section_title,
            started_at=datetime.now().isoformat()
        )
        self.file_logger.info(f"SECTION_START: [{section_key}] {section_title}")
    
    def add_stage_snapshot(self, section_key: str, stage: str, content: str, metadata: Dict = None):
        """단계별 콘텐츠 스냅샷 저장"""
        if section_key not in self.session.sections:
            return
        
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "content": content,
            "length": len(content),
            "preview": content[:300] + "..." if len(content) > 300 else content,
            "metadata": metadata or {}
        }
        
        self.session.sections[section_key].stage_snapshots[stage] = snapshot
        self.session.sections[section_key].content_evolution.append({
            "stage": stage,
            "length": len(content),
            "timestamp": snapshot["timestamp"]
        })
        
        self.file_logger.debug(f"SNAPSHOT: [{section_key}] {stage} = {len(content)}자")
    
    def end_section(self, section_key: str, final_score: int, final_grade: str, 
                    included: bool, sources: List[str]):
        """섹션 처리 완료"""
        if section_key not in self.session.sections:
            return
        
        section = self.session.sections[section_key]
        section.ended_at = datetime.now().isoformat()
        section.final_score = final_score
        section.final_grade = final_grade
        section.included_in_report = included
        section.sources_used = sources
        
        self.file_logger.info(f"SECTION_END: [{section_key}] score={final_score}, "
                              f"grade={final_grade}, included={included}")
    
    def log_supervisor_evaluation(
        self,
        section_key: str,
        stage: str,
        candidates: List[Dict],
        before_content: str = ""
    ) -> str:
        """Supervisor 평가 시작 - 후보 목록 기록"""
        
        self._decision_counter += 1
        decision_id = f"DEC_{self._decision_counter:04d}"
        
        candidate_results = []
        for i, cand in enumerate(candidates):
            self._candidate_counter += 1
            cand_id = f"CAND_{self._candidate_counter:04d}"
            
            content = cand.get("content", "")
            candidate_results.append(CandidateResult(
                candidate_id=cand_id,
                source=cand.get("source", "unknown"),
                content_preview=content[:200] + "..." if len(content) > 200 else content,
                content_length=len(content),
                scores=cand.get("scores", {}),
                total_score=cand.get("total_score", 0),
                grade=cand.get("grade", ""),
                passed=cand.get("passed", False),
                filter_reasons=cand.get("filter_reasons", []),
                metadata=cand.get("metadata", {})
            ))
        
        decision = SupervisorDecisionLog(
            decision_id=decision_id,
            timestamp=datetime.now().isoformat(),
            section=section_key,
            stage=stage,
            candidates=candidate_results,
            total_candidates=len(candidates),
            before_content=before_content[:500] if before_content else "",
            before_length=len(before_content) if before_content else 0
        )
        
        if section_key in self.session.sections:
            self.session.sections[section_key].supervisor_decisions.append(decision)
        
        self.file_logger.info(f"SUPERVISOR_EVAL: {decision_id} | [{section_key}] {stage} | "
                              f"{len(candidates)}개 후보 평가")
        
        for cr in candidate_results:
            status = "PASS" if cr.passed else "FAIL"
            self.file_logger.debug(f"  {cr.candidate_id}: {cr.source} | "
                                   f"score={cr.total_score} | {status}")
            if cr.filter_reasons:
                self.file_logger.debug(f"    필터링 사유: {', '.join(cr.filter_reasons)}")
        
        return decision_id
    
    def log_supervisor_decision(
        self,
        decision_id: str,
        section_key: str,
        action: SupervisorAction,
        selected_ids: List[str],
        rejected_ids: List[str],
        reason: str,
        criteria: Dict,
        after_content: str = "",
        processing_time_ms: float = 0
    ):
        """Supervisor 최종 결정 기록"""
        
        if section_key not in self.session.sections:
            return
        
        for decision in self.session.sections[section_key].supervisor_decisions:
            if decision.decision_id == decision_id:
                decision.action = action.value
                decision.selected_candidate_ids = selected_ids
                decision.rejected_candidate_ids = rejected_ids
                decision.selection_reason = reason
                decision.selection_criteria = criteria
                decision.after_content = after_content[:500] if after_content else ""
                decision.after_length = len(after_content) if after_content else 0
                decision.improvement_delta = decision.after_length - decision.before_length
                decision.processing_time_ms = processing_time_ms
                break
        
        self.file_logger.info(f"SUPERVISOR_DECISION: {decision_id} | action={action.value}")
        self.file_logger.info(f"  선택: {selected_ids}")
        self.file_logger.info(f"  제외: {rejected_ids}")
        self.file_logger.info(f"  근거: {reason}")
    
    def log_error(self, stage: str, error_msg: str, details: Dict = None):
        """오류 기록"""
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "stage": stage,
            "message": error_msg,
            "details": details or {}
        }
        self.session.errors.append(error_entry)
        self.file_logger.error(f"ERROR [{stage}]: {error_msg}")
    
    def finalize(self) -> str:
        """세션 종료 및 저장"""
        self.session.ended_at = datetime.now().isoformat()
        
        self.session.stats = {
            "total_sections": len(self.session.sections),
            "passed_sections": sum(1 for s in self.session.sections.values() if s.included_in_report),
            "rejected_sections": sum(1 for s in self.session.sections.values() if not s.included_in_report),
            "total_decisions": sum(len(s.supervisor_decisions) for s in self.session.sections.values()),
            "total_activities": len(self.session.user_activities),
            "total_errors": len(self.session.errors),
            "sources_summary": self._count_sources()
        }
        
        with open(self.json_file, "w", encoding="utf-8") as f:
            json.dump(asdict(self.session), f, ensure_ascii=False, indent=2)
        
        self.file_logger.info(f"SESSION_END: {self.session_id}")
        self.file_logger.info(f"  로그 저장: {self.json_file}")
        
        return str(self.json_file)
    
    def _count_sources(self) -> Dict[str, int]:
        """출처 유형별 카운트"""
        counts = {"json": 0, "pdf": 0, "web": 0, "csv": 0}
        for section in self.session.sections.values():
            for src in section.sources_used:
                src_lower = src.lower()
                if ".json" in src_lower:
                    counts["json"] += 1
                elif ".pdf" in src_lower:
                    counts["pdf"] += 1
                elif "웹:" in src or "http" in src_lower:
                    counts["web"] += 1
                elif ".csv" in src_lower:
                    counts["csv"] += 1
        return counts
    
    def get_section_comparison(self, section_key: str) -> Dict:
        """섹션의 전후 비교 데이터"""
        if section_key not in self.session.sections:
            return {}
        
        section = self.session.sections[section_key]
        
        return {
            "section_key": section_key,
            "title": section.section_title,
            "content_evolution": section.content_evolution,
            "stage_snapshots": {
                stage: {
                    "length": snap["length"],
                    "preview": snap["preview"],
                    "timestamp": snap["timestamp"]
                }
                for stage, snap in section.stage_snapshots.items()
            },
            "supervisor_decisions": [
                {
                    "decision_id": d.decision_id,
                    "stage": d.stage,
                    "action": d.action,
                    "total_candidates": d.total_candidates,
                    "selected_count": len(d.selected_candidate_ids),
                    "rejected_count": len(d.rejected_candidate_ids),
                    "reason": d.selection_reason,
                    "before_length": d.before_length,
                    "after_length": d.after_length,
                    "improvement": d.improvement_delta,
                    "candidates_detail": [
                        {
                            "id": c.candidate_id,
                            "source": c.source,
                            "score": c.total_score,
                            "grade": c.grade,
                            "passed": c.passed,
                            "reasons": c.filter_reasons,
                            "scores": c.scores
                        }
                        for c in d.candidates
                    ]
                }
                for d in section.supervisor_decisions
            ],
            "final_result": {
                "score": section.final_score,
                "grade": section.final_grade,
                "included": section.included_in_report,
                "sources_count": len(section.sources_used)
            }
        }
    
    def get_full_report(self) -> Dict:
        """전체 세션 리포트"""
        return {
            "session_id": self.session_id,
            "duration": {
                "started": self.session.started_at,
                "ended": self.session.ended_at
            },
            "user_input": self.session.user_input,
            "stats": self.session.stats,
            "sections": {
                key: self.get_section_comparison(key)
                for key in self.session.sections
            },
            "user_activities": [
                {
                    "timestamp": a.timestamp,
                    "stage": a.stage,
                    "action": a.action,
                    "success": a.success,
                    "duration_ms": a.duration_ms
                }
                for a in self.session.user_activities
            ],
            "errors": self.session.errors,
            "log_files": {
                "json": str(self.json_file),
                "log": str(self.log_file)
            }
        }


def load_session_log(session_id: str) -> Optional[Dict]:
    """저장된 세션 로그 로드"""
    json_path = LOG_DIR / f"session_{session_id}.json"
    if not json_path.exists():
        return None
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_session_logs() -> List[Dict]:
    """저장된 세션 로그 목록"""
    logs = []
    for json_file in LOG_DIR.glob("session_*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                logs.append({
                    "session_id": data.get("session_id"),
                    "started_at": data.get("started_at"),
                    "user_input": data.get("user_input", {}),
                    "stats": data.get("stats", {}),
                    "file_path": str(json_file)
                })
        except:
            continue
    return sorted(logs, key=lambda x: x.get("started_at", ""), reverse=True)