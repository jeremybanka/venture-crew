# Wayforge context

Deployment location: a dedicated checkout inside the Wayforge Lima VM. `/home/crew/venture-crew` in examples is a placeholder, not a verified local path. This is the developer environment, not just CI. The Wayfarer CI service remains a separate account and work root; do not use or modify it.

The crew serves selected repositories across this VM. `projects.local.json` (see `projects.example.json`) is inventory only, not an admission allowlist, native workspace registration, or authorization to perform work. Each assignment supplies a named project, revision and intent. Native OpenRig queues and task records carry ownership; no parallel RPG task system is introduced.

The manifest declares 15 seats: Commander, Captain, Sky Command, two Striders, Lancer, Pyro, Witch, Inquisitor, Hierophant, Cleric, Chronicler, Deckhand, Warden and Lookout. Knight and Ranger are absent. Warden includes serialized integration; publication still needs explicit authority.

Runtime assignments are nominal topology, not permanent identities or bypasses of routing. The canonical ordered model policy is model-preferences.json, with high effort for all seats. Only verified entries in model-catalog.json are eligible. Provider-local budgets and session-safe handover gates govern fallback. No native permission overrides are included.

This rig repository owns crew/workflow documentation. Dotfiles supplies only VM and clean-runtime integration, not a duplicate operating plan.

See SETUP.md for verified installation state and remaining activation gates. A valid manifest is not proof of a running or budget-enforced crew.
