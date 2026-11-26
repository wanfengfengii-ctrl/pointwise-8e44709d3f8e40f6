import json
from contextlib import closing

from release.bootstrap import SAMPLE_PATH, initialize_workspace
from release.storage import open_database
from tests.support import WorkbenchCase, running_workbench


class ReadingTests(WorkbenchCase):
    def test_fixed_copy(self):
        bound, old_left, old_right = self.complete_sample_round()
        fixed_number = bound['edition']
        initial = self.read(fixed_number)
        impossible = self.revise('A\t9\t新访谈\nB\t9\t补录')
        self.assertEqual(self.amend(impossible, status=409)['round'], bound['round'])
        self.assertEqual(self.read(fixed_number), initial)
        new_revision = self.revise('A\t10\t新访谈原文。\nB\t9\t重新摘引。\nC\t2\t另一份馆藏记录。')
        new_round = self.amend(new_revision)
        self.assertNotEqual(new_round['round'], bound['round'])
        self.assertEqual(self.report(old_left, 3)['status'], 'repeated')
        self.assertEqual(self.report(old_right, 5)['status'], 'repeated')
        self.bind(status=409)
        left, right = self.sheet('left'), self.sheet('right')
        self.assertNotEqual(left.number, old_left.number)
        self.assertNotEqual(right.number, old_right.number)
        self.report(left, 10)
        self.report(right, 9)
        new_copy = self.read(self.bind()['edition'])
        self.assertEqual([page['page'] for page in new_copy['pages']], [2, 9, 10])
        self.assertEqual(new_copy['pages'][-1]['text'], '新访谈原文。')
        with running_workbench(self.database) as new_port:
            previous_port, self.port = self.port, new_port
            try:
                after = self.read(fixed_number)
                self.read(fixed_number + 100, status=404)
            finally:
                self.port = previous_port
        self.assertEqual(after, initial)
        self.scenario(
            'v8.fixed_copy', {'old_edition': fixed_number, 'new_revision': new_revision},
            [(1, 'C', '录于榆桥社区口述史馆。'), (3, 'A', '过河先听铃。'), (5, 'B', '收摊后才点灯。')],
            [(page['page'], page['quote'], page['text']) for page in after['pages']],
            [('left', old_left.number, old_left.choice(3).value), ('right', old_right.number, old_right.choice(5).value)],
            [(item['seat'], item['sheet'], item['option']) for item in after['citations']],
            ['release/editions.py', 'reading/catalog.py', 'reading/contents.py', 'reading/citations.py'],
            '按样例原文和两张实际纸单核对旧册，新轮同名引文有不同文本和页号。',
        )

    def test_reinitialize(self):
        old, _, _ = self.complete_sample_round()
        old_view = self.read(old['edition'])
        new_revision = self.revise('A\t8,10\t新稿甲\nB\t9\t新稿乙')
        self.amend(new_revision)
        left, right = self.sheet('left'), self.sheet('right')
        actual = self.report(left, 10)['actual']
        with closing(open_database(self.database)) as db:
            self.assertFalse(initialize_workspace(db))
            self.assertFalse(initialize_workspace(db))
        self.assertEqual(self.scalar('SELECT count(*) FROM seed_marks'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM books'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM seat_briefs'), 2)
        self.assertEqual(self.scalar('SELECT count(*) FROM print_returns'), 3)
        self.assertEqual(self.current()['revision_id'], new_revision)
        self.assertEqual(self.sheet('right').options, right.options)
        self.assertEqual(self.report(left, 10)['actual'], actual)
        self.assertEqual(self.read(old['edition']), old_view)

    def test_failed_initialization_rolls_back_sample(self):
        broken = self.temp / 'broken-sample.json'
        sample = json.loads(SAMPLE_PATH.read_text(encoding='utf-8'))
        del sample['seats']['right']
        broken.write_text(json.dumps(sample), encoding='utf-8')
        with closing(open_database(self.temp / 'retry.sqlite3')) as db:
            with self.assertRaisesRegex(ValueError, '左席和右席'):
                initialize_workspace(db, broken)
            counts = db.execute(
                '''SELECT (SELECT count(*) FROM books), (SELECT count(*) FROM rounds),
                          (SELECT count(*) FROM seat_briefs), (SELECT count(*) FROM seed_marks)'''
            ).fetchone()
            self.assertEqual(tuple(counts), (0, 0, 0, 0))
            self.assertTrue(initialize_workspace(db))
            self.assertFalse(initialize_workspace(db, broken))
            self.assertEqual(db.execute('SELECT count(*) FROM seat_briefs').fetchone()[0], 2)
