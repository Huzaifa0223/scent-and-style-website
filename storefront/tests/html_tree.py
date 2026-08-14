"""Element-tree helpers over ``django.test.html.parse_html``.

Not a parser of its own: ``parse_html`` is Django's real HTML parser and
does the parsing. What it does not expose is class-based lookup or
ancestry, which is all this module adds — so the markup assertions built
on it are structural, never a regular expression over markup.

BeautifulSoup or lxml would give this for free, but neither is on
CLAUDE.md's approved dependency list and adding one purely for test
assertions was declined in favour of the stdlib-adjacent route.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from django.test.html import Element


def walk(node: Any) -> Iterator[Element]:
    """Yield ``node`` and every ``Element`` beneath it, depth-first.

    Text nodes are plain ``str`` in this tree and are skipped, which is
    why the parameter is untyped: children are a heterogeneous list.
    """
    if isinstance(node, Element):
        yield node
        for child in node.children:
            yield from walk(child)


def classes(element: Element) -> list[str]:
    """The element's class tokens, or an empty list if it has none."""
    return str(dict(element.attributes).get("class") or "").split()


def with_class(root: Any, name: str) -> list[Element]:
    """Every element at or below ``root`` carrying the exact class token.

    Token-exact, so looking for ``p-card`` does not also match
    ``p-card__media`` the way a substring search would.
    """
    return [element for element in walk(root) if name in classes(element)]


def by_tag(root: Any, tag: str) -> list[Element]:
    return [element for element in walk(root) if element.name == tag]


def with_attr(root: Any, name: str, value: str) -> list[Element]:
    return [element for element in walk(root) if dict(element.attributes).get(name) == value]


def descendants(element: Element) -> list[Element]:
    """Everything beneath ``element``, excluding ``element`` itself."""
    return [node for node in walk(element) if node is not element]


def is_inside(candidate: Element, ancestor: Element) -> bool:
    """Whether ``candidate`` sits anywhere beneath ``ancestor``.

    Compared by identity rather than equality: ``Element`` defines
    ``__eq__`` structurally, so two genuinely different but identical-
    looking tiles would otherwise compare equal and make containment
    assertions meaningless on a page of repeated components.
    """
    return any(node is candidate for node in descendants(ancestor))
