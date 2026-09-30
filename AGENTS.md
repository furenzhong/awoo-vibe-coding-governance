# Awoo Vibe Coding Governance — repository instructions

This is the reusable governance **source kit**, not a business project. It helps people keep intent, evidence and unfinished work usable across AI sessions and execution tools.

## Read only what the task needs

- Current work: `docs/00_PROJECT_CONTROL/PROJECT_CURRENT_STATUS.md`.
- Continuation point: `docs/05_HANDOFF/HANDOFF_CURRENT.md`.
- Governance rules: `docs/00_PROJECT_CONTROL/DOCUMENT_GOVERNANCE_SYSTEM.md`.
- Applying this kit elsewhere: `docs/03_DELIVERY/DELIVERY_PROJECT_INSTANTIATION_GUIDE_v1.md`.
- Upgrading existing or custom governance: `docs/03_DELIVERY/GOVERNANCE_UPGRADE_GUIDE.md`.
- Delegating work: `docs/02_TECH/HARNESS_CONTRACT.md`.
- Task context, corrections, and recovery: `docs/02_TECH/TASK_CONTEXT.md`.
- Optional native event capture and reconciliation: `docs/02_TECH/CONTEXT_CAPTURE.md`.
- Testing whether governance helps: `docs/03_DELIVERY/GOVERNANCE_TRIAL.md`.
- Structure and document ownership: `docs/00_PROJECT_CONTROL/PROJECT_STRUCTURE_AND_NAMING_SPEC.md` and `DOCUMENT_CATALOG.md` in that directory.
- Document lifecycle and context reduction: `docs/00_PROJECT_CONTROL/DOCUMENT_LIFECYCLE.md`.

## Interpret the user's destination correctly

“Apply / deploy this repository's governance to my current project” means integrate the kit into that existing target. Treat this checkout as source material. Determine the target from the user's workspace, not from the directory in which the source was downloaded.

Use `scripts/project_os.py plan --target <target>` before `apply`. Inspect the plan and resolve routine choices within the existing request. Do not add an approval round for an already authorized, additive installation. Ask only if the target or a substantive conflict cannot be determined.

Preserve the target's product, code, Git history, remote, existing rules and uncommitted work. Reuse its authoritative documents through a mapping. Do not copy the source kit's project status into the target, replace its README, repoint origin, or push its business content to the source remote. New empty projects are supported too; they do not require a frontend, backend or a particular stack.

For an authorized upgrade, identify actual adopted components and local customization before proposing changes. Missing adoption history stays unknown. Review explicit candidate changes against current requirements and existing sources, then use the upgrade guide to plan, apply and record only that scope. Coordinate writers of affected files and recheck drift before applying. A newer upstream revision or an edited version number does not prove adoption; a journal or file update does not prove that a running executor received a correction. Upgrade does not start or prompt document cleanup.

Retiring a phase's dispatch does not retire stable rules embedded in the same document. Preserve applicable isolation, write ownership and acceptance constraints through current references. Mark superseded execution clauses at their location with the replacement source and scope, including exceptions for older tasks; keep unrelated constraints effective.

## Maintain facts once

`project-os.json` maps each authoritative source. Stable instructions live here; mutable project state lives in the status document. Handoff preserves unfinished context and points to state. Briefs and indexes link to those sources rather than maintaining another progress list. Historical observations belong in dated evidence or session records.

Backlogs keep task status, the next action and a topic link rather than repeating that topic's requirements, constraints or pending choices. When the current change touches a duplicate entry, replace that duplicate with a reference only after confirming the topic preserves the full content; this does not start unrelated cleanup.

Treat working notes, current authority, evidence, and archives differently. Only when the user explicitly requests document inventory or cleanup, consolidate within the requested scope: preserve constraints, unresolved work, rejected options and their rationale, and evidence in the appropriate sources. Keep canonical paths stable; mark replaced notes in place or update references before archiving. Read archives only for a specific question. For an explicitly requested inventory or cleanup, use `python scripts/project_os.py inventory --target . --json` as needed for read-only signals; its scan is project-wide, but cleanup remains limited to the requested scope. Unclassified or identical files are not a deletion list. Delete only within existing authorization after checking dependencies and retention; age, length, or filename alone is insufficient.

Distinguish user requirements, working assumptions, observed facts and acceptance decisions. Evidence must identify the version and checks it covers. Code, running processes and documentation may disagree: investigate the discrepancy and correct the current summary; do not declare a document true merely because it is marked active. Preserve historical evidence.

Document cleanup starts only on an explicit user request, such as "Use document governance to clean up all project documents" or "Clean up the plans and Markdown under docs/export". Adoption, task closure, replaced decisions, phase handoffs, context conflicts, and new sessions do not start or prompt a cleanup. Normal fact maintenance and task-related questions continue as before. During requested cleanup, investigate uncertain facts first. Ask the user when unresolved intent, a unique constraint, or deletion outside authorization affects the outcome; show the specific conflict, evidence, recommendation, and impact. Preserve disputed material and pause only dependent actions while waiting. Ordinary reversible organization within existing authorization needs no extra approval.

## Work in bounded, verifiable steps

- Test the most consequential uncertainty with the smallest useful experiment. Mock data is useful when it answers that question; model quality or provider behavior may require authorized real samples.
- Define the desired behavior and acceptance basis before implementation. Use relevant tests; do not invent tests that only restate a document edit.
- Delegate independent tasks when useful. Assign write ownership and a baseline; collect an identifiable result and verification evidence before accepting it. An isolated worktree does not isolate databases, ports, processes or external accounts.
- Recover an interrupted task by inspecting its recorded session, files and external operation IDs before redispatching. Carry forward the user's existing authorization and constraints.
- For cross-session or delegated work, retain a versioned dispatch snapshot with relevant constraints and their sources, rejected choices and reasons, assumptions, and acceptance basis. Confirm that the actual executor can access that version. Test a consequential interpretation through an early key choice or representative result; routine edits need no extra approval.
- Each active coordinator/executor maintains its own task checkpoint: observed actions and evidence, unresolved questions, operations and locators, next action, and adopted context revision. Update on meaningful changes or handoffs, not every message. Handoff links these records; it does not become a shared writable memory dump.
- On an explicit request to prepare a new conversation or update handoff, preserve unsaved decisions, corrections, evidence and operating details whose absence would cause repeated questions, trial and error, wrong-environment actions or duplicate operations. Keep stable access/operating knowledge in an existing runbook and temporary state in the task/checkpoint; handoff links both. Record credential locations, never values. Follow the applicable details in `TASK_CONTEXT.md`; no universal server form or new task for discussion. Report the resume entry, gaps and actual checks, distinguishing saved information, reviewed sufficiency and verified resumption. This does not start document cleanup or automatic reminders.
- A correction being recorded, delivered, and adopted are separate facts. Retain delivery/adoption evidence tied to the target session; editing a shared file proves neither. Reconcile stale deliveries and affected work before acceptance. One-shot workers may receive changes only on return; documents cannot interrupt active writers.
- Checkpoints describe the last observation, not live runtime truth. Recheck current authority, task revisions, pending corrections, Git and operations when resuming. Preserve user constraints and distinguish observations from assumptions; do not summarize summaries into new authority. No access to internal compaction or lossless recovery is assumed. This task record maintenance does not initiate document cleanup.
- Keep model choices and tool-specific invocation details outside durable product rules. Shared instructions have one canonical source; `CLAUDE.md` is an import entry.

## Change and validation discipline

Keep Chinese and English README behavior and limitations in sync. Update the relevant source of truth, document catalog and decision log when their contracts change; do not copy the same update into every entry file.

Required checks for installer/checker changes:

```text
python -m unittest discover -s tests -v
python scripts/project_os.py check --target .
```

Machine checks cover declared structure and evidence consistency, not product correctness or actual AI adherence. For changes to onboarding or recovery behavior, also run the independent trial in `GOVERNANCE_TRIAL.md`. Record skipped checks as untested.

Finish with what changed, what was verified, remaining limitations, and only decisions that actually need the user. Do not keep crucial state solely in the conversation.
