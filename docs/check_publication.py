"""Check public documentation boundaries and assets using only the standard library."""

from __future__ import annotations

import argparse
import ast
import math
import re
import runpy
import sys
import xml.etree.ElementTree as ET
import zlib
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = re.compile(
    r"fa_epygram_c\d+|fa_(?:p\d+|c\d+|environment)\.ya?ml"
    r"|(?:docs/)?development/fa|fa_\w+_history(?:\.|/)"
    r"|Frozen\s+developer\s+evidence|\bFA\s+P\d+\b|\bEPyGrAM\s+C\d+\b"
    r"|\b(?:stage|increment)\s+[PC]\d+\b|upgrading_to_v2"
    r"|visualization_tools|frameit\.viz\b|conservative_experiment|wind_method_comparison"
    r"|batsirai|chido|belna|(?:all|3)CH09|1BT01|reference/illustrations|matrix_testing",
    re.IGNORECASE,
)
TEXT_SUFFIXES = {".html", ".js", ".txt", ".rst", ".yaml", ".yml", ".json"}
TROUBLESHOOTING_BOOKMARKS = (
    "configuration-fails-before-inputs-open",
    "input-or-metadata-validation-fails",
    "missing-mesonh-wind-projection",
    "meso-nh-wind-projection-parameters-are-missing",
    "no-common-times-or-a-shortened-track",
    "missing-polar-values-or-unexpected-vector-components",
    "memory-export-or-retry-problems",
)


def check_brand_assets(source: Path, artifact: Path | None = None) -> list[str]:
    """Check the configured marks, not the intentionally text-bearing master SVG."""
    settings = {
        node.targets[0].id: node.value.value
        for node in ast.parse((source / 'conf.py').read_text()).body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
    }
    errors = []
    for name in ('html_logo', 'html_favicon'):
        value = settings.get(name)
        if (not isinstance(value, str) or not value or Path(value).is_absolute()
                or '..' in Path(value).parts or Path(value).suffix != '.svg'):
            errors.append(f'{name}: select a local relative SVG path')
            continue
        paths = [source / value]
        if artifact is not None:
            paths.append(artifact / '_static' / Path(value).name)
        for path in paths:
            try:
                root = ET.parse(path).getroot()
                box = [float(v) for v in root.get('viewBox', '').split()]
                if (root.tag != '{http://www.w3.org/2000/svg}svg' or len(box) != 4
                        or not all(math.isfinite(v) for v in box) or min(box[2:]) <= 0):
                    raise ValueError('expected SVG with a finite positive viewBox')
            except (OSError, ET.ParseError, ValueError) as exc:
                errors.append(f'{path}: invalid or missing SVG: {exc}')
                continue
            for node in root.iter():
                tag = node.tag.rsplit('}', 1)[-1]
                if tag in {'text', 'tspan', 'script', 'foreignObject', 'image'}:
                    errors.append(f'{path}: published mark contains live text/script/image: {tag}')
                if any(k.rsplit('}', 1)[-1].lower().startswith('on') for k in node.attrib):
                    errors.append(f'{path}: published mark contains a script event handler')
                if any(k.rsplit('}', 1)[-1] in {'href', 'src'} and not v.startswith('#')
                       for k, v in node.attrib.items()):
                    errors.append(f'{path}: published mark references an external resource')
                styles = node.get('style', '') + (node.text or '' if tag == 'style' else '')
                if ('font' in styles.lower() or 'url(' in styles.lower() or '@import' in styles.lower()
                        or any(k.startswith('font') for k in node.attrib)):
                    errors.append(f'{path}: published mark requires a font or CSS resource')
    return errors


def check_text(path: Path, text: str) -> list[str]:
    match = FORBIDDEN.search(text)
    if match is None:
        return []
    line = text.count("\n", 0, match.start()) + 1
    return [f"{path}:{line}: non-public reference {match.group()!r}"]


class _HTMLLinks(HTMLParser):
    def __init__(self, path: Path):
        super().__init__()
        self.anchors = Counter()
        self.links = []
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if value and (name == "id" or (tag == "a" and name == "name")):
                self.anchors[value] += 1
            if name in {"href", "src"} and value is not None:
                self.links.append((self.getpos()[0], name, value))


def check_local_links(artifact: Path, site_root: Path | None = None) -> list[str]:
    """Check HTML href/src targets and HTML fragments without network access."""
    artifact = artifact.resolve()
    root = site_root.resolve() if site_root is not None else artifact
    if not artifact.is_relative_to(root):
        return [f"{artifact}: artifact leaves site root {root}"]
    pages = {path.resolve(): _HTMLLinks(path) for path in sorted(root.rglob("*.html"))}
    errors = []
    for path, page in pages.items():
        if not path.is_relative_to(artifact):
            continue
        for line, attribute, value in page.links:
            location = f"{path.relative_to(root)}:{line}"
            if not value and attribute == "src":
                errors.append(f"{location}: empty asset source")
                continue
            try:
                url = urlsplit(value)
            except ValueError as exc:
                errors.append(f"{location}: invalid URL {value!r}: {exc}")
                continue
            if url.scheme == "file":
                errors.append(f"{location}: nonportable file URL {value!r}")
                continue
            if url.scheme or url.netloc:
                continue
            decoded = unquote(url.path)
            if decoded.startswith("/"):
                errors.append(f"{location}: root-relative URL loses the site prefix {value!r}")
                continue
            target = (path.parent / decoded).resolve() if decoded else path
            if not target.is_relative_to(root):
                errors.append(f"{location}: target leaves artifact {value!r}")
                continue
            if target.is_dir():
                target /= "index.html"
            if not target.is_file():
                errors.append(f"{location}: missing local target {value!r}")
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].anchors:
                errors.append(f"{location}: missing HTML anchor {value!r}")
    return errors


def check_diagnostic_links(artifact: Path) -> list[str]:
    """Check code links against the source revision that built this HTML tree."""
    registry = ROOT / "src/frameit/utils/diagnostics.py"
    if not registry.is_file():
        return []
    codes = runpy.run_path(str(registry))["CODE_TOPICS"]
    guide = artifact / "troubleshooting"
    pages = {path.name: _HTMLLinks(path) for path in guide.glob("*.html")}
    index = pages.get("codes.html")
    links = {target for _, attribute, target in index.links if attribute == "href"} if index else set()
    errors = []
    hub = artifact / "troubleshooting.html"
    bookmarks = _HTMLLinks(hub).anchors if hub.is_file() else {}
    for anchor in TROUBLESHOOTING_BOOKMARKS:
        if anchor not in bookmarks:
            errors.append(f"Missing troubleshooting bookmark: troubleshooting.html#{anchor}")
    for code, topic in codes.items():
        if not re.fullmatch(r"[EW][0-9]{4}", code):
            errors.append(f"Invalid FrameIt diagnostic ID: {code}")
        anchor = code.lower()
        page = f"{topic}.html"
        if [name for name, html in pages.items() for _ in range(html.anchors[anchor])] != [page]:
            errors.append(f"{code}: expected one anchor at troubleshooting/{page}#{anchor}")
        if f"{page}#{anchor}" not in links:
            errors.append(f"{code}: diagnostic index must link to {page}#{anchor}")
    for name, page in pages.items():
        for anchor in page.anchors:
            if re.fullmatch(r"[ew][0-9]{4}", anchor) and anchor.upper() not in codes:
                errors.append(f"troubleshooting/{name}: unregistered diagnostic anchor {anchor}")
    return errors


def check_artifact(artifact: Path, site_root: Path | None = None) -> list[str]:
    errors = check_local_links(artifact, site_root)
    errors.extend(check_diagnostic_links(artifact))
    for name in ("index.html", "searchindex.js", "objects.inv", "_sources/index.rst.txt"):
        if not (artifact / name).is_file():
            errors.append(f"{artifact / name}: missing expected Sphinx product")
    for path in sorted(artifact.rglob("*")):
        if FORBIDDEN.search(path.relative_to(artifact).as_posix()):
            errors.append(f"{path}: non-public page copied into artifact")
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            errors.extend(check_text(path, path.read_text(encoding="utf-8")))
    inventory = artifact / "objects.inv"
    if inventory.is_file():
        try:
            header = inventory.read_bytes().split(b"\n", 4)
            if header[0] != b"# Sphinx inventory version 2":
                raise ValueError("expected Sphinx inventory version 2")
            text = zlib.decompress(header[4]).decode("utf-8")
        except (IndexError, ValueError, zlib.error) as exc:
            errors.append(f"{inventory}: invalid inventory: {exc}")
        else:
            errors.extend(check_text(inventory, text))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--site-root", type=Path,
                        help="Combined site root for cross-version local links")
    args = parser.parse_args()
    artifact = args.artifact
    if not artifact.is_dir():
        print(f"Not a documentation artifact directory: {artifact}")
        return 2
    errors = check_brand_assets(ROOT / 'docs/source', artifact)
    readme = ROOT / "README.md"
    errors.extend(check_text(readme, readme.read_text(encoding="utf-8")))
    for source in sorted((ROOT / "docs/source").rglob("*.rst")):
        errors.extend(check_text(source, source.read_text(encoding="utf-8")))
    errors.extend(check_artifact(artifact, args.site_root))
    if errors:
        print("\n".join(errors))
        return 1
    print("Public documentation boundary passed (sources, artifact, search, downloads, inventory, local links).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
