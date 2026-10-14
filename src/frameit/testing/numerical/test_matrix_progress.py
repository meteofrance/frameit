"""Matrix worker output remains visible through process isolation."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frameit.testing.artifacts import atomic_json
from frameit.testing.matrix import _execute_case


class MatrixProgressTests(unittest.TestCase):
    def test_quiet_worker_emits_heartbeat(self):
        class Worker:
            exitcode = 0

            def __init__(self, **kwargs):
                self.completion = Path(kwargs["args"][2])
                self.joins = 0

            def start(self):
                pass

            def join(self, timeout=None):
                self.joins += 1
                if self.joins == 2:
                    atomic_json(self.completion, {"ok": True, "products": []})

            def is_alive(self):
                return self.joins < 2

        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with (
                patch("frameit.testing.matrix.multiprocessing.get_context") as context,
                patch("frameit.testing.matrix.time.monotonic", side_effect=[0, 0, 31, 32]),
                contextlib.redirect_stdout(output),
            ):
                context.return_value.Process.side_effect = Worker
                result = _execute_case(
                    {"id": "quiet", "input_records": []}, Path(directory), None
                )
            self.assertEqual(result["status"], "EXECUTED")
            self.assertIn("[WAIT] quiet still running (31s elapsed)", output.getvalue())
            self.assertIn("cases/quiet/logs/frameit.log", output.getvalue())

    def test_forwards_output_including_final_worker_chunk(self):
        class Worker:
            exitcode = 0

            def __init__(self, **kwargs):
                _, log, completion, _ = kwargs["args"]
                self.log = Path(log)
                self.completion = Path(completion)
                self.running = True
                self.joins = 0

            def start(self):
                self.log.write_text("first line\n", encoding="utf-8")

            def join(self, timeout=None):
                self.joins += 1
                if self.joins == 2:
                    with self.log.open("a", encoding="utf-8") as stream:
                        stream.write("final line\n" + "x" * 70000)
                    atomic_json(self.completion, {"ok": True, "products": []})
                    self.running = False

            def is_alive(self):
                return self.running

        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch("frameit.testing.matrix.multiprocessing.get_context") as context:
                context.return_value.Process.side_effect = Worker
                with contextlib.redirect_stdout(output):
                    result = _execute_case(
                        {"id": "example", "input_records": []}, Path(directory), None
                    )
            self.assertEqual(result["status"], "EXECUTED")
            self.assertEqual(output.getvalue(), "first line\nfinal line\n" + "x" * 70000)
            log = Path(directory) / "cases/example/logs/frameit.log"
            self.assertEqual(log.read_text(), output.getvalue())
