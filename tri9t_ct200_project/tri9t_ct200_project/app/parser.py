"""CT-200-focused PDF extraction. Heuristics are explicit and expose uncertainty."""
import hashlib, re
from dataclasses import dataclass, field
from pathlib import Path
import fitz

@dataclass
class ParsedNode:
    heading: str
    level: int
    body_text: str = ""
    children: list = field(default_factory=list)

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def extract_pdf_text(path: str) -> str:
    doc = fitz.open(path)
    pages = []
    for page in doc:
        text = page.get_text("text").strip()
        # OCR fallback is intentionally optional; native text is preferred.
        if not text:
            try:
                import pytesseract
                from PIL import Image
                import io
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                text = pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))))
            except Exception:
                text = ""
        pages.append(text)
    return "\n\n".join(pages)

_NUM_HEADING = re.compile(r"^(\d+(?:\.\d+){0,5})\s+(.{2,150})$")
_ALLCAPS = re.compile(r"^[A-Z][A-Z0-9 /&(),:-]{3,100}$")

def classify_heading(line: str):
    line = " ".join(line.split()).strip()
    if not line:
        return None
    m = _NUM_HEADING.match(line)
    if m:
        return len(m.group(1).split(".")), line
    if _ALLCAPS.match(line) and len(line.split()) <= 12:
        return 1, line
    return None

def parse_text(text: str) -> list[ParsedNode]:
    """Builds a tree using numbered headings plus conservative uppercase headings.

    Duplicate headings remain separate nodes. Ambiguous/unclassified lines stay in body text.
    This deliberately avoids guessing that every short line is a heading.
    """
    roots: list[ParsedNode] = []
    stack: list[ParsedNode] = []
    current: ParsedNode | None = None
    body_buffer: list[str] = []

    def flush_body():
        nonlocal body_buffer, current
        chunk = "\n".join(body_buffer).strip()
        if chunk and current:
            current.body_text = (current.body_text + "\n" + chunk).strip()
        elif chunk and not current:
            roots.append(ParsedNode("Document introduction", 1, chunk))
        body_buffer = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if body_buffer and body_buffer[-1] != "":
                body_buffer.append("")
            continue
        heading = classify_heading(line)
        if heading:
            flush_body()
            level, title = heading
            node = ParsedNode(title, level)
            while stack and stack[-1].level >= level:
                stack.pop()
            if stack:
                stack[-1].children.append(node)
            else:
                roots.append(node)
            stack.append(node)
            current = node
        else:
            body_buffer.append(line)
    flush_body()
    return roots

def flatten(nodes, parent_path=""):
    rows = []
    for n in nodes:
        path = parent_path + "/" + n.heading
        rows.append({"heading": n.heading, "level": n.level, "body_text": n.body_text,
                     "path": path, "logical_key": sha256(path.lower())[:32],
                     "content_hash": sha256(n.heading + "\n" + n.body_text),
                     "children": flatten(n.children, path)})
    return rows
