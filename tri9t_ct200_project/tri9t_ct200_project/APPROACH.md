# Approach Document — CT-200 Traceable QA API

## 1. Parsing approach
The pipeline uses PyMuPDF to extract native PDF text page by page. If a page has no extractable text, it attempts an optional Tesseract OCR fallback; the external OCR dependencies must be installed separately. This hybrid is practical for a technical manual with selectable text and scanned pages. The current baseline is text-first and does not yet reconstruct table cells, image regions, columns, or captions reliably.

## 2. Hierarchy reconstruction
Numbered headings such as `1`, `1.2`, and `1.2.3` establish levels. Conservative all-caps lines are treated as top-level headings. Ordinary lines remain body text, reducing the risk of promoting every short line into a heading. The parser uses a stack to attach each heading to the closest preceding lower-level heading. Duplicate heading labels are not deduplicated by the parser; each parsed occurrence is a separate object.

## 3. Edge cases and tests
The unit tests cover duplicate labels, multi-level numbered hierarchy, ordinary body lines, and logical path keys. Before submission, inspect the actual CT-200 v1/v2 manuals and add regression fixtures for every irregularity explicitly listed in the full assignment package. The supplied brief refers to manuals in a separate data package; they were not present alongside the brief PDF in this workspace.

## 4. Versioning and identity
Every ingestion creates an immutable document-version row and version-specific nodes. A node content hash is SHA-256 of heading plus body text. A logical key is derived from the normalized heading path. This is explainable and deterministic, but has known failure modes: renames/moves alter identity; repeated identical headings beneath the same parent can collide; OCR noise can create false changes. A production-ready matcher should include occurrence indices, sibling context, normalized text similarity, and a review queue for ambiguous matches.

## 5. Selections and traceability
A selection stores exact node/version pairs and copies the heading, text, and content hash into a snapshot. Therefore, later ingestion does not overwrite the text that the selection was based on. Generated output stores the selection ID and a JSON snapshot of source node IDs, version IDs, and hashes.

## 6. LLM prompt and failure policy
The prompt requires 3–5 JSON test cases grounded only in the selected text and forbids invented numeric thresholds. The response is parsed as JSON and validated using Pydantic. One retry is attempted after malformed output; if it still fails, a deterministic fallback is stored. Duplicate generation requests return the most recent result unless `regenerate=true`. The fallback is deliberately generic and must be reviewed before being used for real medical-device QA.

## 7. Staleness and impact
At retrieval time, each source hash is compared with the matching logical node in the latest version. A missing or hash-changed source marks the generation stale and returns the reason. This is conservative: even a punctuation change may flag stale, while semantic impact is not classified. A production system should distinguish cosmetic edits from safety-critical changes (e.g. pressure limits), preserve old versions, and support human review.

## 8. Decision log
1. **Most likely silent error:** a line can be misclassified as a heading or body, yielding a plausible but incorrect tree. Catch it with page-by-page visual comparison, coverage checks, and human review of headings, tables, and duplicate labels.
2. **Where simplicity was chosen:** path-based matching and whole-node hashes were selected for transparency and speed. Renamed/moved sections and harmless wording changes are the first likely sources of false identity changes or stale flags.
3. **Unsupported input:** a scanned PDF page without Tesseract available cannot be parsed. The ingestion fails with a clear message when no text is extracted rather than silently accepting an empty tree.

## 9. Next improvements
Use the actual v1/v2 PDFs to add manual-specific layout rules; detect page headers/footers and table regions; include duplicate occurrence keys; create golden tree fixtures; add API integration tests for v1→v2 changes; compare diffs at sentence/field level; and record a real incremental Git history.
