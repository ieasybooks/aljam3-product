"""Pure policy decisions. Missing, stale, edited or ambiguous evidence fails closed."""

import fnmatch
import hashlib
import json
import re

PROPOSAL = re.compile(r"\A<!-- aljam3:proposal (\{[^\n]+\}) -->\n")
RECORD = re.compile(r"\A<!-- aljam3:record -->\n```json\n(.*?)\n```\s*\Z", re.S)
SECTIONS = ("Problem and audience", "Research and evidence", "Experience", "Scope and non-goals",
            "Acceptance criteria", "Validation", "Risks and rollout", "Success measure")
QA_AREAS = ("correctness", "security", "performance", "accessibility", "localization",
            "data_integrity", "regression", "compatibility", "experience")
ROLES = ("cto", "qa", "cpo", "ceo")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def revision(issue):
    return digest({"title": issue["title"], "body": issue.get("body") or ""})


def metadata(issue, policy):
    match = PROPOSAL.match(issue.get("body") or "")
    require(match, f"Issue #{issue.get('number', '?')} has no proposal metadata")
    data = json.loads(match[1])
    require(set(data) == {"key", "size", "kind", "repositories", "risk"}, "Unexpected proposal metadata")
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", data["key"]), "Invalid stable proposal key")
    require(data["size"] in policy["limits"]["size"], "Unknown size")
    require(data["kind"] in policy["limits"]["kind"], "Unknown kind")
    require(data["risk"] in ("normal", "human-delivery"), "Unknown risk")
    repos = data["repositories"]
    require(isinstance(repos, list) and repos and len(repos) == len(set(repos)), "Invalid repository scope")
    require(set(repos) <= set(policy["repositories"]), "Repository outside Aljam3")
    for section in SECTIONS:
        require(re.search(r"^## " + re.escape(section) + r"\n\n\S", issue["body"], re.M),
                f"Missing section/content: {section}")
    return data


def human_command(comments, policy, command, value):
    commands = []
    for comment in comments:
        if comment["user"]["id"] != policy["owner"]["id"]:
            continue
        if comment["created_at"] != comment["updated_at"]:
            continue
        line = (comment.get("body") or "").split("\n")[0].strip()
        match = re.fullmatch(r"/aljam3 (approve|changes|reject|pause|delivery) ([0-9a-f]{64})", line)
        if match and match[2] == value:
            commands.append((comment["id"], match[1]))
    if command == "delivery":
        commands = [c for c in commands if c[1] in ("delivery", "pause", "reject", "changes")]
    else:
        commands = [c for c in commands if c[1] != "delivery"]
    return bool(commands) and max(commands)[1] == command


def records(comments, login):
    output = []
    for comment in comments:
        if comment["user"]["login"] != login or comment["created_at"] != comment["updated_at"]:
            continue
        match = RECORD.match(comment.get("body") or "")
        if match:
            output.append((comment["id"], json.loads(match[1])))
    return sorted(output, key=lambda row: row[0])


def terminal(issue, comments, policy):
    rev = revision(issue)
    if human_command(comments, policy, "reject", rev):
        return True
    return any(r.get("type") == "released" and r.get("revision") == rev
               for _, r in records(comments, policy["gate"]["login"]))


def capacity(issues, comments_by_number, policy):
    counts = {dimension: dict.fromkeys(limits, 0) for dimension, limits in policy["limits"].items()
              if dimension in ("size", "kind")}
    keys = set()
    for issue in issues:
        if not (issue.get("body") or "").startswith("<!-- aljam3:proposal"):
            require(not any(l["name"] == "proposal" for l in issue.get("labels", [])),
                    f"Labelled proposal #{issue['number']} is malformed")
            continue
        data = metadata(issue, policy)
        require(data["key"] not in keys, "Duplicate proposal key")
        keys.add(data["key"])
        if terminal(issue, comments_by_number[issue["number"]], policy):
            continue
        for dimension in counts:
            counts[dimension][data[dimension]] += 1
    for dimension, categories in counts.items():
        for category, count in categories.items():
            require(count <= policy["limits"][dimension][category], f"{dimension}/{category} exceeds cap")
    return counts


def active(policy, issue_number=None, live=False):
    require(policy["mode"] in ("pilot", "live"), "Automation is off")
    require(policy["worker"]["id"] and policy["worker"]["login"], "Worker identity is not configured")
    require(policy["worker"]["id"] != policy["owner"]["id"], "Worker must be separate from the owner")
    require(policy["gate"]["app_id"] and policy["gate"]["login"], "Dedicated delivery GitHub App is not configured")
    require(policy["gate"]["login"] not in (policy["worker"]["login"], policy["owner"]["login"]),
            "Delivery App must be separate from the worker and owner")
    if policy["mode"] == "pilot":
        require(issue_number == policy["pilot_issue"] and issue_number is not None, "Pilot is restricted to one issue")
    if live:
        require(policy["mode"] == "live", "Production delivery is disabled during the pilot")


def approved(issue, comments, policy):
    metadata(issue, policy)
    require(issue["state"] == "open", "Proposal must remain open until released/rejected")
    require(human_command(comments, policy, "approve", revision(issue)),
            "Current proposal revision has no current human approval")


def bundle_id(rev, pulls):
    return digest({"revision": rev, "pulls": sorted(
        [{"repository": p["repository"], "number": p["number"], "head": p["head"]["sha"],
          "base": p["base"]["sha"]} for p in pulls], key=lambda p: p["repository"])})


def reviews(comments, policy, bundle):
    latest = {}
    for comment_id, record in records(comments, policy["worker"]["login"]):
        if record.get("type") == "review" and record.get("bundle") == bundle and record.get("role") in ROLES:
            latest[record["role"]] = (comment_id, record)
    require(set(latest) == set(ROLES), "CTO, QA, CPO and CEO evidence is required for this bundle")
    previous, task_ids = 0, set()
    for role in ROLES:
        comment_id, record = latest[role]
        require(comment_id > previous, "Reviews must follow CTO → QA → CPO → CEO")
        previous = comment_id
        require(record.get("verdict") == "pass", f"{role.upper()} has not passed")
        task = record.get("task_id")
        require(isinstance(task, str) and task.strip() and task not in task_ids, "Use independent T3 task IDs for each role")
        task_ids.add(task)
        require(isinstance(record.get("summary"), str) and record["summary"].strip(), "Review summary is required")
        evidence = record.get("evidence")
        require(isinstance(evidence, list) and evidence and all(isinstance(e, str) and e.startswith("https://github.com/") for e in evidence),
                "Review must link durable GitHub evidence")
        require(record.get("unresolved") == [], "Resolve findings before final approval")
        if role == "qa":
            areas = record.get("areas", {})
            require(all(isinstance(areas.get(area), str) and areas[area].strip() for area in QA_AREAS),
                    "QA must address every review area, including justified N/A")
    return {role: record for role, (_, record) in latest.items()}


def check_runs_pass(checks, required):
    for name in required:
        matching = [c for c in checks if c["name"] == name and c.get("app", {}).get("slug") == "github-actions"]
        require(matching, f"Missing CI check: {name}")
        newest = max(matching, key=lambda c: c["id"])
        require(newest["status"] == "completed" and newest["conclusion"] == "success", f"CI has not passed: {name}")


def needs_human_delivery(data, pulls, policy):
    return data["risk"] == "human-delivery" or any(
        fnmatch.fnmatchcase(path, pattern) for pull in pulls for path in pull["files"]
        for pattern in policy["human_delivery_paths"])


def delivery(issue, comments, pulls, policy):
    active(policy, issue["number"])
    approved(issue, comments, policy)
    data = metadata(issue, policy)
    require(len(pulls) == len(data["repositories"]) and {p["repository"] for p in pulls} == set(data["repositories"]),
            "Exactly one PR per approved repository is required")
    rev = revision(issue)
    for pull in pulls:
        repo = pull["repository"]
        require(pull["head"]["repo"]["full_name"] == repo, "Fork PRs are outside autonomous delivery")
        require(pull["base"]["ref"] == policy["repositories"][repo]["branch"], "Unexpected target branch")
        require(pull["state"] == "open" and not pull["draft"], "PR must be open and ready")
        require(pull["mergeable"] is True, "Mergeability is unknown or conflicting; retry after GitHub computes it")
        require(pull["base"]["sha"] == pull["current_base"], "Base changed; refresh the bundle")
        require(pull["base_is_ancestor"], "PR must include the current base and pass CI again")
        require(f"Product issue: https://github.com/{policy['product_repo']}/issues/{issue['number']}" in (pull.get("body") or ""),
                "PR is missing its product issue link")
        require(f"Proposal revision: {rev}" in (pull.get("body") or ""), "PR proposal revision is stale")
        require(not pull.get("changes_requested"), "A current PR review requests changes")
        check_runs_pass(pull["checks"], policy["repositories"][repo]["checks"])
    bundle = bundle_id(rev, pulls)
    reviews(comments, policy, bundle)
    if needs_human_delivery(data, pulls, policy):
        require(human_command(comments, policy, "delivery", bundle), f"Sensitive delivery requires /aljam3 delivery {bundle}")
    return bundle


def render_record(record):
    return "<!-- aljam3:record -->\n```json\n" + json.dumps(record, ensure_ascii=False, indent=2) + "\n```"
