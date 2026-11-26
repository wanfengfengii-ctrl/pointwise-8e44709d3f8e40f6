from tests.support import WorkbenchCase


class ProofTests(WorkbenchCase):
    def test_reassign_slot(self):
        rows = 'A\t2,3\t渡口铃声\nB\t2\t夜市点灯'
        revision = self.revise(rows)
        first = self.preview(revision)
        self.assertEqual(self.preview(revision), first)
        self.assertIsNone(self.current()['revision_id'])
        result = self.amend(revision)
        self.scenario(
            'v1.reassign_slot', {'A': [2, 3], 'B': [2]}, {'A': 3, 'B': 2}, first['pages'],
            revision, result['current'], ['layout/occupancy.py', 'layout/solver.py', 'release/amendments.py'],
            'B 只能占用第 2 页，因此完整布局必须把 A 改派到第 3 页。',
        )

    def test_fixed_conflict(self):
        revision = self.revise('A\t2,3\t引文甲\nB\t2,4\t引文乙')
        conflict = self.preview(revision, 'A\t2\nB\t2', status=409)
        self.assertIsNone(conflict['pages'])
        self.assertIn('第 2 页', conflict['reason'])
        for pins in ('A\t2\nA\t3', 'X\t2', 'B\t3'):
            with self.subTest(pins=pins):
                self.assertIsNone(self.preview(revision, pins, status=409)['pages'])
        self.assertEqual(self.preview(revision, 'A\t2\nA\t2')['pages'], {'A': 2, 'B': 4})

    def test_no_partial_revision(self):
        original = self.open_sample_round()
        before = self.scalar('SELECT count(*) FROM revisions')
        response = self.revise('D\t7\t先录入的稿行\nE\t0\t非法页格', status=400)
        self.assertIn('正整数', response['error'])
        self.assertEqual(self.scalar('SELECT count(*) FROM revisions'), before)
        self.assertEqual(self.scalar('SELECT count(*) FROM revision_quotes'), 3)
        self.assertEqual(self.current()['revision_id'], original)
        self.assertEqual(self.preview(original)['pages'], {'A': 2, 'B': 4, 'C': 1})

    def test_invalid_quote_and_empty_grid(self):
        for draft in ('A\t2\t甲\nA\t3\t乙', '\t2\t甲', 'A\t2\t ', 'A\t\t甲', 'A\t2.5\t甲'):
            with self.subTest(draft=draft):
                self.revise(draft, status=400)
        self.assertEqual(self.scalar('SELECT count(*) FROM revisions'), 0)

    def test_empty_proof_and_impossible_first_release(self):
        impossible = self.revise('A\t2\t甲\nB\t2\t乙')
        self.assertIsNone(self.preview(impossible, status=409)['pages'])
        self.assertIsNone(self.amend(impossible, status=409)['current'])
        self.request('/sheet', query={'book': self.book, 'seat': 'left'}, status=409)
        empty = self.revise('')
        self.assertEqual(self.preview(empty)['pages'], {})
        self.assertEqual(self.amend(empty)['current'], empty)
        self.request('/sheet', query={'book': self.book, 'seat': 'left'}, status=409)
        self.assertEqual(self.scalar('SELECT count(*) FROM sheets'), 0)
