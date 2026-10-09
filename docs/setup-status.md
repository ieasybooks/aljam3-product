# Installation status

Prepared on 2026-10-09. **Policy is off. No pilot, product proposal, role cycle, merge, deployment, or release has been run.**

## Repositories and PRs

- Product repository: https://github.com/ieasybooks/aljam3-product (public, as authorized by the owner).
- Web setup PR: https://github.com/ieasybooks/aljam3-web-app/pull/185.
- Desktop setup PR: https://github.com/ieasybooks/aljam3-desktop/pull/1.

Both PRs are open for review and all hosted checks pass. The application workflows pin the release-authority code to product commit `6ee660975875e1e4c53439486bf08379028aa5b1`. Product policy is always fetched from protected main at runtime.

## Verified setup

- 44 policy/helper tests pass, including quota categories, spoofed/edited/revoked approvals, changed code/base, independent task records, failing CI, duplicate reservations, renewed scope approval and release dispatch recovery. The [final helper revision's hosted CI](https://github.com/ieasybooks/aljam3-product/actions/runs/37970213559) passed.
- Web: 515 examples pass, 100% line and branch coverage, plus Brakeman, RuboCop, Prettier, i18n health, Active Record Doctor and asset builds. The full local agent check and [hosted CI](https://github.com/ieasybooks/aljam3-web-app/actions/runs/37969699382) passed. Disposable service setup and repeated cleanup were exercised.
- Desktop: 285 tests and 5,529 assertions pass locally. A native screenshot was captured and inspected using `bin/peek`. Workflow/ShellCheck validation and Ruby/Python syntax checks pass. Agent publication rejects missing versioned release notes before any release action. The hosted Windows UI audit has a bounded 300-second allowance with all scenario assertions retained. The [final hosted macOS/Windows run](https://github.com/ieasybooks/aljam3-desktop/actions/runs/37969698214), including the aggregate `Aljam3 / CI` check, passed.
- Both app main branches require strict `Aljam3 / CI`; product main requires strict `test`. These checks are bound to GitHub Actions (App ID 15368). All three disable admin bypass, disallow force-push/deletion and require conversation resolution. The final App-bound delivery status and CODEOWNERS review are intentionally installed after bootstrap/identity setup, not claimed active now.
- GitHub initially refused protection on the private product repository under the current plan. The owner authorized public visibility, resolving that restriction. Gitleaks scanned all four existing commits before publication and found no secrets; the product repository had no issues, releases or Actions artifacts to expose.
- The product delivery environment and both app policy/production environments allow only the branch `main`; desktop also has a main-only build environment. Their secret inventories are empty. Production secrets have not been migrated or exposed. Default Actions tokens are read-only.
- All three T3 projects are registered, actions imported, app defaults set to worktrees and product default set to local. No runtime/provider credential or global T3 instruction was changed.

## T3 records

Running server: `0.0.46-nightly.20261008.2819`; environment `323fa82e-1f25-41eb-a131-5beea06dac61`.

| Project | T3 project ID |
| --- | --- |
| aljam3-product | `mcp:bdfe9d3f-1e6f-4f76-975b-402ef55c4ad7` |
| aljam3-web-app | `mcp:cdca0c20-251e-4167-8d64-abbb21d38448` |
| aljam3-desktop | `mcp:49f33e55-6496-46ac-9c41-51eb617e561c` |

| Native automation | Schedule | State |
| --- | --- | --- |
| CPO research | Daily 09:00 server time (UTC) | Disabled; never run; nextRunAt null |
| Reconciliation | Every 60 minutes | Disabled; never run; nextRunAt null |

CPO task ID: `scheduled-task:command:mcp:804061d8-24bc-4e78-becb-156cb1d15f51:schedule-task:aljam3-bootstrap-cpo-20261009`.

Reconciliation task ID: `scheduled-task:command:mcp:804061d8-24bc-4e78-becb-156cb1d15f51:schedule-task:aljam3-bootstrap-reconcile-20261009`.

They create fresh lightweight dispatcher threads in the product project; the active GitHub reservation routes actual work to one durable coordinator. No automation is bound to the installation chat.

## Owner-dependent prerequisites

1. **Identity and secrets:** configure a distinct worker account/runtime, the delivery GitHub App and environment secrets/read-only token as described in `github.md`. The machine currently authenticates gh as the owner, `AliOsm`; that credential must not be inherited by unattended workers. Stored GitHub secret values cannot be read back for automatic migration.
2. **Browser capture:** T3 preview is blocked by AppArmor. Interactive sudo is required for `sudo env "PATH=$PATH" npx t3@nightly browser setup`. The setup session could not perform that interactive authentication.
3. **Signed decision webhook:** its prompt/contract is prepared, but no unsigned webhook task or GitHub hook was created. Complete T3 Connect/public URL verification and private signing-secret entry before creating the disabled hook. The owner may choose hourly reconciliation for the first pilot instead.
4. **Bootstrap and pilot:** review/merge the setup PRs, install final delivery protections, then explicitly start the one-issue pilot in `pilot.md`. Hosted setup CI has passed; policy and schedules stay off until pilot authorization.

These are setup/credential/host decisions to finish at the pilot handoff, not evidence that the autonomous system has already operated successfully.
