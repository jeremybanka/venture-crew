# Wayforge expedition

Read CULTURE.md, SOP.md and CONTEXT.md. This repository owns the VM-wide crew, not the product repositories. Preserve Scrubs' clean/dirty boundary and the separate Wayfarer CI account. Never run a dirty dependency outside its sandbox merely to reach clean agent credentials.

Run `python3 scripts/check.py` for deterministic tests and source consistency. Run `npm run validate` for the pinned OpenRig schema check after installation. Tests must use temporary fixture repos and state, never real cleanup. Do not start the crew unless activation preflight is satisfied. Do not commit runtime state or credentials. Runtime state and local inventory must remain untracked.
