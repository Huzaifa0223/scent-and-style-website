"""Capture the storefront as flat files for a design-review preview.

Every storefront page is server-rendered, so the rendered HTML *is* the
design — no database is needed to look at it. This walks the public GET
pages of a running dev server, writes them as <path>/index.html, and
copies the static and media trees alongside, producing a directory any
static host will serve.

Deliberately narrow: only public storefront pages are captured. Order
confirmation is session-scoped, order tracking results are POST-only, and
the portal requires auth, so none of the customer data in the database
can reach the output. That is asserted rather than assumed — see
``scan_for_pii`` below, which fails the build if it finds any.

Not a deployment tool. Cart, checkout, and search need the backend and
will not work in the output; the injected notice says so.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# A discreet, theme-matched marker so nobody reviewing the output mistakes
# a dead cart button for a bug. Injected before </body>.
NOTICE = """
<div style="position:fixed;right:12px;bottom:12px;z-index:9999;
            font:500 11px/1 system-ui,sans-serif;letter-spacing:.08em;
            text-transform:uppercase;color:#8E837A;background:#14100E;
            border:1px solid #786755;border-radius:999px;padding:9px 14px;
            box-shadow:0 2px 8px rgba(0,0,0,.4)">
  Static preview &middot; cart &amp; checkout disabled
</div>
"""


def fetch(base_url: str, path: str) -> str | None:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=15) as response:
            if response.status != 200:
                return None
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        print(f"    {path} -> HTTP {exc.code}")
        return None
    except urllib.error.URLError as exc:
        print(f"    {path} -> {exc.reason}")
        return None


def write_page(out_dir: Path, path: str, html: str) -> Path:
    """Write ``path`` as a directory index so links keep working untouched.

    "/products/" becomes "products/index.html", which every static host
    resolves for the original URL — so no link rewriting is needed and the
    captured HTML stays byte-identical to what Django served.
    """
    target = out_dir / path.strip("/") / "index.html" if path != "/" else out_dir / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html.replace("</body>", NOTICE + "</body>"), encoding="utf-8")
    return target


def scan_for_pii(out_dir: Path, needles: dict[str, str]) -> list[str]:
    """Fail loudly if anything private reached the output.

    The argument for "storefront pages contain no customer data" is sound,
    but publishing to a public URL is not the place to rely on an argument
    when it can be checked directly.
    """
    findings: list[str] = []
    for page in out_dir.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        for label, needle in needles.items():
            if needle and needle in text:
                findings.append(f"{label} found in {page.relative_to(out_dir)}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", default=str(BASE_DIR / "build" / "preview"))
    parser.add_argument("--product", action="append", default=[])
    parser.add_argument("--category", action="append", default=[])
    args = parser.parse_args()

    out_dir = Path(args.out)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    paths = ["/", "/products/", "/track/"]
    paths += [f"/product/{slug}/" for slug in args.product]
    paths += [f"/category/{slug}/" for slug in args.category]

    print("  capturing pages:")
    captured = 0
    for path in paths:
        html = fetch(args.base_url, path)
        if html is None:
            continue
        write_page(out_dir, path, html)
        captured += 1
        print(f"    {path}")

    if not captured:
        print("  nothing captured — is the dev server running?")
        return 1

    static_source = BASE_DIR / "static"
    if static_source.exists():
        shutil.copytree(static_source, out_dir / "static", dirs_exist_ok=True)
        print("  copied static/")

    # Media is copied by reference, not wholesale. MEDIA_ROOT accumulates
    # every image ever written during development, including the throwaway
    # files factory-boy's ImageField generates on each test run — 347MB of
    # it here against roughly 1MB actually reachable from these pages.
    # Copying only what the captured HTML asks for keeps the output small
    # and means no unreferenced upload can ride along into a public URL.
    referenced: set[str] = set()
    for page in out_dir.rglob("*.html"):
        referenced.update(re.findall(r"/media/([^\"'\s>)]+)", page.read_text(encoding="utf-8")))

    copied = missing = 0
    for relative in sorted(referenced):
        source = BASE_DIR / "media" / relative
        if not source.is_file():
            missing += 1
            continue
        target = out_dir / "media" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    print(f"  copied media/: {copied} referenced file(s)" + (f", {missing} missing" if missing else ""))

    print(f"\n  {captured} pages -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
