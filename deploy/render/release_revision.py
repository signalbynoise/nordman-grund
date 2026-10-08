#!/usr/bin/env python3
"""Pin a Grund commit on its Render service and build that commit.

A push of chat or web main calls this from Gitea's post-receive hook.
publish.sh calls the same script. The build argument is the commit SHA, so
Docker cannot reuse a fetch of an older tree.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.render.com/v1"
SHA = re.compile(r"^[0-9a-f]{40}$")
TERMINAL = {
    "live",
    "deactivated",
    "build_failed",
    "update_failed",
    "canceled",
    "pre_deploy_failed",
}
SERVICES = {"chat": "nordman-chat", "web": "nordman-web"}
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Render:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def request(self, method: str, path: str, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            f"{API}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:200]
            raise RuntimeError(f"render {method} {path} {error.code} {detail}") from error

    def find_service(self, name: str) -> str:
        query = urllib.parse.urlencode({"name": name, "limit": "20"})
        _status, body = self.request("GET", f"/services?{query}")
        for row in body or []:
            service = row.get("service", row)
            if service.get("name") == name:
                return service["id"]
        raise RuntimeError(f"missing service {name}")

    def env_vars(self, service_id: str) -> list[dict]:
        _status, body = self.request("GET", f"/services/{service_id}/env-vars?limit=100")
        vars = []
        for row in body or []:
            item = row.get("envVar", row)
            vars.append({"key": item["key"], "value": item.get("value") or ""})
        return vars

    def put_env(self, service_id: str, vars: list[dict]) -> None:
        self.request("PUT", f"/services/{service_id}/env-vars", vars)

    def deploys(self, service_id: str) -> list[dict]:
        _status, body = self.request("GET", f"/services/{service_id}/deploys?limit=10")
        return [row.get("deploy", row) for row in body or []]

    def trigger(self, service_id: str) -> None:
        self.request("POST", f"/services/{service_id}/deploys", {})

    def logs(self, service_id: str, start: str, end: str) -> list[str]:
        messages = []
        params = {
            "ownerId": os.environ.get("RENDER_WORKSPACE_ID", "tea-csp7qr3gbbvc73d1fvqg"),
            "resource": service_id,
            "startTime": start,
            "endTime": end,
            "direction": "forward",
            "limit": "100",
        }
        while True:
            query = urllib.parse.urlencode(params)
            _status, body = self.request("GET", f"/logs?{query}")
            for row in body.get("logs") or []:
                messages.append(row.get("message") or "")
            if not body.get("hasMore"):
                return messages
            params["startTime"] = body["nextStartTime"]
            params["endTime"] = body.get("nextEndTime") or end


def service_from_names(owner: str, name: str) -> str | None:
    repo_name = name.strip().lower()
    if repo_name.endswith(".wiki"):
        return None
    if owner.strip().lower() == "nordman" and repo_name in SERVICES:
        return SERVICES[repo_name]
    return None


def repository_path(git_dir: str, cwd: str) -> str:
    raw = git_dir.strip()
    if raw in ("", "."):
        return cwd
    if os.path.isabs(raw):
        return raw
    return os.path.normpath(os.path.join(cwd, raw))


def service_name(git_dir: str, cwd: str = "", owner: str = "", repo: str = "") -> str | None:
    # Git sets GIT_DIR=. for a bare repo and runs the hook with that repo as cwd.
    # Gitea also exports GITEA_REPO_USER_NAME and GITEA_REPO_NAME for custom hooks.
    named = service_from_names(owner, repo)
    if named:
        return named
    path = repository_path(git_dir, cwd).replace("\\", "/").rstrip("/").lower()
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[-2] == "nordman" and parts[-1] in SERVICES:
        return SERVICES[parts[-1]]
    return None


def parse_push(
    git_dir: str,
    text: str,
    cwd: str = "",
    owner: str = "",
    repo: str = "",
) -> list[tuple[str, str]]:
    service = service_name(git_dir, cwd, owner, repo)
    if not service:
        return []
    releases = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[2] != "refs/heads/main":
            continue
        new = parts[1].strip()
        if SHA.fullmatch(new):
            releases.append((service, new))
    return releases


def in_progress(deploys: list[dict]) -> bool:
    return any(item.get("status") not in TERMINAL for item in deploys)


def pin_and_deploy(render: Render, service: str, sha: str) -> str:
    if not SHA.fullmatch(sha):
        raise RuntimeError("revision must be the full commit SHA")
    service_id = render.find_service(service)
    current = next(
        (item["value"] for item in render.env_vars(service_id) if item["key"] == "GRUND_SOURCE_REVISION"),
        "",
    )
    if current == sha and in_progress(render.deploys(service_id)):
        return "already"
    if current != sha:
        vars = render.env_vars(service_id)
        updated = [item for item in vars if item["key"] != "GRUND_SOURCE_REVISION"]
        updated.append({"key": "GRUND_SOURCE_REVISION", "value": sha})
        render.put_env(service_id, updated)
    render.trigger(service_id)
    return "started"


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


def fetched_revision(messages: list[str], sha: str) -> bool:
    lines = [strip_ansi(line) for line in messages]
    step = None
    saw_revision = False
    cached = False
    for line in lines:
        if "fetch-source.mjs" in line and line.lstrip().startswith("#"):
            step = line.split()[0]
        if step and line.startswith(f"{step} ") and "CACHED" in line:
            cached = True
        if f"revision: {sha}" in line:
            saw_revision = True
    return saw_revision and not cached


def verify(render: Render, service: str, sha: str, since: str = "", timeout_s: int = 1500) -> dict:
    service_id = render.find_service(service)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        deploys = render.deploys(service_id)
        fresh = sorted(
            (
                item
                for item in deploys
                if not since or item.get("createdAt", "")[:19] >= since[:19]
            ),
            key=lambda item: item.get("createdAt", ""),
            reverse=True,
        )
        if not fresh:
            time.sleep(5)
            continue
        deploy = fresh[0]
        status = deploy.get("status")
        if status not in TERMINAL:
            time.sleep(10)
            continue
        if status != "live":
            raise RuntimeError(f"{service} deploy {deploy.get('id')} {status}")
        end = deploy.get("finishedAt") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        messages = render.logs(service_id, deploy.get("startedAt") or deploy["createdAt"], end)
        if fetched_revision(messages, sha):
            return {"id": deploy["id"], "status": status, "serviceId": service_id}
        raise RuntimeError(f"{service} deploy {deploy.get('id')} is live without fetching {sha}")
    raise RuntimeError(f"{service} deploy did not finish")


def load_release_env() -> None:
    if os.environ.get("RENDER_API_KEY"):
        return
    path = os.environ.get("NORDMAN_RELEASE_ENV", "/repos/gitea/custom/release.env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def main(argv: list[str]) -> int:
    load_release_env()
    if len(argv) >= 3 and argv[1] == "--verify":
        key = os.environ.get("RENDER_API_KEY")
        if not key:
            print("[grund] no RENDER_API_KEY; cannot verify the live build", file=sys.stderr)
            return 1
        result = verify(Render(key), argv[2], argv[3], argv[4] if len(argv) > 4 else "")
        print(
            f"[info] [grund:release] verified {argv[2]} {argv[3]} deploy {result['id']}",
            file=sys.stderr,
        )
        return 0

    git_dir = os.environ.get("GIT_DIR", "")
    forced = os.environ.get("NORDMAN_RELEASE_SHA", "").strip()
    if forced:
        service = os.environ.get("NORDMAN_RELEASE_SERVICE") or service_name(
            git_dir,
            os.getcwd(),
            os.environ.get("GITEA_REPO_USER_NAME", ""),
            os.environ.get("GITEA_REPO_NAME", ""),
        )
        pairs = [(service, forced)] if service else []
    else:
        text = sys.stdin.read()
        owner = os.environ.get("GITEA_REPO_USER_NAME", "")
        repo = os.environ.get("GITEA_REPO_NAME", "")
        pairs = parse_push(git_dir, text, os.getcwd(), owner, repo)
        if not pairs and "refs/heads/main" in text:
            print(
                f"[warn] [grund:release] main push was not released owner={owner or '-'} repo={repo or '-'} git_dir={git_dir or '-'}",
                file=sys.stderr,
            )
    if not pairs:
        return 0
    key = os.environ.get("RENDER_API_KEY")
    if not key:
        print("[warn] [grund:release] RENDER_API_KEY is not set", file=sys.stderr)
        return 1 if os.environ.get("NORDMAN_RELEASE_STRICT") == "1" else 0
    render = Render(key)
    failed = False
    for service, sha in pairs:
        try:
            outcome = pin_and_deploy(render, service, sha)
            print(f"[info] [grund:release] {service} {sha} {outcome}", file=sys.stderr)
        except Exception as error:
            failed = True
            print(f"[warn] [grund:release] {service} {error}", file=sys.stderr)
    if failed and os.environ.get("NORDMAN_RELEASE_STRICT") == "1":
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except Exception as error:
        print(f"[warn] [grund:release] {error}", file=sys.stderr)
        raise SystemExit(1 if os.environ.get("NORDMAN_RELEASE_STRICT") == "1" else 0)
