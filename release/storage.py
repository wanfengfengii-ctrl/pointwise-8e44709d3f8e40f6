import sqlite3
from contextlib import contextmanager


_SCHEMA = '''
CREATE TABLE IF NOT EXISTS books (
    id TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS seed_marks (
    name TEXT PRIMARY KEY NOT NULL
);
CREATE TABLE IF NOT EXISTS seat_briefs (
    book TEXT NOT NULL REFERENCES books(id),
    seat TEXT NOT NULL CHECK (seat IN ('left', 'right')),
    quote TEXT NOT NULL,
    PRIMARY KEY (book, seat)
);
CREATE TABLE IF NOT EXISTS revisions (
    id INTEGER PRIMARY KEY,
    book TEXT NOT NULL REFERENCES books(id),
    UNIQUE (id, book)
);
CREATE TABLE IF NOT EXISTS revision_quotes (
    revision INTEGER NOT NULL REFERENCES revisions(id),
    quote TEXT NOT NULL,
    body TEXT NOT NULL,
    allowed TEXT NOT NULL,
    PRIMARY KEY (revision, quote)
);
CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY,
    book TEXT NOT NULL REFERENCES books(id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    revision INTEGER,
    UNIQUE (book, ordinal),
    UNIQUE (id, book),
    FOREIGN KEY (revision, book) REFERENCES revisions(id, book)
);
CREATE TABLE IF NOT EXISTS sheets (
    id INTEGER PRIMARY KEY,
    book TEXT NOT NULL,
    round_id INTEGER NOT NULL,
    seat TEXT NOT NULL,
    issued_revision INTEGER NOT NULL,
    UNIQUE (round_id, seat),
    FOREIGN KEY (round_id, book) REFERENCES rounds(id, book),
    FOREIGN KEY (book, seat) REFERENCES seat_briefs(book, seat),
    FOREIGN KEY (issued_revision, book) REFERENCES revisions(id, book)
);
CREATE TABLE IF NOT EXISTS sheet_options (
    sheet INTEGER NOT NULL REFERENCES sheets(id),
    short_no INTEGER NOT NULL CHECK (short_no > 0),
    quote TEXT NOT NULL,
    page TEXT NOT NULL,
    PRIMARY KEY (sheet, short_no),
    UNIQUE (sheet, quote, page)
);
CREATE TABLE IF NOT EXISTS print_returns (
    sheet INTEGER PRIMARY KEY,
    short_no INTEGER NOT NULL,
    UNIQUE (sheet, short_no),
    FOREIGN KEY (sheet, short_no) REFERENCES sheet_options(sheet, short_no)
);
CREATE TABLE IF NOT EXISTS fixed_editions (
    id INTEGER PRIMARY KEY,
    book TEXT NOT NULL,
    round_id INTEGER NOT NULL UNIQUE,
    revision INTEGER NOT NULL,
    FOREIGN KEY (round_id, book) REFERENCES rounds(id, book),
    FOREIGN KEY (revision, book) REFERENCES revisions(id, book)
);
CREATE TABLE IF NOT EXISTS fixed_pages (
    edition INTEGER NOT NULL REFERENCES fixed_editions(id),
    quote TEXT NOT NULL,
    page TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (edition, quote),
    UNIQUE (edition, page),
    UNIQUE (edition, quote, page)
);
CREATE TABLE IF NOT EXISTS fixed_citations (
    edition INTEGER NOT NULL REFERENCES fixed_editions(id),
    seat TEXT NOT NULL CHECK (seat IN ('left', 'right')),
    sheet INTEGER NOT NULL,
    short_no INTEGER NOT NULL,
    quote TEXT NOT NULL,
    page TEXT NOT NULL,
    PRIMARY KEY (edition, seat),
    FOREIGN KEY (sheet, short_no) REFERENCES print_returns(sheet, short_no),
    FOREIGN KEY (edition, quote, page) REFERENCES fixed_pages(edition, quote, page)
);
'''


def open_database(path):
    db = sqlite3.connect(path, isolation_level=None, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db


def create_schema(db):
    try:
        db.executescript('BEGIN IMMEDIATE;\n' + _SCHEMA + '\nCOMMIT;')
    except BaseException:
        db.rollback()
        raise


@contextmanager
def _transaction(db, begin):
    db.execute(begin)
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise


def write_transaction(db):
    return _transaction(db, 'BEGIN IMMEDIATE')


def read_transaction(db):
    return _transaction(db, 'BEGIN')
