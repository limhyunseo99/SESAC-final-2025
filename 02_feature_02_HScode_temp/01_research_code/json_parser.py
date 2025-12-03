import re

def parse_llm_hs_result(llm_text: str):
    """
    LLM이 출력한 1순위/2순위/3순위 HS 코드 텍스트를
    [
      {hs_code, title, reason},
      ...
    ]
    형식으로 변환
    """

    final_results = []

    # 순위 블록 단위로 분리 (1순위, 2순위, 3순위 ...)
    blocks = re.split(r"\n\s*\d순위\s*\n?", llm_text)
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # HS 코드 추출
        hs_match = re.search(r"결정세번\s*:\s*([0-9\.\-]+)", block)
        title_match = re.search(r"세번설명\s*:\s*(.+)", block)
        reason_match = re.search(r"결정사유\s*:\s*(.+)", block, re.DOTALL)

        if not hs_match:
            continue

        hs_code = hs_match.group(1).strip()
        title = title_match.group(1).strip() if title_match else ""
        reason = reason_match.group(1).strip() if reason_match else ""

        final_results.append({
            "hs_code": hs_code,
            "title": title,
            "reason": reason
        })

    return final_results