from dataclasses import dataclass

from desk.briefs import SEATS
from reading.catalog import find_bound_copy
from reading.citations import PrintedCitation, project_citations
from reading.contents import BoundPage, project_pages


@dataclass(frozen=True)
class BoundView:
    edition: int
    book: str
    revision: int
    round: int
    pages: tuple[BoundPage, ...]
    citations: tuple[PrintedCitation, ...]
    verified: bool


def verify_citations(pages, citations):
    at_page = {page.page: page.quote for page in pages}
    if sorted(citation.seat for citation in citations) != sorted(SEATS):
        return False
    return all(at_page.get(citation.page) == citation.quote for citation in citations)


def read_edition(db, edition_id):
    snapshot = find_bound_copy(db, edition_id)
    pages = project_pages(snapshot)
    citations = project_citations(snapshot)
    return BoundView(
        snapshot.id, snapshot.book, snapshot.revision_id, snapshot.round_id, pages, citations,
        verify_citations(pages, citations),
    )
