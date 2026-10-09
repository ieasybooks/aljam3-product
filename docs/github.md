# GitHub authority and setup

`aljam3-product` and both application repositories are public. The owner chose public visibility so GitHub can enforce branch protection on the current plan. Research issues, sketches and evidence are public too; store only appropriate, redacted or permissioned material. Keep credentials and personal user data out of repositories, issues and artifacts.

## Identities

| Identity | Authority | Location |
| --- | --- | --- |
| Human owner, `AliOsm` / ID `7662492` | Approve proposal revisions, sensitive deliveries, policy changes, recovery and activation | Human GitHub session |
| Dedicated worker account | Read apps; create branches/PRs/issues/evidence; request trusted delivery workflow | Unattended T3 runtime only |
| Dedicated delivery GitHub App | Validate and set its own required status; merge exact approved heads; dispatch releases; record completion | Product `aljam3-delivery` environment only |
| Read-only product token | Read policy, issue evidence, app PR/check/action state | App `aljam3-read-policy` environments only |
| Production keys | Deploy web or sign desktop updates | App `aljam3-production` environments only |

The current setup session is authenticated as the human owner. It must not become the unattended worker account. Create a separate GitHub worker identity with a fine-grained token limited to these three repositories: contents/PRs/issues read-write and actions read-write as needed to request the trusted workflow. Give it no organization administration, environment administration, secret administration, branch bypass or production access. Prefer no workflow-writing permission; sensitive workflow changes then remain owner-managed work.

Create a GitHub App installed only on these three repositories, with contents, pull requests, issues, commit statuses and actions read/write, checks read, and metadata read. It needs no administration permission and no branch-protection bypass. Record its numeric App ID and bot login in `policy.json`. Put `ALJAM3_GATE_APP_ID` as an environment variable and `ALJAM3_GATE_APP_PRIVATE_KEY` as an environment secret on the product repository's `aljam3-delivery` environment. The worker never gets that key. The required `Aljam3 / delivery` status must be bound to this App ID, so an arbitrary green GitHub Actions job cannot impersonate it.

Create a read-only fine-grained token for policy access: contents/issues read on the product repo and PRs/checks/actions/contents read on the two apps. Store it as `ALJAM3_PRODUCT_READ_TOKEN` in each app's `aljam3-read-policy` environment. The current release workflows still use this token for authenticated cross-repository reads even though the repositories are public. It cannot write approval or delivery records. Secret values belong in GitHub/T3 private input, not chat or repository files.

Run unattended T3 under an OS account/container that cannot read the owner's gh credentials or deployment keys. Merely changing `GH_CONFIG_DIR` in a full-access session on the owner's account is not a security boundary. Do not expose a host Docker socket or host home directory to an allegedly isolated worker; use appropriately scoped local development services. The existing always-on server can be migrated/configured at the pilot handoff, with the owner's interactive access. Codex subscription authentication can remain the chosen provider; this setup does not add an API key dependency.

## Branches and environments

`bin/configure-github --phase bootstrap` installs strict CI protection on `main`, disables admin bypass/force-push/deletion, sets default Actions tokens to read-only, creates product labels and creates environments restricted to the `main` branch. It does not enable automation, merge setup PRs or copy secrets. Run it only on the intended repositories; it sets the documented branch policy, so inspect existing rules first when reusing it.

After the setup PRs merge and identities are configured, the owner runs `--phase delivery`. This adds stale-review dismissal and CODEOWNERS enforcement, and requires the dedicated App's delivery status on both applications. Ordinary automated changes need QA/CPO/CEO evidence but not an additional human PR review; sensitive governance paths still require the owner. Product repository files are all owned by the human. Code owner rules start after bootstrap because the owner cannot approve their own setup PRs. Never use bootstrap again to remove an installed delivery gate.

The product policy/helper changes and activation changes should be submitted from a worker branch for human CODEOWNERS approval. The owner manually merges policy PRs after review. The delivery App is not authorized to merge product-policy changes.

Move the existing web SSH, Rails, PostgreSQL, Meilisearch and Shipyrd secrets into `aljam3-production`, and desktop `UPDATE_PRIVATE_KEY` into its `aljam3-production` environment. Secret names can be inspected, but stored values cannot be read back or migrated automatically. Once copied and checked, remove the corresponding repository-level production secrets. Web test CI must use test-only configuration; it should not need the production Rails master key. The read-policy token belongs in its separate environment. Check organization-level inherited secrets as well.

Environment branch restrictions must allow only the branch `main`, not matching tags or PR refs. In version one the owner-only manual release route remains available for incidents. It checks numeric actor ID, so it depends on genuine runtime identity separation. Do not dispatch an agent release as the owner to get around the gate.

## Source of truth

GitHub issues hold immutable-revision approvals and role records. GitHub refs hold the short proposal-creation reservation and the single active implementation. GitHub Actions owns delivery executions. T3 owns role task histories. No label or local file substitutes for these checks. The gate never checks out or executes untrusted PR code; CI executes it with no production secrets.

There remains a narrow race between the final issue read and GitHub accepting a merge; GitHub cannot atomically transact an issue comment and PR merge. The helper checks current approval and exact SHAs immediately before each merge. The owner should pause the coordinator before changing an in-flight delivery. The pilot must test revocation and failure handling; don't describe this as a transactional multi-repository release.
