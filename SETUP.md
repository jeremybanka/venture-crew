# Installation and activation record

## Installed on Wayforge

The guest repository has a dedicated checkout separate from product repositories. Public examples use `/home/crew/venture-crew` as a placeholder; consult your local deployment for the actual path.
It was initialized on `main`. OpenRig `@openrig/cli` 0.7.3 is a pinned local dependency,
with an npm lockfile, installed using the existing Scrubs dirty proxy. Dependency
install scripts were disabled. Node 26.13.1 uses the guest's existing mise install.
No global tool installation, credential copy, native permission change, service
launch, remote publication or cleanup of user work was performed.

The host scratch directory used to assemble source is not the deployed location.
Wayforge was Running and reachable through `limactl shell wayforge`. Prior
sandbox-limited Lima status checks reported Broken because boot-session sysctl
access failed; the elevated read-only check established actual Running status.
Check guest disk capacity before activation. Preserve held work and avoid launching many builds simultaneously.

## Validation

- `npm run validate`: imports the pinned OpenRig 0.7.3 authoritative RigSpec and
  AgentSpec validators without starting a daemon. Both schemas pass.
- Native CLI `spec validate rig.yaml` passes. Native `agent validate` requires a
  running daemon, so its CLI execution is not claimed; the identical exported
  AgentSpec validator is exercised by `npm run validate`.
- `python3 scripts/check.py`: source/roster/edge/startup consistency plus isolated
  budget and hygiene fixture tests. No real worktrees are retired by tests.
- No model calls, end-to-end native hook enforcement, live seat launch or
  real-work integration has been verified by these tests.

## Remaining activation requirements

1. **Clean runtime boundary.** Guest npm/Node runs within dirty space and cannot
   launch the clean Claude/Codex wrappers or access their credentials. Do not run
   the npm binary outside its sandbox or expose clean credential surfaces to it.
   Dotfiles draft PR #1171 now supplies an opt-in, immutable clean Nix OpenRig
   0.7.3 package. Its build, CLI, SQLite and this rig spec were verified. The
   module remains disabled and no system switch occurred. Review and explicitly
   activate that integration before starting a daemon; the dirty npm copy is
   not a fallback across this boundary.
2. **Provider identity and source.** Codex has a no-model native observer. Claude
   status-line data is available for observation, but its identity/freshness chain
   is not yet proven. Automated Claude admission must remain closed until a
   verified collector is available. An API organization cost balance is not the
   personal subscription quota. No automatic Haiku probe is used.
3. **Explicit opening.** Configure independent account pins, required allowance
   windows and concurrency, then choose temporary remaining-percent floors for
   each factory opening (Codex/Claude, for example 50/40). Both providers begin
   disarmed. Do not transplant Counter-Strike's historical floor or treat a reset
   as permission. Eligible fallback follows the ordered seat policy; native handover still needs verification.
4. **Native hooks and permissions.** Review the generated project-scoped native
   hook fragments and install/verify them for each actual seat workspace while
   preserving unrelated native settings. Verify stable session/turn identities,
   startup, prompt, stop, interrupt, compaction and covered child-launch paths.
   The installed Claude 2.1.321 contract supplies a native `prompt_id` to
   correlate a prompt and its subsequent events; map that exact value rather
   than guessing a turn ID. Native end-to-end verification is still required. Keep the existing permission posture. Native
   hook discovery/trust and denial behavior need actual end-to-end verification.
5. **Bounded first activation.** After these gates, launch a minimal implementation
   and independent-review flow before expanding. Do not launch all 15 seats merely
   because the topology validates. Supply a real task, project, acceptance proof
   and publication boundary. Verify cleanup-hold behavior as well as success.

Persistent quota collection and cleanup timers are not currently running. There
is no claim that this source alone enforces an account-wide billing cap or blocks
hostile code. Models already in flight and unrelated sessions can overshoot a
remaining-percent floor. See each tool's README for its exact boundaries.

## One-shot provider check

A clean guest-shell one-shot `observe-codex --once --print-only` completed on
13 November 2026. The native server returned an identified, included-usage weekly
window and allowed usage. No model conversation was created. This verifies the
Codex read path, not ongoing observation or harness admission. Both provider
controllers remained unconfigured/disarmed with zero active permits afterward.

## Follow-up native discovery check

Native Codex 0.167.1 protocol schemas and `hooks/list` were inspected without
creating a model thread. The hook feature is enabled, but an isolated, untrusted
scratch project containing the generated seven-event fragment returned zero
hooks (no parse warnings/errors). No project trust or hook trust was granted.
This is evidence that file preparation alone is insufficient, not a passing
enforcement test. Actual workspace discovery/trust must be explicitly resolved
before activation. The existing CS16ND native proof is useful precedent, not a
substitute for verification of this installation.

## Requested operating model

Per-opening floors replace the earlier assumption of fixed configured reserves.
The target is authorized queued work → independent Warden review → stacked PRs
for Jeremy to merge, stopping at a floor or reset. This clarification does not
activate the factory or authorize publication for unspecified work. SOP.md records
provider-local pauses, ordered eligible-model fallback and retained-work behavior.

## Ordered-model integration limit

Provider-local budgeting and a tested routing planner implement the decision layer.
They do not execute native model/runtime handover. Exact catalog IDs must be verified;
unknown preferences remain blocked rather than being converted to guessed IDs.
Existing hooks/Claude quota/clean-runtime gates remain in force.

## Default effort

Jeremy selected `high` for every crew seat. All 14 manifest members now explicitly
set effort high; there were no existing seat overrides to replace. Model policy
records the same default and an empty explicit override map for future changes.
OpenRig 0.7.3 maps effort to Codex `model_reasoning_effort` and Claude `--effort`.
Wayforge native Codex model/list confirms gpt-6.1-sol supports high; Claude
2.1.321 --help lists high among accepted effort levels. Unknown model identities
still require their own compatibility proof before use. No session was launched
or rebuilt to apply this setting.

## GitHub issue workflow implementation

`factory/` adds strict selected-issue intake, stable native queue retry identity,
a cold enqueue subprocess adapter, budget-aware cold handoff planning, and
exact-revision independently reviewed draft-PR stack planning. See its README
for executable versus planned boundaries. No selected repo/issue, active queue
connection, dispatcher launch or GitHub publication has occurred. `projects.local.json` (see `projects.example.json`)
is inventory, not native workspace registration or authorization.

## Execution adapter follow-up

Issue workflow now includes explicit executable GitHub-fetch/cold-enqueue and
draft-publication/retry adapters, plus a bounded native fresh-launch executor.
Tests inject mock runners, not real tasks. Native active launch requires a trusted
live evidence collector and verified hooks/automatic-startup admission; that
collector is not installed. No runtime migration or actual task/PR was executed.
Publication verifies base/head and reconciles unknown results without duplicate
create. The existing clean-runtime/Claude-quota/authorization gates still apply.

## Native activation findings (2026-11-13)

Bounded activation now has actual Codex evidence, not just mocked fixtures:

- Codex0.167.1 linked Git worktrees inherit hook definitions from the root
  checkout. Worktree-local inline/JSON hooks are deliberately replaced. The owner
  requires canonical guest repositories, so use explicitly approved root-stored
  dispatchers scoped to the task worktree and inert for unrelated sessions.
- Native hook discovery found all seven reviewed hooks in that task clone.
  The diagnostic clone was retired from active work without deleting its draft;
  product edits were transferred byte-for-byte into the canonical repository task
  worktree. Exact definition hashes were trusted through the native configuration API;
  existing workspace-write and on-request permissions were preserved.
- A closed opening stopped SessionStart before model output. A bounded admitted
  smoke turn exercised SessionStart, UserPromptSubmit and Stop, released its exact
  native permit, and returned the expected response. Real planning tool calls
  subsequently exercised PreToolUse under a live permit.
- The first cold materialized seat starts through `rig launch RIG LOGICAL_SEAT`,
  not the fresh-occupant command. `--plan` checks restore selection and does not
  preview pristine first starts. The current `seat set-cwd` requires startup
  context absent before first launch. Materialize the intended task cwd up front;
  do not edit OpenRig's database or launch the entire crew as a workaround.
- A bounded task cohort launched one Sol/high planning seat, produced a durable
  plan and handoff, released its permit, then launched Strider implementation.
  This is not proof of automatic whole-factory dispatch or completed PR delivery.

The live Claude path requires full native account login, not inference-only
setup-token authentication. The pinned no-model collector and explicit inactive
allowance representation are covered by deterministic tests. Current requested
policy separates weekly reserve from short-window/model availability: Claude's
weekly reserve follows the per-opening value; its five-hour allowance stops at
zero remaining; Fable-specific exhaustion affects Fable eligibility rather than
closing Opus. A provider's actual rate-limit rejection must still be honored.
See budget/README.md for the collector's bounded-age evidence contract and
version-specific limitations. On 2026-11-13 the task-scoped Claude hook was tested
closed (zero model turns/cost) and admitted with Opus 5.5/high (one bounded reply;
the exact native prompt permit was released). This proves that tested lifecycle,
not sustained provider health or completion of any work item. Recheck current
observer freshness and gate state before claiming the lane is running.

The native workspace sandbox initially blocked Scrubs' shared payload-cache
initialization. The dotfiles launcher now supports an exact-worktree
`SCRUBS_DIRTY_CACHE_ROOT="$PWD/.scrubs-dirty-cache"` option. Native workspace
sandbox probes passed for Node and pnpm with this option, preserving all Scrubs
namespaces and native permissions. Keep the cache ignored and task-owned; do not
make the shared home writable or execute dirty binaries directly to work around
launcher failures.
