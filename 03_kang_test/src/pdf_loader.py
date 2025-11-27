# 폴더 안의 모든 PDF를 읽어서, 페이지 단위 혹은 논리 단위 텍스트 리스트로 반환

from pathlib import Path
import fitz  # PyMuPDF


def load_pdfs(pdf_dir: str):
    pdf_dir = Path(pdf_dir)
    docs = []

    for pdf_path in pdf_dir.glob("*.pdf"):
        doc = fitz.open(pdf_path)
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            text = page.get_text("text").strip()
            if not text:
                continue
            docs.append(
                {
                    "id": f"{pdf_path.stem}_p{page_idx + 1}",
                    "source": str(pdf_path),
                    "page": page_idx + 1,
                    "text": text,
                }
            )
    return docs
