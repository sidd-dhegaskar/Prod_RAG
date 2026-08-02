"""Title-anchored panel reconstruction for multi-panel pictures.

Problem: Docling reads text inside a picture region in raw top-to-bottom,
left-to-right order. When a picture contains multiple independent panels
side by side (e.g. two charts), rows from different panels on the same
visual line get interleaved instead of staying grouped per panel.

Approach (see conversation / EXTRACTION_APPROACH.md Section 8): panel
titles/captions are read correctly and positioned above their own panel.
Use them as anchors — assign every other text item to its nearest anchor
by 2D distance, then emit one panel's content fully before the next,
instead of the raw interleaved order. Generalizes to N panels (not just 2)
since it's nearest-anchor assignment, not left/right splitting.

Known limits (see conversation): panels with no distinct title/caption
have no anchor to attach to; densely packed panels risk boundary
ambiguity; this is a heuristic, not a guarantee — validate per document.
"""

import re
from dataclasses import dataclass

ANCHOR_PATTERN = re.compile(r"^(Chart|Figure|Fig\.?|Table)\s+\d+", re.IGNORECASE)


@dataclass
class Item:
    text: str
    l: float
    t: float
    r: float
    b: float

    @property
    def mid_x(self) -> float:
        return (self.l + self.r) / 2

    @property
    def mid_y(self) -> float:
        return (self.t + self.b) / 2


def find_anchors(items: list[Item]) -> list[Item]:
    return [it for it in items if ANCHOR_PATTERN.match(it.text.strip())]


def nearest_anchor_index(item: Item, anchors: list[Item]) -> int:
    distances = [
        (item.mid_x - a.mid_x) ** 2 + (item.mid_y - a.mid_y) ** 2
        for a in anchors
    ]
    return distances.index(min(distances))


def reconstruct(items: list[Item]) -> list[list[Item]]:
    """Returns items grouped into panels: one list per anchor, each
    internally sorted top-to-bottom then left-to-right. Panels are
    ordered by anchor reading position (top-to-bottom, left-to-right).
    Falls back to a single panel (original items, line-sorted) if no
    anchors are found — i.e. this is a no-op for single-panel pictures."""
    anchors = find_anchors(items)

    if not anchors:
        return [sorted(items, key=lambda it: (-it.t, it.l))]

    groups: dict[int, list[Item]] = {i: [] for i in range(len(anchors))}
    for item in items:
        groups[nearest_anchor_index(item, anchors)].append(item)

    anchor_order = sorted(range(len(anchors)), key=lambda i: (-anchors[i].t, anchors[i].l))

    panels = []
    for i in anchor_order:
        panel_items = sorted(groups[i], key=lambda it: (-it.t, it.l))
        panels.append(panel_items)
    return panels


def render(panels: list[list[Item]]) -> str:
    blocks = []
    for panel in panels:
        blocks.append("\n".join(it.text for it in panel))
    return "\n\n---\n\n".join(blocks)
