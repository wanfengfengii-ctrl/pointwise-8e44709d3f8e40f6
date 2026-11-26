from collections import deque
from dataclasses import dataclass

from layout.occupancy import Occupancy


@dataclass(frozen=True)
class Layout:
    assignments: tuple[tuple[str, int], ...]

    def page_map(self):
        return dict(self.assignments)


@dataclass(frozen=True)
class LayoutConflict:
    quote: str
    candidates: tuple[int, ...]


def _make_room(root, choices, fixed_pages, occupancy):
    queue = deque([root])
    seen_quotes = {root}
    previous_quote = {}
    while queue:
        quote = queue.popleft()
        for page in choices[quote]:
            if page in fixed_pages or page in previous_quote:
                continue
            previous_quote[page] = quote
            holder = occupancy.occupant(page)
            if holder is None:
                # Start at the free page. Each move frees the next page along the path.
                while page is not None:
                    page = occupancy.reassign(previous_quote[page], page)
                return True
            if holder not in seen_quotes:
                seen_quotes.add(holder)
                queue.append(holder)
    return False


def solve_layout(problem):
    occupancy = Occupancy()
    choices = dict(problem.choices)
    fixed_quotes = {pin.quote for pin in problem.fixed}
    fixed_pages = {pin.page for pin in problem.fixed}
    for pin in problem.fixed:
        occupancy.reserve(pin.quote, pin.page)
    for quote, pages in problem.choices:
        if quote not in fixed_quotes and not _make_room(quote, choices, fixed_pages, occupancy):
            return LayoutConflict(quote, pages)
    return Layout(occupancy.assignments())
