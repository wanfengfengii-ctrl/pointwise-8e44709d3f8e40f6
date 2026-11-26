from dataclasses import dataclass

from desk.briefs import SeatBrief
from draft.revisions import Revision


@dataclass(frozen=True)
class OptionDraft:
    quote: str
    page: int


@dataclass(frozen=True)
class PrintOption:
    sheet_id: int
    number: int
    quote: str
    page: int

    @property
    def value(self):
        return f'{self.sheet_id}.{self.number}'


def candidate_options(brief: SeatBrief, revision: Revision):
    return tuple(
        OptionDraft(brief.quote, page) for page in revision.page_grid().get(brief.quote, ())
    )


def number_sheet_options(sheet_id, drafts):
    return tuple(
        PrintOption(sheet_id, number, draft.quote, draft.page)
        for number, draft in enumerate(drafts, start=1)
    )
