"""Readable records, targeted warning suppression and scoped logging ownership."""

import io
import logging
import tempfile
import unittest
import warnings
from pathlib import Path

from frameit.utils.logging import FrameitFormatter, configure_warnings, frameit_logging_scope


class LoggingTest(unittest.TestCase):
    def test_formatter_keeps_source_for_debug_only(self):
        record = logging.LogRecord("frameit.core.runner", logging.INFO, "runner.py", 42,
                                   "Loaded %d files", (3,), None)
        self.assertEqual(FrameitFormatter().format(record), "INFO    | Loaded 3 files")
        self.assertIn("frameit.core.runner:42", FrameitFormatter(debug=True).format(record))
        self.assertNotIn("\t", FrameitFormatter().format(record))

    def test_only_known_default_notices_are_suppressed(self):
        for level, count in (("INFO", 2), ("DEBUG", 4)):
            with self.subTest(level=level), warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                configure_warnings(level)
                warnings.warn("The default value of join will change from outer to exact",
                              FutureWarning, stacklevel=1)
                warnings.warn("In a future version of xarray the default value for compat "
                              "will change from no_conflicts to override", FutureWarning,
                              stacklevel=1)
                warnings.warn("invalid value encountered in divide", RuntimeWarning, stacklevel=1)
                warnings.warn("Input coordinates are inconsistent", UserWarning, stacklevel=1)
                self.assertEqual(len(caught), count)

    def test_scope_routes_warnings_and_restores_caller_state(self):
        logger = logging.getLogger("frameit")
        old_level, old_propagate = logger.level, logger.propagate
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)
        previous_handlers = list(logger.handlers)
        old_showwarning = warnings.showwarning
        third_party = logging.getLogger("xarray")
        previous_third_party_level = third_party.level
        try:
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(RuntimeError, "deliberate"):
                    with frameit_logging_scope(directory, simu_name="test") as path:
                        warnings.simplefilter("always")
                        warnings.warn("Essential warning", RuntimeWarning, stacklevel=1)
                        logger.info("Run complete")
                        raise RuntimeError("deliberate")
                text = Path(path).read_text()
                self.assertIn("WARNING | RuntimeWarning: Essential warning", text)
                self.assertIn("INFO    | Run complete", text)
                self.assertNotIn("test_logging.py", text)
                self.assertEqual(stream.getvalue(), "")
            self.assertEqual(logger.handlers, previous_handlers)
            self.assertEqual((logger.level, logger.propagate), (old_level, old_propagate))
            self.assertIs(warnings.showwarning, old_showwarning)
            self.assertEqual(third_party.level, previous_third_party_level)
        finally:
            logger.removeHandler(handler)
            handler.close()
