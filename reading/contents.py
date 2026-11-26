from dataclasses import dataclass

from release.editions import FixedEdition


@dataclass(frozen=True)
class BoundPage:
    page: int
    quote: str
    text: str


def project_pages(snapshot: FixedEdition):
    ordered = sorted(snapshot.pages, key=lambda item: item.page)
    return tuple(BoundPage(item.page, item.quote, item.text) for item in ordered)
