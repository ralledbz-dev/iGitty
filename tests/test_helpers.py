import base64
import unittest
from unittest.mock import Mock, patch

from app import (
    GitHubClient,
    GitHubError,
    format_date,
    validate_file_path,
    validate_repo_name,
)


def json_response(payload, status=200):
    response = Mock()
    response.ok = status < 400
    response.status_code = status
    response.content = b"{}"
    response.headers = {"content-type": "application/json"}
    response.json.return_value = payload
    return response


class ValidationTests(unittest.TestCase):
    def test_repository_name_accepts_github_names(self):
        self.assertEqual(validate_repo_name("my_project-2.0"), "my_project-2.0")

    def test_repository_name_rejects_path_and_empty_values(self):
        for value in ("", "../oops", "name/other", ".."):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_repo_name(value)

    def test_file_path_accepts_nested_relative_path(self):
        self.assertEqual(validate_file_path("docs/intro.md"), "docs/intro.md")

    def test_file_path_rejects_traversal_and_absolute_paths(self):
        for value in (
            "../secret",
            "/absolute.txt",
            "folder//file",
            "folder\\file",
            "./file",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_file_path(value)

    def test_format_date_uses_german_date_format(self):
        self.assertEqual(format_date("2025-02-03T10:11:12Z"), "03.02.2025")

    def test_format_date_handles_missing_or_invalid_values(self):
        self.assertEqual(format_date(None), "—")
        self.assertEqual(format_date("not-a-date"), "—")


class GitHubClientTests(unittest.TestCase):
    @patch("app.requests.request")
    def test_file_content_is_decoded_from_base64(self, request):
        request.return_value = json_response(
            {
                "type": "file",
                "size": 5,
                "encoding": "base64",
                "content": base64.b64encode(b"hello").decode("ascii"),
            }
        )
        client = GitHubClient("sample-token")
        data = client.get_contents("ralf", "demo", "docs/readme.txt", "main")
        self.assertEqual(data["text_content"], "hello")
        self.assertEqual(
            request.call_args.args[:2],
            ("GET", "https://api.github.com/repos/ralf/demo/contents"),
        )
        self.assertEqual(
            request.call_args.kwargs["params"],
            {"path": "docs/readme.txt", "ref": "main"},
        )
        self.assertEqual(
            request.call_args.kwargs["headers"]["Authorization"], "Bearer sample-token"
        )

    @patch("app.requests.request")
    def test_save_file_encodes_url_and_includes_commit_metadata(self, request):
        request.return_value = json_response({"content": {"path": "src/a file.py"}})
        client = GitHubClient("sample-token")
        client.save_file(
            "ralf",
            "demo",
            "src/a file.py",
            "print('ok')",
            "Update script",
            "main",
            "old-sha",
        )
        args = request.call_args
        self.assertEqual(args.args[0], "PUT")
        self.assertEqual(
            args.args[1],
            "https://api.github.com/repos/ralf/demo/contents/src/a%20file.py",
        )
        self.assertEqual(
            args.kwargs["json"],
            {
                "message": "Update script",
                "content": base64.b64encode(b"print('ok')").decode("ascii"),
                "branch": "main",
                "sha": "old-sha",
            },
        )

    @patch("app.requests.request")
    def test_unauthorized_response_has_safe_message(self, request):
        response = json_response({"message": "Bad credentials"}, status=401)
        request.return_value = response
        with self.assertRaisesRegex(GitHubError, "Token wurde abgelehnt"):
            GitHubClient("sample-token").get_user()

    def test_save_file_rejects_payload_over_one_megabyte(self):
        client = GitHubClient("sample-token")
        with self.assertRaisesRegex(ValueError, "höchstens 1 MB"):
            client.save_file(
                "ralf", "demo", "large.txt", "x" * (1024 * 1024 + 1), "Add file", "main"
            )


if __name__ == "__main__":
    unittest.main()

