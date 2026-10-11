#!/usr/bin/env python3
import unittest

from release_revision import (
    app_service_name,
    default_app_service_name,
    ensure_app_site,
    fetched_revision,
    parse_push,
    pin_and_deploy,
    service_from_names,
    service_name,
    static_site_payload,
)

SITE = "nordman-eriklydecker-clipshare"

SHA = "8358cb61109041c00fbb9e9a48f5d30cc72a6e32"
OLDER = "8ddb0554a00ac5bcc4f0eddc0b04529222ca560d"


class FakeRender:
    def __init__(self, revision="", deploys=None):
        self.revision = revision
        self._deploys = list(deploys or [])
        self.puts = 0
        self.triggers = 0

    def find_service(self, name):
        return f"id-{name}"

    def env_vars(self, _service_id):
        return [
            {"key": "GRUND_URL", "value": "https://nordman-grund.onrender.com"},
            {"key": "GRUND_SOURCE_REVISION", "value": self.revision},
        ]

    def put_env(self, _service_id, vars):
        self.puts += 1
        self.revision = next(item["value"] for item in vars if item["key"] == "GRUND_SOURCE_REVISION")
        kept = [item["key"] for item in vars]
        if kept[0] != "GRUND_URL":
            raise AssertionError("env replace dropped existing keys")

    def deploys(self, _service_id):
        return list(self._deploys)

    def trigger(self, _service_id):
        self.triggers += 1
        self._deploys.insert(0, {"id": "dep-new", "status": "build_in_progress", "createdAt": "2026-10-07T16:00:00Z"})


class ReleaseRevisionTest(unittest.TestCase):
    def test_push_of_main_selects_the_service_and_sha(self):
        git_dir = "/repos/git/repositories/nordman/chat.git"
        text = f"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa {SHA} refs/heads/main\n"
        self.assertEqual(parse_push(git_dir, text), [("nordman-chat", SHA)])
        self.assertEqual(parse_push(git_dir, f"old {SHA} refs/heads/topic\n"), [])
        self.assertEqual(parse_push("/tmp/notes.git", text), [])
        self.assertEqual(service_name("/repos/git/repositories/Nordman/web.git"), "nordman-web")

    def test_bare_repo_hook_uses_cwd_when_git_dir_is_dot(self):
        text = f"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa {SHA} refs/heads/main\n"
        cwd = "/repos/git/repositories/nordman/chat.git"
        self.assertEqual(parse_push(".", text, cwd), [("nordman-chat", SHA)])
        self.assertIsNone(service_name(".", "/tmp"))

    def test_gitea_hook_environment_names_the_repository(self):
        text = f"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa {SHA} refs/heads/main\n"
        self.assertEqual(
            parse_push(".", text, "/tmp", "Nordman", "chat"),
            [("nordman-chat", SHA)],
        )
        self.assertIsNone(service_from_names("Nordman", "chat.wiki"))

    def test_new_sha_updates_the_pin_and_starts_a_build(self):
        render = FakeRender(revision=OLDER, deploys=[{"id": "old", "status": "live"}])
        self.assertEqual(pin_and_deploy(render, "nordman-chat", SHA), "started")
        self.assertEqual(render.revision, SHA)
        self.assertEqual(render.puts, 1)
        self.assertEqual(render.triggers, 1)

    def test_same_sha_already_building_does_not_start_another(self):
        render = FakeRender(
            revision=SHA,
            deploys=[{"id": "dep", "status": "build_in_progress"}],
        )
        self.assertEqual(pin_and_deploy(render, "nordman-chat", SHA), "already")
        self.assertEqual(render.triggers, 0)
        self.assertEqual(render.puts, 0)

    def test_cached_fetch_is_not_a_successful_release(self):
        cached = [
            "#11 [stage-0  8/10] RUN echo grund-source-revision && node /runtime/fetch-source.mjs --out /app",
            "#11 CACHED",
        ]
        fetched = [
            "#11 [stage-0  8/10] RUN echo grund-source-revision && node /runtime/fetch-source.mjs --out /app",
            f"grund-source-revision {SHA}",
            f"[info] [runtime:fetch] extracted nordman/chat {{ revision: {SHA}, files: 10 }}",
        ]
        self.assertFalse(fetched_revision(cached, SHA))
        self.assertTrue(fetched_revision(fetched, SHA))
        self.assertFalse(fetched_revision(fetched, OLDER))
        cached_this_sha = [
            f'#11 [stage-0  8/10] RUN echo "grund-source-revision {SHA}" && node /runtime/fetch-source.mjs --out /app',
            "#11 CACHED",
        ]
        self.assertTrue(fetched_revision(cached_this_sha, SHA))
        self.assertFalse(fetched_revision(cached_this_sha, OLDER))


class AppRender:
    def __init__(self, service_id=None, revision="", url=f"https://{SITE}.onrender.com", deploys=None):
        self.service_id = service_id
        self.url = url
        self.env = []
        if revision:
            self.env.append({"key": "GRUND_SOURCE_REVISION", "value": revision})
        self.env.append({"key": "GRUND_URL", "value": "https://nordman-grund.onrender.com"})
        self._deploys = list(deploys or [])
        self.created = []
        self.deleted = []
        self.triggers = 0
        self.redactions = []

    def find_service_id(self, _name):
        return self.service_id

    def find_service(self, name):
        if not self.service_id:
            raise RuntimeError(f"missing service {name}")
        return self.service_id

    def service_url(self, _service_id):
        return self.url

    def create_static_site(self, payload):
        self.created.append(payload)
        self.service_id = "srv-clipshare"
        return self.service_id

    def delete_service(self, service_id):
        self.deleted.append(service_id)

    def env_vars(self, _service_id):
        return list(self.env)

    def put_env(self, _service_id, vars):
        self.env = list(vars)

    def deploys(self, _service_id):
        return list(self._deploys)

    def trigger(self, _service_id):
        self.triggers += 1
        self._deploys.insert(0, {"id": "dep-new", "status": "build_in_progress", "createdAt": "2026-10-11T00:00:00Z"})

    def logs(self, *_args):
        return []


class AppSiteTest(unittest.TestCase):
    def test_topic_selects_the_namespaced_site_and_leaves_other_repos_alone(self):
        self.assertEqual(app_service_name("eriklydecker", "clipshare", ["nordman-app"]), SITE)
        self.assertEqual(app_service_name("ErikLydecker", "ClipShare", ["nordman-app"]), SITE)
        self.assertIsNone(app_service_name("eriklydecker", "clipshare", []))
        self.assertIsNone(app_service_name("Nordman", "chat", ["nordman-app"]))
        self.assertIsNone(app_service_name("Nordman", "web", ["nordman-app"]))
        self.assertIsNone(app_service_name("eriklydecker", "nordman-grund", ["nordman-app"]))

    def test_service_file_pins_the_same_site_and_a_bare_name_is_ignored(self):
        pinned = app_service_name(
            "eriklydecker", "clipshare", ["nordman-app"], f"  {SITE}  \n"
        )
        self.assertEqual(pinned, SITE)
        bare = app_service_name("eriklydecker", "clipshare", ["nordman-app"], "clipshare\n")
        self.assertEqual(bare, SITE)

    def test_long_name_is_cut_to_63_and_loses_a_trailing_hyphen(self):
        owner = "a" * 54
        self.assertEqual(len(f"nordman-{owner}-"), 63)
        name = default_app_service_name(owner, "clipshare")
        self.assertEqual(name, f"nordman-{owner}")
        self.assertLessEqual(len(name), 63)
        self.assertFalse(name.endswith("-"))

    def test_first_push_creates_one_free_static_site_named_for_the_owner_and_repo(self):
        render = AppRender()
        outcome = ensure_app_site(
            render, SITE, "eriklydecker", "clipshare", SHA, "deploy-token", "https://nordman-grund.onrender.com/", "tea-workspace"
        )
        self.assertEqual(outcome, "created")
        self.assertEqual(len(render.created), 1)
        payload = render.created[0]
        self.assertEqual(payload["type"], "static_site")
        self.assertEqual(payload["name"], SITE)
        self.assertEqual(payload["autoDeployTrigger"], "off")
        self.assertNotIn("autoDeploy", payload)
        self.assertNotIn("plan", payload)
        self.assertEqual(payload["repo"], "https://github.com/signalbynoise/nordman-grund")
        self.assertEqual(payload["serviceDetails"]["publishPath"], ".nordman-site")
        self.assertEqual(payload["serviceDetails"]["buildCommand"], "node deploy/render/publish-app-site.mjs")
        env = {item["key"]: item["value"] for item in render.env}
        self.assertEqual(env["GRUND_NAME"], "clipshare")
        self.assertEqual(env["GRUND_OWNER"], "eriklydecker")
        self.assertEqual(env["GRUND_SOURCE_REVISION"], SHA)
        self.assertEqual(env["GRUND_URL"], "https://nordman-grund.onrender.com")
        self.assertEqual(render.triggers, 1)

    def test_later_push_updates_the_same_service(self):
        render = AppRender(service_id="srv-clipshare", revision=OLDER)
        outcome = ensure_app_site(
            render, SITE, "eriklydecker", "clipshare", SHA, "deploy-token", "https://nordman-grund.onrender.com", "tea-workspace"
        )
        self.assertEqual(outcome, "started")
        self.assertEqual(render.created, [])
        self.assertEqual(render.deleted, [])
        self.assertEqual(render.service_id, "srv-clipshare")
        self.assertEqual(render.triggers, 1)
        env = {item["key"]: item["value"] for item in render.env}
        self.assertEqual(env["GRUND_SOURCE_REVISION"], SHA)
        self.assertEqual(env["GRUND_URL"], "https://nordman-grund.onrender.com")

    def test_same_revision_already_building_does_not_trigger(self):
        render = AppRender(
            service_id="srv-clipshare",
            revision=SHA,
            deploys=[{"id": "dep", "status": "build_in_progress"}],
        )
        render.env.append({"key": "GRUND_OWNER", "value": "eriklydecker"})
        render.env.append({"key": "GRUND_NAME", "value": "clipshare"})
        render.env.append({"key": "GRUND_DEPLOY_TOKEN", "value": "deploy-token"})
        render.env.append({"key": "NODE_VERSION", "value": "22"})
        outcome = ensure_app_site(
            render, SITE, "eriklydecker", "clipshare", SHA, "deploy-token", "https://nordman-grund.onrender.com", "tea-workspace"
        )
        self.assertEqual(outcome, "already")
        self.assertEqual(render.triggers, 0)
        self.assertEqual(render.created, [])

    def test_wrong_hostname_is_not_kept(self):
        render = AppRender(url=f"https://{SITE}-abcd.onrender.com")
        with self.assertRaises(RuntimeError):
            ensure_app_site(
                render, SITE, "eriklydecker", "clipshare", SHA, "deploy-token", "https://nordman-grund.onrender.com", "tea-workspace"
            )
        self.assertEqual(render.deleted, ["srv-clipshare"])
        self.assertEqual(render.triggers, 0)

    def test_payload_pins_the_commit_the_site_must_fetch(self):
        payload = static_site_payload(
            SITE, "eriklydecker", "clipshare", SHA, "deploy-token", "https://nordman-grund.onrender.com", "tea-workspace"
        )
        values = {item["key"]: item["value"] for item in payload["envVars"]}
        self.assertEqual(values["GRUND_SOURCE_REVISION"], SHA)
        self.assertNotIn("plan", payload["serviceDetails"])


if __name__ == "__main__":
    unittest.main()
