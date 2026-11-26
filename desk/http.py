import argparse
import json
from contextlib import closing
from dataclasses import asdict
from functools import partial
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from desk.briefs import SEAT_LABELS, SEATS
from desk.forms import field_value, parse_fields, parse_return_form, positive_identifier
from desk.forms import render_preprint_form, render_preprint_result, render_return_result, render_sheet_form
from desk.issue import issue_sheet
from desk.returns import accept_return
from draft.editor import revise
from draft.pages import validate_page_number
from draft.quotes import Quote
from draft.revision_store import load_revision
from layout.placements import PagePin
from layout.proof import describe_conflict, preview
from reading.proof import read_edition
from release.amendments import amend
from release.binding import bind
from release.bootstrap import SAMPLE_BOOK, initialize_workspace
from release.commitments import can_offer_option, load_seat_promises
from release.editions import find_working_edition
from release.preprints import PreprintRefused, load_preprint, preview_preprint, sign_preprint
from release.storage import open_database, read_transaction, write_transaction


_STYLE = Path(__file__).with_name('workbench.css')
_MAX_FORM_BYTES = 256 * 1024


class _RequestProblem(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _page_number(value):
    value = value.strip()
    if not value.isascii() or not value.isdecimal():
        raise ValueError('页号必须是正整数。')
    return validate_page_number(int(value))


def _quote_rows(raw):
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split('\t', 2)
        if len(parts) != 3:
            raise ValueError('每行稿件需要引文键、页格和正文，使用制表符分列。')
        key, pages, text = parts
        yield Quote(key, text), tuple(_page_number(page) for page in pages.split(','))


def _pins(raw):
    for line in raw.splitlines():
        if not line.strip():
            continue
        fields = line.split('\t')
        if len(fields) != 2 or not fields[0]:
            raise ValueError('指定页每行需要引文键和页号，使用制表符分列。')
        yield PagePin(fields[0], _page_number(fields[1]))


def _notice(title, message):
    return f'<section><h1>{escape(title)}</h1><p>{escape(message)}</p></section>'


def _selected_result(actual):
    if actual is None:
        return None
    option = actual.option
    return {
        'book': actual.book, 'seat': actual.seat, 'round': actual.round_id,
        'sheet': actual.sheet_id, 'option': option.value, 'number': option.number,
        'quote': option.quote, 'page': option.page,
    }


def _render_bound(view):
    report = '两席索引均与正文相符。' if view.verified else '实印索引与固定正文不符。'
    source = ''
    if view.preprint is not None:
        source = (
            f' · 先印底稿 <a href="/preprint?book={escape(view.book)}&amp;id={view.preprint}">'
            f'#{view.preprint}</a>'
        )
    indexes = ''.join(
        f'<li>{SEAT_LABELS[item.seat]}纸单 #{item.sheet}，选项 {item.number}：'
        f'<a href="#page-{item.page}">{escape(item.quote)} → 第 {item.page} 页</a></li>'
        for item in view.citations
    )
    pages = ''.join(
        f'<article id="page-{page.page}"><h2>第 {page.page} 页 · {escape(page.quote)}</h2>'
        f'<p>{escape(page.text)}</p></article>'
        for page in view.pages
    )
    return (
        f'<h1>固定册 #{view.edition}</h1><p>正文修订 #{view.revision} · {report}{source}</p>'
        f'<section><h2>实印索引</h2><ul>{indexes}</ul></section>{pages}'
    )


def _render_workbench(working):
    book = escape(working.book)
    hidden = f'<input type="hidden" name="book" value="{book}">'
    revision_field = '<label>修订号 <input name="revision" type="number" min="1" required></label>'
    status = '待发布首稿' if working.revision_id is None else f'正式稿 #{working.revision_id}'
    if working.fixed_id is not None:
        status += f' · <a href="/read?id={working.fixed_id}">已固定册 #{working.fixed_id}</a>'
    links = []
    for seat in SEATS:
        query = escape(urlencode({'book': working.book, 'seat': seat}))
        links.append(f'<li><a href="/sheet?{query}">打开{SEAT_LABELS[seat]}纸单</a></li>')
    seats = ''.join(links)
    return f'''
<h1>{escape(working.title)}</h1>
<p>册 {book} · 第 {working.ordinal} 轮 · {status}</p>
<div class="grid">
<section><h2>录入页格稿</h2><form action="/revise" method="post">{hidden}
<label>每行用制表符分隔引文键、逗号分隔的页格、正文。
<textarea name="quotes" rows="6" spellcheck="false"></textarea></label>
<button>保存修订</button></form></section>
<section><h2>整册试排</h2><form action="/preview" method="get">{hidden}{revision_field}
<label>指定页码（选填，每行填写引文键、制表符、页号）<textarea name="pins" rows="3"></textarea></label>
<button>计算完整布局</button></form></section>
<section><h2>先印预览</h2><form action="/preprint" method="get">{hidden}
<label>引文键（空白分隔，例如 <code>C D</code>）<input name="quotes" required></label>
<button>预览先印页</button></form>
<form action="/preprint" method="get">{hidden}
<label>按底稿号查阅 <input name="id" type="number" min="1" required></label>
<button>领取先印底稿</button></form></section>
<section><h2>发布正文</h2><form action="/amend" method="post">{hidden}{revision_field}
<button>核定并发布</button></form><h2>领取纸单</h2><ul>{seats}</ul></section>
<section><h2>装订查阅</h2><form action="/bind" method="post">{hidden}<button>按实印成册</button></form>
<form action="/read" method="get"><label>固定册号 <input name="id" type="number" min="1" required></label>
<button>查阅固定册</button></form></section>
</div>'''


class WorkbenchHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, database, **kwargs):
        self.database = database
        super().__init__(*args, **kwargs)

    @property
    def origin(self):
        return f'http://127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        self._handle('GET')

    def do_POST(self):
        self._handle('POST')

    def _send(self, status, content_type, content):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Vary', 'Accept')
        self.end_headers()
        self.wfile.write(content)

    def _respond(self, status, data, body):
        if 'application/json' in self.headers.get('Accept', ''):
            content = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self._send(status, 'application/json; charset=utf-8', content)
            return
        page = (
            '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<base href="{self.origin}/"><link rel="stylesheet" href="/workbench.css">'
            '<title>榆桥折页编印</title></head><body>'
            '<header><a href="/">榆桥社区口述史馆 · 折页编印</a></header>'
            f'<main>{body}</main></body></html>'
        )
        self._send(status, 'text/html; charset=utf-8', page.encode('utf-8'))

    def _form_body(self):
        if self.headers.get_content_type() != 'application/x-www-form-urlencoded':
            raise _RequestProblem(415, '请使用普通网页表单提交。')
        length = self.headers.get('Content-Length', '')
        if not length.isascii() or not length.isdecimal():
            raise _RequestProblem(400, '无法读取表单长度。')
        size = int(length)
        if size > _MAX_FORM_BYTES:
            raise _RequestProblem(413, '表单超过允许的大小。')
        data = self.rfile.read(size)
        if len(data) != size:
            raise _RequestProblem(400, '表单内容不完整。')
        return data.decode('utf-8')

    def _handle(self, method):
        try:
            target = urlsplit(self.path)
            if method == 'GET' and target.path == '/workbench.css':
                self._send(200, 'text/css; charset=utf-8', _STYLE.read_bytes())
                return
            routes = {
                ('GET', '/'): self._home,
                ('POST', '/revise'): self._revise,
                ('GET', '/preview'): self._preview,
                ('GET', '/preprint'): self._preprint,
                ('POST', '/preprint'): self._sign_preprint,
                ('GET', '/sheet'): self._sheet,
                ('POST', '/return'): self._return,
                ('POST', '/amend'): self._amend,
                ('POST', '/bind'): self._bind,
                ('GET', '/read'): self._read,
            }
            route = routes.get((method, target.path))
            if route is None:
                raise LookupError('找不到此编印入口。')
            fields = parse_fields(target.query if method == 'GET' else self._form_body())
            mutates = method == 'POST' or target.path == '/sheet'
            transaction = write_transaction if mutates else read_transaction
            with closing(open_database(self.database)) as db, transaction(db):
                status, data, body = route(db, fields)
        except _RequestProblem as error:
            status, data, body = error.status, {'error': str(error)}, _notice('请求无法办理', str(error))
        except LookupError as error:
            status, data, body = 404, {'error': str(error)}, _notice('未找到', str(error))
        except PreprintRefused as error:
            status, data, body = error.status, {'reason': str(error)}, _notice('先印未能办理', str(error))
        except ValueError as error:
            status, data, body = 400, {'error': str(error)}, _notice('输入有误', str(error))
        self._respond(status, data, body)

    def _home(self, db, fields):
        book = field_value(fields, 'book', default=SAMPLE_BOOK)
        working = find_working_edition(db, book)
        if working is None:
            raise LookupError('找不到这册折页。')
        return 200, asdict(working), _render_workbench(working)

    def _revise(self, db, fields):
        book = field_value(fields, 'book')
        rows = _quote_rows(field_value(fields, 'quotes'))
        revision = revise(db, book, rows)
        return 200, {'revision': revision}, _notice('正文已保存', f'修订 #{revision} 可用于试排或发布。')

    def _preview(self, db, fields):
        book = field_value(fields, 'book')
        number = positive_identifier(field_value(fields, 'revision'))
        revision = load_revision(db, book, number)
        if revision is None:
            raise LookupError('找不到该册的修订。')
        result = preview(revision, tuple(_pins(field_value(fields, 'pins', default=''))))
        if result.layout is None:
            reason = describe_conflict(result.conflict)
            data = {'revision': number, 'pages': None, 'reason': reason}
            return 409, data, _notice('无法完成试排', reason)
        pages = result.layout.page_map()
        lines = ''.join(
            f'<li>第 {page} 页 · {escape(key)}</li>' for key, page in sorted(pages.items(), key=lambda item: item[1])
        )
        if not lines:
            lines = '<li>空稿，无正文页。</li>'
        return 200, {'revision': number, 'pages': pages}, f'<section><h1>完整试排</h1><ol>{lines}</ol></section>'

    def _preprint(self, db, fields):
        if 'id' in fields:
            record = load_preprint(db, positive_identifier(field_value(fields, 'id')))
            book = field_value(fields, 'book', default=None) if 'book' in fields else None
            if record is None or (book is not None and record.book != book):
                raise LookupError('找不到这份先印底稿。')
            data = {
                'book': record.book, 'round': record.round_id, 'revision': record.revision,
                'preprint': record.id,
                'pages': [
                    {'quote': page.quote, 'page': page.page, 'text': page.text}
                    for page in record.pages
                ],
            }
            return 200, data, render_preprint_result(record, repeated=True)
        book = field_value(fields, 'book')
        quotes = field_value(fields, 'quotes', default='')
        selected = [key for key in quotes.split() if key]
        data = preview_preprint(db, book, selected)
        return 200, data, render_preprint_form(data, self.origin + '/preprint')
    def _sign_preprint(self, db, fields):
        if set(fields) != {'book', 'round', 'revision', 'pins'}:
            raise _RequestProblem(400, '签领需要册、轮次、来源稿号和整组页码。')
        book = field_value(fields, 'book')
        round_id = positive_identifier(field_value(fields, 'round'))
        revision_id = positive_identifier(field_value(fields, 'revision'))
        record, repeated = sign_preprint(
            db, book, round_id, revision_id, tuple(_pins(field_value(fields, 'pins'))),
        )
        data = {
            'book': record.book, 'round': record.round_id, 'revision': record.revision,
            'preprint': record.id,
            'pages': [
                {'quote': page.quote, 'page': page.page, 'text': page.text}
                for page in record.pages
            ],
        }
        return 200, data, render_preprint_result(record, repeated)

    def _sheet(self, db, fields):
        book = field_value(fields, 'book')
        seat = field_value(fields, 'seat')
        working = find_working_edition(db, book)
        if working is None or seat not in SEATS:
            raise LookupError('找不到这册的印席。')
        revision = None if working.revision_id is None else load_revision(db, book, working.revision_id)
        promises = load_seat_promises(db, working.id)
        other = next(promise for promise in promises if promise.seat != seat)
        result = issue_sheet(
            db, book, working.id, seat, revision,
            lambda option: can_offer_option(revision, option, other),
        )
        if result.sheet is None:
            return 409, {'reason': result.reason}, _notice('暂不可领取纸单', result.reason)
        sheet = result.sheet
        data = {
            'sheet': sheet.id, 'round': sheet.round_id, 'book': sheet.book, 'seat': sheet.seat,
            'options': [dict(asdict(option), value=option.value) for option in sheet.options],
        }
        return 200, data, render_sheet_form(sheet, self.origin + '/return')

    def _return(self, db, fields):
        decision = accept_return(db, parse_return_form(fields))
        data = {
            'status': decision.status, 'message': decision.message, 'actual': _selected_result(decision.actual),
        }
        return (200 if decision.accepted else 409), data, render_return_result(decision)

    def _amend(self, db, fields):
        book = field_value(fields, 'book')
        revision = positive_identifier(field_value(fields, 'revision'))
        result = amend(db, book, revision)
        data = {
            'accepted': result.accepted, 'current': result.working.revision_id,
            'round': result.working.id, 'reason': result.reason, 'blocked': [asdict(pin) for pin in result.blocked],
        }
        if result.accepted:
            return 200, data, _notice('正文已发布', f'当前正式稿为修订 #{revision}。')
        return 409, data, _notice('改版未获准', result.reason)

    def _bind(self, db, fields):
        result = bind(db, field_value(fields, 'book'))
        if result.edition is None:
            return 409, {'reason': result.reason}, _notice('暂不可成册', result.reason)
        view = read_edition(db, result.edition.id)
        data = dict(asdict(view), repeated=result.repeated)
        if view.preprint is None:
            data.pop('preprint')
        return 200, data, _render_bound(view)

    def _read(self, db, fields):
        edition = positive_identifier(field_value(fields, 'id'))
        view = read_edition(db, edition)
        data = asdict(view)
        if view.preprint is None:
            data.pop('preprint')
        return 200, data, _render_bound(view)


def main(argv=None):
    parser = argparse.ArgumentParser(description='榆桥社区口述史馆折页编印工作台')
    parser.add_argument('--db', type=Path, default=Path('workbench.sqlite3'))
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args(argv)
    with closing(open_database(args.db)) as db:
        initialize_workspace(db)
    factory = partial(WorkbenchHandler, database=args.db)
    with ThreadingHTTPServer(('127.0.0.1', args.port), factory) as server:
        print(f'折页编印工作台 http://127.0.0.1:{server.server_port}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
