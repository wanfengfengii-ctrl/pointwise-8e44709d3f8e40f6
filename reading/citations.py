from dataclasses import dataclass

from release.editions import FixedEdition


@dataclass(frozen=True)
class PrintedCitation:
    seat: str
    sheet: int
    option: str
    number: int
    quote: str
    page: int


def project_citations(snapshot: FixedEdition):
    return tuple(
        PrintedCitation(actual.seat, actual.sheet_id, actual.option.value,
                        actual.option.number, actual.option.quote, actual.option.page)
        for actual in snapshot.returns
    )
