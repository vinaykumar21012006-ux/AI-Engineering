# CT-200 Traceable QA API

A starter implementation for the Tri9T AI Engineering Internship Assignment. It provides PDF ingestion, a versioned hierarchical tree, node search/diff, version-pinned selections, QA case generation, and retrieval-time staleness checks.

## Requirements
- Python 3.10+
- For scanned PDFs, install Tesseract OCR and optionally `pytesseract` + `Pillow`.
- CT-200 v1 and v2 manuals must be obtained from the assignment package and placed in `data/`. They were **not included with the assignment brief PDF supplied here**, so this ZIP intentionally does not invent those source documents.

## Run on Windows PowerShell
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```
Open `http://127.0.0.1:8000/docs`.

## Ingest v1 then v2
Use Swagger `/documents/{document_key}/ingest` and upload v1, then upload v2 using the same `document_key` (e.g. `ct200`). Or:
```powershell
curl.exe -X POST "http://127.0.0.1:8000/documents/ct200/ingest" -F "file=@data/ct200_manual_v1.pdf"
curl.exe -X POST "http://127.0.0.1:8000/documents/ct200/ingest" -F "file=@data/ct200_manual_v2.pdf"
```
Then browse `/documents/ct200/sections`, search `/nodes?q=pressure`, compare a node with `/nodes/{node_id}/diff`, and inspect `/generations/{generation_id}` after generating test cases.

## Selection and generation flow
1. Get node IDs from `GET /documents/ct200/sections`.
2. `POST /selections` with `{"name":"Safety review","node_ids":[1,2]}` (IDs must all be from the same version).
3. `POST /generate` with `{"selection_id":1}`.
4. `GET /generations/1` exposes output plus staleness. Repeating generation for the same selection returns the existing result unless `regenerate: true`.

## LLM configuration
Set `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` in the environment. The code uses an OpenAI-compatible `/chat/completions` API. Without a key, it uses a deterministic fallback. Malformed output gets one retry, Pydantic validation, then a fallback rather than persisting invalid JSON. Do not commit real API keys.

## Tests
```powershell
pytest -q
```

## API overview
- `POST /documents/{document_key}/ingest`
- `GET /documents/{document_key}/sections?version=1`
- `GET /nodes/{node_id}`
- `GET /nodes?q=pressure&version=1`
- `GET /nodes/{node_id}/diff`
- `POST /selections`
- `GET /selections/{selection_id}`
- `POST /generate`
- `GET /generations?selection_id=1` or `?node_id=1`
- `GET /generations/{generation_id}`

## Important limitations to discuss honestly
- Heading classification is heuristic and needs validation against the actual CT-200 manual's layout. It currently recognizes numbered headings and conservative all-caps headings.
- Logical matching uses a hash of the heading path. Renames/moves can appear as a new logical node; duplicate headings under the same parent path can collide and require occurrence-aware matching.
- Hash differences flag any text difference, including harmless wording changes; semantic risk scoring is not implemented.
- OCR fallback requires external Tesseract and optional Python packages. Tables, figures, captions, columns, and page headers/footers need manual validation.
- SQLite is appropriate for a demo, not concurrent production workloads.
- No Git history is fabricated. Initialize a Git repo and commit incremental milestones as you develop.
