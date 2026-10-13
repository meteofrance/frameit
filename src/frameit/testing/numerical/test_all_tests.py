"""Combined-suite failure propagation and benchmark accounting."""

import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from frameit.cli import _build_parser
from frameit.testing.all_tests import run_all_tests


class AllTestsTest(unittest.TestCase):
    def test_cli_defaults(self):
        args = _build_parser().parse_args(["run-all-tests", "--output", "results"])
        self.assertIsNone(args.data_root)
        self.assertEqual(args.output, Path("results"))

    def test_numerical_failure_still_runs_matrix(self):
        matrix = ModuleType("frameit.testing.matrix")
        matrix.run_matrix = Mock(return_value={
            "exit_code": 0,
            "results": [
                {"id": "pass", "status": "PASS", "computation_s": 2.5,
                 "timing_sections_s": {"tracking": 2.5, "Netcdf export": 100}},
                {"id": "fail", "status": "RUN_FAILED", "computation_s": 50},
            ],
        })
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results"
            with patch.dict("sys.modules", {"frameit.testing.matrix": matrix}), patch(
                "frameit.testing.all_tests.subprocess.run",
                return_value=SimpleNamespace(returncode=1, stdout=""),
            ):
                report = run_all_tests(output)
            self.assertEqual(report["exit_code"], 1)
            self.assertEqual(report["benchmark"]["computation_s"], 2.5)
            self.assertTrue(matrix.run_matrix.call_args.kwargs["benchmark"])
            self.assertTrue(matrix.run_matrix.call_args.kwargs["ci"])
            self.assertEqual(json.loads((output / "all-tests.json").read_text()), report)
            with self.assertRaises(ValueError):
                run_all_tests(output)

    def test_scientific_failure_propagates_after_numerical_success(self):
        matrix = ModuleType("frameit.testing.matrix")
        matrix.run_matrix = Mock(return_value={"exit_code": 0, "results": []})
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("sys.modules", {"frameit.testing.matrix": matrix}), patch(
                "frameit.testing.all_tests.subprocess.run",
                side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=1)],
            ):
                report = run_all_tests(Path(directory) / "results")
        self.assertEqual(report["exit_code"], 1)
        self.assertEqual(report["scientific_qualification"]["exit_code"], 1)
        matrix.run_matrix.assert_called_once()
