from dataclasses import dataclass

from draft.pages import normalize_allowed_pages
from draft.quotes import Quote, validate_quotes


@dataclass(frozen=True)
class Revision:
    book: str
    number: int | None
    rows: tuple[tuple[Quote, tuple[int, ...]], ...]

    def page_grid(self):
        return {quote.key: pages for quote, pages in self.rows}


def build_revision(book, rows, number=None):
    rows = tuple(rows)
    quotes = validate_quotes(quote for quote, _ in rows)
    normalized = []
    for quote, (_, pages) in zip(quotes, rows, strict=True):
        try:
            allowed = normalize_allowed_pages(pages)
        except ValueError as error:
            raise ValueError(f'引文 {quote.key}：{error}') from error
        normalized.append((quote, allowed))
    normalized.sort(key=lambda row: row[0].key)
    return Revision(book, number, tuple(normalized))
