from draft.revision_store import insert_revision
from draft.revisions import build_revision


def revise(db, book, rows):
    if db.execute('SELECT 1 FROM books WHERE id = ?', (book,)).fetchone() is None:
        raise LookupError('找不到这册折页。')
    revision = build_revision(book, rows)
    return insert_revision(db, revision)
