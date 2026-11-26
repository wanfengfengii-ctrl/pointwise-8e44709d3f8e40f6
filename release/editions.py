from dataclasses import dataclass

from desk.options import PrintOption
from desk.returns import PrintReturn
from draft.revisions import Revision
from layout.solver import Layout


@dataclass(frozen=True)
class WorkingEdition:
    id: int
    book: str
    title: str
    ordinal: int
    revision_id: int | None
    fixed_id: int | None


@dataclass(frozen=True)
class _FixedPage:
    quote: str
    page: int
    text: str


@dataclass(frozen=True)
class FixedEdition:
    id: int
    book: str
    round_id: int
    revision_id: int
    pages: tuple[_FixedPage, ...]
    returns: tuple[PrintReturn, ...]
    preprint: int | None = None


def register_booklet(db, book, title):
    if not isinstance(book, str) or not book.strip() or not isinstance(title, str) or not title.strip():
        raise ValueError('样例册缺少册号或标题。')
    db.execute('INSERT INTO books(id, title) VALUES (?, ?)', (book, title))
    db.execute('INSERT INTO rounds(book, ordinal) VALUES (?, 1)', (book,))


def find_working_edition(db, book):
    row = db.execute(
        '''SELECT r.id, r.book, b.title, r.ordinal, r.revision, f.id AS fixed_id
             FROM rounds AS r JOIN books AS b ON b.id = r.book
             LEFT JOIN fixed_editions AS f ON f.round_id = r.id
            WHERE r.book = ? ORDER BY r.ordinal DESC LIMIT 1''',
        (book,),
    ).fetchone()
    if row is None:
        return None
    return WorkingEdition(row['id'], row['book'], row['title'], row['ordinal'], row['revision'], row['fixed_id'])


def publish_revision(db, working, revision_id):
    if working.fixed_id is None:
        db.execute('UPDATE rounds SET revision = ? WHERE id = ?', (revision_id, working.id))
    else:
        db.execute(
            'INSERT INTO rounds(book, ordinal, revision) VALUES (?, ?, ?)',
            (working.book, working.ordinal + 1, revision_id),
        )
    return find_working_edition(db, working.book)


def save_fixed_edition(db, working, revision: Revision, layout: Layout, actuals, preprint_id=None):
    cursor = db.execute(
        'INSERT INTO fixed_editions(book, round_id, revision, preprint) VALUES (?, ?, ?, ?)',
        (working.book, working.id, revision.number, preprint_id),
    )
    edition_id = cursor.lastrowid
    contents = {quote.key: quote.text for quote, _ in revision.rows}
    db.executemany(
        'INSERT INTO fixed_pages(edition, quote, page, body) VALUES (?, ?, ?, ?)',
        ((edition_id, key, str(page), contents[key]) for key, page in layout.assignments),
    )
    db.executemany(
        '''INSERT INTO fixed_citations(edition, seat, sheet, short_no, quote, page)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (
            (edition_id, actual.seat, actual.sheet_id, actual.option.number,
             actual.option.quote, str(actual.option.page))
            for actual in actuals
        ),
    )
    return find_fixed_edition_snapshot(db, edition_id)


def find_fixed_edition_snapshot(db, edition_id):
    header = db.execute(
        'SELECT id, book, round_id, revision, preprint FROM fixed_editions WHERE id = ?', (edition_id,)
    ).fetchone()
    if header is None:
        return None
    pages = db.execute('SELECT quote, page, body FROM fixed_pages WHERE edition = ?', (edition_id,))
    indexes = db.execute(
        'SELECT seat, sheet, short_no, quote, page FROM fixed_citations WHERE edition = ? ORDER BY seat',
        (edition_id,),
    )
    returns = []
    for row in indexes:
        option = PrintOption(row['sheet'], row['short_no'], row['quote'], int(row['page']))
        returns.append(PrintReturn(header['book'], row['seat'], header['round_id'], row['sheet'], option))
    return FixedEdition(
        edition_id, header['book'], header['round_id'], header['revision'],
        tuple(_FixedPage(row['quote'], int(row['page']), row['body']) for row in pages),
        tuple(returns), header['preprint'],
    )
