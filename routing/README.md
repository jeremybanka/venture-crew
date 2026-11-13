# Budget-aware route planner

This is a read-only decision tool, not a launcher or active scheduling bridge.
It does not activate a crew, rewrite manifests, stop sessions, obtain permits,
release permits, inspect credentials, or call providers. Missing evidence blocks.

```sh
python3 -m routing --seat work.strider1 \
  --db "$HOME/.local/state/wayforge-rig/budget.sqlite3" \
  --readiness /path/to/verified-readiness.json \
  --session-evidence /path/to/verified-session-evidence.json
```

Defaults load repository-root `model-preferences.json` and `model-catalog.json`;
`--preferences` and `--catalog` override them. Required schemas:

- Preferences: `{"preferences":{"work.strider1":["Sol","Opus"]}}`.
  Order is preserved. No default is inferred for an absent seat, including Inquisitor.
- Catalog: `{"models":{"Sol":{"verified":true,"model":"EXACT_NATIVE_ID","provider":"codex","runtime":"codex"}}}`.
  This is a schema example, not model availability evidence. An empty `models`
  object safely blocks. The planner never expands aliases or verifies the catalog
  itself. Allowed provider/runtime pairs are `codex`/`codex` and `claude`/`claude-code`.
- Readiness: `{"codex":false,"claude-code":false}`. Set literal `true` only on
  independently verified native readiness. Do not infer it from an installed binary.
- New session evidence: `{"no_existing_session":true}`. This is an explicit caller
  assertion, not an implicit default. Omitted or contradictory evidence blocks.
- Existing session evidence: `{"current":{"session_id":"old-session","model":"EXACT_NATIVE_ID","provider":"codex","runtime":"codex"}}`.
  When the chosen model/provider/runtime changes, also supply
  `"handover":{"session_id":"old-session","stopped":true,"checkpoint":{"reference":"durable-artifact-reference","durable":true}}`.
  Only assert this after verifying the old session stopped and the checkpoint
  exists durably. The planner validates evidence shape, not the artifact contents.

Both providers' status must be readable, including active permits. Any active
permit for the same seat yields `wait`, even if another provider could accept work.
For each preference, the planner checks its exact verified catalog entry, provider
admission, and harness readiness, recording skipped reasons. A changed route without
handover evidence returns `handover_required`; no candidate returns `blocked`.

Output `selected` and `ready_to_launch:true` mean eligible **at the snapshot**, not
permission to execute. Status reads are not a multi-provider atomic launch
transaction. The missing native bridge must recheck current session state, catalog,
harness readiness and budget, atomically acquire a permit, bind exact native turn
identity, and wire verified enforcement hooks before any launch. Stop/reconcile
and checkpoint validation also remain bridge responsibilities. Do not use this
command as a shell launcher. Exit codes: 0 selected, 2 blocked/wait/handover required,
1 invalid input/unavailable state. Controller access is SQLite read-only and never
initializes missing state.

The crew's default effort is `high` in both the manifest and model policy. Future
explicit seat overrides take precedence. A native bridge must carry the resolved
effort when changing model/runtime; the planner does not execute that setting.
Verified Sol supports high, and installed Claude accepts the high effort flag.
Still verify each newly resolved model's supported effort before launch.

Fable 5.2 additionally needs `--model-snapshot` (default
`.state/claude-latest.json` under the rig checkout). Its input is the collector's
persisted `{"accepted":true,"sample":{...}}` record, not a bare sample.
Rejected/missing records fail closed for Fable only. The sample's account,
observation time, source and enforced windows must match the controller's latest
accepted observation, and remain fresh. `informational_windows["model:fable"]`
must show valid, unexpired availability above zero. This is not a 40% model
reserve, and never blocks Opus. Native dispatch preflight supplies this same
record as `model_snapshot` and revalidates it before launch; a route snapshot is
still not an admission permit.
