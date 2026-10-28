<div align="center">

# 🛡️ DepositGuard

### Configurable FDR Assurance & Document Integrity Management

**A security-focused prototype for managing Fixed Deposit Receipt (FDR) records, document evidence, workflow compliance, and review prioritization.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/Language-TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

</div>

---

## 📌 Overview

DepositGuard is a prototype designed to support the management and review of Fixed Deposit Receipts (FDRs) within an institution-oriented workflow.

Financial and institutional document reviews involve multiple records, supporting evidence, verification steps, deadlines, and approval stages. Managing these activities without a structured workflow can make it difficult to maintain traceability, identify inconsistencies, and prioritize pending reviews.

DepositGuard brings these activities into a unified workspace. It combines configurable workflows, document version management, cryptographic integrity checks, relationship analysis, review prioritization, and audit logging.

The goal is to make FDR-related review processes **more organized, traceable, configurable, and easier to monitor**.

> **Project status:** Local prototype under active development. This is not an officially integrated AICTE platform or a production banking verification system.

## ✨ Key Features

### 📊 1. Dashboard & Monitoring
- Centralized workspace for FDR-related activities.
- Dashboard metrics and activity information.
- Visibility into available records and review workflows.

### 🏢 2. Institution & FDR Management
- Institution-oriented record organization.
- FDR record creation and retrieval.
- Institution-level access boundaries.
- Workflow-aware record management.

### 🔄 3. Configurable Workflow Engine
- Configurable workflow stages and transitions.
- Validation of requested state changes.
- Versioned workflow configuration snapshots.
- Configuration fingerprinting and validation.
- Audit events for successful and rejected transitions.

The workflow engine is designed to keep business rules configurable rather than embedding every rule directly into application code.

### 📄 4. Document Management & Integrity
- Private document storage.
- Document upload validation.
- Versioned document evidence.
- SHA-256 cryptographic hashes for file-integrity checks.
- Document integrity outcomes: `PASS`, `FAIL`, and `INDETERMINATE`.
- Evidence history and related audit events.

SHA-256 helps determine whether a file matches its recorded digest. It does **not**, by itself, prove that the document was issued by a bank or that its contents are genuine.

### 🔗 5. FDR Relationship Analysis
- Relationship graph for connected FDR records.
- Breadth-First Search (BFS) and Depth-First Search (DFS) traversal.
- Cycle prevention in relationship handling.

These capabilities help organize