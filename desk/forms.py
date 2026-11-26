from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from desk.briefs import SEAT_LABELS
from desk.sheets import PrintSheet

if TYPE_CHECKING:
    from desk.returns import ReturnDecision
    from release.preprints import PreprintRecord


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


def _render_preprint_pages(pages):
    rows = ''.join(
        f'<tr><td>{escape(page.quote)}</td><td>第 {page.page} 页</td><td>{escape(page.text)}</td></tr>'
        for page in pages
    )
    return (
        '<table><thead><tr><th>引文</th><th>页号</th><th>原文</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
    )


def render_preprint_form(preview, action='/preprint', action_label='按这组页签领'):
    pages = preview['pages']
    rows = ''.join(
        f'<tr><td>{escape(page["quote"])}</td><td>第 {page["page"]} 页</td>'
        f'<td>{escape(page["text"])}</td></tr>'
        for page in pages
    )
    pins = '\n'.join(f'{page["quote"]}\t{page["page"]}' for page in pages)
    book = escape(preview['book'])
    return (
        '<section><h1>先印预览</h1>'
        f'<p>册 {book} · 编印轮次 #{preview["round"]} · 来源稿 #{preview["revision"]}</p>'
        '<p>以下页号可应付两席所有仍可报回的组合，余页可随组合另排。预览不授权印刷，'
        '须按这组页签领后才可开印。</p>'
        '<table><thead><tr><th>引文</th><th>页号</th><th>原文</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        f'<form action="{escape(action)}" method="post">'
        f'<input type="hidden" name="book" value="{book}">'
        f'<input type="hidden" name="round" value="{preview["round"]}">'
        f'<input type="hidden" name="revision" value="{preview["revision"]}">'
        f'<label>实际所审页组（每行引文键、制表符、页号）'
        f'<textarea name="pins" rows="4" spellcheck="false">{escape(pins)}</textarea></label>'
        f'<button type="submit">{escape(action_label)}</button></form></section>'
    )


def render_preprint_result(record: 'PreprintRecord', repeated):
    stamp = '复领原底稿' if repeated else '签领完成'
    return (
        f'<section><h1>先印签领 · {stamp}</h1>'
        f'<p>底稿 #{record.id} · 册 {escape(record.book)} · 轮次 #{record.round_id} · '
        f'来源稿 #{record.revision}</p>{_render_preprint_pages(record.pages)}'
        f'<p><a href="/preprint?id={record.id}">按底稿号查阅</a></p></section>'
    )
