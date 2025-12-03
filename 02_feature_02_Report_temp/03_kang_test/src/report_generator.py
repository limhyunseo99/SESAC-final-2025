# report_generator.py (프로덕션 안정화 버전)
import json
import re
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from supervisor import Supervisor

class SafePromptBuilder:
    @staticmethod
    def escape_json(d):
        try:
            return "```json\n" + json.dumps(d, ensure_ascii=False, indent=2) + "\n```"
        except:
            return "[JSON ERROR]"

    @staticmethod
    def safe_invoke(llm, prompt):
        try:
            res = llm.invoke(prompt)
            return res.content if isinstance(res, AIMessage) else str(res)
        except Exception as e:
            raise RuntimeError(f"LLM CALL FAILED: {e}")


class FootnoteManager:
    def __init__(self):
        self.footnotes = {}
        self.counter = 0

    def add_url(self, u):
        if u not in self.footnotes:
            self.counter += 1
            self.footnotes[u] = self.counter
        return self.footnotes[u]

    def extract_and_number_urls(self, text):
        pattern = r"https?://[^\s\)\"']+"

        def rep(m):
            idx = self.add_url(m.group(0))
            return f"[{idx}]"

        return re.sub(pattern, rep, text)

    def generate_footnotes(self):
        if not self.footnotes:
            return ""
        lines = ["\n## Reference Links\n"]
        for url, idx in sorted(self.footnotes.items(), key=lambda x: x[1]):
            lines.append(f"[{idx}] {url}")
        return "\n".join(lines)


class ReportGenerator:
    def __init__(self):
        self.llm_draft = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.llm_final = ChatOpenAI(model="gpt-5", temperature=0)
        self.prompt_builder = SafePromptBuilder()
        self.foot = FootnoteManager()
        self.supervisor = Supervisor(model="gpt-4o-mini")

    def generate_draft_with_rag(self, country_info, sections, table_hint, req):
        country_data = self.prompt_builder.escape_json(country_info)
        req_json = self.prompt_builder.escape_json(req)
        hint_json = self.prompt_builder.escape_json(table_hint)
        section_summary = self._summarize_sections(sections)

        prompt = f"""
You are an expert in *Export Market Strategy Reports*.

Use the following structured information:

[COUNTRY INFO]
{country_data}

[USER REQUEST]
{req_json}

[RAG RESULTS]
{section_summary}

[TABLE/IMAGE REFERENCES]
{hint_json}

WRITING RULES:
1. All numeric data must be specific (e.g., “123,800,000 people”, “as of 2024”).
2. All statistics from RAG must include citations: 
   Format → [KATI 2024 Japan p.12], [KOTRA 2023].
3. Add table/graph references:
   - [📊 Table: filename p.X]
   - [📈 Chart: filename p.X]
4. Use comparative analysis (Korea vs competitors, YoY changes).
5. Provide concrete evidence. Avoid vague language.

PROHIBITED:
- vague terms (“approximately”, “roughly”)
- numbers without sources
- generic statements without data

REPORT STRUCTURE:
# {req.get("country_name")} Export Market Strategy Report

## 1. Executive Summary  
(Min 300 characters, at least 3 numerical metrics)

## 2. Country & Market Overview
### 2.1 Basic Country Information
### 2.2 Food Market Size & Growth

## 3. HS {req.get("hs_code")} Product Fit Assessment

## 4. Market Size & Forecast

## 5. Distribution Channels & Competition

## 6. Regulatory & Certification Requirements

## 7. Consumer Trends

## 8. Strategic Recommendations  
(General strategy only — *no short-term strategy section*)

Write the full draft now.
"""

        return self.prompt_builder.safe_invoke(self.llm_draft, prompt)

    def integrate_deep_research(self, draft, deep_result):
        deep_json = self.prompt_builder.escape_json(deep_result)

        prompt = f"""
You will now integrate latest Deep Research results into the draft report.

[DRAFT]
{draft}

[DEEP RESEARCH RESULTS]
{deep_json}

UPDATE RULES:
1. Add a regulatory update box:
⚠️ Major Regulatory Updates (2024–2025)

[date] [description]

Source: [URL]

markdown
코드 복사

2. Price trends must include numerical direction (e.g., “+12% YoY”).

3. Risk level classification:
🔴 High Risk: ...
🟡 Medium Risk: ...
🟢 Low Risk: ...

python
코드 복사

4. Add a new section:
## 9. Latest Insights (Deep Research)
### 9.1 Regulation Updates
### 9.2 Price Trend Analysis
### 9.3 Market Risk Evaluation

5. Keep URLs as-is (footnote conversion later).

Update the entire report accordingly.
"""

        updated = self.prompt_builder.safe_invoke(self.llm_draft, prompt)
        return self.foot.extract_and_number_urls(updated)

    def assemble_final_report(self, draft_text, req):
        country = req.get("country_name")
        hs = req.get("hs_code")

        prompt = f"""
You will refine and finalize the full export strategy report.

[DRAFT REPORT]
{draft_text}

FINALIZATION RULES:

1. Executive Summary MUST include:
   - Market size with year + currency
   - Korea’s ranking or market share
   - Three key opportunities (with data)
   - Two major risks
   - One-sentence strategic recommendation

2. Minimum section length:
   - Major sections: 500+ characters
   - Subsections: 300+ characters

3. Strategic recommendations should be actionable (no 3-month section required).

4. Add reference section:
10. References
KATI, "{country} Market Report 2024", 2024

KOTRA, "{country} Market Trends 2023", 2023

php
코드 복사

Produce the final polished report.
"""

        final_report = self.prompt_builder.safe_invoke(self.llm_final, prompt)

        exec_summary = self._extract_exec_summary(final_report)
        validation = self.supervisor.validate_executive_summary(exec_summary)

        notes = self.foot.generate_footnotes()
        if notes:
            final_report += "\n\n" + notes

        return final_report, validation

    def _summarize_sections(self, sections):
        if not sections:
            return "No RAG results found."

        out = []
        for name, docs in sections.items():
            out.append(f"\n[{name}]")
            if not docs:
                out.append("  (No content)")
                continue

            for i, d in enumerate(docs[:3], 1):
                try:
                    if isinstance(d, dict):
                        content = d.get("content", "")[:200]
                        source = d.get("source", "Unknown")
                        year = d.get("year", "N/A")
                        file = d.get("file_name", "N/A")
                    else:
                        content = getattr(d, "page_content", "")[:200]
                        meta = getattr(d, "metadata", {})
                        source = meta.get("source", "Unknown")
                        year = meta.get("year", "N/A")
                        file = meta.get("file_name", "N/A")

                    out.append(f"{i}. [{source} {year}] {file}\n   {content}...")
                except Exception as e:
                    out.append(f"{i}. ERROR: {e}")

        return "\n".join(out)

    def _extract_exec_summary(self, text):
        pattern = r"##\s*(?:1\.)?\s*Executive Summary\s*\n(.*?)(?=\n##|\Z)"
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else text[:500]