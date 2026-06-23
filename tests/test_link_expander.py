"""Tests for link_expander module."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.workflow_cli.link_expander import (
    LinkExpansionResult,
    LinkStatus,
    expand_links,
    extract_links,
)


class TestExtractLinks(unittest.TestCase):
    def test_extracts_https_url(self):
        result = extract_links("See https://example.com for details")
        self.assertIn("https://example.com", result)

    def test_extracts_http_url(self):
        result = extract_links("Visit http://example.org/page")
        self.assertIn("http://example.org/page", result)

    def test_extracts_relative_dot_slash_path(self):
        result = extract_links("See ./local.md for more")
        self.assertIn("./local.md", result)

    def test_extracts_parent_relative_path(self):
        result = extract_links("Reference ../bar.md here")
        self.assertIn("../bar.md", result)

    def test_extracts_subdir_path(self):
        result = extract_links("Check docs/baz.md for info")
        self.assertIn("docs/baz.md", result)

    def test_extracts_both_url_and_local_path(self):
        result = extract_links("See https://example.com and ./local.md")
        self.assertIn("https://example.com", result)
        self.assertIn("./local.md", result)

    def test_returns_list(self):
        result = extract_links("plain text with no links")
        self.assertIsInstance(result, list)

    def test_no_links(self):
        result = extract_links("plain text with no links")
        self.assertEqual(result, [])

    def test_multiple_urls(self):
        result = extract_links("https://a.com and https://b.com")
        self.assertIn("https://a.com", result)
        self.assertIn("https://b.com", result)


class TestLinkStatus(unittest.TestCase):
    def test_has_external(self):
        self.assertEqual(LinkStatus.EXTERNAL, "external")

    def test_has_local_found(self):
        self.assertEqual(LinkStatus.LOCAL_FOUND, "local_found")

    def test_has_local_missing(self):
        self.assertEqual(LinkStatus.LOCAL_MISSING, "local_missing")

    def test_all_values(self):
        values = {s.value for s in LinkStatus}
        self.assertEqual(values, {"external", "local_found", "local_missing"})


class TestLinkExpansionResult(unittest.TestCase):
    def test_is_dataclass_with_required_fields(self):
        result = LinkExpansionResult(url="https://example.com", status=LinkStatus.EXTERNAL)
        self.assertEqual(result.url, "https://example.com")
        self.assertEqual(result.status, LinkStatus.EXTERNAL)

    def test_content_preview_defaults_to_empty_string(self):
        result = LinkExpansionResult(url="x", status=LinkStatus.EXTERNAL)
        self.assertEqual(result.content_preview, "")

    def test_error_defaults_to_empty_string(self):
        result = LinkExpansionResult(url="x", status=LinkStatus.EXTERNAL)
        self.assertEqual(result.error, "")

    def test_can_set_content_preview(self):
        result = LinkExpansionResult(url="x", status=LinkStatus.LOCAL_FOUND, content_preview="hello")
        self.assertEqual(result.content_preview, "hello")

    def test_can_set_error(self):
        result = LinkExpansionResult(url="x", status=LinkStatus.LOCAL_MISSING, error="timeout")
        self.assertEqual(result.error, "timeout")


class TestExpandLinksLocalFiles(unittest.TestCase):
    def test_local_file_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("# Hello\nContent here")
            results = expand_links("See ./notes.md", base_path=Path(tmp))
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, LinkStatus.LOCAL_FOUND)
            self.assertIn("Hello", results[0].content_preview)

    def test_local_file_preview_max_500_chars(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.md"
            path.write_text("x" * 1000)
            results = expand_links("See ./big.md", base_path=Path(tmp))
            self.assertEqual(results[0].status, LinkStatus.LOCAL_FOUND)
            self.assertLessEqual(len(results[0].content_preview), 500)

    def test_hidden_local_file_is_not_previewed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("API_TOKEN=SECRET", encoding="utf-8")
            results = expand_links("See ./.env", base_path=Path(tmp))
            self.assertEqual(results[0].status, LinkStatus.LOCAL_FOUND)
            self.assertEqual(results[0].content_preview, "")
            self.assertIn("hidden", results[0].error.lower())
            self.assertNotIn("SECRET", results[0].error)

    def test_sensitive_local_file_is_not_previewed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secrets.txt"
            path.write_text("PASSWORD=SECRET", encoding="utf-8")
            results = expand_links("See ./secrets.txt", base_path=Path(tmp))
            self.assertEqual(results[0].status, LinkStatus.LOCAL_FOUND)
            self.assertEqual(results[0].content_preview, "")
            self.assertIn("sensitive", results[0].error.lower())
            self.assertNotIn("SECRET", results[0].error)

    def test_sensitive_local_directory_is_not_previewed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credentials" / "context.md"
            path.parent.mkdir()
            path.write_text("PASSWORD=SECRET", encoding="utf-8")
            results = expand_links("See credentials/context.md", base_path=Path(tmp))
            self.assertEqual(results[0].status, LinkStatus.LOCAL_FOUND)
            self.assertEqual(results[0].content_preview, "")
            self.assertIn("sensitive", results[0].error.lower())
            self.assertNotIn("SECRET", results[0].error)

    def test_local_file_missing(self):
        results = expand_links("See ./nonexistent.md", base_path=Path("/tmp"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, LinkStatus.LOCAL_MISSING)

    def test_local_file_missing_error_message(self):
        results = expand_links("See ./nonexistent.md", base_path=Path("/tmp"))
        self.assertIn("nonexistent.md", results[0].error)

    def test_parent_relative_path_outside_base_is_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "repo"
            base.mkdir()
            outside = root / "secret.md"
            outside.write_text("SECRET", encoding="utf-8")

            results = expand_links("See ../secret.md", base_path=base)

            self.assertEqual(results[0].status, LinkStatus.LOCAL_MISSING)
            self.assertEqual(results[0].content_preview, "")
            self.assertIn("outside base path", results[0].error)

    def test_local_file_url_field(self):
        results = expand_links("See ./nonexistent.md", base_path=Path("/tmp"))
        self.assertEqual(results[0].url, "./nonexistent.md")

    def test_deduplicates_same_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dup.md"
            path.write_text("content")
            results = expand_links("./dup.md and ./dup.md again", base_path=Path(tmp))
            urls = [r.url for r in results]
            self.assertEqual(len(urls), len(set(urls)))

    def test_returns_list_of_expansion_results(self):
        results = expand_links("See ./missing.md", base_path=Path("/tmp"))
        self.assertIsInstance(results, list)
        for r in results:
            self.assertIsInstance(r, LinkExpansionResult)


class TestExpandLinksURLs(unittest.TestCase):
    def test_url_recorded_as_external(self):
        results = expand_links("See https://example.com")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, LinkStatus.EXTERNAL)

    def test_url_field_preserved(self):
        results = expand_links("See https://example.com/spec")
        self.assertEqual(results[0].url, "https://example.com/spec")

    def test_url_not_fetched_no_preview(self):
        # r2p must never make an outbound request for a URL in requirement text,
        # so an external link carries no fetched preview and no network error.
        results = expand_links("See http://169.254.169.254/latest/meta-data/")
        self.assertEqual(results[0].status, LinkStatus.EXTERNAL)
        self.assertEqual(results[0].content_preview, "")
        self.assertEqual(results[0].error, "")


class TestExpandLinksEdgeCases(unittest.TestCase):
    def test_empty_text_returns_empty_list(self):
        results = expand_links("")
        self.assertEqual(results, [])

    def test_no_links_returns_empty_list(self):
        results = expand_links("just plain text here")
        self.assertEqual(results, [])

    def test_mixed_local_and_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.md"
            path.write_text("# Doc")
            results = expand_links(
                f"See ./doc.md and https://example.com",
                base_path=Path(tmp),
            )
            statuses = {r.url: r.status for r in results}
            self.assertEqual(statuses["./doc.md"], LinkStatus.LOCAL_FOUND)
            self.assertEqual(statuses["https://example.com"], LinkStatus.EXTERNAL)


if __name__ == "__main__":
    unittest.main()
