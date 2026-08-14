# Submission Compliance Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair confirmed audit, portability, documentation, and packaging defects without changing the validated L1–L5 runtime behavior or original evidence.

**Architecture:** A machine-readable manifest becomes the submission source of truth. Audit and verification tools consume the manifest, while documents and a clean evidence ZIP expose the same facts to reviewers. Runtime paths are protected by a baseline tree-hash comparison against commit `4b9d7ed71d57e307d7a0bb3b41f55201704a466e`.

**Tech Stack:** Python 3.11+, JSON, Markdown, Git, Git LFS, SHA-256, ZIP.

## Global Constraints

- Do not modify any file under the validated runtime paths listed in the approved design.
- Do not alter the 15 original score/result/trajectory evidence files.
- Fix the official reference to an immutable 40-character commit and archive SHA-256.
- Treat direct MuJoCo access in skills as an unresolved organizer-interface question, not as resolved compliance.
- Read and write all text explicitly as UTF-8.

---

### Task 1: Freeze the official reference

**Files:**
- Create: `/private/tmp/jciiot-official-reference/`
- Record later in: `JCIIOT/team_submission/submission_manifest.json`

**Interfaces:**
- Produces: official repository URL, commit SHA, archive SHA-256, audit timestamp, and exact upstream file inventory.

- [ ] Resolve `refs/heads/master` from the organizer repository to a 40-character SHA.
- [ ] Download the archive for that exact SHA and calculate SHA-256.
- [ ] Inspect Git LFS pointers and retrieve only upstream objects required by the protected inventory.
- [ ] Compare the fixed inventory with the submission and classify every protected path.

### Task 2: Build manifest and immutable evidence index

**Files:**
- Create: `JCIIOT/team_submission/submission_manifest.json`
- Create: `JCIIOT/team_submission/evidence/EVIDENCE_INDEX.json`
- Create: `JCIIOT/team_submission/evidence/EVIDENCE_INDEX.md`

**Interfaces:**
- Consumes: Task 1 official reference and current evidence/model files.
- Produces: canonical submission facts consumed by validation and documentation checks.

- [ ] Hash the 15 evidence files and six LFS-backed model files.
- [ ] Extract score, time, environment, model route, and grasp router for L1–L5.
- [ ] Write the manifest and evidence indexes with repository-relative POSIX paths.
- [ ] Verify all indexed hashes immediately after writing.

### Task 3: Harden final validation

**Files:**
- Modify: `JCIIOT/team_submission/audits/verify_final_submission.py`
- Create: `JCIIOT/team_submission/audits/test_verify_final_submission.py`

**Interfaces:**
- Consumes: `submission_manifest.json`, evidence index, protected audit.
- Produces: seven independent PASS/FAIL groups and a nonzero exit code on failure.

- [ ] Add UTF-8 helpers and pre-hash Git LFS pointer detection.
- [ ] Validate Python/JSON, models, evidence, routing, SOP, boundary, and document consistency independently.
- [ ] Add tests for Chinese default encoding, LFS pointers, bad hashes, and unchanged evidence.
- [ ] Run under `python -X utf8` and `python -X utf8=0`.

### Task 4: Make training configurations portable

**Files:**
- Modify: `JCIIOT/team_submission/training_configs/*.json`
- Create: `JCIIOT/team_submission/TRAINING_DATA_MANIFEST.md`
- Create: `JCIIOT/team_submission/audits/validate_training_configs.py`

**Interfaces:**
- Produces: configurations whose relative paths resolve from the `JCIIOT/` project root.

- [ ] Replace machine-specific dataset and output paths with project-root-relative paths.
- [ ] Document required HDF5 files and their submission status.
- [ ] Load all 28 JSON files and resolve all dataset/output paths from `JCIIOT/`.
- [ ] Fail validation if a Windows drive path or `/Users/` path remains.

### Task 5: Synchronize submission documents

**Files:**
- Modify: `README.md`
- Modify: `技术报告.md`
- Modify: `实验开发日志.md`
- Modify: `复现指南.md`
- Modify: `最终提交清单.md`
- Modify: `排行榜提交草稿.md`
- Modify: `提交合规说明.md`

**Interfaces:**
- Consumes: canonical facts from the manifest.
- Produces: consistent reviewer-facing descriptions and an explicit unresolved interface-risk statement.

- [ ] Replace stale score, timing, audit, identity, issue, and repository facts.
- [ ] Mark historical development conclusions as non-final.
- [ ] State the inference-versus-training reproducibility boundary accurately.
- [ ] Add the Git clone plus Git LFS requirement and prohibit use of GitHub source ZIP for models.

### Task 6: Restore and audit protected upstream resources

**Files:**
- Restore: only protected files present in the fixed official commit and missing locally.
- Modify: `JCIIOT/team_submission/audits/official_boundary_audit.json`
- Modify: `JCIIOT/team_submission/audits/official_boundary_audit.md`

**Interfaces:**
- Consumes: fixed official archive and official LFS objects.
- Produces: truthful classification with no hand-written LFS pointers.

- [ ] Restore normal files byte-for-byte and LFS files through Git LFS.
- [ ] Generate ordinary-identical, pointer-identical, LFS-materialized, LFS-unavailable, and missing counts.
- [ ] Record reference URL, commit, archive hash, and audit time.
- [ ] Verify the audit does not claim zero missing unless the inventory proves it.

### Task 7: Build the clean evidence package

**Files:**
- Create: `JCIIOT/team_submission/tools/build_evidence_package.py`
- Replace local artifact: `JCIIOT2026.zip`

**Interfaces:**
- Consumes: current root documents, evidence index, and 15 evidence JSON files.
- Produces: deterministic UTF-8 ZIP with ASCII paths and no model or Mac metadata.

- [ ] Build the documented ASCII directory layout.
- [ ] Include all score/result/trajectory evidence files.
- [ ] Reject absolute local paths in package-generated summary/index files.
- [ ] Parse every packaged JSON and inspect every ZIP entry.

### Task 8: Prove zero runtime change and finish verification

**Files:**
- Create: `JCIIOT/team_submission/audits/runtime_immutability_report.json`
- Create: `JCIIOT/team_submission/audits/runtime_immutability_report.md`

**Interfaces:**
- Produces: final evidence that runtime files and historical evidence are unchanged.

- [ ] Compare protected runtime paths against `4b9d7ed71d57e307d7a0bb3b41f55201704a466e`.
- [ ] Compare all 15 evidence hashes against the baseline commit.
- [ ] Run JSON/Python validation, training-config validation, final verification, Git LFS fsck, and ZIP inspection.
- [ ] Inspect `git diff --name-only` against the baseline and reject any path outside the approved allowlist.
- [ ] Commit the completed repair without pushing until the user reviews the final report.
