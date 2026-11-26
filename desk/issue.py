from dataclasses import dataclass

from desk.briefs import load_seat_brief
from desk.options import candidate_options
from desk.sheets import PrintSheet, find_round_sheet, save_issued_sheet
from draft.revisions import Revision


@dataclass(frozen=True)
class SheetIssueResult:
    sheet: PrintSheet | None
    reason: str | None = None


def issue_sheet(db, book, round_id, seat, revision: Revision | None, can_offer):
    brief = load_seat_brief(db, book, seat)
    if brief is None:
        raise LookupError('找不到这册的印席。')
    original = find_round_sheet(db, round_id, seat)
    if original is not None:
        return SheetIssueResult(original)
    if revision is None:
        return SheetIssueResult(None, '正式稿发布后才可领取纸单。')
    choices = tuple(option for option in candidate_options(brief, revision) if can_offer(option))
    if not choices:
        return SheetIssueResult(None, f'当前正式稿没有可发给引文 {brief.quote} 的相容选项。')
    sheet = save_issued_sheet(db, book, round_id, seat, revision.number, choices)
    return SheetIssueResult(sheet)
