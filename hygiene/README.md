# Deckhand: task-owned worktree hygiene

Python 3 standard library and Git only. The ledger lives outside source control at
`~/.local/state/wayforge-rig/hygiene`; override with `--state PATH` or
`WAYFORGE_HYGIENE_STATE`. This is deterministic tooling for the Deckhand role,
not an autonomous agent, model loop, deletion timer, or substitute task queue.

## Lifecycle

Captain/worker creates a worktree in the project's ignored `.worktrees/` directory,
using its queue-task ID. Register it immediately, naming the owner and the
approved remote that will retain the result:

```sh
python3 hygiene/deckhand.py register --task TASK_ID --repo /home/crew/project \
  --tree /home/crew/project/.worktrees/TASK_ID --owner crew.strider-1 --remote origin
python3 hygiene/deckhand.py inventory
```

Registration is explicit: Deckhand never adopts arbitrary clones or trees found
on disk. Keep the queue task as the authority for intent and status; Captain must
reflect its lifecycle in this small worktree ownership ledger. It does not scrape
or invent a second queue. `inventory` reports registered trees only. It neither
reads network remotes nor removes anything.

Before pausing, wait for **all** processes/agents using the tree to stop. Pausing
locks the worktree with a task-specific reason. Resuming removes only a lock this
tool placed for this task, never someone else's lock:

```sh
python3 hygiene/deckhand.py set-state --task TASK_ID paused --confirm-inactive
python3 hygiene/deckhand.py set-state --task TASK_ID active
```

A completed or abandoned queue task requests retirement; it does not force it.
Push only to an authorized destination. Stop all worktree consumers, then:

```sh
python3 hygiene/deckhand.py set-state --task TASK_ID closed --confirm-inactive
python3 hygiene/deckhand.py retire --task TASK_ID --confirm-inactive
```

Use `abandoned` instead of `closed` for abandoned tasks. `--confirm-inactive` is an
operator assertion that every agent, shell, editor, build and background process
using the tree has stopped. The tool cannot reliably discover external processes
on every platform. The Captain must quiesce the tree and retain exclusive ownership
through retirement. Do not claim this flag provides OS-level process isolation.
A paused tree remains locked on closure; resume/unlock deliberately before closing
it if retirement is intended.

## Retirement proof and holds

Removal requires all of the following:

- Explicitly registered task in closed/abandoned state and inactive confirmation.
- Canonical nonsymlink primary checkout and a registered secondary worktree that
  is a direct child of its `.worktrees/` directory, sharing the expected Git store.
- No lock, missing/prunable state, tracked modifications, untracked **or ignored**
  files, hidden index flags, in-progress Git operation, or submodules.
- A live `git ls-remote --heads` result from the configured approved remote whose
  branch tip exactly equals the worktree HEAD. Local tracking refs are not proof.
- A repeated state and HEAD check after obtaining remote proof.

The exact-tip rule is intentionally conservative: a commit merely ancestral to a
remote branch is held for manual review. Failed authentication, network failure,
unpushed changes, uncertainty, or changed state produce a recorded cleanup hold
and exit status 2. No credential material is read or stored by Deckhand; Git uses
its configured authentication. Remote locations and their retention policy must
be approved by the owner. No automatic push or archive is attempted.

The final command is ordinary `git worktree remove`, **never `--force`**. The
branch is retained. Every success records the exact revision, remote branch refs,
and verification timestamp. Ledger writes are atomic and commands using this
ledger serialize with an advisory lock. These checks cannot prevent an unrelated
writer racing after the final check; quiescence/exclusive ownership is mandatory.
If a command is interrupted, inspect actual Git registration and disk state before
retrying. A missing tree is held rather than inferred to have been safely removed.

Seven-day idleness is a reminder to inventory, **not** permission to delete. Paused
or locked work is preserved. No expiry daemon is installed here. Arbitrary full
clones, primary checkouts, caches outside a registered tree, and human repositories
are never sweep targets. Scratch policy belongs in the rig's SOP; ignored files
are not assumed disposable by this tool. A cleanup hold stays owned even when the
substantive task is delivered.

## Tests

```sh
python3 -m unittest discover -s hygiene -p 'test_*.py' -v
```

Tests use isolated temporary repositories and a bare fixture remote only. They
exercise successful normal retirement, active/locked/dirty/ignored/untracked and
unpushed holds, live-remote proof, path escapes, index flags, duplicate ownership,
state persistence, and a concurrent change during proof collection. They do not
operate on user worktrees.
