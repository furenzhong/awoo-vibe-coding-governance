# Awoo Vibe Coding Governance

English · [简体中文](README.md)

Release: [v1.5.0 notes and download](https://github.com/furenzhong/awoo-vibe-coding-governance/releases/tag/v1.5.0). Existing projects adopt relevant changes through the [upgrade guide](docs/03_DELIVERY/GOVERNANCE_UPGRADE_GUIDE.md); publishing does not modify projects or enable hooks automatically.

This working tree includes **v1.6.0 candidate** changes for operational handoff and growing record histories; it is not a formal release. See the [implementation plan](docs/03_DELIVERY/CONTINUITY_AND_SCALE_PLAN.md) for scope and [current status](docs/00_PROJECT_CONTROL/PROJECT_CURRENT_STATUS.md) for actual validation evidence.

Keep the same project moving correctly when you switch conversations, models, or execution tools.

Awoo Vibe Coding Governance is a lightweight governance kit that integrates into **existing projects**. It helps an AI find effective requirements, current facts, unfinished work, and acceptance evidence. It includes additive installation and local checking tools. You can give this repository link directly to the AI already working on your project.

It is intended for ongoing development with tools such as Codex and Claude Code. For a one-off task, borrowing a few principles may be enough. It does not build your application automatically or require a specific model, technology stack, or multiple agents.

## The simplest way to use it

Send this prompt to the AI in your existing project:

```text
Integrate the documentation governance from
https://github.com/furenzhong/awoo-vibe-coding-governance
into the project I am currently developing.

Follow the kit's integration guide. Identify the source kit and the target
project, reuse my existing rules and authoritative documents, and add only
what is missing. Preserve application code, existing documents, uncommitted
work, Git history, and remotes. Do not copy the kit's own product identity
or project status into my project facts.

Run the machine checks and an independent handoff exercise. Tell me what
the checks found, what was actually verified, what remains untested, and
whether a specific decision needs my input. Do not make me fill in a set
of governance forms.
```

The AI's operational entry is the [integration guide](docs/03_DELIVERY/DELIVERY_PROJECT_INSTANTIATION_GUIDE_v1.md). When the project already contains the necessary information, the AI should extract it rather than ask you to enter it again or approve routine implementation choices.

## What it addresses

| Common failure | Mechanism |
|---|---|
| A new conversation reopens settled decisions | Explicit sources for current facts and decisions; read context on demand |
| Multiple “current status” documents disagree | Maintain each fact once; handoffs and briefs reference it |
| An AI says “done” without a clear basis | Bind results to a revision, checks, and evidence; record acceptance separately |
| An omitted constraint sends Claude Code's implementation off course | Dispatch snapshots preserve constraint sources, rejected options, assumptions, and acceptance criteria |
| Compaction or a new conversation loses track of other AI workers | Separate checkpoints for each execution identity; distinguish recorded, delivered, and adopted corrections |
| A successor knows the plan but cannot find the admin console or previously successful procedure | Keep stable operating knowledge in existing runbooks, temporary state in checkpoints, and handoff pointers with explicit gaps |
| Installing a kit replaces the project's identity | Check source and target identities; preserve the target's Git and business content |
| Documentation grows without visible benefit | Run AI handoff and failure exercises; report outcomes and maintenance effort |
| Old proposals become current requirements, or cleanup loses open questions | Consolidate conclusions, constraints, rationale, and unresolved work; retrieve history on demand |

Start with the smallest experiment that tests the most consequential uncertainty. Mock data may validate a UI flow; model quality, provider behavior, and generated output need relevant empirical evidence. Templates do not require every project to build a frontend, backend, or rules engine first.

## What integration adds

By default, four small documents are added. Existing equivalents can be mapped directly instead of creating another set.

```text
your-project/
  project-os.json             # Authoritative paths and kit provenance
  .project-os-adoption.json    # Actual installed content and provenance evidence
  AGENTS.md                   # Original content preserved; index appended
  CLAUDE.md                   # Original content preserved; shared-rule import appended
  scripts/project_os.py       # Local checking tool
  project-os/
    RULES.md                  # Stable rules
    STATUS.md                 # Current facts, assumptions, and goals
    HANDOFF.md                # Unfinished work and recovery context
    DECISIONS.md              # Significant choices and their rationale
```

Task and evidence directories are used when work calls for them. Tasks spanning conversations or delegated to other executors can retain dispatch snapshots, individual checkpoints, and correction evidence there, without adding a fifth global source or a `MEMORY.md`. Heavier PRD, API, and risk templates remain optional resources in the kit; **they are not copied into every project**. The AI must populate the initial documents from your actual project. File existence alone does not constitute successful integration.

For compatibility with existing installations, `project-os.json`, `project-os/`, and `scripts/project_os.py` retain their names. The brand change does not require migrating project files.

## Manual commands

Requires Python 3.10+ and Git, with no model API key or third-party Python packages. Platforms share the Python entry; see [current status](docs/00_PROJECT_CONTROL/PROJECT_CURRENT_STATUS.md) for cross-platform validation of a specific version. Run these commands from the **target project's root**, with the source kit beside it:

```text
git clone https://github.com/furenzhong/awoo-vibe-coding-governance.git ../awoo-governance-kit
python ../awoo-governance-kit/scripts/project_os.py plan --target .
python ../awoo-governance-kit/scripts/project_os.py apply --target .
python scripts/project_os.py check --target .
python scripts/project_os.py snapshot --target . --json
python scripts/project_os.py inventory --target . --json
```

- `plan` reads the project and lists proposed changes and conflicts. After inspecting it, the AI can `apply` within the user's existing authorization.
- `apply` creates or appends incrementally. Repeated use preserves user content. Conflicts are reported rather than resolved by replacing the project.
- `check` checks declared paths, entrypoints, tasks, and evidence consistency. For tasks using the context protocol, it also checks snapshot SHA-256 digests, revision references, correction evidence, and the context a receipt declares it adopted. It calls no model, application service, or network endpoint.
- `snapshot` reports observable state without rewriting project status.
- `inventory` reads Markdown and related documents and reports entrypoints, working material, evidence, archives, unclassified files, exact duplicate candidates, and lifecycle conflicts. Classification uses declarations and paths, not observed AI reading; unclassified does not mean disposable. It never archives, merges, or deletes files automatically.

Use `--mapping` to adopt existing documents; see the [mapping example](examples/adoption-mapping.json) and [integration guide](docs/03_DELIVERY/DELIVERY_PROJECT_INSTANTIATION_GUIDE_v1.md). Replace example paths with real target paths. `apply` handles initial additive adoption, not upgrades. First adoption records actual content and provenance; rerunning it in an existing project does not invent an earlier installation history. The adoption record is upgrade evidence, not a fifth authoritative source. Legacy tasks remain supported, and the context protocol is optional. The report's `context.legacy` identifies tasks not checked against the new protocol; do not fabricate historical records to migrate them.

## Upgrading a project already in development

Send this prompt to the AI maintaining your target project:

```text
Follow the upgrade guide at
https://github.com/furenzhong/awoo-vibe-coding-governance
to adopt the governance capabilities appropriate for this project.
Identify existing governance responsibilities and actual adoption first.
Preserve application code, requirements, uncommitted work, historical
evidence, and active tasks. Reuse existing directories and sources of truth.

Verify continuation in an isolated copy before applying reviewed local
changes. Retain evidence of actual adoption and how to roll it back.
Do not replace project material with templates, start document cleanup,
or invent task history. Report what was adopted, verified, and left uncovered.
Do not ask me to fill in a migration form.
```

The AI follows the [existing-project upgrade guide](docs/03_DELIVERY/GOVERNANCE_UPGRADE_GUIDE.md), establishes constraints and facts, and prepares explicit candidate content. `upgrade-plan` creates a self-contained plan. `upgrade-apply` rechecks it, writes one item at a time, and retains before/after content. `upgrade-rollback` reverts this upgrade's content only while it has not been changed again. A known adoption baseline enables three-way comparison; without one, adaptation starts from verifiable current material, not a guessed version.

These tools do not decide requirements or perform semantic merges. They are not a cross-file transaction or a lock against arbitrary writers. A detected file change at a pre-write check rejects the stale plan; files changed after the upgrade need a focused reverse patch. An upstream push does not update your project, and there is no background upgrade or automatic cleanup. Custom governance directories do not require rewriting their history. See [current status](docs/00_PROJECT_CONTROL/PROJECT_CURRENT_STATUS.md) for implementation and actual validation coverage.

Ending an old phase does not invalidate stable collaboration rules embedded in its documents. Preserve those rules and mark superseded execution clauses with their replacements. Plans and journals can contain full project text: retain them with private project backups. The tool requires them to be stored outside the target, so they do not automatically enter its Git history. Usually revert the latest upgrade first; never overwrite later work with an older snapshot.

Research notes, candidate designs, and phase plans should not all enter every AI session. When the user explicitly requests cleanup, follow the [document lifecycle](docs/00_PROJECT_CONTROL/DOCUMENT_LIFECYCLE.md) within the requested scope to consolidate current conclusions while preserving user constraints, rejected options and their rationale, open questions, and evidence before marking replacements or archiving. Judge success by whether a fresh AI finds the current decision and preserves unresolved work, not by the number of deleted files. Deletion is never the default action.

Cleanup starts only on an explicit user request, such as "Use document governance to clean up all project documents, plans, and Markdown" or "Organize only the proposals under docs/export". Adoption, task closure, replaced decisions, phase handoffs, conflicts, and new sessions neither start cleanup nor prompt the user to start it. Once requested, inspect evidence first, and ask only about unresolved user intent, a unique constraint that might be lost, or deletion outside existing authorization. State the specific sources, recommendation, and impact. While awaiting an answer, preserve the material and pause only dependent actions.

## Retaining context across native compaction

v1.5 adds optional [session event capture](docs/02_TECH/CONTEXT_CAPTURE.md). Once explicitly adopted in a project, supported native hooks retain input, compaction, and result evidence privately. During normal work, the AI writes meaningful changes to existing topic documents or checkpoints. Capture, reconciliation, persisted changes, and executor adoption remain separate facts. A new session can discover pending input and unknown coverage instead of relying solely on an old summary.

Default installation provides the tools; **it does not enable session capture**. Adoption checks the actual host and version, configures project hooks, and follows the host's trust mechanism. Claude can supply readable `compact_summary`; Codex summary text is not assumed available, and event support varies by host version. Tools without native integration use model-assisted records with explicit coverage limits. See [current status](docs/00_PROJECT_CONTROL/PROJECT_CURRENT_STATUS.md) for the actual validation scope.

Events stay in Git-ignored `.project-os-local/`, with common credentials filtered and truncation declared by default. They are not uploaded to this repository. Native summaries remain historical evidence and cannot override later decisions. `status/resume` report captured, pending, and unknown coverage; these records do not prove semantic accuracy or real-time synchronization. Each adapter can be disabled while retaining evidence. No event starts or prompts document cleanup.

Events and reconciliation receipts keep accumulating. There is currently no automatic rotation, retention period, or capacity limit. Reducing repeated reads and computation does not bound storage growth; measured evidence defines performance coverage. Native adapters do not capture every tool call either: a successful command visible only in terminal output may still need the AI to preserve it in a runbook.

## Before starting a new conversation

Send this request in the old conversation:

```text
I am about to start a new conversation. Follow project governance to save
information from this session that is still missing from the relevant
project documents and would affect continuation. Preserve my decisions,
corrections, rejected options and reasons, actual checks, and unfinished work.

If continuation depends on a server, admin console, or tool, update the
existing runbook with the environment, entry point, identity, credential
location (no secret values), successful steps, and verification time.
Update existing checkpoints with operation IDs, query methods, the current
stopping point, and unknowns. Link these sources from the handoff.
Do not fill irrelevant tables, force a new task for each conversation,
clean up history, or change application code.

Give the new conversation its entry point. Report separately what was saved,
what was checked, whether continuation was actually tested, and specific
remaining gaps. Keep unverifiable information marked unknown.
```

In the new conversation, say: "Recover context from the project's governance entry. Check the current goal, constraints, actual environment, and existing operation before continuing the authorized next step. Identify any gaps." The [starter template](docs/05_HANDOFF/templates/NEXT_SESSION_STARTER_TEMPLATE_v1.md) provides more detail. Query an existing operation before acting; an old conversation ending without a final response is not a reason to resubmit it.

Preserve information whose absence would make a successor ask you again, repeat failed attempts, use the wrong environment, or repeat an accepted operation. Update existing documents in place, with pointers in HANDOFF. Projects without servers need no access table. A handoff saves verifiable information; it cannot recover unavailable history or guarantee inherited login state. **Saved records, checked handoff information, and tested continuation are separate outcomes.** Preparing a handoff does not automatically establish all three.

This is a user-invoked handoff entry. It adds no scheduled prompts, automatic exit interception, or cleanup triggers. The [offline continuation example](examples/continuity/README.md) demonstrates the structure; repeating a public example does not count as a blind handoff test.

## How to tell whether it helps when the AI uses it

Ask the AI for a short result receipt instead of reviewing every template yourself:

```text
Machine checks: pass / issues found; actual report attached
Independent handoff: pass / fail / untested; correct goal, work state, next step?
Operational continuation: environment, original operation, and action evidence;
explicitly mark it inapplicable or untested when appropriate
Failure exercises: what was detected, and what was missed?
Observed use: recorded repeated work, user corrections, and maintenance effort
Your decision: none, or one specific question
```

At first adoption and after substantial changes to reading or collaboration behavior, follow the [governance trial](docs/03_DELIVERY/GOVERNANCE_TRIAL.md) in an isolated copy: fresh-session recovery, stale statements, missing acceptance evidence, and interrupted work. When operations are involved, also test whether a fresh AI finds the correct environment, queries the original operation, performs a real next step, and identifies a deliberately missing dependency. Seal expected answers before the trial and withhold them from the successor. Day-to-day work checks only relevant changes. It does not rerun the entire trial on every edit or automatically create monitoring or paid calls.

**A machine pass establishes only the checked structural and declaration rules.** It does not establish product quality, the truth of every document, or actual agent adherence. Mark exercises that were not run as untested. Report evidence and a minimal correction when something fails. See the [current status](docs/00_PROJECT_CONTROL/PROJECT_CURRENT_STATUS.md) for measured coverage and the corresponding versioned evidence.

## Collaboration such as Codex → Claude Code

The [harness contract](docs/02_TECH/HARNESS_CONTRACT.md) defines tool-independent dispatch and return: goal and baseline → bounded execution → inspectable delivery → acceptance → update the authoritative state.

Suppose you told Codex, "Document cleanup starts only when I request it," but it sends Claude Code only a plan to "complete document governance." Claude might add automatic cleanup while following that plan. The missing input is the decision and its rationale reaching the executor along with the task.

The [task context protocol](docs/02_TECH/TASK_CONTEXT.md) adds three things for such tasks:

- **Retain the context dispatched.** Versioned snapshots record the goal, constraints and their sources, rejected options and reasons, assumptions, non-goals, and acceptance criteria, so the coordinator can compare them with the revision the executor actually adopted when work returns.
- **Preserve each participant's recovery state.** The coordinator and executors keep separate checkpoints for actions actually completed, results, unresolved issues, ongoing operations, and the next step. A new conversation checks these clues against the actual environment before resuming.
- **Check whether a correction was adopted.** Editing a shared file only records it. A resumable session needs targeted delivery and adoption evidence. When a one-shot invocation cannot receive an update, keep the correction pending and inspect the affected scope of its old-context output when it returns. Do not accept it before reconciliation.

Maintain these records at necessary points such as dispatch, consequential choices, corrections, and handoff, as part of the authorized task. They require no per-turn summaries and do not start document cleanup, scheduled jobs, or extra approval rounds. Tasks with meaningful design choices should expose a key choice or a small representative result early, so misunderstandings can be found; mechanical edits need no confirmation ceremony.

The task context protocol provides contracts, examples, and local receipt checks. The [optional event capture](docs/02_TECH/CONTEXT_CAPTURE.md) added in v1.5 separately receives supported pre/post-compaction events and available summaries; actual capability depends on the host version, trust state, and recorded validation. The kit does not provide a cross-model orchestrator or guarantee lossless memory. Markdown cannot pause an active executor or prove it understood a requirement. A project chooses its executors, models, and CLI adapters. Separate worktrees do not isolate databases, ports, or external accounts. After interruption, inspect the existing task, exact session, and ongoing operations before resuming to avoid repeating effects that already occurred.

## Reading and contributing

- [Governance principles](docs/00_PROJECT_CONTROL/DOCUMENT_GOVERNANCE_SYSTEM.md): ownership of requirements, facts, assumptions, and acceptance.
- [Implementation and limitations](docs/00_PROJECT_CONTROL/PROJECT_CURRENT_STATUS.md): grounded in actual records.
- [Contributing](CONTRIBUTING.md): improve the kit through concrete failures and verification.
- [MIT License](LICENSE): copy, modify, use commercially, and redistribute while retaining the license notice.

Shared rules live in `AGENTS.md`; `CLAUDE.md` is a compatibility entry. Optional `.agents/skills/` provide workflow guidance. Integration does not automatically modify global skills or model configuration. Detailed operational documents are currently primarily in Chinese; this English README covers the complete public quick-start and capability boundaries.
