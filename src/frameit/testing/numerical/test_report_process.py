"""Keep native check work and its terminal side effects out of the UI process."""

import asyncio
import os
import signal
import subprocess
import sys
from contextlib import suppress
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
from time import monotonic, sleep

import pytest
from textual.worker import WorkerCancelled

from frameit.cli import _collect_report
from frameit.core.reports import PreflightResult, project_report
from frameit.testing.numerical.test_validate_tui import _case, _text


def _reported_check(root, config, *, progress, **options):
    with (root / "reader-pids").open("a") as output:
        print(os.getpid(), file=output)
    os.write(1, b"native stdout must stay off screen\n")
    os.write(2, b"native stderr must stay off screen\n")
    print("WARNING:fixture:metadata warning", file=sys.stderr)
    return _collect_report(config, progress=progress, **options)


@pytest.mark.parametrize("command,schema", [
    ("inspect", False), ("validate", True), ("validate", False),
])
def test_isolated_checks_reuse_one_reader_and_keep_the_projection(tmp_path, capfd, command, schema):
    from frameit.report_check import ReportProcess

    config = _case(tmp_path)
    options = dict(command=command, schema_only=schema, sample_only=command == "inspect")
    expected = project_report(_collect_report(config, **options))
    reader = ReportProcess(partial(_reported_check, tmp_path, config, **options))
    progress, warnings = [], []
    try:
        for _ in range(2):
            assert reader.read(lambda *event: progress.append(event), lambda: False,
                               warnings.append) == expected
        first, second = map(int, (tmp_path / "reader-pids").read_text().splitlines())
        assert first == second != os.getpid()
        assert warnings == ["metadata warning"] * 2
        assert [event[0] for event in progress].count("report") == 2
        captured = capfd.readouterr()
        assert "native stdout" not in captured.out and "native stderr" not in captured.err
    finally:
        reader.close()
    if os.name == "posix":
        with pytest.raises(ProcessLookupError):
            os.kill(first, 0)


_WAITING_DECODER = """
import os, signal, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path(sys.argv[1]).write_text(str(os.getpid()))
time.sleep(8)
"""


def _running(pid):
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return False
    return state not in {"Z", "X"}


def _wait_stopped(pid):
    deadline = monotonic() + 2
    while _running(pid) and monotonic() < deadline:
        sleep(.02)
    assert not _running(pid), f"Decoder {pid} still running"


def _faulty_check(crash, *, progress):
    if crash.exists():
        ready = crash.with_name("decoder-ready")
        decoder = subprocess.Popen(
            [sys.executable, "-c", _WAITING_DECODER, str(ready)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        crash.write_text(str(decoder.pid))
        deadline = monotonic() + 5
        while not ready.exists() and monotonic() < deadline:
            sleep(.02)
        os._exit(7)
    return PreflightResult("validate")


@pytest.mark.skipif(sys.platform != "linux", reason="inspects a Linux decoder process")
def test_a_crashed_reader_never_reports_success_and_can_be_restarted(tmp_path):
    from frameit.report_check import ReportProcess

    marker = tmp_path / "crash"
    marker.touch()
    reader = ReportProcess(partial(_faulty_check, marker))
    try:
        with pytest.raises(RuntimeError, match="Metadata helper"):
            reader.read(lambda *event: None, lambda: False, lambda warning: None)
        pid = int(marker.read_text())
        _wait_stopped(pid)
        marker.unlink()
        report = reader.read(lambda *event: None, lambda: False, lambda warning: None)
        assert report["status"] == "ok"
    finally:
        if marker.exists() and (pid := marker.read_text()):
            with suppress(ProcessLookupError):
                os.kill(int(pid), signal.SIGKILL)
        reader.close()


def _concurrent_warnings(*, progress):
    progress("configuration", None, None, None)
    ready = Barrier(4)

    def warn(letter):
        ready.wait(5)
        print("WARNING:fixture:" + letter * 1_000_000, file=sys.stderr)

    threads = [Thread(target=warn, args=(letter,)) for letter in "abc"]
    for thread in threads:
        thread.start()
    ready.wait(5)
    progress("metadata", "air", 0, 1)
    for thread in threads:
        thread.join(5)
    return PreflightResult("validate")


def test_reader_keeps_warning_messages_intact_while_threads_report_progress():
    from frameit.report_check import ReportProcess

    reader = ReportProcess(_concurrent_warnings)
    warnings = []
    try:
        # Let the sender fill the real socket buffer before reading the larger messages.
        report = reader.read(lambda *event: sleep(.1), lambda: False, warnings.append)
        assert sorted(warnings) == [letter * 1_000_000 for letter in "abc"]
        assert report["status"] == "ok"
    finally:
        reader.close()


def _gated_check(config, root, *, progress):
    progress("metadata", "atmosphere", 0, 1)
    if (root / "gate-next").exists():
        (root / f"entered-{os.getpid()}").touch()
        deadline = monotonic() + 8
        while not (root / "release").exists() and monotonic() < deadline:
            sleep(.01)
        progress("metadata", "atmosphere", 1, 1)
    return _collect_report(config, command="validate", schema_only=True, progress=progress)


def test_cancel_during_an_isolated_read_waits_and_restores_previous_report(tmp_path):
    from frameit.validate_tui import ValidationApp

    config = _case(tmp_path)
    path = tmp_path / "gate-next"
    release = tmp_path / "release"

    async def exercise():
        app = ValidationApp(config, partial(_gated_check, config, tmp_path), schema_only=True,
                            isolate=True)
        app._reader.start()  # The foreground driver does this before capturing stderr.
        async with app.run_test(size=(80, 24)) as pilot:
            try:
                await app.workers.wait_for_complete()
                await pilot.press("2")
                status = _text(app, "#status")
                path.touch()
                await pilot.press("r")
                async with asyncio.timeout(6):
                    while not list(tmp_path.glob("entered-*")):
                        await asyncio.sleep(.02)
                reader_pid = int(next(tmp_path.glob("entered-*")).name.split("-")[-1])
                assert reader_pid != os.getpid() and "Refreshing report" in _text(app, "#status")
                worker = next(iter(app.workers))
                await pilot.press("ctrl+c")
                assert app.busy and "waiting" in _text(app, "#status")
                release.touch()
                with pytest.raises(WorkerCancelled):
                    await worker.wait()
                await pilot.pause()
                assert app.result_code == 130
                assert status in _text(app, "#status")
                assert app.query_one("#report-tabs").active == "findings"
                path.unlink()
                await pilot.press("r")
                await app.workers.wait_for_complete()
                await pilot.pause()
                assert app.result_code == 0
            finally:
                release.touch()

    asyncio.run(exercise())


def gated_cli_report(root, config, *, progress, **options):
    """Model the same subprocess.run + scratch directory lifetime as an FA request."""
    (root / "raw-stdin").write_text(str(os.isatty(0)))
    progress("metadata", "atmosphere", 0, 1)
    with TemporaryDirectory(dir=root, prefix="decoder-scratch-") as scratch:
        marker = root / f"entered-{os.getpid()}"
        subprocess.run([sys.executable, "-c", _WAITING_DECODER, str(marker)],
                       cwd=scratch, check=False)
    return _collect_report(config, progress=progress, **options)
