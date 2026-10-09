"""Small GitHub adapter. Authentication stays in gh/environment, never in files."""

import json
import subprocess


class GitHub:
    def request(self, path, method="GET", data=None):
        command = ["gh", "api", "-X", method, path]
        if data is not None:
            command += ["--input", "-"]
        result = subprocess.run(command, input=json.dumps(data) if data is not None else None,
                                text=True, capture_output=True, check=True)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def pages(self, path):
        separator = "&" if "?" in path else "?"
        rows = []
        for page in range(1, 1001):
            batch = self.request(f"{path}{separator}per_page=100&page={page}")
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise ValueError("Pagination limit reached; refusing an incomplete snapshot")

    def issues(self, repository):
        return [i for i in self.pages(f"repos/{repository}/issues?state=all") if "pull_request" not in i]

    def comments(self, repository, number):
        return self.pages(f"repos/{repository}/issues/{number}/comments")

    def comment(self, repository, number, body):
        return self.request(f"repos/{repository}/issues/{number}/comments", "POST", {"body": body})
