"""Combined-suite failure propagation and benchmark accounting."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from frameit.cli import _build_parser
from frameit.testing.all_tests import run_all_tests
from frameit.testing.artifacts import environment_metadata


class AllTestsTest(unittest.TestCase):
    def test_external_ci_fixture_reaches_numerical_children_and_reduced_matrix(self):
        metadata = environment_metadata()
        matrix = ModuleType("frameit.testing.matrix")
        matrix.run_matrix = Mock(return_value={"exit_code": 0, "results": []})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "authorized fixture"
            fixture.mkdir()
            with patch.dict(os.environ, {"FRAMEIT_CI_DATA_ROOT": str(fixture)}), patch.dict(
                "sys.modules", {"frameit.testing.matrix": matrix}
            ), patch("frameit.testing.all_tests.subprocess.run",
                     return_value=SimpleNamespace(returncode=0)) as child, patch(
                         "frameit.testing.all_tests.environment_metadata", return_value=metadata
                     ):
                report = run_all_tests(root / "results")
            self.assertEqual(matrix.run_matrix.call_args.args[0], fixture)
            self.assertTrue(matrix.run_matrix.call_args.kwargs["ci"])
            self.assertEqual(report["numerical"]["data_root"], str(fixture))
            for call in child.call_args_list:
                self.assertEqual(call.kwargs["env"]["FRAMEIT_CI_DATA_ROOT"], str(fixture))

    def test_cli_defaults(self):
        args = _build_parser().parse_args(["run-all-tests", "--output", "results"])
        self.assertIsNone(args.data_root)
        self.assertEqual(args.output, Path("results"))

    def test_full_matrix_inputs_do_not_replace_the_reduced_numerical_fixture(self):
        metadata = environment_metadata()
        matrix = ModuleType("frameit.testing.matrix")
        matrix.run_matrix = Mock(return_value={"exit_code": 0, "results": []})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture, full = root / "fixture", root / "simulations"
            fixture.mkdir()
            full.mkdir()
            with patch.dict(os.environ, {"FRAMEIT_CI_DATA_ROOT": str(fixture)}), patch.dict(
                "sys.modules", {"frameit.testing.matrix": matrix}
            ), patch("frameit.testing.all_tests.subprocess.run",
                     return_value=SimpleNamespace(returncode=0)), patch(
                         "frameit.testing.all_tests.environment_metadata", return_value=metadata
                     ):
                report = run_all_tests(root / "results", data_root=full)
                with self.assertRaisesRegex(ValueError, "must not overlap"):
                    run_all_tests(fixture / "do-not-write", data_root=full)
            self.assertEqual(report["numerical"]["data_root"], str(fixture))
            self.assertEqual(matrix.run_matrix.call_args.args[0], full)
            self.assertFalse(matrix.run_matrix.call_args.kwargs["ci"])
            self.assertFalse((fixture / "do-not-write").exists())

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
