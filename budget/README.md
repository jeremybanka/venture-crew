# Independent provider budgets

This package observes quota and grants bounded-turn permits. Codex and Claude have
separate account pins, required windows, remaining-percentage floors, arming,
concurrency, observations and permits in one transactional SQLite database. A
reset, refill, pause or invalid sample for one provider does not transfer capacity
or reopen the other. Never add their percentages together. Ordered eligible-model fallback uses its own provider gate, not borrowed quota.

## Safe initial state

Both providers begin unconfigured and closed. The user has requested independent
budgets with reserves chosen per factory opening, not permanent installation
floors. Account pins, applicable windows and concurrency remain setup policy.
Neither a first workload nor a live opening is inferred from an illustrative
“50/40” example or Counter-Strike's historical settings.
Configuration does not arm admission. Only a fresh, account-bound reading covering
all configured windows, followed by explicit operator arming, can do that.

From the repo root:

```sh
python3 -m unittest discover -s budget -t . -v
python3 -m budget status codex
python3 -m budget status claude
python3 -m budget pause codex
python3 -m budget pause claude
```

The default state path is `~/.local/state/wayforge-rig/budget.sqlite3`; set
`WAYFORGE_BUDGET_DB` or pass `--db` before the subcommand to change it. Keep it out
of Git and share it between all rig seats/worktrees. The audit table records
sanitized metadata, not prompts or credentials. Do not create one budget per seat.

## Codex observation without model calls

`python3 -m budget observe-codex --once --print-only` starts a native app-server,
reads account identity and quota, verifies identity did not change during the
read, prints sanitized windows and an account hash, then exits. It does not read
credential files, create model threads or refresh credentials explicitly.

For initial binding, configure using the observed account hash and **all
applicable quota windows**. The placeholders below show low-level provider
configuration; factory operation uses `open-factory`, not individual `arm`. For example, the following placeholders are to be
replaced by the operator's choices, not run literally or interpreted as a grant:

```sh
python3 -m budget configure codex --account ACCOUNT_HASH --floors '{"codex:300": FLOOR, "codex:10080": FLOOR}' --max-active COUNT
python3 -m budget observe-codex --interval 60
# Once an eligible provider and its activation gates are ready, use open-factory.
# The CLI does not permit legacy arm; use explicit per-provider opening outcomes.
```

The persistent observer stores newer samples, invalidates on collector failure
and on shutdown, and never calls a model to measure balance. Malformed or exhausted extra buckets also close admission. Native optional
primary/secondary windows may be absent or null; a non-null malformed window or
a bucket with no usable windows is rejected. A malformed bucket map never falls
back to a valid-looking single bucket. Required windows must be explicitly listed;
no missing five-hour/weekly allowance is treated as unlimited. A changed reset or
increased remaining allowance disarms that provider and requires review/rearming.

## Claude telemetry and the unresolved binding boundary

The installed OpenRig Claude status-line adapter carries five-hour and seven-day
remaining quota but cannot prove those readings belong to the daemon's current
login. A status-line redraw/receipt time does not prove a new provider fetch.
Its alternative credential-labelled probe invokes Haiku. This package **does not
run that probe**, read credentials, or assume an organization API balance equals
personal subscription quota.

`python3 -m budget claude-statusline --file payload.json` sanitizes the native
status-line JSON for inspection. It labels account binding and freshness as
unproven and does not feed it into admission. Preserve it as telemetry; do not
mark it fresh merely because a timer reread the same file.

The common `observe claude --file sample.json` entry point supports a future
trusted collector with a documented, verified identity/freshness chain. It uses
the same controller/tests as Codex. Its sample contract is:

```json
{
  "provider": "claude",
  "account_id": "opaque-account-fingerprint",
  "account_bound": true,
  "freshness_proven": true,
  "observed_at": 1900000000,
  "usage_allowed": true,
  "source": "verified-collector-name",
  "windows": {
    "five_hour": {"remaining_percent": 80, "resets_at": 1900010000},
    "seven_day": {"remaining_percent": 60, "resets_at": 1900500000}
  }
}
```

The boolean evidence fields are a trusted-adapter contract, not cryptographic
proof. Never set them by operator guesswork or join an independent login query to
an anonymous cached reading. Automated Claude admission remains closed until a
collector can satisfy this contract. Reading the existing adapter is not live
provider verification.

### Native contract investigation (Claude 2.1.321)

The installed binary and [official hooks reference](https://code.claude.com/docs/en/hooks)
agree that common `prompt_id` correlates the current prompt with subsequent
hook events. [Status-line documentation](https://code.claude.com/docs/en/statusline)
exposes utilization/reset values after an API response, but not an account-bound
provider observation timestamp. Timer redraws do not establish fresh quota.
The binary also contains an experimental structured `/usage` control schema,
including subscription rate windows and cached-data distinctions. Its presence
alone establishes neither a supported no-model collector invocation nor an
atomic identity/freshness chain. No such collector has been verified here.
No credentials were read, native model calls made, or hook settings installed.
The remaining quota blocker is trustworthy observation, not lack of a native
prompt identifier. Keep automated Claude admission closed.

## Enforcement and lifecycle

`admit PROVIDER --seat SEAT --session SESSION --turn TURN` returns a permit or
nonzero denial. `release` requires the matching provider, session and exact turn. Session-wide
recovery is a separate `reconcile-session` command requiring a written reason and
`--confirmed-stopped`; use it only after verifying that every covered turn has
ended. Ordinary completion never clears other turns in the session. Crashed turns keep their permits across restart; no TTL
silently releases a still-running model. Each seat can hold at most one active
permit across providers. Provider concurrency is enforced atomically.

`python3 -m budget.hook --provider PROVIDER --seat SEAT --event EVENT` is a
native-hook adapter for UserPromptSubmit, Stop, Interrupt, SessionStart,
PreCompact, PostCompact and PreToolUse. It requires native session **and turn**
identities rather than guessing from prompt hashes. A harness lacking a stable
turn identity stays blocked. For Claude 2.1.321, documented native `prompt_id`
is mapped to the canonical turn identity, scoped by `session_id`; missing
`prompt_id` is denied even if a `turn_id` appears. Subagent events cannot reuse
or release the main permit. This mapping is unit-tested, not end-to-end verified.
Claude Stop does not fire on user interrupt, and API failures use StopFailure.
Neither is inferred as successful completion: unhandled endings retain their
permit for explicit stopped-session reconciliation. Child-agent launches are denied
in covered tool paths; work must go through declared seats. Tool work also needs
an existing permit and fresh provider admission.

The hook does not install or trust itself. Generate review-only native settings
fragments (the target paths are reported in the output):

```sh
python3 -m budget.prepare_hooks --provider codex --seat crew.strider1 --root /home/crew/venture-crew --python /absolute/approved/python3 --db /home/crew/.local/state/wayforge-rig/budget.sqlite3
python3 -m budget.prepare_hooks --provider claude --seat crew.witch --root /home/crew/venture-crew --python /absolute/approved/python3 --db /home/crew/.local/state/wayforge-rig/budget.sqlite3
```

These commands print JSON and do not touch native settings. Review the
`fragment` field rather than installing the whole metadata envelope. Codex's
fragment includes explicit shell-failure denial. Claude's fragment is deliberately
an unconditional admission blockade, not a ready-to-run quota adapter, pending
native end-to-end lifecycle verification and reliable identity-bound fresh telemetry.
The Claude prompt/tool blockades use `onFailure: "block"` (native 2.1.295+)
so timeout/process failure must not silently continue. It does not invoke Claude.
Do not replace this blockade with the generic hook merely to make it launch.

Before activation, install the reviewed Codex fragment in the
appropriate project/seat hook config while preserving unrelated hooks, add a
shell failure fallback returning explicit denial JSON, and verify native hook
discovery/trust and real blocking behavior for the installed harness. A parser
unit test is **not** proof of native enforcement. Do not launch autonomous seats
with unverified or omitted hooks and call them budget-controlled.

Hooks govern bounded phases, not every token. In-flight requests and other chats
can overshoot a floor. They are not a hostile-code sandbox, account-wide billing
cap or protection against an agent deliberately editing its controller. Native
hook infrastructure can skip/fail open outside this package's process boundary.
Compaction, resumed turns, aliases, hosted tools and provider switching require
end-to-end validation before claiming comprehensive coverage.

## Verification

The unit suite covers independent providers, reset/refill, stale/future/expired
samples, missing windows, unknown identity, replay after rejection, concurrency,
restart/stranded permits, session/seat collisions, closed-turn replay, status-line
limitations, sanitized native Codex parsing and hook denials. No test uses a model
or real account data. Source references are the CS16ND observer/controller and
installed OpenRig 0.7.3 Claude adapters; the native Codex client is adapted from
Jeremy's CS16ND observer without changing that source.

## Per-opening reserves and factory lifecycle

The requested interface is “open the factory with a floor of 50/40”: Codex 50%
and Claude 40% **remaining**, applied to all configured applicable windows of
each provider. A new explicit opening may choose a different pair. Keep account
pins, required windows and concurrency; never reconfigure identity to reopen.

The budget CLI primitive is:

```sh
python3 -m budget open-factory --floors 50/40 --reason 'Actual owner opening instruction and queue scope reference'
```

This is not a launcher, permission grant, hook installer or telemetry verifier.
Do not invoke it before the relevant SETUP.md activation gates are satisfied.
The opening evaluates each provider independently and reports which armed and
which remained closed. Missing/unproven Claude quota need not block valid Codex.
The pair is illustrative here, not authorization to arm the live database. Any
outstanding permit prevents a new opening; reconcile only verified ended turns.

Floor/reset/refill or invalid/stale telemetry latches only that provider closed.
The other may serve a seat's next eligible model preference. An increased balance
does not reopen authority. A later explicit opening requires fresh evidence.
In-flight work retains permits; pause cannot cancel already-spent tokens. Exact
seat completion and a durable checkpoint precede model/runtime handover.

Captain drives the authorized native queue under the opening. Warden independently
reviews exact revisions and prepares a dependent PR stack targeting the authorized
base then predecessor branches. Jeremy merges. The budget primitive does not
implement that dispatcher or publish PRs; see SOP.md for handoff and pause records.

Production CLI/hook admission requires a factory opening record; the old single-provider
`arm` CLI is disabled. Internal independent controller APIs remain only for
fixtures and are not a security boundary against arbitrary Python execution.
