import time

from app import db
from app.docs.extract import extract
from app.docs.reader import read_document


def process_document(data: bytes, filename: str, mode: str = "ladder", allow_cloud=None) -> dict:
    t0 = time.perf_counter()
    doc = read_document(data, filename)
    return finish(doc.text, doc.kind, doc.method, filename, mode, allow_cloud, doc.meta.get("ocr_conf"), t0)


def process_text(text: str, filename: str, mode: str = "ladder", allow_cloud=None) -> dict:
    """n8n-in 'Extract From File' node-u PDF-dən mətni artıq çıxarıb: yalnız ekstraksiya."""
    return finish(text, "pdf-text", "given", filename, mode, allow_cloud, None, time.perf_counter())


def finish(text, kind, method, filename, mode, allow_cloud, ocr_conf, t0) -> dict:
    res = extract(text, mode=mode, allow_cloud=allow_cloud, ocr_conf=ocr_conf)
    seconds = round(time.perf_counter() - t0, 2)
    doc_id = db.save_document(filename, kind, method, res.extractor, res.status, res.data, res.issues, len(text), seconds)
    return {"id": doc_id, "filename": filename, "kind": kind, "method": method, "extractor": res.extractor, "status": res.status,
            "data": res.data, "issues": res.issues, "notes": res.notes, "calls": res.calls, "tried": res.tried, "ocr_conf": ocr_conf,
            "text_chars": len(text), "seconds": seconds, "text_preview": text[:600]}
