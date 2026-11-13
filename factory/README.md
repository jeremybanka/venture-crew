# Selected GitHub issues → native queue → reviewed PR stack

These components implement validated planning plus explicit cold enqueue, bounded
fresh-launch and draft-publication execution adapters. They are not a running
factory or GitHub poller. Execution has only been tested with injected fixtures.
No repository, issue or readiness label is eligible by default.

## Explicit intake

Select owner/repository and issue number from Jeremy's instruction, not the issue
body. Fetch its snapshot through the connected GitHub reader or authenticated
`gh api repos/OWNER/REPO/issues/NUMBER` in the approved clean context. No credential
copy or new login is part of these tools. Then:

```sh
python3 -m factory intake --repo OWNER/REPO --issue NUMBER \
  --snapshot /path/issue.json --source ACTUAL_CALLER \
  --destination REGISTERED_COMMANDER --target-repo REGISTERED_REPO
```

This outputs a draft, stable issue identity/queue retry ID, source revision, native
argv and stdin body. It does not create the queue item. Repository and issue URL
must agree; PR objects and closed issues are rejected by default. Issue text is
isolated as untrusted task data. Changed revisions retain the same intake identity:
reconcile the existing native item, do not blindly create another.

`target_repo` must match an actual native RigSpec workspace repository. The current
inventory `projects.local.json` (see `projects.example.json`) is not that registration and grants no task scope. There
is no selected repository/issue, registered intake mapping, or verified caller
context yet. Do not fabricate those to make a command run.

## Cold enqueue bridge

`factory.bridge.cold_enqueue` is a bounded subprocess adapter with injectable
runner and a retry journal. It accepts only the checked `queue create` argument
shape with `--no-nudge`, fixed `--id`, `--target-repo`, and `--json`. It deliberately
omits `--source`: run only from an actual managed caller context. Do not set another
seat's identity. Use the reviewed clean OpenRig executable, not the dirty npm copy.

To adapt an intake draft, verify its actual caller/destination/repo mapping, remove
its preview `rig` and declared `--source` pair, materialize its exact stdin body to
a private ignored-state file, and replace `--body-file -` with that absolute path.
The bridge rejects body/journal path collisions, serializes shared body artifacts,
and uses unique atomic temporary files. It writes that body and records an unknown attempt before invoking native
CLI. Only a successful correlated `qitemId` receipt becomes submitted. Unknown outcomes require native readback/reconciliation, never automatic resubmission; changed content/destination holds for reconciliation.
A submitted queue item is not a started model, accepted work, or human notification.

The retry journal is not a second task queue. Native OpenRig owns task states and
handoff history. Native output formats not matching the verified receipt shape
remain unknown for readback. There has been no live daemon/enqueue round trip.

## Budget-aware cold dispatch

`python3 -m factory dispatch --evidence /path/dispatch.json` consumes the documented
`plan_dispatch` fields in `dispatch.py`: trusted task scope/owned workspace, current
native claimed owner/caller and seat-to-destination binding, model catalog/preferences, both provider statuses,
readiness and explicit session evidence (`no_existing_session:true` or current
session plus handover evidence). It uses the routing
planner and emits only a cold `rig queue handoff … --no-nudge --json` plan.

The native handoff derives its actor from the real managed seat; no `--from` or
borrowed identity is supplied. Re-read native ownership immediately before use.
This code validates evidence shape and equality, not its authenticity. The native
model-launch bridge still must verify runtime/model/high effort, checkpoint,
permissions, hooks and atomic turn admission. Cold handoff never bypasses those.

## Independently reviewed stacked PRs

```sh
python3 -m factory publication --repo OWNER/REPO --issue NUMBER \
  --base APPROVED_BASE --slices /path/reviewed-slices.json
```

The ordered slices schema is documented in `publication.py`. Each entry records
branch, exact head SHA, author, independent review receipt, tests for that SHA and
optional predecessor slice. Invalid branches/graphs or duplicate artifacts reject;
missing/stale review/tests block the slice and descendants. Ready output contains
explicit `gh pr create --draft --repo … --base … --head …` argv and generated body.
No merge, auto-merge, implicit push/fork or issue auto-close command is generated.
Review/test receipt hashes identify supplied evidence without publishing raw logs.

Before executing a generated publication command, the authorized operator must
verify receipt authenticity, current remote head/base, branch ownership, repository
publication permission and existing PRs for retry idempotency, then materialize the
body verbatim. Do not blindly rerun create after an uncertain response. The explicit `publish --execute` adapter below creates drafts with durable retry
protection. No code pushes branches, merges PRs, marks drafts ready, or restacks
remote branches. Jeremy merges. Only verified merge state can satisfy delivery;
Deckhand still independently checks unique/unpushed/active work before retirement.

## Verified scope and remaining work

Fixture tests cover intake boundaries, native argument shapes, stable identity,
cold retry records, claimed-owner dispatch, provider/permit gating, exact-review
stack topology and shell-injection avoidance. OpenRig 0.7.3 create/handoff flags and
installed gh create flags were inspected. No actual selected issue, native queue,
GitHub publication or model turn was used in tests.

Remaining: explicit issue/repo selection and native workspace registration, trusted
live dispatch evidence collection, real cold/native-launch/GitHub round trips,
safe runtime migration, and existing runtime/hook/Claude quota activation gates. The same permission and hygiene boundaries apply.


## Explicit execution adapters

Execution is opt-in, scoped, and must use approved absolute clean executables.
The CLI has no default repository/issue. Its `--execute` flag is an operational
safeguard, not a replacement for owner authorization or verified evidence.

`factory.github_intake.intake_selected` reads the selected issue with `gh api`,
validates it, and cold-enqueues idempotently. Its trusted context requires current
native registration and actual managed caller matching the inherited environment;
it never sets another seat's identity. Expose only verified mappings, not issue
fields. The equivalent CLI is:

```sh
python3 -m factory enqueue --repo OWNER/REPO --issue NUMBER \
  --context /path/verified-native-context.json --gh /approved/gh \
  --rig /approved/rig --state-dir /private/intake-state --execute
```

`factory.native_dispatch.launch_fresh` is an executable native bridge, not just
argv generation. A live trusted `preflight()` collector must establish claimed
task ownership, exact seat mapping, materialized native model/runtime/high effort,
permissions, verified task/artifact context SHA-256 and workspace revision,
serialized settings, exact-turn hooks and automatic
startup admission. It checks only the selected provider's open gate while retaining
cross-provider same-seat permit holds. It requires explicit no-existing-session
and expected native session name, validates `seat launch --fresh --plan --json`,
rechecks live evidence, then journals durably before `seat launch --fresh`.
It never uses --stop, runtime switching, permission overrides or guessed turn IDs.
A recorded attempt, including timeout, always requires native reconciliation before
another launch. The native hook admits the actual turn; no synthetic permit is
acquired. A launch receipt is not task completion or proof of model admission.
**The production live evidence collector and end-to-end hook verification are not
installed.** Arbitrary JSON true values are not adequate preflight evidence. Native
successor-first runtime switching is deliberately unsupported by this adapter.

`factory.github.GitHubPublisher` and CLI `publish` execute reviewed draft creation:

```sh
python3 -m factory publish --repo OWNER/REPO --issue NUMBER \
  --base BASE --base-sha EXPECTED_SHA --slices /path/reviewed-slices.json \
  --slice-id SLICE --state-dir /private/publication-state \
  --gh /approved/gh --execute
```

The publisher pins all GitHub calls to github.com (ignoring ambient GH_HOST),
canonicalizes repository identity for retry lanes, and blocks new creation for a
closed issue. It reruns exact-revision review planning, reads the selected issue,
checks existing PRs, exact remote branch SHA and expected base SHA (a dependent
slice uses its predecessor's approved SHA). It creates only a draft, then reads
back and rechecks head/base. There is no push/fork/merge/auto-merge operation.
Ambiguous, closed, non-draft, cross-repo or mismatched existing PRs block. A private
locked SQLite journal records an unknown attempt **before** create, keyed by repo
and head branch so changing SHA/base/issue cannot bypass it. Unknown outcomes only
reconcile by verified readback; they never blindly create again. An unresolved
unknown requires operator investigation, not deleting the journal. A concurrent
remote update between reads and create cannot be atomically excluded by gh;
post-create mismatch is therefore reported unknown, never accepted as verified.

Review/test receipt authenticity remains a trusted Warden integration contract.
Do not source approval receipts from an implementor's claim or issue content.
Already-published branch/PR state must be reconciled before changing scope. No real
issue, PR, model launch or credential mutation was performed during fixture tests.

## Pre-publication check coverage

`python3 -m factory.checks --repo /path/to/worktree --head FULL_SHA` emits a
content-hashed inventory from Git objects at that commit. Discovery is read-only
and needs no YAML dependency: the complete workflow text is the obligation,
so nested/multiline commands, matrix/default context and `uses` are not lost.
All package scripts are included (non-check scripts need an explicit exclusion).
Follow remote/reusable actions and tool config references during independent
review; discovery does not claim to resolve the transitive CI graph automatically.

Each slice now additionally requires:

```json
{
  "check_coverage": {
    "manifest": {"version": 1, "head_sha": "FULL_SHA", "units": [], "digest": "FROM_DISCOVERY"},
    "reviewer": "warden",
    "coverage": {
      ".github/workflows/lint.yml": {"disposition": "required", "runs": ["knip", "knip-production"]},
      "package.json#scripts/dev": {"disposition": "not_applicable", "reason": "Interactive development server, not a CI check"}
    },
    "runs": {
      "knip": {"head_sha": "FULL_SHA", "exit_code": 0, "environment": "approved guest toolchain and dependencies", "command": "pnpm run lint:unused", "proof": "local immutable result reference"},
      "knip-production": {"head_sha": "FULL_SHA", "exit_code": 0, "environment": "approved guest toolchain and dependencies", "command": "pnpm run lint:unused:production", "proof": "local immutable result reference"}
    }
  }
}
```

Use the actual manifest, never this illustrative empty one. Every inventory ID
must have a disposition; required entries need successful, current-head command
proof. Missing, stale, failed, unresolved or entirely waived coverage blocks
publication. No repository command is automatically executed. Like existing
review/test receipts, evidence authentication is the trusted caller's job; it
must regenerate the manifest and verify receipts, not trust an implementor's
claim. Cheap pre-commit checks supplement, not replace, this publication gate.

The executing `publish` CLI also requires `--check-repository /canonical/worktree`.
It regenerates the exact-head inventory from local Git objects and compares the
entire manifest before any GitHub write. Omitting a workflow from a self-consistent
receipt therefore blocks publication. Review/run proof authenticity remains the
trusted caller's responsibility. This is intentionally a breaking gate for old
receipts: rediscover/review coverage rather than adding a bypass flag.

## Lookout: open-PR CI watch

```sh
python3 -m factory.lookout --repo owner/product --pr 123 \
  --gh /absolute/path/to/gh --state /absolute/ignored/lookout.sqlite3 \
  --expected-check Knip --watch --interval 300
```

Use explicitly assigned PRs and real check names discovered from their workflows.
The deterministic observer double-reads the current head, emits changed JSON
reports, and stops on merge/closure. It never comments, changes CI, repairs code,
or merges. Captain must consume/acknowledge its handoffs and route failures to the
slice owner and systemic gaps to Cleric. Watch all PRs in a stack individually.
Unknown, missing, stale and unavailable evidence holds delivery; observed green
is not proof that every required check or independent review is satisfied.

Reports include same-repository GitHub CI evidence links when supplied by GitHub.
The full sanitized latest report is saved before stdout emission, so a consumer
can recover after a crash without issuing another request:

```sh
python3 -m factory.lookout --repo owner/product --pr 123 \
  --state /absolute/ignored/lookout.sqlite3 --latest
```

This recovery is non-consuming and network-free. Durable observation is not an
acknowledged handoff: Captain/automation still owns delivery and repair dispatch.

For durable Captain handoffs, run `python3 -m factory.lookout_service` with the
same explicit repo/PR plus `--state-dir`, `--rig /absolute/clean/rig`,
`--source lookout-observer@<rig>` and `--destination bridge-captain@<rig>`.
It polls every 300 seconds, holds a lifetime single-instance lock, and sends
changed failures or incomplete evidence through idempotent native queue items
with `--no-nudge`. It never starts model work. Immutable delivery payloads and
retry IDs survive interruption; `delivery-status.json` records observation and
queue submission state. Submitted does not mean acknowledged. Captain or the
operator backstop must consume pending notifications. Supervise this process
with the host's existing service manager; a service process is distinct from a
live model seat. It stops on PR closure/merge. Keep credentials out of its unit.

Once Captain's native quota admission is verified, enable the Lookout service's
`--wake-captain` option. It uses ordinary OpenRig queue-create nudges and a
`ci-triage` gate tag; native OpenRig owns delivery, idle-gate wake, ownership and
handoff. It is not a second message bus or a custom dispatcher. Default remains
cold for installations without a verified metered Captain. Already submitted
observations are not duplicated or resent merely because wake is enabled.
After a reported problem, current-head green recovery is also handed to Captain,
so dependent work can resume on evidence rather than an external manual check.
