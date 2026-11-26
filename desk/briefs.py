from dataclasses import dataclass


SEATS = ('left', 'right')
SEAT_LABELS = {'left': '左席', 'right': '右席'}


@dataclass(frozen=True)
class SeatBrief:
    book: str
    seat: str
    quote: str


def store_seat_briefs(db, book, assignments):
    if set(assignments) != set(SEATS):
        raise ValueError('样例册需要左席和右席各一份任务。')
    rows = []
    for seat in SEATS:
        quote = assignments[seat]
        if not isinstance(quote, str) or not quote or any(ch.isspace() for ch in quote):
            raise ValueError(f'{SEAT_LABELS[seat]}的引文键无效。')
        rows.append((book, seat, quote))
    db.executemany('INSERT INTO seat_briefs(book, seat, quote) VALUES (?, ?, ?)', rows)


def load_seat_brief(db, book, seat):
    row = db.execute(
        'SELECT book, seat, quote FROM seat_briefs WHERE book = ? AND seat = ?', (book, seat)
    ).fetchone()
    return None if row is None else SeatBrief(row['book'], row['seat'], row['quote'])
