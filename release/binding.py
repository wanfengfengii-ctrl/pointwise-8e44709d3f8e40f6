from dataclasses import dataclass

from desk.briefs import SEATS
from desk.returns import find_return
from desk.sheets import find_round_sheet
from draft.revision_store import load_revision
from layout.placements import PagePin
from layout.proof import describe_conflict, preview
from release.editions import FixedEdition, find_fixed_edition_snapshot, find_working_edition, save_fixed_edition


@dataclass(frozen=True)
class BindingResult:
    edition: FixedEdition | None
    reason: str | None = None
    repeated: bool = False


def bind(db, book):
    working = find_working_edition(db, book)
    if working is None:
        raise LookupError('找不到这册折页。')
    if working.fixed_id is not None:
        return BindingResult(find_fixed_edition_snapshot(db, working.fixed_id), repeated=True)
    if working.revision_id is None:
        return BindingResult(None, '发布正式稿后才可成册。')
    actuals = []
    for seat in SEATS:
        sheet = find_round_sheet(db, working.id, seat)
        actual = None if sheet is None else find_return(db, sheet.id)
        if actual is not None:
            actuals.append(actual)
    if len(actuals) != len(SEATS):
        return BindingResult(None, '两席实印尚未报齐。')
    revision = load_revision(db, book, working.revision_id)
    pins = tuple(PagePin(actual.option.quote, actual.option.page) for actual in actuals)
    proof = preview(revision, pins)
    if proof.layout is None:
        return BindingResult(None, describe_conflict(proof.conflict))
    edition = save_fixed_edition(db, working, revision, proof.layout, actuals)
    return BindingResult(edition)
