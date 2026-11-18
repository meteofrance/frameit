"""Reject incomplete or incorrectly linked two-version Sphinx publications."""

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class _Navigation(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.links = []
        self.warning = False
        self.in_warning = False
        self.warning_text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "data-docs-channel" in attrs:
            self.links.append(attrs)
        if tag == "aside" and "docs-development-warning" in attrs.get("class", "").split():
            self.warning = True
            self.in_warning = True

    def handle_endtag(self, tag):
        if tag == "aside":
            self.in_warning = False

    def handle_data(self, data):
        if self.in_warning:
            self.warning_text.append(data)


def check_versions(site: Path) -> list[str]:
    """Check every generated page while leaving downloadable HTML untouched."""
    site = site.resolve()
    errors = []
    for channel, root in (("main", site), ("develop", site / "develop")):
        for product in ("index.html", "search.html", "searchindex.js", "objects.inv",
                        "_sources/index.rst.txt"):
            if not (root / product).is_file():
                errors.append(f"{channel}: missing Sphinx product {product}")
        for page in sorted(root.rglob("*.html")):
            relative = page.relative_to(root)
            if (relative.parts[0] in ("_static", "_sources", "_downloads")
                    or (channel == "main" and relative.parts[0] == "develop")):
                continue
            navigation = _Navigation(page.read_text(encoding="utf-8"))
            links = navigation.links
            location = page.relative_to(site)
            if len(links) != 2 or {link["data-docs-channel"] for link in links} != {"main", "develop"}:
                errors.append(f"{location}: expected both documentation version links")
                continue
            for link in links:
                target_channel = link["data-docs-channel"]
                target = site / ("develop/index.html" if target_channel == "develop" else "index.html")
                try:
                    url = urlsplit(link.get("href", ""))
                except ValueError:
                    errors.append(f"{location}: malformed {target_channel} home link")
                    continue
                if (url.scheme or url.netloc or url.path.startswith("/") or url.query
                        or url.fragment or (page.parent / unquote(url.path)).resolve() != target):
                    errors.append(f"{location}: invalid {target_channel} home link")
                if (link.get("aria-current") == "true") != (target_channel == channel):
                    errors.append(f"{location}: incorrect current documentation version")
            if (navigation.warning != (channel == "develop")
                    or (channel == "develop"
                        and "unreleased" not in "".join(navigation.warning_text).lower())):
                errors.append(f"{location}: incorrect unreleased documentation warning")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    errors = check_versions(parser.parse_args().site)
    if errors:
        print("\n".join(errors))
        return 1
    print("Documentation versions passed (both trees, navigation, development warning).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
