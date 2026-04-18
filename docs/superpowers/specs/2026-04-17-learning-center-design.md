# Learning Center Design Spec

**Date**: 2026-04-17
**Status**: Approved
**Architecture**: Overlay + Standalone Service Layer + LiteratureAgent (Plan B)

---

## Overview

Learning Center is a knowledge management system for bioinformatics literature. Users upload PDF papers, the system extracts structured knowledge (methods, figures, tables) using Vision LLM, stores it as searchable chunks with pgvector embeddings, and enables one-click forging of analysis code via Chat collaboration.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| UI form | Overlay modal panel | Consistent with SkillCenter/DataCenter |
| PDF parsing | Vision LLM first | Better figure understanding |
| Forge flow | Send to Chat collaboration | More flexible than auto-generating drafts |
| RAG integration | MVP included | High value, moderate complexity |
| Input methods | PDF upload + DOI import (MVP) | Both supported from the start |
| Knowledge granularity | Paragraph-level chunks | Balanced precision and simplicity |
| Architecture | Service layer + LiteratureAgent | Independent Agent node for code generation with hardcoded conventions |

---

## Data Model

### Literature (文献主表)

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID FK | Owner |
| title | str | Paper title |
| authors | str | Comma-separated author list |
| year | int | Publication year |
| journal | str | Journal/conference name |
| doi | str | DOI identifier |
| abstract | str | Abstract text |
| keywords | str | Comma-separated keywords |
| file_path | str | Original PDF storage path |
| file_hash | str | SHA256 hash for dedup |
| thumbnail_url | str | Cover thumbnail URL |
| page_count | int | Number of pages |
| status | enum | `uploading/parsing/ready/error` |
| parse_error | str | Parse failure reason |
| created_at | datetime | Creation time |
| updated_at | datetime | Update time |

### LiteratureChunk (段落级知识块)

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| literature_id | UUID FK | Parent literature |
| chunk_index | int | Chunk sequence number |
| chunk_type | enum | `text/figure/table/equation` |
| content | str | Chunk text content |
| page_number | int | Page number |
| section_title | str | Section heading |
| figure_caption | str | Figure/table caption (only for figure/table types) |
| embedding | vector(1536) | pgvector embedding |
| metadata_ | JSON | Extended metadata |

### LiteratureNote (用户笔记/标注)

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| literature_id | UUID FK | Parent literature |
| user_id | UUID FK | Owner |
| chunk_id | UUID FK | Associated chunk (optional) |
| content | str | Note content |
| color | str | Highlight color |
| created_at | datetime | Creation time |

### LiteratureTag (标签)

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID FK | Owner |
| name | str | Tag name |
| color | str | Tag color |

### literature_tag_assoc (文献-标签关联表)

M:N relationship between Literature and LiteratureTag.

### Relationships

- User → Literature (1:N)
- Literature → LiteratureChunk (1:N)
- Literature → LiteratureNote (1:N)
- Literature ↔ LiteratureTag (M:N)

---

## Backend Architecture

### Route Group `/api/learning`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/literatures` | GET | List user literatures (paginated, tag filtered) |
| `/literatures` | POST | Upload PDF (multipart, batch supported) |
| `/literatures/{id}` | GET | Get literature detail |
| `/literatures/{id}` | DELETE | Delete literature |
| `/literatures/{id}/status` | GET | Poll parse status |
| `/literatures/{id}/chunks` | GET | Get all chunks for a literature |
| `/literatures/{id}/notes` | GET/POST | Note CRUD |
| `/search` | POST | Hybrid search (keyword + pgvector semantic) |
| `/tags` | GET/POST | Tag management |
| `/ingest/doi` | POST | DOI import (via CrossRef/Unpaywall) |
| `/forge-context` | POST | Generate forge context (structured Prompt for Chat) |

### Service Layer

**`learning_service.py`** — Core business logic
- Literature CRUD, tag management, note management
- Search logic: keyword search (PostgreSQL `tsvector`) + semantic search (pgvector cosine distance)
- Dedup check (file_hash)

**`pdf_processor.py`** — Existing, needs extension
- PyMuPDF text extraction + figure cropping
- Smart chunking: split by section/paragraph/figure boundaries
- Caption alignment: associate "As shown in Fig 1A" with corresponding figure

**`learning_ingestion_service.py`** — New
- Coordinate PDF processing pipeline
- Call Vision LLM for figure understanding (structured JSON extraction)
- Call Embedding API to generate vectors
- Persist to DB (LiteratureChunk + embedding)

### Celery Tasks

**`learning_tasks.py`** — Existing, needs rewrite
- `process_literature_task(literature_id)` — Main parse task
  1. Update status to `parsing`
  2. Call `pdf_processor` to extract text and figures
  3. Call Vision LLM for figure understanding
  4. Smart chunking + generate Embeddings
  5. Persist LiteratureChunk records
  6. Update status to `ready`
  7. On error: update status to `error` + record error message
- `process_doi_task(doi)` — DOI parse task
  1. Call CrossRef API for metadata
  2. Try Unpaywall for open access PDF
  3. If PDF obtained, trigger `process_literature_task`

### RAG Tool

**`literature_tools.py`** — New
- `search_learning_center(query, top_k=5)` — LangGraph tool
  - Search learning center knowledge base
  - Return matching chunks + source literature info
  - Register in main Agent's tool list

---

## Frontend Architecture

### Overlay Structure

**`LearningCenter.tsx`** — Main Overlay with Tab switching

```
LearningCenter (Overlay)
├── Tab: Library (文献库)
│   ├── Search bar + tag filter
│   ├── Masonry card grid (thumbnail + title + tags + status)
│   ├── Upload area (drag + click)
│   └── Batch action toolbar
├── Tab: Knowledge (知识库)
│   ├── Full-text search
│   ├── Chunk list (with source literature, page, section)
│   └── Figure preview
├── Tab: Notes (笔记)
│   ├── Note timeline
│   └── Group by literature/tag
└── Tab: Settings (设置)
    ├── Tag management
    └── Import/Export
```

### Detail Drawer

Clicking a literature card opens a right-side detail drawer:

```
LiteratureDetailDrawer
├── Header: title, authors, journal, year, DOI link
├── Abstract
├── Tab: Chunks
│   ├── Paragraph list (collapsible sections)
│   ├── Figure gallery (click to enlarge)
│   └── Table preview
├── Tab: Notes
│   ├── Highlight annotations
│   └── Note list
└── Action bar
    ├── One-click forge → send to Chat
    ├── Edit tags
    └── Delete
```

### State Management

**`useLearningStore.ts`** — New Zustand Store

```typescript
interface LearningState {
  // Literature list
  literatures: Literature[]
  totalCount: number
  currentPage: number
  filters: { tags: string[]; search: string; status?: string }

  // Selected literature
  selectedLiterature: Literature | null
  chunks: LiteratureChunk[]
  notes: LiteratureNote[]

  // Knowledge search
  searchResults: SearchResult[]
  searchQuery: string

  // Upload state
  uploadingFiles: File[]
  uploadProgress: Map<string, number>

  // Actions
  fetchLiteratures: (page?: number) => Promise<void>
  uploadPDF: (files: File[]) => Promise<void>
  deleteLiterature: (id: string) => Promise<void>
  selectLiterature: (id: string) => Promise<void>
  searchKnowledge: (query: string) => Promise<void>
  forgeToChat: (literatureId: string, chunkIds?: string[]) => void
}
```

### One-Click Forge Flow

1. User clicks "One-click forge" in detail drawer
2. Frontend calls `POST /api/learning/forge-context` with `literature_id` and optional `chunk_ids`
3. Backend returns structured Prompt (containing method descriptions, parameters, code snippets)
4. Frontend injects Prompt into Chat input and triggers send
5. Main Agent collaborates in Chat to generate code

### RAG Integration

When users ask questions in Chat, the main Agent automatically calls `search_learning_center` tool to retrieve relevant knowledge chunks as context. No frontend changes needed.

---

## PDF Processing Pipeline

### Processing Flow

```
PDF File
  │
  ▼
PyMuPDF Extraction
  ├── Text (by page, by paragraph)
  ├── Figure regions (coordinates + crop to PNG)
  └── Tables (text table recognition)
  │
  ▼
Smart Chunking
  ├── Split by section titles (recognize "1. Introduction", "Methods", etc.)
  ├── Figures as independent chunks (caption + figure image)
  ├── Paragraph merging (merge short paragraphs, split long ones, target 200-500 chars)
  └── Metadata annotation (page number, section, type)
  │
  ▼
Vision LLM Processing (only for figure/table chunks)
  ├── Input: figure image + caption text
  ├── Extract: analysis type, tool chain, parameters, methodology description
  └── Output: structured JSON (ExtractedKnowledge schema)
  │
  ▼
Embedding Generation
  ├── Text chunks: direct embedding
  ├── Figure chunks: concatenate (caption + LLM-extracted method description) → embedding
  └── Use text-embedding-3-large (1536 dimensions)
  │
  ▼
Persistence
  ├── LiteratureChunk records
  ├── pgvector index
  └── Update Literature status to ready
```

### Vision LLM Prompt

```
You are a rigorous computational biology expert. Analyze the provided literature figure and its caption to extract bioinformatics analysis methods.

Absolute rules:
1. Maintain scientific objectivity, no exaggeration or subjective inference
2. Focus on: dimensionality reduction, clustering, differential analysis, trajectory inference, and other statistical algorithms
3. Accurately identify open-source software (Seurat, Scanpy, DESeq2, etc.) and parameter settings
4. Must output JSON with structure: {methodology, tool_stack, parameters, analysis_type}
5. Fill "Not specified" for missing information, never fabricate
```

### Error Handling

| Scenario | Strategy |
|----------|----------|
| PDF upload failure | Frontend Toast notification, non-blocking |
| PDF parse exception | Celery retry 3x, final failure → Literature.status=error, show error reason |
| Vision LLM timeout | Degrade to text LLM, extract from captions |
| Embedding service unavailable | Mark as partial_ready, keyword search only |
| Duplicate file upload | file_hash dedup, return existing literature ID |
| DOI parse failure | Prompt user to upload PDF manually |
| pgvector index error | Degrade to keyword-only search |

---

## LiteratureAgent & RAG Integration

### LiteratureAgent Design

**Role**: Independent LangGraph node for literature-related requests and code generation.

**System Prompt** (hardcoded code conventions):
```
You are Autonome's literature analysis Agent. Based on the learning center knowledge base, help users understand literature methods or generate executable analysis code.

Code generation absolute rules:
1. All code must include detailed comments explaining "why" not just "what"
2. Must use argparse (Python) or commandArgs (R) for parameter systems with sensible defaults
3. Tabular data must output TSV format, never CSV
4. Plots must output both PDF and PNG, using publication-grade color palettes
5. Each figure must include the underlying data file (TSV)

Maintain scientific objectivity. Output structured analysis logic and high-quality code directly.
```

**Tool Set**:
- `search_learning_center(query, top_k)` — Search knowledge base
- `create_skill_draft(code, language, tool_stack)` — Create skill draft

**Intent Routing Rules** (added to main Router):
Route to LiteratureAgent when user message contains:
- 文献, 论文, paper, article
- 复现, reproduce
- 图表, figure
- 学习中心, learning center
- 算道, pipeline (in bioinformatics context)

### RAG Tool Integration

`search_learning_center` tool registered in main Agent's tool list:

```python
@tool
def search_learning_center(query: str, top_k: int = 5) -> list[dict]:
    """Call when user asks about bioinformatics analysis methods or references literature.
    Returns matching knowledge chunks from the learning center with source literature info."""
    # 1. Generate query embedding
    # 2. pgvector cosine distance search top_k results
    # 3. Return [{content, source_title, source_doi, page_number, chunk_type, ...}]
```

### Forge Context Generation

`POST /api/learning/forge-context` logic:

1. Get all chunks for specified literature
2. Filter figure/table chunks (or use specified chunk_ids)
3. Assemble structured Prompt:
   ```
   Based on the following literature knowledge, please generate executable analysis code:

   Literature: {title} ({journal}, {year})
   DOI: {doi}

   Analysis methods:
   {methodology from each chunk}

   Tool chain:
   {tool_stack from each chunk}

   Key parameters:
   {parameters from each chunk}

   Please follow Autonome code conventions to generate a complete Python/R script.
   ```
4. Return Prompt text

---

## Expert Correction Loop

- Chunk content in detail drawer is editable
- User modifications saved via `PUT /api/learning/chunks/{id}`
- Modifications trigger embedding regeneration
- Correction records optionally stored (for future SFT fine-tuning)

---

## Testing Strategy

### Backend Tests

- `test_learning_models.py` — Model CRUD tests
- `test_learning_routes.py` — API endpoint tests (upload, search, forge context)
- `test_pdf_processor.py` — PDF parsing unit tests (using sample PDFs)
- `test_learning_search.py` — Hybrid search tests (keyword + semantic)
- `test_literature_agent.py` — Agent behavior tests (code convention compliance)

### Frontend Tests

- LearningCenter component render tests
- Upload interaction tests (drag, click)
- Search interaction tests
- Forge context injection to Chat tests

---

## Phase Plan

### Phase 1: MVP (Current)
- PDF upload + Vision LLM parsing
- DOI/PMID import (via CrossRef/Unpaywall)
- Literature CRUD + tag management
- Hybrid search (keyword + pgvector)
- One-click forge (Chat collaboration)
- RAG tool for main Agent
- LiteratureAgent as independent LangGraph node
- Overlay UI with Library + Knowledge tabs

### Phase 2: Enhancement
- Note/highlight system
- Batch operations
- Expert correction loop with versioning

### Phase 3: Advanced
- Knowledge graph (entity-relation extraction)
- Cross-literature synthesis
- SFT fine-tuning from correction data
- Collaborative sharing