"""Isolate live metadata work without moving the terminal's report lifecycle."""

import os
import signal
from asyncio import CancelledError
from contextlib import redirect_stderr, suppress
from io import TextIOBase
from multiprocessing import get_context
from threading import Event, Lock
from time import monotonic

from frameit.core.reports import project_report


def collect_projection(collect, notify, is_cancelled):
    last_key, last_sent = None, 0.0

    def progress(stage, source, checked, total):
        nonlocal last_key, last_sent
        if is_cancelled():
            raise CancelledError
        at, key = monotonic(), (stage, source, total)
        if key != last_key or (checked is not None and checked == total or at - last_sent >= .12):
            notify(stage, source, checked, total, at)
            last_key, last_sent = key, at

    result = collect(progress=progress)
    progress("report", None, None, None)
    return project_report(result)


class _Warnings(TextIOBase):
    def __init__(self, channel):
        self.channel = channel

    def write(self, text):
        level, _, message = text.rstrip().partition(":")
        if level == "WARNING" and message:
            self.channel.send(("warning", message.partition(":")[2] or message))
        return len(text)


def _serve(channel, collect):
    if os.name == "posix":
        os.setsid()  # Readers may launch their own native helper.
    with open(os.devnull, "w") as quiet:
        for descriptor in (1, 2):
            os.dup2(quiet.fileno(), descriptor)

    def notify(*args):
        channel.send(("progress", args))

    def cancelled():
        if channel.poll():
            if channel.recv() == "stop":
                raise SystemExit
            return True
        return False

    with channel, redirect_stderr(_Warnings(channel)), suppress(EOFError, BrokenPipeError):
        while (request := channel.recv()) != "stop":
            if request != "check":  # Cancellation may arrive just after a result was sent.
                continue
            try:
                report = collect_projection(collect, notify, cancelled)
            except CancelledError:
                channel.send(("cancelled", None))
            except Exception as exc:
                channel.send(("error", str(exc)))
            else:
                channel.send(("report", report))


class ReportProcess:
    """One reusable child and at most one check in flight, owned by the app."""

    def __init__(self, collect):
        self._collect = collect
        self._process = self._channel = None
        self._closing = Event()
        self._lock = Lock()

    def _start(self):
        context = get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(target=_serve, args=(child, self._collect),
                                  name="frameit-report-check", daemon=True)
        try:
            process.start()
        except BaseException:
            parent.close()
            raise
        finally:
            child.close()
        self._process, self._channel = process, parent

    def start(self):
        with self._lock:
            if self._closing.is_set():
                raise CancelledError
            if self._process is not None and not self._process.is_alive():
                self._channel.close()
                self._process.close()
                self._process = self._channel = None
            if self._process is None:
                self._start()
            return self._process, self._channel

    def read(self, notify, is_cancelled, warn):
        process, channel = self.start()
        sent_cancel = False
        try:
            with self._lock:
                if self._closing.is_set():
                    raise CancelledError
                channel.send("check")
            while not self._closing.is_set():
                if not sent_cancel and is_cancelled():
                    with self._lock:
                        if not self._closing.is_set():
                            channel.send("cancel")
                    sent_cancel = True
                if not channel.poll(.05):
                    continue
                kind, value = channel.recv()
                if kind == "progress":
                    notify(*value)
                elif kind == "warning":
                    warn(value)
                elif kind == "error":
                    raise RuntimeError(value)
                elif kind == "cancelled":
                    raise CancelledError
                elif kind == "report":
                    return value
        except (EOFError, OSError) as exc:
            with self._lock:
                if not self._closing.is_set():
                    process.join(.25)
                    raise RuntimeError(
                        "Metadata helper stopped before returning a report.") from exc
        raise CancelledError

    def close(self):
        self._closing.set()
        with self._lock:
            process, channel = self._process, self._channel
            self._process = self._channel = None
            if process is None:
                return
            with suppress(OSError):
                channel.send("stop")
        # Quit can be forced by SIGTERM while a reader is still inside a native call.
        process.join(.25)
        if process.is_alive():
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    process.kill()
            else:
                process.kill()
            process.join()
        channel.close()
        process.close()
