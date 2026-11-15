# Visual and UI PR evidence

Owner direction (Jeremy, 2026-11-15): “On the factory-rules level, make sure screenshots are being included in PRs that affect visuals and UI”.

## Required delivery

- Applies across the factory to visual/UI changes, including layout, typography, colors, interactive demos, responsive behavior and component styling. Apply it to currently open affected PRs, not only new PRs.
- The implementor captures real rendered screenshots of the candidate at representative affected states and viewports. For responsive changes include desktop and narrow/mobile evidence. Provide before/after comparison where an existing appearance changes; for a new view, label the new state. Do not manufacture screenshots or treat mockups as implementation evidence.
- Record the exact candidate commit, capture revision, route/story, viewport dimensions, relevant state, runtime/build mode and material limitations. If evidence is carried forward by verified tree equality rather than a rerun, say so explicitly. Recapture affected evidence after visual changes; never label stale images as current.
- Include the screenshots in the PR description or a clearly linked PR comment, as embedded images or reviewer-accessible direct image links. A local path, screenshot count, test claim, or report that merely says images exist is not inclusion. Keep concise captions identifying what each image proves. A CI artifact alone is not sufficient unless the PR links directly to the accessible screenshots with provenance; note retention limits.
- Use synthetic/demo data and inspect images for credentials, private information, unrelated windows and account details before publication. Use the repository's existing authorized attachment/artifact mechanism. This rule does not grant new storage/account access, credentials, or permission to publish unrelated or sensitive data. If no supported safe upload path exists, retain the captures and log the precise delivery blocker rather than bypassing controls.

## Responsibility and verification

1. Captain adds screenshot acceptance to existing native tasks for affected work; do not spawn duplicate implementation tasks. The worker supplies captures and a manifest in the handoff.
2. The independent reviewer inspects the actual pixels, checks relevant behavior separately, and records whether the evidence represents the reviewed revision and shows the intended change. Screenshots do not replace interaction tests, accessibility checks, required CI, or truthful limitations.
3. The authorized publisher attaches/links evidence within the existing approved PR scope. Captain reads back the remote PR body/comment, verifies image links are accessible to intended reviewers and match the manifest, and records that receipt in the native task.
4. Without included, verified screenshot evidence, an affected PR may remain draft with an explicit evidence hold, but must not be called complete or ready. Fix the hold before ready/handback. Human merge authority is unchanged.

## Rollout

Captain should inspect existing affected PRs, retain valid current evidence, and add only what is missing. This is an operating rule, not a claim that an automated publication gate has been implemented or any screenshots are already uploaded. Keep per-task rollout receipts in private runtime records, not the published rig definition.
