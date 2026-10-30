import os
import unittest
from unittest.mock import Mock, patch

import requests

from gitea_client import GITEA_TOKEN_ENV, GiteaClient, GiteaError, validate_gitea_name


def response(payload=None, status=200):
    item = Mock()
    item.status_code = status
    item.ok = status < 400
    if payload is None:
        item.json.side_effect = ValueError("invalid json")
    else:
        item.json.return_value = payload
    return item


SOURCE_PUBLIC = {
    "owner": {"login": "octocat"},
    "name": "hello-world",
    "private": False,
    "description": "A demo repository",
}
SOURCE_PRIVATE = {**SOURCE_PUBLIC, "private": True}
MIGRATED = {
    "name": "hello-world",
    "owner": {"login": "mirror-owner"},
    "id": 7,
    "mirror": True,
}


class ValidationTests(unittest.TestCase):
    def test_names_are_stripped_and_safe(self):
        self.assertEqual(validate_gitea_name("  repo-1 "), "repo-1")

    def test_names_reject_traversal_empty_and_invalid_values(self):
        for value in ("", ".", "..", "a/b", "a\\b", "a b", "x" * 101, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_gitea_name(value)


class GiteaClientTests(unittest.TestCase):
    def setUp(self):
        self.client = GiteaClient("gitea-secret")

    def tearDown(self):
        self.client._session.close()

    @patch.dict(os.environ, {GITEA_TOKEN_ENV: " env-token "}, clear=True)
    def test_from_environment_uses_token_without_persisting_it(self):
        client = GiteaClient.from_environment()
        try:
            self.assertEqual(client._token, "env-token")
            self.assertNotIn(GITEA_TOKEN_ENV, client.__dict__)
        finally:
            client._session.close()

    @patch.dict(os.environ, {}, clear=True)
    def test_from_environment_requires_token(self):
        with self.assertRaisesRegex(GiteaError, "Kein Gitea-Token"):
            GiteaClient.from_environment()

    def test_user_request_has_token_auth_loopback_url_and_no_redirects(self):
        self.client._session.request = Mock(return_value=response({"login": "admin"}))
        self.assertEqual(self.client.get_user()["login"], "admin")
        call = self.client._session.request.call_args
        self.assertEqual(call.args, ("GET", "http://127.0.0.1:3000/api/v1/user"))
        self.assertEqual(call.kwargs["headers"]["Authorization"], "token gitea-secret")
        self.assertFalse(call.kwargs["allow_redirects"])
        self.assertEqual(call.kwargs["timeout"], (3.05, 15))
        self.assertFalse(self.client._session.trust_env)

    def test_get_repository_returns_none_only_for_404(self):
        self.client._session.request = Mock(return_value=response(status=404))
        self.assertIsNone(self.client.get_repository("owner", "repo"))

    def test_public_mirror_payload_omits_github_credentials(self):
        self.client._session.request = Mock(
            side_effect=[response(status=404), response(MIGRATED)]
        )
        result = self.client.create_mirror(
            SOURCE_PUBLIC, "mirror-owner", "hello-world", private=False
        )
        self.assertEqual(result, MIGRATED)
        call = self.client._session.request.call_args_list[1]
        self.assertEqual(call.args[1], "http://127.0.0.1:3000/api/v1/repos/migrate")
        self.assertEqual(call.kwargs["timeout"], (3.05, 600))
        self.assertEqual(
            call.kwargs["json"],
            {
                "clone_addr": "https://github.com/octocat/hello-world.git",
                "service": "git",
                "mirror": True,
                "repo_owner": "mirror-owner",
                "repo_name": "hello-world",
                "private": False,
                "description": "A demo repository",
            },
        )

    def test_private_mirror_requires_token_and_stays_private(self):
        with self.assertRaisesRegex(ValueError, "GitHub-Token"):
            self.client.create_mirror(SOURCE_PRIVATE, "mirror-owner", "hello-world")
        with self.assertRaisesRegex(ValueError, "privat"):
            self.client.create_mirror(
                SOURCE_PRIVATE,
                "mirror-owner",
                "hello-world",
                private=False,
                github_token="gh",
            )

    def test_private_mirror_includes_github_credentials(self):
        self.client._session.request = Mock(
            side_effect=[response(status=404), response(MIGRATED)]
        )
        self.client.create_mirror(
            SOURCE_PRIVATE, "mirror-owner", "hello-world", github_token="gh-secret"
        )
        payload = self.client._session.request.call_args_list[1].kwargs["json"]
        self.assertEqual(payload["auth_username"], "x-access-token")
        self.assertEqual(payload["auth_password"], "gh-secret")
        self.assertTrue(payload["private"])

    def test_existing_repository_is_refused_without_post(self):
        self.client._session.request = Mock(
            return_value=response({"name": "hello-world"})
        )
        with self.assertRaisesRegex(GiteaError, "existiert bereits"):
            self.client.create_mirror(SOURCE_PUBLIC, "mirror-owner", "hello-world")
        self.client._session.request.assert_called_once()

    def test_clone_url_is_not_trusted(self):
        source = {**SOURCE_PUBLIC, "clone_url": "https://evil.example/token.git"}
        self.client._session.request = Mock(
            side_effect=[response(status=404), response(MIGRATED)]
        )
        self.client.create_mirror(source, "mirror-owner", "hello-world", private=False)
        self.assertEqual(
            self.client._session.request.call_args_list[1].kwargs["json"]["clone_addr"],
            "https://github.com/octocat/hello-world.git",
        )

    def test_server_errors_do_not_expose_body(self):
        item = response({"message": "Bearer TOP-SECRET leaked body"}, status=422)
        self.client._session.request = Mock(return_value=item)
        with self.assertRaises(GiteaError) as raised:
            self.client.get_user()
        self.assertNotIn("TOP-SECRET", str(raised.exception))
        self.assertNotIn("Bearer", str(raised.exception))

    def test_migration_422_is_safe_and_helpful(self):
        self.client._session.request = Mock(
            side_effect=[response(status=404), response({"message": "secret"}, 422)]
        )
        with self.assertRaisesRegex(GiteaError, "ungültiger"):
            self.client.create_mirror(SOURCE_PUBLIC, "mirror-owner", "hello-world")

    def test_timeout_on_post_has_unclear_outcome_and_no_retry(self):
        self.client._session.request = Mock(
            side_effect=[response(status=404), requests.Timeout("secret")]
        )
        with self.assertRaisesRegex(GiteaError, "Ausgang ist unklar"):
            self.client.create_mirror(SOURCE_PUBLIC, "mirror-owner", "hello-world")
        self.assertEqual(self.client._session.request.call_count, 2)

    def test_malformed_success_response_is_not_claimed_as_success(self):
        self.client._session.request = Mock(
            side_effect=[response(status=404), response({})]
        )
        with self.assertRaisesRegex(GiteaError, "unvollständige"):
            self.client.create_mirror(SOURCE_PUBLIC, "mirror-owner", "hello-world")

    def test_non_mirror_response_is_not_success(self):
        self.client._session.request = Mock(
            side_effect=[response(status=404), response({**MIGRATED, "mirror": False})]
        )
        with self.assertRaisesRegex(GiteaError, "unvollständige"):
            self.client.create_mirror(SOURCE_PUBLIC, "mirror-owner", "hello-world")

    def test_redirect_is_rejected_without_following(self):
        self.client._session.request = Mock(
            return_value=response({"login": "admin"}, status=302)
        )
        with self.assertRaisesRegex(GiteaError, "HTTP 302"):
            self.client.get_user()
        self.client._session.request.assert_called_once()

    def test_invalid_user_response_is_rejected(self):
        self.client._session.request = Mock(return_value=response({"id": 1}))
        with self.assertRaisesRegex(GiteaError, "Benutzerantwort"):
            self.client.get_user()


if __name__ == "__main__":
    unittest.main()
