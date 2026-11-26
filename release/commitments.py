from dataclasses import dataclass
from itertools import product

from desk.briefs import SEATS
from desk.options import PrintOption
from desk.returns import find_return
from desk.sheets import find_round_sheet
from layout.placements import PagePin
from layout.proof import describe_conflict, preview


@dataclass(frozen=True)
class SeatPromise:
    seat: str
    sheet_id: int | None
    options: tuple[PrintOption, ...]

    def choices(self):
        if self.sheet_id is None:
            return (None,)
        return tuple(PagePin(option.quote, option.page) for option in self.options)


@dataclass(frozen=True)
class CoverageDecision:
    accepted: bool
    blocked: tuple[PagePin, ...] = ()
    reason: str | None = None


def load_seat_promises(db, round_id):
    promises = []
    for seat in SEATS:
        sheet = find_round_sheet(db, round_id, seat)
        if sheet is None:
            promises.append(SeatPromise(seat, None, ()))
            continue
        actual = find_return(db, sheet.id)
        options = sheet.options if actual is None else (actual.option,)
        promises.append(SeatPromise(seat, sheet.id, options))
    return tuple(promises)


def covers_outstanding_choices(revision, promises):
    for combination in product(*(promise.choices() for promise in promises)):
        pins = tuple(pin for pin in combination if pin is not None)
        result = preview(revision, pins)
        if result.layout is None:
            return CoverageDecision(False, pins, describe_conflict(result.conflict))
    return CoverageDecision(True)


def can_offer_option(revision, option, other):
    offered = PagePin(option.quote, option.page)
    for alternative in other.choices():
        pins = (offered,) if alternative is None else (offered, alternative)
        if preview(revision, pins).layout is None:
            return False
    return True
