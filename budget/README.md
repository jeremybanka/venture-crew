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

### Native Claude quota observer (pinned 2.1.321)

`python -m budget observe-claude --once --print-only` makes only native
`initialize` and `get_usage` control requests, never a model prompt. The account
binding is a hash of the same process's account email and organization; raw
identity and credentials are never emitted. A native full account login is
required. The existing inference-only setup token does not qualify.

Static inspection of 2.1.321 proves that usage snapshots are account-UUID bound
and accepted for less than 60 seconds before an endpoint fetch is required.
The observer therefore dates samples at request start minus 60 seconds. It
requires the structured `limits` and `model_scoped` projections; native seeded
fallback after fetch failure strips `limits`, so that response is rejected.
All ordinary and model-specific windows are enforced conservatively. Paid extra
usage is never treated as allowance. An inactive zero-used five-hour window has
no reset until activity begins; it is explicitly marked inactive. Unknown
structured limits, missing account identity, unsupported native versions, errors,
and observer shutdown fail closed. The protocol is experimental and must be
reverified before upgrading the pinned native version.

The authorized Claude opening policy uses a 40% reserve for `seven_day`, with
`five_hour` availability stopping only at zero. Invoke the observer with
`--observe-only-window model:fable` to retain Fable quota in
`informational_windows` without blocking Opus on that model-specific limit.
Fable exhaustion still makes Fable unavailable: the dispatcher must consult that
informational window before launching Fable and use the seat's allowed fallback.
No other model window may be exempted by this flag. Any unconfigured enforced
window fails observation closed and requires operator reconciliation.

Structured native limits must exactly agree with projected percentages and reset
times, with no duplicates or missing projections. Credential-file metadata is
checked across initialize and usage; an allowlisted account identity fingerprint (account UUID, organization UUID,
email address) is checked across initialize and usage. Volatile configuration
counters and profile refresh timestamps are deliberately excluded. This detects
normal concurrent login/replacement without reading credential contents. It is
not protection against a hostile local process restoring identity and credential metadata (ABA), nor a
claim that native credentials are immutable. Native accountUuid cache validation
provides the separate quota/account association. The controller still rejects
an observed account hash different from its configured account.

Reset precision: pinned native `Wor` preserves successful endpoint ISO reset
strings; the header parser uses `Math.round` seconds. Successful endpoint samples
were observed to jitter by fractions of a second around the same boundary (for
example 05:59:59.555658 and 06:00:00.140253). After exact structured/projection
validation, the collector canonicalizes to nearest second **minus one second**.
That preserves whole-window reset detection while expiring evidence no later
than the raw reset. Original numeric timestamps remain in top-level `raw_reset_times` in
collector output for diagnosis, never as extra keys within normalized windows. This is a precision assumption specific to the
verified native version, not permission to ignore arbitrary reset changes.

A native seeded/incomplete fallback gets at most one retry after two seconds.
The fallback itself is never accepted; retry evidence retains the first attempt's
conservative freshness timestamp. Existing controller evidence continues aging
and no gate is re-armed automatically. Account, version, and consistency failures
are not retried; a second fallback fails closed normally.


The long-running observer now retains one zero-model native process. Native
2.1.321 keeps bearer-keyed endpoint failure backoff in process memory (403/429:
Retry-After or default 300 seconds, capped at 3600). Restarting on each sample or
seeded retry discarded that traffic protection. Seeded failures retain the
process, but still invalidate/latch the controller exactly as before. No stale
quota is accepted, no automatic rearm occurs, and freshness continues aging.
Account identity and credential metadata are checked against the original native
initialization on every sample. Other failures dispose of the process. This
reduces unnecessary endpoint traffic; it does not guarantee endpoint recovery.

### Last-successful Claude signal (Jeremy's one-hour policy)

This supersedes the earlier immediate-invalidation / two-second-retry policy.
Use `python -m budget set-freshness claude --seconds 3600` once with no active
Claude permits. This preserves the account-bound successful observation but
leaves the lane disarmed; it never reopens an earlier stop. Codex is unchanged.

The Claude observer defaults to a five-minute refresh interval (`--interval 300`,
allowed 300–1800 seconds). Failed attempts back off to 5, 10, 20, then 30 minutes;
the persistent native client's own Retry-After remains in force. There is no
immediate retry. A seeded fallback or transport timeout never becomes new quota.
Instead the controller keeps the last validated successful sample at its original
`observed_at`, for at most 3600 seconds. Normalization's conservative 60-second
cache-age allowance remains, so acceptance never extends beyond the proven age.

The private sample file retains the last success, including model allowances;
refresh errors go to a separate `.refresh.json` record. Neither failure nor
observer exit rewrites the successful timestamp. Controller state is durable,
and admission/routing check its age and original reset deadlines. A signal older
than an hour fails closed. Expired/reset windows, observed floors, actual provider
denials, identity changes and schema failures still stop immediately when known.
Local account/credential checks run every 15 seconds between network refreshes.
No quota is invented, no reset is guessed, and no failure or later success
implicitly rearms a latched lane.

Limit: cached usage is a last-known measurement, not a real-time guarantee. Usage
may cross a reserve between successful refreshes; actual provider quota errors
still stop execution. Model-specific Fable exhaustion is not a provider-wide
reserve and remains governed by the existing model routing checks.

### Rig-owned Claude hook plugins

`budget.claude_plugin.build` / `write_plugin` prepare a local plugin artifact
containing the existing native quota hooks. Declare its path relative to the rig
source root in an OpenRig Claude member's `plugin_dirs` (absolute paths are rejected).
Pinned OpenRig 0.7.3 projects a private
seat copy and supplies native `--plugin-dir`; quota settings need not be installed
in guest home or any product checkout. This is launch-local configuration, not a
new message bus. Inter-agent work, notifications and wakes remain native OpenRig
queue/handoff/watchdog responsibilities.

The artifact is bound to an exact native session name, inert for other sessions,
and changes no permission mode or allowlist. It uses the same account-bound
controller, native prompt identity, 40/40 opening and fail-closed admission as the
existing adapter. Preparation is not activation: verify the actual launch loads
the plugin and denies a closed lane before admitting model work. Preserve native
workspace trust and request any required confirmation rather than bypassing it.
The helper refuses to overwrite an existing artifact. Rematerialization/handover
must preserve the plugin in the recorded native launch configuration; a copied
file alone is not proof that a session loads it.
