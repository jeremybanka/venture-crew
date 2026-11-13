# Venture Crew

A VM-owned OpenRig crew serving Wayforge's development repositories. The deployment checkout lives **inside the Wayforge VM**; `/home/crew/venture-crew` below is an example path. It is separate from
both dotfiles and the product repo `/home/crew/project`. This repository owns
the canonical crew, model policy, budgets, hygiene and issue-to-PR workflow.
Dotfiles owns only VM/clean-runtime provisioning; its integration points here
rather than duplicating the workflow plan.

## Crew

| Seat | Job |
| --- | --- |
| bridge.commander | Human liaison, original intent and corrections |
| bridge.captain | Admission, allocation, sequencing and continuations |
| bridge.sky-command | Architecture and bounded planning |
| work.strider1 / work.strider2 | Two standard implementors, features and repairs |
| work.lancer | “Parodies” of existing code from a specified stance |
| work.pyro | Simplification with net-negative deltas |
| inquiry.witch | Bounded experiments and prototypes |
| inquiry.inquisitor | Major-bug and cross-system root-cause investigation |
| inquiry.hierophant | Questions through human judgment and reconciled continuation |
| care.cleric | Developer experience and prevention of workflow failures |
| care.chronicler | Documentation and useful decision records |
| care.deckhand | Safe task-linked worktree hygiene |
| refinery.warden | Independent exact-revision review and serialized integration |

Knight and Ranger are not seats. Striders own ordinary fixes and hardening.
Warden's integration remit does not authorize remote publication or deployment.
Runtime choices are configuration, not identities; two Striders do not imply two
simultaneous admitted turns. Roles are available responsibilities, not 14
always-spending sessions.

## What is implemented

- Native RigSpec and AgentSpec with all 14 seats, role guidance and handoff edges.
- [Culture](CULTURE.md), [SOP](SOP.md), and [guest context](CONTEXT.md).
- [Independent Claude and Codex budget controllers](budget/README.md): separate
  identities, windows, remaining-percentage floors, permits, freshness, reset
  handling and audit. No cross-provider borrowing or automatic refill spending.
- [Deckhand tooling](hygiene/README.md): explicit task registration, pause locks,
  inventory, cleanup holds and conservative verified retirement. No dirty expiry.
- [Ordered model routing](routing/README.md), with exact preferences in
  [model-preferences.json](model-preferences.json), verified model IDs in
  [model-catalog.json](model-catalog.json), and high effort by default for every seat.
- [Selected GitHub issue workflow](factory/README.md): intake, cold queue execution,
  bounded native fresh-launch adapter, and reviewed draft-PR publication/retry.
  Execution is opt-in and fixture-tested, not a running factory.
- A guest project inventory in `projects.local.json` (see `projects.example.json`), source checks and fixture tests.

## Status and use

**Configured repository, not an active crew.** See [SETUP.md](SETUP.md) for exactly
what was verified and the unresolved activation boundaries. Both budgets start
closed. No first workload, per-opening reserve instruction or permission expansion is selected by this checkout.

From a clean Wayforge shell:

```sh
cd /home/crew/venture-crew
python3 scripts/check.py
python3 -m budget status codex
python3 -m budget status claude
python3 hygiene/deckhand.py inventory
npm run validate
```

The npm command runs through the existing dirty proxy. That validates source;
it must not be used to bypass the clean agent/credential boundary to run a daemon.
No secrets or runtime queues belong in this repository. Use native OpenRig task
records and the shared runtime-state location documented by each tool.

## Provenance

This public source snapshot preserves the implementation from guest commit `ca4d861` with machine-specific inventory and paths removed. Original development history remains private on the guest.

Crew design follows Jeremy's November 12–13 instructions. The original sketch
was on dotfiles branch `plan/wayforge-expedition` at `e17eb49`; that is historical
provenance, not the current canonical plan. Warden includes the broader CS16ND refinery
remit following the subsequent setup instruction. Hygiene retains the spirit of
“Git worktree cleanup standards” but explicitly protects unique uncommitted work.
CS16ND was inspected read-only and has not been changed.

## Current model order

All seats default to **high** effort. First eligible entry wins, using that
provider's independent gate. A closed provider does not block the other.

| Seat | Order |
| --- | --- |
| Commander | Sol → Opus |
| Captain | Opus → Sol |
| Sky Command | Fable 5.2 → Sol |
| Hierophant | Opus → Sol |
| Strider 1 | Sol → Opus |
| Strider 2 | Opus → Sol |
| Lancer | Sol → Opus |
| Witch | Opus → Sol |
| Pyro | Opus → Sol |
| Chronicler | Fable 5.2 → Sol |
| Warden | Opus → Sol |
| Deckhand | Sol → Opus |
| Cleric | Sol → Opus |
| Inquisitor | Sol → Opus |

Unknown model IDs are ineligible, never guessed. A model-order change does not
activate a provider or override native permission/handover gates.
