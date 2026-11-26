from dataclasses import dataclass
from itertools import product

from draft.revision_store import load_revision
from layout.placements import PagePin
from layout.proof import describe_conflict, preview
from release.commitments import load_seat_promises
from release.editions import find_working_edition


@dataclass(frozen=True)
class PreprintPage:
    quote: str
    page: int
    text: str


@dataclass(frozen=True)
class PreprintRecord:
    id: int
    book: str
    round_id: int
    revision: int
    pages: tuple[PreprintPage, ...]

    def page_map(self):
        return {page.quote: page.page for page in self.pages}


class PreprintRefused(Exception):
    """A well-formed request that the current state cannot honour."""

    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def _quote_texts(revision):
    return {quote.key: quote.text for quote, _ in revision.rows}


def _describe_pins(pins):
    return '、'.join(f'{pin.quote}→{pin.page}' for pin in pins) or '空单'


def _loaded_promises(db, round_id):
    promises = load_seat_promises(db, round_id)
    if any(promise.sheet_id is None for promise in promises):
        raise PreprintRefused('两席都领取原纸单后才可先印。')
    return promises


def _remaining(revision, fixed_pins, promises):
    """Each layout the two seats can still report, on top of the fixed pages."""
    for combination in product(*(promise.choices() for promise in promises)):
        pins = tuple(fixed_pins) + tuple(combination)
        yield pins, preview(revision, pins)


def _coverage_failure(revision, fixed_pins, promises):
    for pins, result in _remaining(revision, fixed_pins, promises):
        if result.layout is None:
            return (
                f'两席仍可报回的组合 {_describe_pins(pins)} 无法排完整册：'
                f'{describe_conflict(result.conflict)}'
            )
    return None


def _round_header(db, book, round_id):
    return db.execute(
        '''SELECT r.id, r.book, r.revision, f.id AS fixed_id
             FROM rounds AS r LEFT JOIN fixed_editions AS f ON f.round_id = r.id
            WHERE r.id = ? AND r.book = ?''',
        (round_id, book),
    ).fetchone()


def _current_round(db, book):
    working = find_working_edition(db, book)
    if working is None:
        raise LookupError('找不到这册折页。')
    return working


def preview_preprint(db, book, quotes):
    """Pick one page per selected quote that survives every remaining seat choice."""
    working = _current_round(db, book)
    if working.fixed_id is not None:
        raise PreprintRefused('本轮已成册，不能先印。')
    if working.revision_id is None:
        raise PreprintRefused('正式稿发布后才可先印。')
    selected = list(dict.fromkeys(quotes))
    if not selected:
        raise PreprintRefused('请先选择一组非空正文引文。')
    revision = load_revision(db, book, working.revision_id)
    grid = revision.page_grid()
    for key in selected:
        if key not in grid:
            raise LookupError(f'稿中没有引文 {key}。')
    promises = _loaded_promises(db, working.id)

    texts = _quote_texts(revision)
    ordered = sorted(selected)
    # Only the selected quotes' pages are fixed; leftover quotes may follow each combination.
    for assignment in product(*(grid[key] for key in ordered)):
        if len(set(assignment)) != len(assignment):
            continue
        pages = dict(zip(ordered, assignment))
        pins = tuple(PagePin(key, pages[key]) for key in ordered)
        result = preview(revision, pins)
        if result.layout is None:
            continue
        if _coverage_failure(revision, pins, promises) is not None:
            continue
        rows = [
            {'quote': key, 'page': pages[key], 'text': texts[key]}
            for key in sorted(selected, key=lambda key: (pages[key], key))
        ]
        return {
            'book': book,
            'round': working.id,
            'revision': working.revision_id,
            'pages': rows,
        }
    chosen = '、'.join(selected)
    raise PreprintRefused(f'所选引文 {chosen} 找不到共同排法，未能先印，原单照常办理。')


def _normalize_pins(pins):
    by_quote = {}
    by_page = {}
    for pin in pins:
        if pin.quote in by_quote and by_quote[pin.quote] != pin.page:
            raise PreprintRefused(f'引文 {pin.quote} 被指定到不同页。')
        if pin.page in by_page and by_page[pin.page] != pin.quote:
            raise PreprintRefused(f'第 {pin.page} 页被指定给多段引文。')
        by_quote[pin.quote] = pin.page
        by_page[pin.page] = pin.quote
    return by_quote


def sign_preprint(db, book, round_id, revision_id, pins):
    """Record the audited page group for this round, or return the existing one."""
    header = _round_header(db, book, round_id)
    if header is None:
        raise LookupError('找不到该册的这一轮。')
    source = load_revision(db, book, revision_id)
    if source is None:
        raise LookupError('找不到该册的修订。')
    audited = _normalize_pins(pins)
    if not audited:
        raise PreprintRefused('请提交实际所审的整组页码。')
    existing = round_preprint(db, round_id)
    if existing is not None:
        if existing.revision == revision_id and existing.page_map() == audited:
            return existing, True
        raise PreprintRefused('本轮已有另一份签领底稿，不能另选。')

    working = _current_round(db, book)
    if working.id != round_id or working.fixed_id is not None:
        raise PreprintRefused('首次签领须指向当前未成册轮。')
    if working.revision_id is None:
        raise PreprintRefused('正式稿发布后才可签领。')
    current = load_revision(db, book, working.revision_id)
    source_grid = source.page_grid()
    current_grid = current.page_grid()
    source_texts = _quote_texts(source)
    current_texts = _quote_texts(current)
    for quote, page in audited.items():
        if quote not in source_grid:
            raise LookupError(f'稿中没有引文 {quote}。')
        if page not in source_grid[quote]:
            raise PreprintRefused(f'所审页 {quote}→{page} 不在来源稿允许页内。')
        if quote not in current_grid or page not in current_grid[quote]:
            raise PreprintRefused(f'引文 {quote} 已不在第 {page} 页，所审页失效。')
        if source_texts.get(quote) != current_texts.get(quote):
            raise PreprintRefused(f'引文 {quote} 的原文与来源稿不同，所审原文失效。')

    promises = _loaded_promises(db, working.id)
    ordered = tuple(PagePin(quote, audited[quote]) for quote in sorted(audited))
    failure = _coverage_failure(current, ordered, promises)
    if failure is not None:
        raise PreprintRefused(failure)

    cursor = db.execute(
        'INSERT INTO preprints(book, round_id, revision) VALUES (?, ?, ?)',
        (book, round_id, revision_id),
    )
    preprint_id = cursor.lastrowid
    db.executemany(
        'INSERT INTO preprint_pages(preprint, quote, page, body) VALUES (?, ?, ?, ?)',
        (
            (preprint_id, quote, str(page), source_texts[quote])
            for quote, page in sorted(audited.items())
        ),
    )
    record = load_preprint(db, preprint_id)
    return record, False


def load_preprint(db, preprint_id):
    header = db.execute(
        'SELECT id, book, round_id, revision FROM preprints WHERE id = ?', (preprint_id,)
    ).fetchone()
    if header is None:
        return None
    rows = db.execute(
        'SELECT quote, page, body FROM preprint_pages WHERE preprint = ? ORDER BY CAST(page AS INTEGER), quote',
        (preprint_id,),
    )
    return PreprintRecord(
        header['id'], header['book'], header['round_id'], header['revision'],
        tuple(PreprintPage(row['quote'], int(row['page']), row['body']) for row in rows),
    )


def round_preprint(db, round_id):
    row = db.execute('SELECT id FROM preprints WHERE round_id = ?', (round_id,)).fetchone()
    return None if row is None else load_preprint(db, row['id'])


def current_preprint(db, book):
    """The signed draft for this book's current round, if the round already has one."""
    working = _current_round(db, book)
    return round_preprint(db, working.id)


def preprint_blocker(revision, pages):
    """Return why a signed page group no longer holds in this revision, if it does not."""
    grid = revision.page_grid()
    texts = _quote_texts(revision)
    for page in pages:
        if page.quote not in grid or page.page not in grid[page.quote]:
            return f'已签页 {page.quote}→{page.page} 在新稿中已不允许。'
        if texts.get(page.quote) != page.text:
            return f'已签页 {page.quote}→{page.page} 的原文已被改写或移除。'
    return None
