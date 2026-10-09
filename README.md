# Aljam3 product automation

This repository holds the product mandate, four agent roles, approval policy, and small GitHub helpers for `ieasybooks/aljam3-web-app` and `ieasybooks/aljam3-desktop`. T3 Code runs the agents using the existing Codex subscription. GitHub Actions runs ordinary tests and the delivery gate; no OpenAI API billing integration is required by this setup.

**Initial state: off. No pilot, autonomous work, merge, or release has been authorized by this repository.** The owner must complete the [pilot runbook](docs/pilot.md) before enabling operation. The two application setup PRs also need review and merging first.

The loop is CPO research → owner approves the exact issue revision → CTO implements → independent QA tests/reviews → CPO accepts the experience → CEO approves delivery → deterministic GitHub gate merges and releases. A failed stage returns concrete findings to CTO, with at most three repair rounds. Changed scope goes back to the owner.

| Outstanding proposal size | Ceiling | Outstanding proposal kind | Ceiling |
| --- | ---: | --- | ---: |
| Large | 2 | Bug fix | 2 |
| Medium | 3 | Current enhancement | 2 |
| Small | 5 | New feature | 6 |

These are independent ceilings across the product, not targets. One cross-app feature is one issue with two linked PRs. Approved work still occupies its slot. Only one implementation is active initially.

- [Product principles and research](docs/product.md)
- [Workflow, commands and evidence](docs/workflow.md)
- [T3 automations and hooks](docs/t3.md)
- [GitHub identity and enforcement](docs/github.md)
- [Pilot and recovery](docs/pilot.md)
- [Setup status and remaining prerequisites](docs/setup-status.md)
- Roles: [CPO](roles/cpo.md), [CTO](roles/cto.md), [QA](roles/qa.md), [CEO](roles/ceo.md), [coordinator](roles/coordinator.md)

Run `python3 -m unittest discover -s tests -v` to test policy without GitHub, agents, or production services. `python3 bin/productctl status` and `capacity` inspect current GitHub state. All runtime decisions load `policy.json` from the product repository's `main` branch, not a worker's modified checkout.

This is deliberately a small single-machine system. The helpers use GitHub references for atomic reservations and issues/comments for durable records. A crashed reservation is never silently expired while its original worker could still be running. Prompts are workflow instructions, not a security boundary; the dedicated delivery App, protected branches and protected environment credentials provide the delivery boundary.
