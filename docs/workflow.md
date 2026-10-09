# Workflow and evidence

## Propose and approve

The CPO writes a proposal using `templates/proposal.md`. The first line is machine-readable metadata; size and kind belong to independent dimensions. The stable key prevents duplicate creation after a lost response. The title and entire body, including asset URLs pinned to commits, form the SHA-256 proposal revision.

```sh
python3 bin/productctl digest --title 'Proposal title' --body-file proposals/example.md
python3 bin/productctl capacity
python3 bin/productctl propose --title 'Proposal title' --body-file proposals/example.md
```

`propose` is enabled only in live mode, checks both caps inside an atomic GitHub reservation, and posts the approval command. It counts closed proposals unless they have an authenticated rejection or completed release record. Labels aid navigation; they are not approvals or terminal authority. Do not fill all slots merely because they are available. In pilot mode the owner creates exactly one small proposal from the template; autonomous research remains paused.

The owner posts a new, unedited comment whose first line is `/aljam3 approve <revision>`. To request edits, reject, or pause, use `/aljam3 changes <revision>`, `/aljam3 reject <revision>`, or `/aljam3 pause <revision>`. Commands must be written by GitHub user ID `7662492` (`AliOsm`). Quoted commands, labels, bot comments, edited approvals, and webhook sender claims do not authorize work. Editing an approval pauses that revision; editing a denial does not restore an older approval. A new body/title needs a new approval. To reverse a command, post another comment; the latest applicable command wins. Preserve command comments as the audit trail rather than deleting them.

## Claim and implement

```sh
python3 bin/productctl claim --issue 123 --thread COORDINATOR_THREAD_ID
```

Only one `automation/active` GitHub ref can exist. Creating it is atomic. Its commit message records the issue, proposal revision, and owning T3 thread. A duplicate wake-up routes to that thread instead of starting another CTO. A failed/abandoned worker keeps the reservation until the owner inspects the T3 tasks and explicitly recovers it. Rejection does not silently cancel a live process; the coordinator cancels children, stops PR watches, confirms all work has stopped, and then the owner clears the reservation.

After scope edits, the same coordinator must stop old child work, obtain the owner's new approval, and call `claim` again. It advances the existing reservation to the approved revision with a fast-forward-only GitHub ref update. A different thread cannot take ownership this way.

The CTO gets the complete approved issue, repository `AGENTS.md`, exact base commits, explicit isolated workspace paths, rollout order and line budget. For a cross-app change preserve the public web API for installed desktop clients; normally deploy a backward-compatible server first. Never require simultaneous deployments for correctness.

Each PR body contains these exact lines:

```text
Product issue: https://github.com/ieasybooks/aljam3-product/issues/123
Proposal revision: <64-character revision>
```

Record the complete PR set and obtain the bundle fingerprint:

```sh
python3 bin/productctl link --issue 123 --pull 'ieasybooks/aljam3-web-app#456'
python3 bin/productctl snapshot --issue 123
```

For both apps, supply `--pull` twice. Exactly one PR per approved repository must pass before delivery. The bundle hashes the proposal revision plus each PR number, head SHA, and base SHA. Any code/base change invalidates every role's prior acceptance for that bundle. Refresh the branch, rerun CI, and request fresh reviews.

## Review and repair

Each role produces `templates/review.json`, retaining its actual T3 task ID and linking durable evidence (test run, diff review, screenshots or artifact report). The coordinator validates the child result against the recorded task and posts it using `record`. It must not invent task results. A shared worker identity authenticates the recorder, not independent model reasoning; separate T3 tasks and the pilot audit establish that independence.

```sh
python3 bin/productctl record --issue 123 --file /path/to/review.json
```

The sequence is CTO evidence, QA pass, CPO acceptance, CEO pass. Failed QA records must also be posted with `verdict: fail`; they consume the repair budget. There are at most three repairs after the first implementation. Any unresolved finding blocks final approval; explicitly resolve or dismiss it with evidence. New scope returns to the owner. Each review round is a new `delegate_task` call with the original brief and prior findings; don't reopen the old child as a new review round.

## Delivery

The coordinator requests the trusted product repository's `Delivery` workflow, never a local `gh pr merge` or production command. `check` is read-only and works in pilot mode; `merge`, `release`, and `finish` require live mode. The workflow loads trusted main, uses the delivery App, and never executes PR code. `merge` validates current approvals, independent role records, CI, branch protections and exact SHAs, sets the App-bound delivery status, and asks GitHub to squash-merge that exact head. Sensitive work additionally needs `/aljam3 delivery <bundle>` from the owner. The required CODEOWNERS review remains a separate GitHub enforcement layer for governance files.

After all PRs merge, wait for the same required CI on every merge commit. `release` verifies reviewed tree equality, current main, approvals and role evidence, then records a unique permit before dispatching each app's existing workflow. Every agent release validates that permit again before obtaining production credentials. Desktop builds both platform packages and signs updates only in the production environment. Web deploys the approved commit with Kamal. Fixed inputs replace shell interpolation of free-form deployment commands.

`finish` closes the proposal and frees its slot only after each uniquely identified release run completes successfully, including post-delivery smoke checks. Dispatch success, a draft desktop release, or an agent claiming completion is insufficient. Keep evidence artifacts for at least 30 days and a durable summary on the issue.

Cross-repository merge/deploy is not atomic. A partial merge or release stays visibly blocked, retains the slot and reservation, and requires inspected recovery. Never retry an ambiguous external write blindly. Reconcile the exact workflow run/commit first. Do not roll back a database automatically; use an approved migration/restore plan. Policy changes and bypasses belong to the owner, outside the product agents' authority.
