"""GitHub-backed commands; there is no daemon, scheduler or local job database."""

import argparse
import base64
from contextlib import contextmanager
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

from .github import GitHub
from .policy import (active, approved, bundle_id, capacity, check_runs_pass, delivery, human_command,
                     metadata, needs_human_delivery, records, render_record, require, reviews, revision, terminal)

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "ieasybooks/aljam3-product"


class Product:
    def __init__(self, api=None):
        self.api = api or GitHub()
        content = self.api.request(f"repos/{PRODUCT}/contents/policy.json?ref=main")
        self.policy = json.loads(base64.b64decode(content["content"]))
        require(self.policy["product_repo"] == PRODUCT, "Unexpected product repository")
        self.path = f"repos/{PRODUCT}"

    def issue(self, number):
        return self.api.request(f"{self.path}/issues/{number}"), self.api.comments(PRODUCT, number)

    def all_proposals(self):
        issues = self.api.issues(PRODUCT)
        comments = {i["number"]: self.api.comments(PRODUCT, i["number"]) for i in issues
                    if (i.get("body") or "").startswith("<!-- aljam3:proposal")}
        return issues, comments

    def worker(self):
        user = self.api.request("user")
        require(user["id"] == self.policy["worker"]["id"] and user["id"] != self.policy["owner"]["id"],
                "Use the dedicated worker account, never the owner's gh credentials")

    def post(self, number, record):
        result = self.api.comment(PRODUCT, number, render_record(record))
        expected = self.policy["worker"]["login"] if record["type"] in ("review", "pulls") else self.policy["gate"]["login"]
        require(result["user"]["login"] == expected, "Record was not written by the authorized identity; no further action is allowed")
        return result

    def lock(self, name):
        refs = self.api.request(f"{self.path}/git/matching-refs/heads/automation/{name}")
        refs = [r for r in refs if r["ref"] == f"refs/heads/automation/{name}"]
        if not refs:
            return None
        commit = self.api.request(f"{self.path}/git/commits/{refs[0]['object']['sha']}")
        return {"sha": refs[0]["object"]["sha"], **json.loads(commit["message"])}

    def acquire(self, name, value):
        require(self.lock(name) is None, f"{name} is reserved; inspect it before attempting recovery")
        base = self.api.request(f"{self.path}/git/refs/heads/main")["object"]["sha"]
        tree = self.api.request(f"{self.path}/git/commits/{base}")["tree"]["sha"]
        commit = self.api.request(f"{self.path}/git/commits", "POST",
                                  {"tree": tree, "parents": [base], "message": json.dumps(value)})
        # Creating an existing ref fails atomically, even if two callers observed no lock.
        self.api.request(f"{self.path}/git/refs", "POST",
                         {"ref": f"refs/heads/automation/{name}", "sha": commit["sha"]})
        return commit["sha"]

    def release_lock(self, name, sha):
        lock = self.lock(name)
        require(lock and lock["sha"] == sha, "Reservation changed; refusing to clear it")
        self.api.request(f"{self.path}/git/refs/heads/automation/{name}", "DELETE")

    @contextmanager
    def proposal_lock(self):
        sha = self.acquire("proposals", {"request": str(uuid.uuid4())})
        try:
            yield
        finally:
            self.release_lock("proposals", sha)

    def propose(self, title, body):
        require(self.policy["mode"] == "live", "Scheduled proposal creation is disabled until live mode")
        active(self.policy)
        self.worker()
        proposal = {"title": title, "body": body}
        data = metadata(proposal, self.policy)
        with self.proposal_lock():
            issues, comments = self.all_proposals()
            for issue in issues:
                if (issue.get("body") or "").startswith("<!-- aljam3:proposal"):
                    if metadata(issue, self.policy)["key"] == data["key"]:
                        require(revision(issue) == revision(proposal), "Proposal key already exists with different content")
                        return {"issue": issue["html_url"], "existing": True, "revision": revision(issue)}
            counts = capacity(issues, comments, self.policy)
            for dimension in counts:
                require(counts[dimension][data[dimension]] < self.policy["limits"][dimension][data[dimension]],
                        f"No {dimension}/{data[dimension]} capacity")
            result = self.api.request(f"{self.path}/issues", "POST", {**proposal, "labels": [
                "proposal", "state:proposed", f"size:{data['size']}", f"kind:{data['kind']}"]})
            rev = revision(result)
            self.api.comment(PRODUCT, result["number"],
                             f"Proposal revision: `{rev}`\n\n@{self.policy['owner']['login']}: approve with `/aljam3 approve {rev}` or request edits with `/aljam3 changes {rev}`. Approval covers the title and entire issue body.")
            return {"issue": result["html_url"], "revision": rev, "existing": False}

    def claim(self, number, thread):
        active(self.policy, number)
        self.worker()
        issue, comments = self.issue(number)
        approved(issue, comments, self.policy)
        capacity(*self.all_proposals(), self.policy)
        require(not terminal(issue, comments, self.policy), "Proposal is already terminal")
        require(re.fullmatch(r"[A-Za-z0-9_-]{10,100}", thread), "Supply the T3 coordinator thread ID")
        value = {"issue": number, "revision": revision(issue), "thread": thread}
        existing = self.lock("active")
        if existing:
            require(all(existing.get(k) == v for k, v in value.items()),
                    f"Work is already owned by T3 thread {existing.get('thread')}; route the wake-up there")
            return existing
        return {**value, "sha": self.acquire("active", value)}

    def linked_pulls(self, number, comments, rev):
        links = [r for _, r in records(comments, self.policy["worker"]["login"])
                 if r.get("type") == "pulls" and r.get("revision") == rev]
        require(links, f"No PR bundle recorded for issue #{number}")
        return links[-1]["pulls"]

    def pull(self, repo, number):
        require(repo in self.policy["repositories"], "Repository outside Aljam3")
        path = f"repos/{repo}"
        pull = self.api.request(f"{path}/pulls/{int(number)}")
        sha = pull["head"]["sha"]
        branch = self.policy["repositories"][repo]["branch"]
        base = self.api.request(f"{path}/git/refs/heads/{branch}")["object"]["sha"]
        comparison = self.api.request(f"{path}/compare/{base}...{sha}")
        pr_reviews = self.api.pages(f"{path}/pulls/{number}/reviews")
        latest_reviews = {}
        for review in pr_reviews:
            if review["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
                latest_reviews[review["user"]["id"]] = review["state"]
        pull.update(repository=repo, current_base=base, base_is_ancestor=comparison["status"] in ("ahead", "identical"),
                    files=[f["filename"] for f in self.api.pages(f"{path}/pulls/{number}/files")],
                    changes_requested="CHANGES_REQUESTED" in latest_reviews.values(), checks=self.checks(repo, sha))
        return pull

    def checks(self, repo, sha):
        output = []
        for page in range(1, 1001):
            batch = self.api.request(f"repos/{repo}/commits/{sha}/check-runs?per_page=100&page={page}")["check_runs"]
            output.extend(batch)
            if len(batch) < 100:
                return output
        raise ValueError("Too many check runs")

    def snapshot(self, number):
        issue, comments = self.issue(number)
        pulls = [self.pull(p["repository"], p["number"]) for p in self.linked_pulls(number, comments, revision(issue))]
        return issue, comments, pulls

    def link(self, number, specifications):
        active(self.policy, number)
        self.worker()
        issue, comments = self.issue(number)
        approved(issue, comments, self.policy)
        pulls = []
        for spec in specifications:
            repo, pr = spec.rsplit("#", 1)
            require(repo in metadata(issue, self.policy)["repositories"], "PR is outside approved scope")
            pulls.append({"repository": repo, "number": int(pr)})
        require(len(pulls) == len({p['repository'] for p in pulls}), "Only one PR per repo in a bundle")
        self.post(number, {"type": "pulls", "revision": revision(issue), "pulls": pulls})
        return pulls

    def record(self, number, record):
        active(self.policy, number)
        self.worker()
        issue, comments, pulls = self.snapshot(number)
        approved(issue, comments, self.policy)
        require(record.get("type") == "review" and record.get("role") in ("cto", "qa", "cpo", "ceo"), "Only role reviews may be recorded")
        require(record.get("bundle") == bundle_id(revision(issue), pulls), "Review is for a stale bundle")
        failures = [r for _, r in records(comments, self.policy["worker"]["login"])
                    if r.get("type") == "review" and r.get("role") == "qa" and r.get("verdict") == "fail"
                    and r.get("revision") == revision(issue)]
        require(len(failures) <= self.policy["limits"]["repair_rounds"], "Repair budget exhausted; escalate to the owner")
        self.post(number, {**record, "revision": revision(issue)})
        return {"recorded": True}

    def gate(self, number):
        issue, comments, pulls = self.snapshot(number)
        bundle = delivery(issue, comments, pulls, self.policy)
        lock = self.lock("active")
        require(lock and lock["issue"] == number and lock["revision"] == revision(issue), "Active reservation is missing or stale")
        for p in pulls:
            protection = self.api.request(f"repos/{p['repository']}/branches/{p['base']['ref']}/protection")
            required = protection.get("required_status_checks") or {}
            require(required.get("strict"), "Strict branch checks must be enforced")
            checks = required.get("checks", [])
            require(any(c["context"] == self.policy["delivery_context"] and c.get("app_id") == self.policy["gate"]["app_id"] for c in checks),
                    "Required delivery status must belong to the dedicated GitHub App")
            require(protection.get("enforce_admins", {}).get("enabled"), "Admin bypass must be disabled")
            require((protection.get("required_pull_request_reviews") or {}).get("require_code_owner_reviews"), "Code owner review must be enforced")
            require(all(any(c["context"] == name and c.get("app_id") == 15368 for c in checks)
                        for name in self.policy["repositories"][p["repository"]]["checks"]), "Required CI protection is incomplete")
        return issue, comments, pulls, bundle

    def merge(self, number):
        active(self.policy, number, live=True)
        issue, comments, pulls, bundle = self.gate(number)
        require(not any(r.get("type") == "merge-started" for _, r in records(comments, self.policy["gate"]["login"])),
                "A merge attempt already exists; inspect partial delivery before recovery")
        summary = [{"repository": p["repository"], "number": p["number"], "head": p["head"]["sha"],
                    "base": p["base"]["sha"]} for p in pulls]
        self.post(number, {"type": "merge-started", "revision": revision(issue), "bundle": bundle, "pulls": summary})
        merged = []
        for pull in pulls:
            fresh_issue, fresh_comments = self.issue(number)
            approved(fresh_issue, fresh_comments, self.policy)
            require(revision(fresh_issue) == revision(issue), "Scope changed during merge")
            fresh = self.pull(pull["repository"], pull["number"])
            require(fresh["head"]["sha"] == pull["head"]["sha"] and fresh["current_base"] == pull["base"]["sha"], "PR/base changed during merge")
            require(fresh["mergeable"] is True and not fresh["changes_requested"] and not fresh["draft"], "PR is no longer ready")
            reviews(fresh_comments, self.policy, bundle)
            if needs_human_delivery(metadata(issue, self.policy), pulls, self.policy):
                require(human_command(fresh_comments, self.policy, "delivery", bundle), "Sensitive approval changed during merge")
            check_runs_pass(fresh["checks"], self.policy["repositories"][pull["repository"]]["checks"])
            self.api.request(f"repos/{pull['repository']}/statuses/{pull['head']['sha']}", "POST", {
                "state": "success", "context": self.policy["delivery_context"], "description": "Approved proposal and current independent reviews",
                "target_url": issue["html_url"]})
            try:
                result = self.api.request(f"repos/{pull['repository']}/pulls/{pull['number']}/merge", "PUT",
                                          {"sha": pull["head"]["sha"], "merge_method": "squash"})
            except Exception:
                self.api.request(f"repos/{pull['repository']}/statuses/{pull['head']['sha']}", "POST", {
                    "state": "failure", "context": self.policy["delivery_context"], "description": "Merge was not confirmed; inspected recovery required"})
                raise
            if not result.get("merged"):
                self.api.request(f"repos/{pull['repository']}/statuses/{pull['head']['sha']}", "POST", {
                    "state": "failure", "context": self.policy["delivery_context"], "description": "Merge refused; inspected recovery required"})
            require(result.get("merged"), "GitHub refused the merge")
            merged.append({"repository": pull["repository"], "number": pull["number"], "head": pull["head"]["sha"], "merge": result["sha"]})
            self.post(number, {"type": "merge-progress", "revision": revision(issue), "bundle": bundle, "pulls": merged})
        self.post(number, {"type": "merged", "revision": revision(issue), "bundle": bundle, "pulls": merged,
                           "human_delivery_required": needs_human_delivery(metadata(issue, self.policy), pulls, self.policy)})
        return {"bundle": bundle, "merged": merged}

    def release_ready(self, number):
        active(self.policy, number, live=True)
        issue, comments = self.issue(number)
        approved(issue, comments, self.policy)
        completed = [r for _, r in records(comments, self.policy["gate"]["login"])
                     if r.get("type") == "merged" and r.get("revision") == revision(issue)]
        require(completed, "No completed bundle merge exists")
        merged = completed[-1]
        require({p["repository"] for p in merged["pulls"]} == set(metadata(issue, self.policy)["repositories"]), "Incomplete cross-repository merge")
        reviews(comments, self.policy, merged["bundle"])
        if merged.get("human_delivery_required"):
            require(human_command(comments, self.policy, "delivery", merged["bundle"]), "Human delivery authorization was revoked")
        for pull in merged["pulls"]:
            repo, sha = pull["repository"], pull["merge"]
            pr = self.api.request(f"repos/{repo}/pulls/{pull['number']}")
            require(pr["merged"] and pr["merge_commit_sha"] == sha and pr["head"]["sha"] == pull["head"], "Merged PR no longer matches the approved bundle")
            branch = self.policy["repositories"][repo]["branch"]
            require(self.api.request(f"repos/{repo}/git/refs/heads/{branch}")["object"]["sha"] == sha, "main has moved; release needs a new review")
            head_tree = self.api.request(f"repos/{repo}/git/commits/{pull['head']}")["tree"]["sha"]
            require(self.api.request(f"repos/{repo}/git/commits/{sha}")["tree"]["sha"] == head_tree, "Merge changed the reviewed tree")
            check_runs_pass(self.checks(repo, sha), self.policy["repositories"][repo]["checks"])
        return issue, comments, merged

    def release(self, number):
        issue, comments, merged = self.release_ready(number)
        existing = [r for _, r in records(comments, self.policy["gate"]["login"])
                    if r.get("type") == "release-requested" and r.get("bundle") == merged["bundle"]]
        requests = []
        # Deploy the compatible server first; only dispatch desktop after its health checks pass.
        for pull in sorted(merged["pulls"], key=lambda p: (not p["repository"].endswith("web-app"), p["repository"])):
            previous = [r for r in existing if r["repository"] == pull["repository"]]
            require(len(previous) <= 1, "Ambiguous release requests; inspect before recovery")
            if previous:
                run = self.release_run(previous[0])
                if run is None or run["status"] != "completed":
                    return {"waiting_for": previous[0], "note": "Do not redispatch; inspect an absent/old run for recovery."}
                require(run["conclusion"] == "success", "Previous release failed; inspected recovery is required")
                continue
            delivery_id = str(uuid.uuid4())
            repo = pull["repository"]
            request = {"type": "release-requested", "revision": revision(issue), "bundle": merged["bundle"],
                       "repository": repo, "sha": pull["merge"], "delivery_id": delivery_id}
            self.post(number, request)
            inputs = {"delivery": "agent", "product_issue": str(number), "release_sha": pull["merge"], "delivery_id": delivery_id}
            if repo.endswith("desktop"):
                inputs["release"] = "publish"
            else:
                inputs["command"] = "deploy"
            config = self.policy["repositories"][repo]
            self.api.request(f"repos/{repo}/actions/workflows/{config['release_workflow']}/dispatches", "POST",
                             {"ref": config["branch"], "inputs": inputs})
            requests.append(request)
            break
        return {"requested": requests, "note": "Dispatch is not release success. Reconcile the completed runs."}

    def release_run(self, permit):
        repo = permit["repository"]
        workflow = self.policy["repositories"][repo]["release_workflow"]
        runs = self.api.request(f"repos/{repo}/actions/workflows/{workflow}/runs?event=workflow_dispatch&head_sha={permit['sha']}&per_page=100")["workflow_runs"]
        matches = [r for r in runs if r["display_title"] == f"Aljam3 delivery {permit['delivery_id']}"]
        require(len(matches) <= 1, "Ambiguous release run identity")
        return matches[0] if matches else None

    def authorize_release(self, number, repository, sha, delivery_id):
        issue, comments, merged = self.release_ready(number)
        require(any(p["repository"] == repository and p["merge"] == sha for p in merged["pulls"]), "Artifact SHA is outside the merged bundle")
        permits = [r for _, r in records(comments, self.policy["gate"]["login"])
                   if r.get("type") == "release-requested" and r.get("bundle") == merged["bundle"]
                   and r.get("repository") == repository and r.get("sha") == sha and r.get("delivery_id") == delivery_id]
        require(permits, "No matching release permit")
        return {"authorized": True, "sha": sha, "delivery_id": delivery_id}

    def finish(self, number):
        issue, comments = self.issue(number)
        active(self.policy, number, live=True)
        permits = [r for _, r in records(comments, self.policy["gate"]["login"])
                   if r.get("type") == "release-requested" and r.get("revision") == revision(issue)]
        require(len(permits) == len(metadata(issue, self.policy)["repositories"]), "Missing or ambiguous release requests")
        require({p["repository"] for p in permits} == set(metadata(issue, self.policy)["repositories"]), "Release requests do not cover the entire proposal")
        urls = []
        for permit in permits:
            run = self.release_run(permit)
            require(run and run["status"] == "completed" and run["conclusion"] == "success", "Release is pending, failed or ambiguous; keep the proposal slot")
            urls.append(run["html_url"])
        self.post(number, {"type": "released", "revision": revision(issue), "evidence": urls})
        self.api.request(f"{self.path}/issues/{number}", "PATCH", {"state": "closed", "state_reason": "completed"})
        lock = self.lock("active")
        require(lock and lock["issue"] == number, "Unexpected active reservation")
        self.release_lock("active", lock["sha"])
        return {"released": True, "evidence": urls}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "capacity", "digest", "propose", "claim", "link", "snapshot", "record", "gate", "merge", "release", "authorize-release", "finish"])
    parser.add_argument("--issue", type=int)
    parser.add_argument("--title")
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--thread")
    parser.add_argument("--pull", action="append", default=[])
    parser.add_argument("--repository")
    parser.add_argument("--sha")
    parser.add_argument("--delivery-id")
    args = parser.parse_args()
    try:
        if args.command == "digest":
            require(args.title and args.body_file, "digest needs --title and --body-file")
            result = {"revision": revision({"title": args.title, "body": args.body_file.read_text()})}
        else:
            product = Product()
            if args.command == "status":
                result = {"mode": product.policy["mode"], "active": product.lock("active"), "proposal_lock": product.lock("proposals")}
            elif args.command == "capacity":
                result = capacity(*product.all_proposals(), product.policy)
            elif args.command == "propose":
                require(args.title and args.body_file, "propose needs --title and --body-file")
                result = product.propose(args.title, args.body_file.read_text())
            else:
                require(args.issue and args.issue > 0, "A positive --issue is required")
                if args.command == "claim":
                    result = product.claim(args.issue, args.thread or "")
                elif args.command == "link":
                    result = product.link(args.issue, args.pull)
                elif args.command == "snapshot":
                    issue, comments, pulls = product.snapshot(args.issue)
                    result = {"revision": revision(issue), "bundle": bundle_id(revision(issue), pulls),
                              "pulls": [{"repository": p["repository"], "number": p["number"], "head": p["head"]["sha"], "base": p["base"]["sha"]} for p in pulls]}
                elif args.command == "record":
                    require(args.file, "record needs --file")
                    result = product.record(args.issue, json.loads(args.file.read_text()))
                elif args.command == "gate":
                    result = {"bundle": product.gate(args.issue)[3], "eligible": True}
                elif args.command == "authorize-release":
                    result = product.authorize_release(args.issue, args.repository, args.sha, args.delivery_id)
                else:
                    result = getattr(product, args.command)(args.issue)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f"Blocked: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
