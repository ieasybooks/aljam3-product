# Pilot and activation runbook

**Stop point for installation: everything stays off.** Do not create the pilot issue, dispatch role tasks, merge/release product work or enable schedules until the owner explicitly starts this runbook. Normal policy tests and application CI are setup validation, not a pilot.

## Before the pilot

1. Review and merge the two setup PRs after their CI succeeds. Check the actual native macOS/Windows results, not just Linux tests. Review the new release workflows and CODEOWNERS paths.
2. Configure the distinct worker identity, delivery App, read-only token and isolated unattended runtime described in `github.md`. Set the real worker ID/login and gate App ID/login through an owner-reviewed policy PR. Keep mode off. Verify the worker cannot use the owner's token, access production keys, change policy/main or bypass the delivery status.
3. Finish environment-scoped secret migration and branch restrictions. Remove production credentials from web PR CI and from repository/organization scope where a worker-authored workflow could read them. Install `configure-github --phase delivery` only after the bootstrap PRs are merged.
4. Fix the host's T3 browser sandbox with the owner-run sudo command in `t3.md`; capture a real screenshot from a disposable web preview. Validate desktop `peek` separately. Prepare permissioned sample books and test identities for the pilot's acceptance criteria.
5. Set up T3 Connect and the signed GitHub decision webhook using private secret input. Keep it disabled. Alternatively explicitly choose hourly reconciliation for the pilot and add the webhook later. Check the saved project actions and the current native tool contracts.

## One small pilot

1. The owner selects one low-risk small enhancement or bug fix, creates a fully specified product issue from the template and reviews its experience sketch. Existing backlog entries are not automatically approved. Set `mode: pilot` and that issue's number in an owner-reviewed policy PR. All schedules remain disabled.
2. Start one coordinator turn manually in the product T3 project with `roles/coordinator.md`. First test no approval, a bot-authored approval, an edited approval, a wrong revision, and an out-of-scope issue. Each must refuse work. Then the owner posts a new exact-revision approval.
3. Run CTO → independent QA → repair if needed → CPO → CEO. Confirm actual task IDs, separate QA work, explicit app worktrees, meaningful evidence and current CI. Duplicate a wake-up and restart/resume the coordinator; there must still be only one implementation reservation.
4. Change code after a review, update the base, and request scope edits in controlled stages. Each stale approval/review must block delivery until the correct new approval/evidence exists. Exercise a failed CI check and verify the aggregate cannot pass because a dependency skipped or failed. Test quota boundaries in local fixtures; don't create ten fake live proposals to exercise them.
5. Request the read-only `Delivery` operation `check`. It may report eligibility for that exact bundle but must never merge/release in pilot mode. Record independent owner observations and remaining defects in the issue. Test the pause/kill procedure and inspect recovery without forcibly deleting an active reservation.
6. The owner evaluates whether the CPO proposed something useful, QA found real risks, the final experience met the approved intent, and the audit trail was understandable. Fix any system defects before activation. Pilot success does not silently authorize live mode.

## Live operation

The owner approves a separate activation policy PR setting `mode: live`, after pilot acceptance and identity/credential checks. Decide what to do with the pilot PRs explicitly. Enable reconciliation and the signed decision webhook, then the daily CPO research task. Record their IDs and the activation time. A scheduled dispatch succeeding is not evidence of product delivery.

Start with one active implementation and the defined caps. Review actual user outcomes weekly. Tighten or widen authority only through owner-reviewed policy changes with observed evidence. Do not expand to multiple machines/implementations or add separate controllers until the single-machine workflow has proven reliable.

## Pause and recovery

Disable the T3 tasks and stop/interrupt the coordinator and active children. Revoke worker credentials if authority may be compromised; cancel pending GitHub delivery/release runs when appropriate. Use a policy PR to set mode off; an in-flight deployment may already have started, so inspect its exact run before claiming it was stopped.

On an ambiguous command, inspect GitHub refs, issue records, PR SHAs and workflow runs. Reservations never expire automatically. For a stale `automation/proposals` ref, verify no creation process remains before the owner deletes it. For `automation/active`, verify child tasks/workspaces and deployment state before handing ownership to a replacement coordinator or deleting the ref. Do not discard work or free capacity while a release is unknown.

Partial cross-app merges/releases require an owner-reviewed recovery plan. Keep the proposal open and its capacity occupied. Identify which reviewed commits are deployed, preserve backward compatibility, and decide whether to repair forward or use the existing manual rollback/update process. Never blindly redispatch after a lost response. Re-run a failed workflow only after checking which external steps already happened. A failed database migration is not solved by an automatic application rollback.

The autonomous helpers intentionally refuse to repeat a merge attempt after `merge-started` exists. An owner can recover after inspecting the individual PRs, or approve a new plan. This conservative boundary avoids treating a partial delivery as atomic success.
