from dataclasses import dataclass

from draft.revision_store import load_revision
from layout.placements import PagePin
from release.commitments import covers_outstanding_choices, load_seat_promises
from release.editions import WorkingEdition, find_working_edition, publish_revision
from release.preprints import preprint_blocker, round_preprint


@dataclass(frozen=True)
class AmendmentDecision:
    accepted: bool
    working: WorkingEdition
    blocked: tuple[PagePin, ...] = ()
    reason: str | None = None


def amend(db, book, revision_id):
    working = find_working_edition(db, book)
    if working is None:
        raise LookupError('找不到这册折页。')
    candidate = load_revision(db, book, revision_id)
    if candidate is None:
        raise LookupError('找不到该册的候选修订。')
    if working.fixed_id is not None:
        promises = ()
        signed = None
    else:
        promises = load_seat_promises(db, working.id)
        signed = round_preprint(db, working.id)
    fixed_pins = ()
    if signed is not None:
        blocker = preprint_blocker(candidate, signed.pages)
        if blocker is not None:
            return AmendmentDecision(False, working, tuple(
                PagePin(page.quote, page.page) for page in signed.pages
            ), blocker)
        fixed_pins = tuple(PagePin(page.quote, page.page) for page in signed.pages)
    coverage = covers_outstanding_choices(candidate, promises, fixed_pins)
    if not coverage.accepted:
        return AmendmentDecision(False, working, coverage.blocked, coverage.reason)
    working = publish_revision(db, working, revision_id)
    return AmendmentDecision(True, working)
