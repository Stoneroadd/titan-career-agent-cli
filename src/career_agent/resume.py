"""Resume parsing, fact segmentation, redaction, and output validation."""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from pypdf import PdfReader


def read_resume(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt" or suffix == ".md":
        text = path.read_text(encoding="utf-8")
    elif suffix == ".pdf":
        text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    elif suffix == ".docx":
        document = Document(path)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        for table in document.tables:
            text += "\n" + "\n".join(" | ".join(cell.text for cell in row.cells) for row in table.rows)
    else:
        raise ValueError("Formato no soportado. Usa .pdf, .docx, .txt o .md.")
    text = "\n".join(line.strip() for line in text.splitlines()).strip()
    if not text:
        raise ValueError("No se encontró texto. Si el PDF es escaneado, aplica OCR local antes de importar.")
    return text


def facts_from_text(text: str, include_pii: bool = False, full_name: str = "") -> list[dict]:
    lines = [re.sub(r"\s+", " ", line).strip(" •\t-") for line in text.splitlines()]
    facts = []
    for line in lines:
        if len(line) < 3:
            continue
        safe = line
        if not include_pii:
            safe = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL REDACTADO]", safe)
            safe = re.sub(r"(?i)(?:\b(?:tel[eé]fono|phone|celular|m[oó]vil|mobile|whatsapp)\b\s*[:#]?\s*|\+)(?:\d[\d ().-]{6,}\d)", "[TELÉFONO REDACTADO]", safe)
            safe = re.sub(r"https?://\S+", "[URL REDACTADA]", safe)
            if full_name:
                safe = re.sub(re.escape(full_name), "[NOMBRE REDACTADO]", safe, flags=re.IGNORECASE)
        facts.append({"id": f"F{len(facts) + 1:03d}", "text": safe[:1200]})
    return facts


def validate_blocks(blocks: object, valid_ids: set[str]) -> tuple[list[dict], list[str]]:
    accepted: list[dict] = []
    warnings: list[str] = []
    if not isinstance(blocks, list):
        return accepted, ["La salida del modelo no incluyó una lista de bloques CV."]
    for index, block in enumerate(blocks, start=1):
        if not isinstance(block, dict):
            warnings.append(f"Bloque {index} descartado: formato inválido.")
            continue
        text = str(block.get("text", "")).strip()
        refs = block.get("fact_ids", [])
        refs = [str(ref) for ref in refs] if isinstance(refs, list) else []
        valid_refs = [ref for ref in refs if ref in valid_ids]
        if not text or not valid_refs:
            warnings.append(f"Bloque {index} omitido: falta texto o referencia a un hecho fuente válido.")
            continue
        accepted.append({"section": str(block.get("section", "Experiencia")).strip()[:80],
                         "text": text[:2000], "fact_ids": valid_refs})
    return accepted, warnings


def redact_for_prompt(text: str, include_pii: bool, full_name: str = "") -> str:
    if include_pii:
        return text
    safe = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL REDACTADO]", text)
    safe = re.sub(r"(?i)(?:\b(?:tel[eé]fono|phone|celular|m[oó]vil|mobile|whatsapp)\b\s*[:#]?\s*|\+)(?:\d[\d ().-]{6,}\d)", "[TELÉFONO REDACTADO]", safe)
    safe = re.sub(r"https?://\S+", "[URL REDACTADA]", safe)
    if full_name:
        safe = re.sub(re.escape(full_name), "[NOMBRE REDACTADO]", safe, flags=re.IGNORECASE)
    else:
        lines = safe.splitlines()
        for index, line in enumerate(lines):
            candidate = line.strip()
            words = candidate.split()
            if candidate and len(words) in range(2, 6) and len(candidate) < 70 and not any(char.isdigit() for char in candidate):
                lines[index] = "[NOMBRE REDACTADO]"
                break
        safe = "\n".join(lines)
    return safe
