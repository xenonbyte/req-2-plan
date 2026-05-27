import json
import os
import unittest
from unittest.mock import patch

from tools.workflow_cli.output import (
    format_error,
    format_gate_result,
    format_stop,
    format_success,
    is_json_mode,
    EXIT_CLI_ERR,
    EXIT_CONFLICT,
    EXIT_DRY_RUN,
    EXIT_GATE_FAIL,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_REVIEW_REQ,
)


class TestExitCodes(unittest.TestCase):
    """Test exit code constants."""

    def test_exit_ok(self):
        self.assertEqual(EXIT_OK, 0)

    def test_exit_cli_err(self):
        self.assertEqual(EXIT_CLI_ERR, 2)

    def test_exit_gate_fail(self):
        self.assertEqual(EXIT_GATE_FAIL, 3)

    def test_exit_dry_run(self):
        self.assertEqual(EXIT_DRY_RUN, 4)

    def test_exit_review_req(self):
        self.assertEqual(EXIT_REVIEW_REQ, 5)

    def test_exit_conflict(self):
        self.assertEqual(EXIT_CONFLICT, 6)

    def test_exit_not_found(self):
        self.assertEqual(EXIT_NOT_FOUND, 7)


class TestIsJsonMode(unittest.TestCase):
    """Test JSON mode detection."""

    def test_json_mode_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_json_mode())

    def test_json_mode_set_to_1(self):
        with patch.dict(os.environ, {"R2P_JSON": "1"}):
            self.assertTrue(is_json_mode())

    def test_json_mode_set_to_0(self):
        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            self.assertFalse(is_json_mode())

    def test_json_mode_set_to_other_value(self):
        with patch.dict(os.environ, {"R2P_JSON": "true"}):
            self.assertFalse(is_json_mode())


class TestFormatSuccess(unittest.TestCase):
    """Test format_success function."""

    def test_success_human_mode_with_message(self):
        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            output = format_success({"run_id": "WF-123"}, "run created")
            self.assertIn("run created", output)
            self.assertIn("WF-123", output)
            self.assertNotIn("status", output)

    def test_success_human_mode_without_message(self):
        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            output = format_success({"run_id": "WF-123"})
            self.assertIn("WF-123", output)

    def test_success_json_mode(self):
        with patch.dict(os.environ, {"R2P_JSON": "1"}):
            output = format_success({"run_id": "WF-123"})
            data = json.loads(output)
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["run_id"], "WF-123")

    def test_success_with_list_data(self):
        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            output = format_success({"items": ["a", "b", "c"]})
            self.assertIn("items", output)
            self.assertIn("a", output)
            self.assertIn("b", output)

    def test_success_with_dict_data(self):
        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            output = format_success({"config": {"key": "value"}})
            self.assertIn("config", output)
            self.assertIn("key", output)
            self.assertIn("value", output)


class TestFormatError(unittest.TestCase):
    """Test format_error function."""

    def test_error_human_mode(self):
        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            output = format_error("failed")
            self.assertIn("failed", output)

    def test_error_human_mode_with_details(self):
        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            output = format_error("failed", ["issue 1", "issue 2"])
            self.assertIn("failed", output)
            self.assertIn("issue 1", output)
            self.assertIn("issue 2", output)

    def test_error_json_mode(self):
        with patch.dict(os.environ, {"R2P_JSON": "1"}):
            output = format_error("failed")
            data = json.loads(output)
            self.assertEqual(data["status"], "error")
            self.assertEqual(data["message"], "failed")

    def test_error_json_mode_with_details(self):
        with patch.dict(os.environ, {"R2P_JSON": "1"}):
            output = format_error("failed", ["issue 1", "issue 2"])
            data = json.loads(output)
            self.assertEqual(data["status"], "error")
            self.assertEqual(data["details"], ["issue 1", "issue 2"])

    def test_error_default_exit_code(self):
        with patch.dict(os.environ, {"R2P_JSON": "1"}):
            output = format_error("failed")
            data = json.loads(output)
            self.assertEqual(data["exit_code"], EXIT_CLI_ERR)

    def test_error_custom_exit_code(self):
        with patch.dict(os.environ, {"R2P_JSON": "1"}):
            output = format_error("failed", exit_code=EXIT_NOT_FOUND)
            data = json.loads(output)
            self.assertEqual(data["exit_code"], EXIT_NOT_FOUND)


class TestFormatStop(unittest.TestCase):
    """Test format_stop function."""

    def test_stop_human_mode(self):
        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            output = format_stop("waiting for user")
            self.assertIn("waiting", output)

    def test_stop_human_mode_with_next_step(self):
        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            output = format_stop("waiting for user", "run r2p-continue")
            self.assertIn("waiting", output)
            self.assertIn("r2p-continue", output)

    def test_stop_json_mode(self):
        with patch.dict(os.environ, {"R2P_JSON": "1"}):
            output = format_stop("waiting")
            data = json.loads(output)
            self.assertEqual(data["status"], "stop")
            self.assertEqual(data["reason"], "waiting")

    def test_stop_json_mode_with_next_step(self):
        with patch.dict(os.environ, {"R2P_JSON": "1"}):
            output = format_stop("waiting", "run r2p-continue")
            data = json.loads(output)
            self.assertEqual(data["status"], "stop")
            self.assertEqual(data["next_step"], "run r2p-continue")

    def test_stop_json_mode_with_data(self):
        with patch.dict(os.environ, {"R2P_JSON": "1"}):
            output = format_stop("waiting", data={"run_id": "WF-123"})
            data = json.loads(output)
            self.assertEqual(data["status"], "stop")
            self.assertEqual(data["run_id"], "WF-123")

    def test_stop_human_mode_with_data(self):
        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            output = format_stop("waiting", data={"run_id": "WF-123"})
            self.assertIn("waiting", output)


class TestFormatGateResult(unittest.TestCase):
    """Test format_gate_result function."""

    def test_gate_passed(self):
        from unittest.mock import Mock

        gate_result = Mock()
        gate_result.passed = True

        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            output = format_gate_result(gate_result, "entry")
            self.assertIn("entry", output)
            self.assertIn("passed", output)

    def test_gate_failed(self):
        from unittest.mock import Mock

        gate_result = Mock()
        gate_result.passed = False
        gate_result.issues = ["issue 1", "issue 2"]
        gate_result.exit_code = EXIT_GATE_FAIL

        with patch.dict(os.environ, {"R2P_JSON": "0"}):
            output = format_gate_result(gate_result, "quality")
            self.assertIn("quality", output)
            self.assertIn("failed", output)
            self.assertIn("issue 1", output)

    def test_gate_failed_json(self):
        from unittest.mock import Mock

        gate_result = Mock()
        gate_result.passed = False
        gate_result.issues = ["issue 1"]
        gate_result.exit_code = EXIT_GATE_FAIL

        with patch.dict(os.environ, {"R2P_JSON": "1"}):
            output = format_gate_result(gate_result, "quality")
            data = json.loads(output)
            self.assertEqual(data["status"], "error")
            self.assertEqual(data["exit_code"], EXIT_GATE_FAIL)


if __name__ == "__main__":
    unittest.main()
