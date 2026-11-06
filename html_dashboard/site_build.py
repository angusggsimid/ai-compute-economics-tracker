"""Build every standalone static page under ``public/``.

The build is deliberately split from the data step: ``site_data`` writes the
committed JSON slices, then ``write_site`` renders the shared shell, list pages,
detail pages and the three tool pages.  Keeping the two phases separate makes
it possible to test a page against fixture data without touching the deployable
``public/data`` directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

try:  # package import path (html_dashboard.site_build)
    from .site_detail import write_card_pages, write_provider_pages
    from .site_landscape import write_landscape_page, write_providers_page
    from .site_shell import write_assets
    from .site_tools import write_tool_pages
except ImportError:  # script import path used by the build / test suite
    from site_detail import write_card_pages, write_provider_pages  # type: ignore
    from site_landscape import write_landscape_page, write_providers_page  # type: ignore
    from site_shell import write_assets  # type: ignore
    from site_tools import write_tool_pages  # type: ignore


def _absolute(public_dir: Path, path: Path | str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = public_dir / candidate
    return str(candidate.resolve())


def _load_site_index(public_dir: Path) -> dict:
    path = public_dir / "data" / "site-index.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing; write the site data before generating pages"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_stale_pages(directory: Path, expected_names: Iterable[str]) -> List[str]:
    """Remove HTML pages that the current site-index no longer generates.

    Only the generated page directories are touched.  Assets, root pages and
    the committed data files stay untouched.
    """
    if not directory.is_dir():
        return []
    expected = set(expected_names)
    removed: List[str] = []
    for path in sorted(directory.glob("*.html")):
        if path.name in expected:
            continue
        path.unlink()
        removed.append(str(path))
    return removed


def write_site(public_dir: Path) -> List[str]:
    """Write assets, list pages, detail pages and tool pages.

    ``public_dir`` is the public root (the directory that contains
    ``index.html`` and ``data/``).  Data files must already exist; this
    function never writes prices or copies ``public/index.html``.

    Returns every generated file as an absolute path.  The 174 HTML pages are
    accompanied by ``assets/site.css`` and ``assets/site.js``.
    """
    public_dir = Path(public_dir).resolve()
    public_dir.mkdir(parents=True, exist_ok=True)

    index = _load_site_index(public_dir)
    providers = index.get("providers") or {}
    expected_cards = {
        f"{card.get('slug')}.html"
        for card in index.get("cards") or []
        if card.get("slug")
    }
    expected_providers = {
        f"{provider.get('slug')}.html"
        for key in ("own", "external")
        for provider in providers.get(key) or []
        if provider.get("slug")
    }
    _clean_stale_pages(public_dir / "gpu", expected_cards)
    _clean_stale_pages(public_dir / "providers", expected_providers)

    write_assets(public_dir)

    written: List[str] = [
        _absolute(public_dir, public_dir / "assets" / "site.css"),
        _absolute(public_dir, public_dir / "assets" / "site.js"),
        _absolute(public_dir, write_landscape_page(public_dir)),
        _absolute(public_dir, write_providers_page(public_dir)),
    ]

    written.extend(_absolute(public_dir, path) for path in write_card_pages(public_dir))
    written.extend(_absolute(public_dir, path) for path in write_provider_pages(public_dir))
    written.extend(_absolute(public_dir, path) for path in write_tool_pages(public_dir))

    missing = [path for path in written if not Path(path).is_file()]
    if missing:
        raise FileNotFoundError(
            "site build reported files that were not written: " + ", ".join(missing)
        )
    return written
