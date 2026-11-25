"""Capture the storage tutorial's interactive Validate Overview for the guide."""

import asyncio
import re
import shutil
import sys
from contextlib import chdir
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

from frameit.cli import _collect_report
from frameit.testing.documentation_example import create_task_fixtures
from frameit.validate_tui import ValidationApp


async def capture(config):
    app = ValidationApp(config, partial(_collect_report, config, command="validate"))
    async with app.run_test(size=(88, 26)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.press("1")
        await pilot.pause()
        svg = app.export_screenshot(title="FrameIt Validate — Overview", simplify=True)
    assert "Recommended" in svg and "RSS:" in svg, "RAM estimate is not visible"
    # Rich's default SVG pulls a web font. The real terminal capture needs no network resource.
    svg = re.sub(r"@font-face\s*\{[^}]*\}", "", svg).replace("'Fira Code', monospace", "monospace")
    return "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"


if __name__ == "__main__":
    output = Path(sys.argv[1]).resolve()
    source = Path(__file__).resolve().parents[1] / "example/tutorials/storage-and-resources.yaml"
    with TemporaryDirectory() as scratch:
        root = Path(scratch) / "tutorial-data"
        create_task_fixtures(root)
        shutil.copyfile(source, root / source.name)
        with chdir(root):
            output.write_text(asyncio.run(capture(Path(source.name))), encoding="utf-8")
