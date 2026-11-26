import json

from draft.quotes import Quote
from draft.revisions import Revision


def insert_revision(db, revision):
    cursor = db.execute('INSERT INTO revisions(book) VALUES (?)', (revision.book,))
    number = cursor.lastrowid
    db.executemany(
        'INSERT INTO revision_quotes(revision, quote, body, allowed) VALUES (?, ?, ?, ?)',
        (
            (number, quote.key, quote.text, json.dumps(pages))
            for quote, pages in revision.rows
        ),
    )
    return number


def load_revision(db, book, number):
    header = db.execute(
        'SELECT id FROM revisions WHERE book = ? AND id = ?', (book, number)
    ).fetchone()
    if header is None:
        return None
    rows = db.execute(
        'SELECT quote, body, allowed FROM revision_quotes WHERE revision = ? ORDER BY quote',
        (number,),
    )
    return Revision(
        book,
        number,
        tuple((Quote(row['quote'], row['body']), tuple(json.loads(row['allowed']))) for row in rows),
    )
