import json
import unittest
from contextlib import closing, contextmanager
from dataclasses import dataclass
from functools import partial
from html.parser import HTMLParser
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlencode, urlsplit

from desk.http import WorkbenchHandler
from release.bootstrap import SAMPLE_BOOK, SAMPLE_PATH, initialize_workspace
from release.storage import open_database


@dataclass(frozen=True)
class BrowserOption:
    value: str
    quote: str
    page: int
    number: int


class SavedSheet(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.action = None
        self.hidden = {}
        self.options = []
        self._inside_form = False
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attributes):
        fields = dict(attributes)
        if tag == 'form' and fields.get('method', '').lower() == 'post':
            self.action = fields['action']
            self._inside_form = True
        if tag != 'input' or not self._inside_form:
            return
        if fields.get('type') == 'hidden':
            self.hidden[fields['name']] = fields['value']
        if fields.get('type') == 'radio' and fields.get('name') == 'option':
            self.options.append(BrowserOption(
                fields['value'], fields['data-quote'], int(fields['data-page']), int(fields['data-number'])
            ))

    def handle_endtag(self, tag):
        if tag == 'form':
            self._inside_form = False

    def choice(self, page):
        return next(option for option in self.options if option.page == page)

    def fields_for(self, page):
        return dict(self.hidden, option=self.choice(page).value)

    @property
    def number(self):
        return int(self.hidden['sheet'])


class _QuietWorkbench(WorkbenchHandler):
    def log_message(self, format, *args):
        pass


@contextmanager
def running_workbench(database):
    factory = partial(_QuietWorkbench, database=database)
    with ThreadingHTTPServer(('127.0.0.1', 0), factory) as server:
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            thread.join()


class WorkbenchCase(unittest.TestCase):
    book = SAMPLE_BOOK

    def setUp(self):
        self.temp = Path(self.enterContext(TemporaryDirectory()))
        self.database = self.temp / 'workbench.sqlite3'
        with closing(open_database(self.database)) as db:
            initialize_workspace(db)
        self.port = self.enterContext(running_workbench(self.database))

    def request(self, path, *, query=None, form=None, status=200, html=False):
        if query is not None:
            path += '?' + urlencode(query)
        headers = {'Accept': 'text/html' if html else 'application/json'}
        body = None
        method = 'GET'
        if form is not None:
            method = 'POST'
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            body = urlencode(form).encode('ascii')
        with closing(HTTPConnection('127.0.0.1', self.port, timeout=5)) as connection:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            text = response.read().decode('utf-8')
            self.assertEqual(response.status, status, text)
        return text if html else json.loads(text)

    def revise(self, rows=None, *, status=200):
        if rows is None:
            rows = json.loads(SAMPLE_PATH.read_text(encoding='utf-8'))['quotes']
        if not isinstance(rows, str):
            rows = '\n'.join(
                f"{row['key']}\t{','.join(map(str, row['pages']))}\t{row['text']}" for row in rows
            )
        answer = self.request('/revise', form={'book': self.book, 'quotes': rows}, status=status)
        return answer['revision'] if status == 200 else answer

    def preview(self, revision, pins='', *, status=200):
        query = {'book': self.book, 'revision': revision, 'pins': pins}
        return self.request('/preview', query=query, status=status)

    def amend(self, revision, *, status=200):
        return self.request('/amend', form={'book': self.book, 'revision': revision}, status=status)

    def sheet(self, seat):
        text = self.request('/sheet', query={'book': self.book, 'seat': seat}, html=True)
        original = SavedSheet(text)
        self.assertTrue(original.options, text)
        self.assertEqual(original.hidden['seat'], seat)
        self.assertEqual(original.hidden['book'], self.book)
        return original

    def report(self, sheet, page, *, status=200, html=False):
        target = urlsplit(sheet.action)
        self.assertEqual((target.scheme, target.hostname, target.port, target.path),
                         ('http', '127.0.0.1', self.port, '/return'))
        return self.request(target.path, form=sheet.fields_for(page), status=status, html=html)

    def bind(self, *, status=200):
        return self.request('/bind', form={'book': self.book}, status=status)

    def read(self, edition, *, status=200, html=False):
        return self.request('/read', query={'id': edition}, status=status, html=html)

    def current(self):
        return self.request('/', query={'book': self.book})

    def scalar(self, sql, parameters=()):
        with closing(open_database(self.database)) as db:
            return db.execute(sql, parameters).fetchone()[0]

    def open_sample_round(self):
        first = self.revise()
        self.assertTrue(self.amend(first)['accepted'])
        return first

    def complete_sample_round(self):
        self.open_sample_round()
        left, right = self.sheet('left'), self.sheet('right')
        self.assertEqual(self.report(left, 3)['status'], 'accepted')
        self.assertEqual(self.report(right, 5)['status'], 'accepted')
        return self.bind(), left, right

    def scenario(self, case_id, inputs, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
        self.assertEqual(actual, expected)
        self.assertEqual(downstream_actual, downstream_expected)
        record = {
            'case_id': case_id, 'input': inputs, 'expected': expected, 'actual': actual,
            'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
            'code_paths': code_paths, 'oracle': oracle,
        }
        print('POINTWISE_SCENARIO ' + json.dumps(record, ensure_ascii=False, sort_keys=True), flush=True)
