from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from desk.briefs import SEAT_LABELS
from desk.sheets import PrintSheet

if TYPE_CHECKING:
    from desk.returns import ReturnDecision


@dataclass(frozen=True)
class ReturnSubmission:
    book: str
    seat: str
    sheet_id: int
    option: str


def parse_fields(encoded):
    return parse_qs(
        encoded, keep_blank_values=True, strict_parsing=True,
        max_num_fields=32, encoding='utf-8', errors='strict',
    )


def field_value(fields, name, *, default=None):
    values = fields.get(name)
    if values is None and default is not None:
        return default
    if values is None or len(values) != 1:
        raise ValueError(f'字段 {name} 必须提交一次。')
    return values[0]


def positive_identifier(value):
    if not value.isascii() or not value.isdecimal():
        raise ValueError('编号必须是正整数。')
    number = int(value)
    if not 0 < number <= 2**63 - 1:
        raise ValueError('编号超出有效范围。')
    return number


def parse_return_form(fields):
    if set(fields) != {'book', 'seat', 'sheet', 'option'}:
        raise ValueError('报回需要原网页中的册、席、纸单和实印选项。')
    book = field_value(fields, 'book')
    seat = field_value(fields, 'seat')
    sheet_id = positive_identifier(field_value(fields, 'sheet'))
    option = field_value(fields, 'option')
    if not all((book, seat, option)):
        raise ValueError('报回字段不能为空。')
    return ReturnSubmission(book, seat, sheet_id, option)


def render_sheet_form(sheet: PrintSheet, action='/return'):
    book = escape(sheet.book)
    seat = escape(sheet.seat)
    choices = []
    for option in sheet.options:
        key = escape(option.quote)
        choices.append(
            f'<label><input type="radio" name="option" value="{escape(option.value)}" '
            f'data-quote="{key}" data-page="{option.page}" data-number="{option.number}" required> '
            f'{key} → 第 {option.page} 页（选项 {option.number}）</label>'
        )
    return (
        f'<section><h1>{SEAT_LABELS[sheet.seat]}纸单 #{sheet.id}</h1>'
        f'<p>册 {book} · 编印轮次 #{sheet.round_id}</p>'
        '<p>从这张纸单选择实际印出的索引并报回。</p>'
        f'<form action="{escape(action)}" method="post">'
        f'<input type="hidden" name="book" value="{book}">'
        f'<input type="hidden" name="seat" value="{seat}">'
        f'<input type="hidden" name="sheet" value="{sheet.id}">'
        '<fieldset><legend>实际印选</legend>' + ''.join(choices) + '</fieldset>'
        '<button type="submit">报回实印</button></form></section>'
    )


def render_return_result(decision: ReturnDecision):
    body = f'<section><h1>实印报回</h1><p>{escape(decision.message)}</p>'
    actual = decision.actual
    if actual is not None:
        option = actual.option
        body += (
            f'<p>{SEAT_LABELS[actual.seat]}纸单 #{actual.sheet_id} · '
            f'选项 {option.number} · {escape(option.quote)} → 第 {option.page} 页</p>'
        )
    return body + '</section>'
