# Expedition procedures

## Intake to closure

1. Commander records the goal, original words and later changes. Sky Command plans bounded slices and acceptance proof. Hierophant resolves genuine judgment questions through reconciliation.
2. Captain assigns a native queue task, project, revision, owner and next continuation. Check the relevant provider budget, resource reservations and guest disk before admitting a phase. Work on unrelated admitted tasks may continue while a question is held.
3. Create a task worktree under the project's ignored `.worktrees/` with a stable task identifier. Register its ownership before work. Keep scratch in explicit `.scratch/` or temporary locations. Do not make extra full clones or scatter worktrees in home or `/tmp`.
4. The worker reads project instructions, implements and supplies exact candidate commits, tests and limitations. Positive/negative size goals never replace acceptance criteria.
5. Warden independently reviews in a separate task-owned tree. Repairs return to the appropriate implementor. Inquisitor diagnoses major causes; Witch runs bounded experiments. Questions go to Hierophant, which owns reconciliation.
6. Warden holds the integration slot, rebases onto the current target, verifies the new exact revision, and performs only authorized integration. Substantive conflict resolutions or evaluator repairs need independent review. Serialize builds and integration. Push/publish/deploy are separate authorization boundaries.
7. Commander returns the result. Chronicler preserves rationale. Close the task and request Deckhand retirement. Work can be delivered with a cleanup hold but cannot be called fully retired until resolved.

## Budget lifecycle

Use `budget/README.md`. Keep separate Claude and Codex state, account bindings, observation times, allowance windows, reset times, floors and permits. Do not sum percentages or borrow allowance. Choose eligible models in the ordered seat preference list; each uses only its own provider budget. Default admission is closed. Account identity, required windows and concurrency are setup policy; reserve floors are chosen afresh for each opening, not fixed installation settings. Each bounded turn/phase requires admission; continuation needs another permit.

Account changes, missing/expired observations, refills and interrupted turns require explicit reconciliation. Do not expire permits blindly while a process may still be spending. Native hooks must be loaded and trusted in the actual harness before claiming enforcement. Conversation during a pause must not start downstream work. No paid/model probes merely to observe allowance.

## Hygiene lifecycle

Use `hygiene/README.md` and its fixture-tested CLI. Queue-task closure requests inspection, not forced deletion. Pauses remain owned and locked. Seven days is an inspection backstop, never automatic destruction.

Check registration, containment, locks, active ownership, staged/unstaged/untracked/ignored content and unpushed commits. Preserve uncertainties as cleanup holds with owner and next step. Do not label arbitrary untracked files scratch. A stash is not durable proof. Only normal worktree removal is allowed after explicit retirement and verified preservation; never force-remove or delete branches as a fallback. Push only to an authorized destination. Idle full clones require separate inventory and decisions.

Deckhand carries routine hygiene; Cleric improves recurring failure prevention. If disk is tight, stop new work and resolve holds rather than sacrifice unique work.

## Recovery

Restore from native queue records, role guidance and exact artifact evidence. Check that old workers ended before releasing permits or declaring a tree inactive. A daemon restart does not prove a model turn stopped. Keep captured failure details in ignored state and a concise durable task record. Do not change credential boundaries, bypass permissions, or restart services unrelated to the rig.

## Opening the factory and delivering a PR stack

Jeremy's command “open the factory with a floor of 50/40” means preserve 50% of
Codex allowance and 40% of Claude allowance for this opening. It is not 50/40
spending, a permanent default, or permission to reopen automatically after reset.
Apply each provider's reserve to every configured applicable allowance window.
Commander records the instruction verbatim and Captain opens the approved queue
scope only for providers with verified identity, fresh quota, working native
hooks and the trusted runtime. An unavailable provider does not block the other. An illustrative example in a discussion is not a
live opening instruction. See budget/README.md for the budget-only command.

Provider-local stopping: a floor, reset/refill, invalid telemetry or stale
observation closes only the affected provider to new work. Its gate stays latched
until explicitly reopened. The other eligible provider may continue through the
seat's ordered preference list. Never transfer allowance, reopen on reset, change
models mid-turn, or release an outstanding permit merely to switch providers.
Already in-flight requests may finish or overshoot a reserve. Preserve exact
completion evidence and a durable checkpoint before changing runtime/model.

An opening spends effort on already authorized, ready queue work, not invented
projects or work blocked on human decisions. Every item must identify repository,
base branch, intended outcome, acceptance proof, authorized publication destination
and dependencies. Captain records the opening and native queue lineage. Missing
scope or repository publication authorization is a hold, not a reason to guess.

Warden's refinery remit produces an independently reviewed PR stack for Jeremy to
merge, rather than merging it for him. The first PR targets the authorized base;
each dependent PR targets its predecessor's branch. Independent work need not be
artificially stacked. Track branch, exact head SHA, base SHA, predecessor PR, review
receipt and tests in the native queue record. Publish draft PRs while incomplete;
mark ready only after acceptance evidence. Never enable auto-merge or merge these
PRs. Rebase/restack through the integration slot, preserve published work, and
repeat affected checks and independent review for material conflict resolutions.

At a budget pause, leave truthful PR descriptions and durable next steps; partial
work stays draft. Do not start extra model turns merely to polish shutdown notes.
Chronicler records the stack order and remaining caveats, and Commander reports
which PRs are ready, which are draft, and the reason work paused. Deckhand retains
unmerged or otherwise uncertain branches/worktrees; publishing a PR is not proof
that deleting its unique local work is safe.

This is the target operating procedure, not a claim that a queue dispatcher or
native-harness activation has been completed. The local budget primitive does not
start OpenRig or create PRs by itself.

## Ordered models and safe runtime handover

`model-preferences.json` records Jeremy's exact ordering. `model-catalog.json` is
a verified native-ID mapping, not a list of guessed aliases. Unknown entries are
ineligible; continue to a verified eligible later preference. Inquisitor uses Sol, then Opus, as explicitly selected by Jeremy.

The routing planner checks provider-local admission, native model identity, harness
readiness and same-seat active permits. A runtime/model change requires the old
session's exact stopped evidence and a durable checkpoint recording task lineage,
branch/head, tests, remaining work and continuation owner. Native OpenRig handover
must carry this checkpoint and the seat's provider-specific hook configuration.
A failed rebuild is a hold, not permission to duplicate the worker.

The planner returns a decision; it does not start or rebuild native sessions.
Until runtime/model selection and hook-preserving native handover are verified
end-to-end, automatic model switching is not operational. Nominal `rig.yaml`
runtimes are placeholders for initial topology, never a bypass of routing.


## Guest working environment

The rig's guest is its working environment. Registered repositories already in
the guest are the canonical project checkouts. Work with those repositories;
create task-owned Git worktrees inside the selected repository where isolation
is useful. Do not create an independent clone as a routine trust, tooling, or
permission workaround. Preserve human branches, uncommitted work and unrelated
worktrees. Report a real blocker and obtain any required scoped trust approval
instead of silently substituting another checkout.

For linked-worktree Codex hooks, storage may be required in the main checkout.
Any shared-root dispatcher must be explicitly approved, narrowly scoped to the
authorized task worktree, and inert for unrelated sessions. Keep existing native
sandbox and approval settings. No worker may widen scope or modify quota gates.

## Check discovery before PR publication

Before opening or updating a candidate PR, inventory checks from the exact head:
`python3 -m factory.checks --repo <canonical-worktree> --head <full-sha>`.
Review every full workflow, local action, package script and hook/task config.
Do not assume package-scoped tests or a pre-commit hook cover repository-wide
checks. In Atom.io, both `lint:unused` and `lint:unused:production` are relevant
Knip modes. Workflow matrices, conditions, reusable actions, working directories
and remote actions require inspection, not blind execution of extracted text.
Follow referenced check definitions until their obligations are understood.

Warden maps every discovered obligation to successful exact-head command receipts
or an explicit reason it is not applicable. Include setup/environment, command,
exit status and proof reference. A blocked/unavailable check is not a passing
check or an exclusion. Full CI-only work may require an approved equivalent or
human exception; do not silently waive it. Regenerate inventory and evidence
when the head changes. Trusted publication callers must regenerate and compare
the inventory against the repository; receipt self-attestation is not enough.
The publication planner requires `check_coverage`, even when generic test proof
is present. Keep cheap formatting checks at pre-commit; put complete applicable
coverage at pre-publication rather than running every matrix on every commit.

## Post-publication CI ownership

Captain assigns every published factory PR to Lookout with repository, PR,
owner and slice. Start the read-only observer and preserve its state under the
ignored runtime directory. Lookout reports current-head failures/missing checks
and routes repairs to the worker; Cleric owns systemic coverage/tooling fixes.
Warden still owns independent review. Neither seat automatically merges.
A configured seat alone is not a running watch: confirm observer health and
consume its durable changed-status reports. Human merges remain the endpoint.
