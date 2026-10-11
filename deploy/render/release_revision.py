#!/usr/bin/env python3
"""Pin a Grund commit on its Render service and build that commit.

A push of chat or web main calls this from Gitea's post-receive hook and
redeploys that existing service. A push of main on any other repo whose
topics include nordman-app creates or updates one free static site named
exactly as the repo, serving that commit's tree at https://{repo}.onrender.com.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
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
APP_TOPIC = "nordman-app"
APP_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
PROTECTED_SERVICES = {"nordman-grund", "nordman-chat", "nordman-web"}
BOOTSTRAP_REPO = "https://github.com/signalbynoise/nordman-grund"
APP_BUILD = "node deploy/render/publish-app-site.mjs"
APP_PUBLISH_PATH = ".nordman-site"
DEFAULT_ORIGIN = "https://nordman-grund.onrender.com"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Render:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.redactions = [api_key]

    def redact(self, text: str) -> str:
        redacted = text
        for secret in self.redactions:
            if secret:
                redacted = redacted.replace(secret, "[redacted]")
        return redacted

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
            detail = self.redact(error.read().decode("utf-8", "replace")[:200])
            raise RuntimeError(f"render {method} {path} {error.code} {detail}") from error

    def find_service(self, name: str) -> str:
        service_id = self.find_service_id(name)
        if not service_id:
            raise RuntimeError(f"missing service {name}")
        return service_id

    def find_service_id(self, name: str) -> str | None:
        query = urllib.parse.urlencode({"name": name, "limit": "20"})
        _status, body = self.request("GET", f"/services?{query}")
        for row in body or []:
            service = row.get("service", row)
            if service.get("name") == name:
                return service["id"]
        return None

    def service_url(self, service_id: str) -> str:
        _status, body = self.request("GET", f"/services/{service_id}")
        service = body.get("service", body) if isinstance(body, dict) else {}
        details = service.get("serviceDetails") or {}
        return str(details.get("url") or "")

    def create_static_site(self, payload: dict) -> str:
        _status, body = self.request("POST", "/services", payload)
        service = body.get("service", body) if isinstance(body, dict) else {}
        service_id = service.get("id")
        if not service_id:
            raise RuntimeError("render did not return a service id")
        return service_id

    def delete_service(self, service_id: str) -> None:
        self.request("DELETE", f"/services/{service_id}")

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


def parse_topics(value: str) -> list[str]:
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def app_service_name(owner: str, repo: str, topics: list[str]) -> str | None:
    # Platform repos keep their existing services. An app site is the repo name
    # itself, which is the hostname Chat already promised.
    name = repo.strip()
    if service_from_names(owner, name) or name.lower().endswith(".wiki"):
        return None
    if name in PROTECTED_SERVICES or name.lower() in PROTECTED_SERVICES:
        return None
    if APP_TOPIC not in {topic.strip().lower() for topic in topics}:
        return None
    if not APP_SLUG.fullmatch(name):
        return None
    return name


def main_shas(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[2] != "refs/heads/main":
            continue
        new = parts[1].strip()
        if SHA.fullmatch(new):
            found.append(new)
    return found


def app_env(origin: str, owner: str, name: str, sha: str, token: str) -> dict[str, str]:
    return {
        "GRUND_URL": origin.rstrip("/"),
        "GRUND_OWNER": owner,
        "GRUND_NAME": name,
        "GRUND_DEPLOY_TOKEN": token,
        "GRUND_SOURCE_REVISION": sha,
        "NODE_VERSION": "22",
    }


def static_site_payload(name: str, owner: str, sha: str, token: str, origin: str, workspace: str) -> dict:
    return {
        "type": "static_site",
        "name": name,
        "ownerId": workspace,
        "repo": BOOTSTRAP_REPO,
        "branch": "main",
        "autoDeploy": "no",
        "autoDeployTrigger": "off",
        "envVars": [{"key": key, "value": value} for key, value in app_env(origin, owner, name, sha, token).items()],
        "serviceDetails": {
            "buildCommand": APP_BUILD,
            "publishPath": APP_PUBLISH_PATH,
            "pullRequestPreviewsEnabled": "no",
            "previews": {"generation": "off"},
            "renderSubdomainPolicy": "enabled",
            "headers": [
                {"path": "/", "name": "Cache-Control", "value": "no-cache"},
                {"path": "/index.html", "name": "Cache-Control", "value": "no-cache"},
            ],
        },
    }


def upsert_env(render: Render, service_id: str, values: dict[str, str]) -> bool:
    current = render.env_vars(service_id)
    merged = [item for item in current if item["key"] not in values]
    changed = False
    for key, value in values.items():
        old = next((item["value"] for item in current if item["key"] == key), None)
        if old != value:
            changed = True
        merged.append({"key": key, "value": value})
    if changed:
        render.put_env(service_id, merged)
    return changed


def ensure_app_site(render: Render, name: str, owner: str, sha: str, token: str, origin: str, workspace: str) -> str:
    if not SHA.fullmatch(sha):
        raise RuntimeError("revision must be the full commit SHA")
    expected = f"https://{name}.onrender.com"
    render.redactions.append(token)
    service_id = render.find_service_id(name)
    created = service_id is None
    if created:
        service_id = render.create_static_site(static_site_payload(name, owner, sha, token, origin, workspace))
    url = render.service_url(service_id).rstrip("/")
    if url != expected:
        if created:
            render.delete_service(service_id)
        raise RuntimeError(f"{name} is {url or 'missing'}, expected {expected}")
    upsert_env(render, service_id, app_env(origin, owner, name, sha, token))
    outcome = pin_and_deploy(render, name, sha)
    if created:
        return "created"
    return outcome


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
    return [(service, sha) for sha in main_shas(text)]


def in_progress(deploys: list[dict]) -> bool:
    return any(item.get("status") not in TERMINAL for item in deploys)


def live_has_revision(render: Render, service_id: str, sha: str) -> bool:
    for deploy in render.deploys(service_id):
        if deploy.get("status") != "live":
            continue
        start = deploy.get("startedAt") or deploy.get("createdAt")
        end = deploy.get("finishedAt")
        if not start or not end:
            return False
        return fetched_revision(render.logs(service_id, start, end), sha)
    return False


def pin_and_deploy(render: Render, service: str, sha: str) -> str:
    if not SHA.fullmatch(sha):
        raise RuntimeError("revision must be the full commit SHA")
    service_id = render.find_service(service)
    current = next(
        (item["value"] for item in render.env_vars(service_id) if item["key"] == "GRUND_SOURCE_REVISION"),
        "",
    )
    if current == sha and (
        in_progress(render.deploys(service_id)) or live_has_revision(render, service_id, sha)
    ):
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
    instruction = ""
    saw_revision = False
    cached = False
    for line in lines:
        if "fetch-source.mjs" in line and line.lstrip().startswith("#"):
            step = line.split()[0]
            instruction = line
        if step and line.startswith(f"{step} ") and "CACHED" in line:
            cached = True
        if f"revision: {sha}" in line:
            saw_revision = True
    # A cached step is that commit only when the fetch instruction itself contains the SHA.
    if cached:
        return sha in instruction
    return saw_revision


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


def grund_origin() -> str:
    return os.environ.get("GRUND_PUBLIC_ORIGIN", DEFAULT_ORIGIN).rstrip("/")


def workspace_id() -> str:
    return os.environ.get("RENDER_WORKSPACE_ID", "tea-csp7qr3gbbvc73d1fvqg")


def deploy_token(render: Render) -> str:
    service_id = render.find_service("nordman-web")
    token = next(
        (item["value"] for item in render.env_vars(service_id) if item["key"] == "GRUND_DEPLOY_TOKEN"),
        "",
    )
    if token:
        render.redactions.append(token)
    return token


def gitea_topics(origin: str, token: str, owner: str, repo: str) -> list[str]:
    quoted = f"{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"
    req = urllib.request.Request(
        f"{origin}/api/v1/repos/{quoted}",
        headers={"Authorization": f"token {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as response:
            body = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"grund topics {error.code}") from error
    topics = body.get("topics") if isinstance(body, dict) else None
    if not isinstance(topics, list):
        return []
    return [str(topic).strip().lower() for topic in topics if str(topic).strip()]


def topics_for_repo(render: Render, owner: str, repo: str, token: str) -> list[str]:
    if "GITEA_REPO_TOPICS" in os.environ:
        topics = parse_topics(os.environ["GITEA_REPO_TOPICS"])
        if APP_TOPIC in topics:
            return topics
    if not token:
        if "GITEA_REPO_TOPICS" in os.environ:
            return parse_topics(os.environ["GITEA_REPO_TOPICS"])
        return []
    return gitea_topics(grund_origin(), token, owner, repo)


def schedule_topic_recheck(owner: str, repo: str, sha: str) -> None:
    # The contents API push finishes before Chat's topic update. Look again
    # after this hook returns so that later topic write still publishes.
    if os.environ.get("NORDMAN_APP_RECHECK") == "1":
        return
    env = os.environ.copy()
    env["NORDMAN_APP_RECHECK"] = "1"
    env["NORDMAN_RELEASE_SHA"] = sha
    env["GITEA_REPO_USER_NAME"] = owner
    env["GITEA_REPO_NAME"] = repo
    env.pop("GITEA_REPO_TOPICS", None)
    log_path = os.environ.get("NORDMAN_APP_RECHECK_LOG", "/repos/gitea/log/app-release.log")
    log = subprocess.DEVNULL
    try:
        log = open(log_path, "a", encoding="utf-8")
    except OSError:
        log = subprocess.DEVNULL
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--app-recheck"],
        env=env,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
    )
    if log is not subprocess.DEVNULL:
        log.close()


def release_targets(render: Render, services: list[tuple[str, str]], owner: str, repo: str, shas: list[str]) -> int:
    failed = False
    for service, sha in services:
        try:
            outcome = pin_and_deploy(render, service, sha)
            print(outcome)
            print(f"[info] [grund:release] {service} {sha} {outcome}", file=sys.stderr)
        except Exception as error:
            failed = True
            print(f"[warn] [grund:release] {service} {render.redact(str(error))}", file=sys.stderr)
    if services or not shas or not app_service_name(owner, repo, [APP_TOPIC]):
        return 1 if failed and os.environ.get("NORDMAN_RELEASE_STRICT") == "1" else 0
    try:
        token = deploy_token(render)
        topics = topics_for_repo(render, owner, repo, token)
    except Exception as error:
        failed = True
        print(f"[warn] [grund:release] {repo} {render.redact(str(error))}", file=sys.stderr)
        return 1 if os.environ.get("NORDMAN_RELEASE_STRICT") == "1" else 0
    name = app_service_name(owner, repo, topics)
    if not name:
        for sha in shas:
            schedule_topic_recheck(owner, repo, sha)
        return 0
    if not token:
        print("[warn] [grund:release] GRUND_DEPLOY_TOKEN is not set", file=sys.stderr)
        return 1 if os.environ.get("NORDMAN_RELEASE_STRICT") == "1" else 0
    for sha in shas:
        try:
            outcome = ensure_app_site(render, name, owner, sha, token, grund_origin(), workspace_id())
            print(outcome)
            print(f"[info] [grund:release] {name} {sha} {outcome}", file=sys.stderr)
        except Exception as error:
            failed = True
            print(f"[warn] [grund:release] {name} {render.redact(str(error))}", file=sys.stderr)
    return 1 if failed and os.environ.get("NORDMAN_RELEASE_STRICT") == "1" else 0


def main(argv: list[str]) -> int:
    load_release_env()
    if len(argv) >= 2 and argv[1] == "--app-recheck":
        time.sleep(8)
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
    owner = os.environ.get("GITEA_REPO_USER_NAME", "")
    repo = os.environ.get("GITEA_REPO_NAME", "")
    forced = os.environ.get("NORDMAN_RELEASE_SHA", "").strip()
    text = ""
    if forced:
        service = os.environ.get("NORDMAN_RELEASE_SERVICE") or service_name(git_dir, os.getcwd(), owner, repo)
        pairs = [(service, forced)] if service and SHA.fullmatch(forced) else []
        shas = [forced] if SHA.fullmatch(forced) else []
    else:
        text = sys.stdin.read()
        pairs = parse_push(git_dir, text, os.getcwd(), owner, repo)
        shas = main_shas(text)
        if not pairs and service_name(git_dir, os.getcwd(), owner, repo) and "refs/heads/main" in text:
            print(
                f"[warn] [grund:release] main push was not released owner={owner or '-'} repo={repo or '-'}",
                file=sys.stderr,
            )
    if not pairs and not shas:
        return 0
    key = os.environ.get("RENDER_API_KEY")
    if not key:
        if pairs or app_service_name(owner, repo, [APP_TOPIC]):
            print("[warn] [grund:release] RENDER_API_KEY is not set", file=sys.stderr)
            return 1 if os.environ.get("NORDMAN_RELEASE_STRICT") == "1" else 0
        return 0
    return release_targets(Render(key), pairs, owner, repo, shas)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except Exception as error:
        print(f"[warn] [grund:release] {error}", file=sys.stderr)
        raise SystemExit(1 if os.environ.get("NORDMAN_RELEASE_STRICT") == "1" else 0)
