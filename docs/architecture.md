# Evidentia Architecture

## System Overview

Evidentia is structured as a modular, tool-orchestrated research operating system built around a strict **Plan → Call → Validate → Decide** loop.

```
Client Layer (Web UI / CLI)
        │
        ▼
   API Gateway
   (Auth, Rate Limiting, Validation)
        │
        ▼
   Orchestrator (Control Plane)
   ┌─────────────────────────────┐
   │  Planner (LLM structured)  │
   │         ↓                   │
   │  Tool Router (parallel)     │
   │         ↓                   │
   │  Validator                  │
   │         ↓                   │
   │  Decision Engine            │
   │         ↓                   │
   │  Claim Graph Builder        │
   └─────────────────────────────┘
        │
        ▼
   Tool Gateway (MCP-style)
   ┌─────────────────────────────┐
   │  Web Search  │  ArXiv       │
   │  Sem.Scholar │  DOI/Crossref│
   │  PDF Parser  │  Python Sandbox│
   │  SQL         │  Custom Tools│
   └─────────────────────────────┘
        │
        ▼
   Evidence & Storage Layer
   ┌─────────────────────────────┐
   │  PostgreSQL + pgvector      │
   │  Redis (cache/queue)        │
   │  Object Store (S3)          │
   └─────────────────────────────┘
```

## Core Execution Flow

```
1. User submits query
2. Planner generates structured plan (LLM → JSON)
3. Tool Router executes steps (parallel if no dependencies)
4. Validator checks each output (schema + citation + evidence)
5. Decision Engine evaluates: continue / retry / replan / stop
6. Evidence stored & indexed in hybrid search
7. Claim graph constructed with citations + confidence scores
8. Final structured answer returned
9. Run logged for reproducibility
```

## Key Design Decisions

### Tool Contract System
Every tool declares strict input/output JSON schemas, timeout policies, auth requirements, and retry config. Tools are pluggable — adding a new tool requires implementing `BaseTool` and registering it.

### BYO-API Architecture
Two execution modes:
- **Hosted**: API keys encrypted via vault, executed server-side
- **User-Owned**: Docker runtime in user's environment, receives signed requests

### Claim-First Output
Instead of raw text, outputs are structured as atomic claims with:
- Citations (DOI, URL, title, authors)
- Evidence spans (exact text offsets)
- Confidence scores
- Conflict indicators

### Hybrid Retrieval
Combines BM25 keyword search with vector similarity (pgvector), followed by cross-encoder reranking for optimal relevance.
