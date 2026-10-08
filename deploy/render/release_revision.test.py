#!/usr/bin/env python3
import unittest

from release_revision import (
    fetched_revision,
    parse_push,
    pin_and_deploy,
    service_from_names,
    service_name,
)

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


if __name__ == "__main__":
    unittest.main()
