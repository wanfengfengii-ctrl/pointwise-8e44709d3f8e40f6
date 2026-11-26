from dataclasses import dataclass

from desk.options import PrintOption, number_sheet_options


@dataclass(frozen=True)
class PrintSheet:
    id: int
    book: str
    round_id: int
    seat: str
    issued_revision: int
    options: tuple[PrintOption, ...]


def find_sheet(db, sheet_id):
    row = db.execute(
        'SELECT id, book, round_id, seat, issued_revision FROM sheets WHERE id = ?', (sheet_id,)
    ).fetchone()
    if row is None:
        return None
    options = db.execute(
        'SELECT short_no, quote, page FROM sheet_options WHERE sheet = ? ORDER BY short_no',
        (sheet_id,),
    )
    return PrintSheet(
        row['id'], row['book'], row['round_id'], row['seat'], row['issued_revision'],
        tuple(PrintOption(sheet_id, item['short_no'], item['quote'], int(item['page'])) for item in options),
    )


def find_round_sheet(db, round_id, seat):
    row = db.execute(
        'SELECT id FROM sheets WHERE round_id = ? AND seat = ?', (round_id, seat)
    ).fetchone()
    return None if row is None else find_sheet(db, row['id'])


def save_issued_sheet(db, book, round_id, seat, revision_id, drafts):
    drafts = tuple(drafts)
    if not drafts:
        raise ValueError('纸单至少需要一个可选印项。')
    cursor = db.execute(
        'INSERT INTO sheets(book, round_id, seat, issued_revision) VALUES (?, ?, ?, ?)',
        (book, round_id, seat, revision_id),
    )
    sheet_id = cursor.lastrowid
    options = number_sheet_options(sheet_id, drafts)
    db.executemany(
        'INSERT INTO sheet_options(sheet, short_no, quote, page) VALUES (?, ?, ?, ?)',
        ((sheet_id, item.number, item.quote, str(item.page)) for item in options),
    )
    return PrintSheet(sheet_id, book, round_id, seat, revision_id, options)
