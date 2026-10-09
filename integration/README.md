# Integration contracts

Application release workflows check out the product gate code at an immutable commit and load live policy from the product repository's protected `main`. The pinned code must be updated through a governance PR when the gate implementation changes. The read-only token has contents and issues read access to the public product repository and read access to app PRs, checks and actions; it cannot approve, merge, release or modify policy. Public visibility does not remove the current workflows' authenticated cross-repository read-token requirement.

`Delivery` dispatches these inputs to the application workflow on `main`: `delivery=agent`, `product_issue`, `release_sha`, `delivery_id`, plus `command=deploy` for web or `release=publish` for desktop. The run title must be exactly `Aljam3 delivery <delivery_id>` so completion reconciliation can identify it. Agent releases must not accept empty IDs or an arbitrary branch/SHA.

The applications retain an explicit manual dispatch route limited to owner user ID 7662492. It is for the human owner, including emergencies, and is not available to the worker identity. The owner account must never be inherited by an unattended T3 process. Delivery and production secrets are environment-scoped with branch restrictions to `main`; merely defining an environment name in YAML does not move an existing repository secret into it.

The user-facing production workflows are not called during setup or the pilot. Tests use pure fixtures and normal CI. A real release requires live mode after the pilot acceptance record.
