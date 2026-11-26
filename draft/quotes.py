from dataclasses import dataclass


@dataclass(frozen=True)
class Quote:
    key: str
    text: str


def validate_quotes(quotes):
    validated = []
    seen = set()
    for quote in quotes:
        if not isinstance(quote, Quote):
            raise ValueError('每条引文应包含引文键和正文。')
        if not isinstance(quote.key, str) or not quote.key.strip():
            raise ValueError('引文键不能为空。')
        if quote.key != quote.key.strip() or any(ch.isspace() for ch in quote.key):
            raise ValueError('引文键不能包含空白。')
        if not isinstance(quote.text, str) or not quote.text.strip():
            raise ValueError(f'引文 {quote.key} 缺少正文。')
        if quote.key in seen:
            raise ValueError(f'引文键 {quote.key} 重复。')
        seen.add(quote.key)
        validated.append(quote)
    return tuple(validated)
