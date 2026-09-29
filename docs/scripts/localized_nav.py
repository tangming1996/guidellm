"""Build locale-specific navigation from the documentation translation map."""

from __future__ import annotations

import re
import runpy
from pathlib import Path, PurePosixPath
from typing import Any, cast

from mkdocs.structure.nav import Link, Navigation, Section
from mkdocs.structure.pages import Page

translation_routes = runpy.run_path(
    str(Path(__file__).resolve().parent / "check_translations.py")
)["translation_routes"]

ZH_SECTION_TITLES = {
    "getting started": "快速开始",
    "guides": "使用指南",
    "examples": "示例",
    "developer": "开发者",
    "reference": "API 参考",
    "api reference": "API 参考",
    "multimodal": "多模态",
}


def _route(page: Page) -> str:
    path = PurePosixPath(page.file.src_uri)
    route = path.parent if path.name == "index.md" else path.with_suffix("")
    value = route.as_posix()
    return "" if value == "." else f"{value}/"


def _pages(item: Any) -> list[Page]:
    if isinstance(item, Page):
        return [item]
    if isinstance(item, Section):
        return [page for child in item.children for page in _pages(child)]
    return []


def _navigation_entries(item: Any) -> list[Page | Link]:
    if isinstance(item, (Page, Link)):
        return [item]
    if isinstance(item, Section):
        return [
            entry for child in item.children for entry in _navigation_entries(child)
        ]
    return []


def _page_title(page: Page) -> str:
    if page.title:
        return str(page.title)

    content = page.file.content_string
    frontmatter = re.match(r"^---\s*\n(.*?)\n---(?:\s*\n|$)", content, re.DOTALL)
    if frontmatter:
        title = re.search(
            r"^title:\s*[\"']?(.*?)[\"']?\s*$", frontmatter[1], re.MULTILINE
        )
        if title and title[1]:
            return title[1]

    heading = re.search(r"^#\s+(.+?)\s*#*\s*$", content, re.MULTILINE)
    if heading:
        return heading[1]

    return PurePosixPath(page.file.src_uri).stem.replace("-", " ").title()


def _localized_title(title: str) -> str:
    return ZH_SECTION_TITLES.get(" ".join(title.casefold().split()), title)


def _clone_page(
    page: Page,
    *,
    chinese: bool,
    routes: dict[str, dict[str, str | bool]],
    pages_by_route: dict[str, Page],
) -> Any | None:
    route = _route(page)
    if route.startswith("zh/"):
        return None
    if not chinese:
        return page

    details = routes.get(route)
    translated = pages_by_route.get(str(details["translation"])) if details else None
    if translated is not None:
        if not translated.title:
            translated.title = _page_title(translated)
        return translated

    return Link(f"{_page_title(page)} (English)", page.url)


def _clone_section(
    item: Section,
    *,
    chinese: bool,
    routes: dict[str, dict[str, str | bool]],
    pages_by_route: dict[str, Page],
) -> Section | None:
    children = [
        child
        for source_child in item.children
        if (
            child := _clone_item(
                source_child,
                chinese=chinese,
                routes=routes,
                pages_by_route=pages_by_route,
            )
        )
        is not None
    ]
    if not children:
        return None

    title = _localized_title(item.title) if chinese else item.title
    section = Section(title, children)
    for child in children:
        child.parent = section
    section.active = any(
        child.active for child in children if isinstance(child, (Page, Link, Section))
    )
    return section


def _clone_item(
    item: Any,
    *,
    chinese: bool,
    routes: dict[str, dict[str, str | bool]],
    pages_by_route: dict[str, Page],
) -> Any | None:
    if isinstance(item, Page):
        return _clone_page(
            item,
            chinese=chinese,
            routes=routes,
            pages_by_route=pages_by_route,
        )
    if isinstance(item, Section):
        return _clone_section(
            item,
            chinese=chinese,
            routes=routes,
            pages_by_route=pages_by_route,
        )
    return item


def _navigation_for_page(nav: Navigation, chinese: bool) -> Navigation:
    routes = translation_routes()
    pages_by_route = {_route(candidate): candidate for candidate in nav.pages}
    items = [
        item
        for source_item in nav.items
        if (
            item := _clone_item(
                source_item,
                chinese=chinese,
                routes=routes,
                pages_by_route=pages_by_route,
            )
        )
        is not None
    ]
    pages = [candidate for item in items for candidate in _pages(item)]
    localized_nav = Navigation(items, pages)

    if chinese:
        localized_nav.homepage = pages_by_route.get("zh/")
        if localized_nav.homepage:
            localized_nav.homepage.parent = None
    else:
        localized_nav.homepage = pages_by_route.get("")

    return localized_nav


def _set_adjacent_pages(page: Page, nav: Navigation) -> None:
    entries = [entry for item in nav.items for entry in _navigation_entries(item)]
    current_index = next(
        (index for index, entry in enumerate(entries) if entry is page), None
    )
    if current_index is None:
        page.previous_page = None
        page.next_page = None
        return

    # MkDocs templates render Link neighbors as footer links as well.
    page.previous_page = (
        cast("Page", entries[current_index - 1]) if current_index > 0 else None
    )
    page.next_page = (
        cast("Page", entries[current_index + 1])
        if current_index + 1 < len(entries)
        else None
    )


def on_page_context(context: dict, page: Page, config, nav: Navigation):
    """Replace the shared nav with the tree for the current locale."""
    _ = config
    page_route = _route(page)
    chinese = page_route == "zh/" or page_route.startswith("zh/")
    localized_nav = _navigation_for_page(nav, chinese)
    context["nav"] = localized_nav
    _set_adjacent_pages(page, localized_nav)
    return context
