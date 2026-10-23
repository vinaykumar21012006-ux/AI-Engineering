import json, os, re
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from .db import Base, engine, get_db
from .models import DocumentVersion, Node, Selection, SelectionItem, Generation
from .schemas import SelectionCreate, GenerateRequest
from .parser import extract_pdf_text, parse_text, flatten, sha256
from .llm import generate_cases

Base.metadata.create_all(bind=engine)
app = FastAPI(title="CT-200 Traceable QA API", version="1.0.0")

def now(): return datetime.now(timezone.utc).isoformat()

def latest_version(db, key="ct200"):
    return db.scalar(select(DocumentVersion).where(DocumentVersion.document_key==key).order_by(desc(DocumentVersion.version_number)))

def serialize_node(n, db, include_children=True):
    out = {"id":n.id,"logical_key":n.logical_key,"version_id":n.version_id,"parent_id":n.parent_id,
           "heading":n.heading,"level":n.level,"body_text":n.body_text,"content_hash":n.content_hash,
           "changed_from_previous":n.changed_from_previous}
    if include_children:
        out["children"] = [serialize_node(c, db) for c in db.scalars(select(Node).where(Node.parent_id==n.id, Node.version_id==n.version_id)).all()]
    return out

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/documents/{document_key}/ingest")
async def ingest(document_key: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Upload a PDF file")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Uploaded PDF is empty")
    temp = Path("data") / ("upload_" + re.sub(r"[^a-zA-Z0-9_.-]", "_", file.filename))
    temp.parent.mkdir(exist_ok=True)
    temp.write_bytes(raw)
    try:
        text = extract_pdf_text(str(temp))
        if not text.strip(): raise HTTPException(422, "No extractable text; install/configure Tesseract OCR for scanned PDFs.")
        tree = parse_text(text)
        if not tree: raise HTTPException(422, "No document structure detected.")
        previous = latest_version(db, document_key)
        version_num = previous.version_number + 1 if previous else 1
        version = DocumentVersion(document_key=document_key, version_number=version_num, source_name=file.filename, created_at=now())
        db.add(version); db.flush()
        warnings = []
        count = 0
        def save(nodes, parent_id=None, parent_path=""):
            nonlocal count
            for n in nodes:
                path = parent_path + "/" + n.heading
                logical_key = sha256(path.lower())[:32]
                digest = sha256(n.heading + "\n" + n.body_text)
                old = db.scalar(select(Node).where(Node.logical_key==logical_key, Node.version_id==previous.id)) if previous else None
                changed = bool(old and old.content_hash != digest)
                node = Node(logical_key=logical_key, version_id=version.id, parent_id=parent_id,
                    heading=n.heading, level=n.level, body_text=n.body_text, content_hash=digest,
                    changed_from_previous=changed if old else bool(previous))
                db.add(node); db.flush(); count += 1
                if old and not changed: node.changed_from_previous = False
                save(n.children, node.id, path)
        save(tree)
        db.commit()
        return {"document_key":document_key,"version":version_num,"version_id":version.id,"node_count":count,
                "warnings":warnings + ["OCR fallback requires local Tesseract + pytesseract/Pillow for scanned pages.",
                 "Heading recognition is heuristic; manually inspect the tree and duplicate-heading cases."]}
    except Exception:
        db.rollback()
        raise
    finally:
        try: temp.unlink(missing_ok=True)
        except Exception: pass

@app.get("/documents/{document_key}/sections")
def sections(document_key: str, version: int | None = None, db: Session = Depends(get_db)):
    v = db.scalar(select(DocumentVersion).where(DocumentVersion.document_key==document_key,
        DocumentVersion.version_number==version)) if version else latest_version(db, document_key)
    if not v: raise HTTPException(404, "Document/version not found")
    nodes = db.scalars(select(Node).where(Node.version_id==v.id, Node.parent_id.is_(None))).all()
    return {"document_key":document_key,"version":v.version_number,"sections":[serialize_node(n,db) for n in nodes]}

@app.get("/nodes/{node_id}")
def get_node(node_id: int, db: Session = Depends(get_db)):
    n = db.get(Node,node_id)
    if not n: raise HTTPException(404,"Node not found")
    return serialize_node(n,db)

@app.get("/nodes")
def search_nodes(q: str = Query(..., min_length=1), document_key: str = "ct200",
                 version: int | None = None, db: Session = Depends(get_db)):
    v = db.scalar(select(DocumentVersion).where(DocumentVersion.document_key==document_key,
        DocumentVersion.version_number==version)) if version else latest_version(db,document_key)
    if not v: raise HTTPException(404,"Document/version not found")
    needle = "%" + q.lower() + "%"
    rows = db.scalars(select(Node).where(Node.version_id==v.id,
        (Node.heading.ilike(needle)) | (Node.body_text.ilike(needle)))).all()
    return {"version":v.version_number,"results":[serialize_node(n,db,False) for n in rows]}

@app.get("/nodes/{node_id}/diff")
def node_diff(node_id: int, db: Session = Depends(get_db)):
    n = db.get(Node,node_id)
    if not n: raise HTTPException(404,"Node not found")
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_key==
        db.get(DocumentVersion,n.version_id).document_key).order_by(DocumentVersion.version_number)).all()
    previous = next((v for v in versions if v.version_number == db.get(DocumentVersion,n.version_id).version_number-1),None)
    old = db.scalar(select(Node).where(Node.logical_key==n.logical_key, Node.version_id==previous.id)) if previous else None
    return {"node_id":n.id,"logical_key":n.logical_key,"changed": bool(old and old.content_hash!=n.content_hash) if old else n.changed_from_previous,
            "current_hash":n.content_hash,"previous_hash":old.content_hash if old else None,
            "summary": "Content hash differs; inspect body text for semantic impact." if old and old.content_hash!=n.content_hash else ("No prior logical node found." if not old else "Content unchanged.")}

@app.post("/selections")
def create_selection(payload: SelectionCreate, db: Session = Depends(get_db)):
    nodes = [db.get(Node, nid) for nid in payload.node_ids]
    if any(n is None for n in nodes): raise HTTPException(404,"One or more node IDs do not exist")
    versions = {n.version_id for n in nodes}
    if len(versions) != 1: raise HTTPException(400,"All selected nodes must belong to the same document version")
    sel = Selection(name=payload.name, created_at=now()); db.add(sel); db.flush()
    for n in nodes:
        db.add(SelectionItem(selection_id=sel.id,node_id=n.id,version_id=n.version_id,content_hash=n.content_hash,
            heading_snapshot=n.heading,text_snapshot=(n.heading + "\n" + n.body_text)))
    db.commit()
    return {"selection_id":sel.id,"name":sel.name,"version_id":next(iter(versions)),"node_ids":payload.node_ids}

@app.get("/selections/{selection_id}")
def get_selection(selection_id: int, db: Session = Depends(get_db)):
    s = db.get(Selection,selection_id)
    if not s: raise HTTPException(404,"Selection not found")
    return {"id":s.id,"name":s.name,"items":[{"node_id":i.node_id,"version_id":i.version_id,"heading":i.heading_snapshot,
        "content_hash":i.content_hash,"text":i.text_snapshot} for i in s.items]}

@app.post("/generate")
async def generate(payload: GenerateRequest, db: Session = Depends(get_db)):
    s = db.get(Selection,payload.selection_id)
    if not s: raise HTTPException(404,"Selection not found")
    if not payload.regenerate:
        existing = db.scalar(select(Generation).where(Generation.selection_id==s.id).order_by(desc(Generation.id)))
        if existing: return {"generation_id":existing.id,"selection_id":s.id,"deduplicated":True,"payload":json.loads(existing.payload_json)}
    source = "\n\n".join(i.text_snapshot for i in s.items)
    result, provider = await generate_cases(source)
    for case in result["test_cases"]:
        case["source_node_ids"] = [i.node_id for i in s.items]
    gen = Generation(selection_id=s.id,created_at=now(),provider=provider,payload_json=json.dumps(result),
        source_snapshot_json=json.dumps([{"node_id":i.node_id,"version_id":i.version_id,"hash":i.content_hash} for i in s.items]))
    db.add(gen); db.commit(); db.refresh(gen)
    return {"generation_id":gen.id,"selection_id":s.id,"deduplicated":False,"provider":provider,"payload":result}

def generation_staleness(gen, db):
    source = json.loads(gen.source_snapshot_json)
    stale = []
    for item in source:
        old = db.get(Node,item["node_id"])
        if not old: stale.append({"node_id":item["node_id"],"reason":"source node missing"}); continue
        docv = db.get(DocumentVersion,old.version_id)
        latest = latest_version(db,docv.document_key)
        current = db.scalar(select(Node).where(Node.logical_key==old.logical_key,Node.version_id==latest.id)) if latest else None
        if not current or current.content_hash != item["hash"]:
            stale.append({"node_id":old.id,"current_node_id":current.id if current else None,
                "reason":"node missing in latest version" if not current else "content hash changed"})
    return {"stale":bool(stale),"stale_sources":stale}

@app.get("/generations/{generation_id}")
def get_generation(generation_id: int, db: Session = Depends(get_db)):
    gen = db.get(Generation,generation_id)
    if not gen: raise HTTPException(404,"Generation not found")
    return {"generation_id":gen.id,"selection_id":gen.selection_id,"created_at":gen.created_at,
        "provider":gen.provider,"payload":json.loads(gen.payload_json),**generation_staleness(gen,db)}

@app.get("/generations")
def list_generations(selection_id: int | None = None, node_id: int | None = None, db: Session = Depends(get_db)):
    query = select(Generation)
    if selection_id is not None: query = query.where(Generation.selection_id==selection_id)
    rows = db.scalars(query.order_by(desc(Generation.id))).all()
    if node_id is not None:
        rows = [g for g in rows if any(x["node_id"]==node_id for x in json.loads(g.source_snapshot_json))]
    return [{"generation_id":g.id,"selection_id":g.selection_id,"created_at":g.created_at,
             **generation_staleness(g,db)} for g in rows]
