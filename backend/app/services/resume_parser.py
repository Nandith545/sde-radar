import io

from pypdf import PdfReader

from .skills import extract_skills, extract_years_experience


def extract_text(filename: str, content: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    # Treat anything else as plain text (txt, md, pasted content).
    return content.decode("utf-8", errors="ignore")


def parse_resume(filename: str, content: bytes) -> dict:
    text = extract_text(filename, content)
    return {
        "raw_text": text,
        "skills": extract_skills(text),
        "years_experience": extract_years_experience(text),
    }
