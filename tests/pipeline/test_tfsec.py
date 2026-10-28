"""Fail-closed scanner execution checks; actual detection runs in the tfsec job."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("tfsec_runner", ROOT / "scripts/tfsec.py")
tfsec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tfsec)


class TfsecTests(unittest.TestCase):
    def test_tampered_binary_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "tfsec"
            binary.write_bytes(b"not the reviewed binary")
            with patch.object(tfsec, "BINARY", binary), patch.object(tfsec.subprocess, "run") as execute:
                with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                    tfsec.scan()
                execute.assert_not_called()

    def test_missing_binary_does_not_silently_skip(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(tfsec, "BINARY", Path(temporary) / "absent"):
                with self.assertRaisesRegex(ValueError, "install first"):
                    tfsec.verified_binary()

    def test_one_failed_target_fails_the_scan_after_checking_all_targets(self):
        outcomes = [subprocess.CompletedProcess([], 0) for _ in tfsec.TARGETS]
        outcomes[2] = subprocess.CompletedProcess([], 1)
        with patch.object(tfsec, "verified_binary", return_value=Path("/synthetic/tfsec")), \
                patch.object(tfsec.subprocess, "run", side_effect=outcomes) as execute:
            with self.assertRaisesRegex(ValueError, "scan failed"):
                tfsec.scan()
            self.assertEqual(execute.call_count, len(tfsec.TARGETS))

    def test_ambient_flags_do_not_enable_soft_fail(self):
        with patch.dict(tfsec.os.environ, {"TFSEC_SOFT_FAIL": "true", "TFSEC_EXCLUDE": "*"}):
            self.assertFalse(any(key.startswith("TFSEC_") for key in tfsec.scanner_environment()))

    def test_ci_scanner_is_mandatory_without_cloud_privileges(self):
        workflow = yaml.load((ROOT / ".github/workflows/validate.yml").read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["tfsec"]
        self.assertNotIn("if", job)
        self.assertNotIn("continue-on-error", job)
        self.assertEqual(job["runs-on"], "ubuntu-24.04")
        commands = []
        for step in job["steps"]:
            self.assertNotIn("if", step)
            self.assertNotIn("continue-on-error", step)
            if "run" in step:
                commands.append(step["run"])
        self.assertEqual(commands, ["python3 scripts/tfsec.py install", "python3 scripts/tfsec.py scan", "python3 scripts/tfsec.py test-detection"])
        self.assertNotIn("secrets.", str(job))


if __name__ == "__main__":
    unittest.main()
