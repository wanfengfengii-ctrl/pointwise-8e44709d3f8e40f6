from dataclasses import dataclass

from draft.pages import validate_page_number


@dataclass(frozen=True)
class PagePin:
    quote: str
    page: int


@dataclass(frozen=True)
class PlacementProblem:
    choices: tuple[tuple[str, tuple[int, ...]], ...]
    fixed: tuple[PagePin, ...]


class PlacementConflict(ValueError):
    pass


def build_placement_problem(revision, pins=()):
    choices = revision.page_grid()
    by_quote = {}
    by_page = {}
    for pin in pins:
        try:
            validate_page_number(pin.page)
        except ValueError as error:
            raise PlacementConflict(str(error)) from error
        if pin.quote not in choices:
            raise PlacementConflict(f'稿中没有引文 {pin.quote}。')
        if pin.page not in choices[pin.quote]:
            raise PlacementConflict(f'引文 {pin.quote} 不允许排在第 {pin.page} 页。')
        if pin.quote in by_quote and by_quote[pin.quote] != pin.page:
            raise PlacementConflict(f'引文 {pin.quote} 被指定到不同页。')
        if pin.page in by_page and by_page[pin.page] != pin.quote:
            raise PlacementConflict(f'第 {pin.page} 页被指定给多段引文。')
        by_quote[pin.quote] = pin.page
        by_page[pin.page] = pin.quote
    fixed = tuple(PagePin(quote, page) for quote, page in sorted(by_quote.items()))
    return PlacementProblem(tuple(sorted(choices.items())), fixed)
