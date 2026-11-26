from dataclasses import dataclass

from draft.revision_store import load_revision
from layout.placements import PagePin
from release.commitments import covers_outstanding_choices, load_seat_promises
from release.editions import WorkingEdition, find_working_edition, publish_revision


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
    promises = () if working.fixed_id is not None else load_seat_promises(db, working.id)
    coverage = covers_outstanding_choices(candidate, promises)
    if not coverage.accepted:
        return AmendmentDecision(False, working, coverage.blocked, coverage.reason)
    working = publish_revision(db, working, revision_id)
    return AmendmentDecision(True, working)
