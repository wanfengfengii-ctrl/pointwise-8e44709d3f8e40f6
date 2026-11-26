from itertools import product

from tests.support import WorkbenchCase


def _page_map(view):
    return {item['quote']: item['page'] for item in view['pages']}


def _printed_index(view):
    return [(item['seat'], item['quote'], item['page'], item['sheet']) for item in view['citations']]


class BindingTests(WorkbenchCase):
    def test_all_pairs(self):
        first = self.open_sample_round()
        left, right = self.sheet('left'), self.sheet('right')
        for a, b in product((2, 3), (4, 5)):
            with self.subTest(a=a, b=b):
                self.assertEqual(self.preview(first, f'A\t{a}\nB\t{b}')['pages'], {'A': a, 'B': b, 'C': 1})
        second = self.revise('A\t3\t渡口铃声\nB\t4,5\t夜市点灯\nC\t1\t馆藏备注')
        self.assertEqual(self.preview(second)['pages'], {'A': 3, 'B': 4, 'C': 1})
        denied = self.amend(second, status=409)
        self.assertEqual(denied['blocked'], [{'quote': 'A', 'page': 2}, {'quote': 'B', 'page': 4}])
        self.scenario(
            'v5.all_pairs', {'old': {'A': [2, 3], 'B': [4, 5]}, 'new_A': [3]},
            False, denied['accepted'], first, self.current()['revision_id'],
            ['release/commitments.py', 'release/amendments.py', 'layout/proof.py'],
            '当前纸单允许 A→2，与 B→4 同报时新稿无法安放 A。',
        )
        self.assertEqual(self.report(left, 3)['actual']['page'], 3)
        self.assertEqual(self.amend(second)['current'], second)
        self.assertEqual(self.report(right, 5)['actual']['page'], 5)
        self.assertEqual(_page_map(self.bind()), {'A': 3, 'B': 5, 'C': 1})

    def test_joint_pair(self):
        first = self.open_sample_round()
        self.sheet('left')
        self.sheet('right')
        candidate = self.revise('A\t2,3\t甲\nB\t4,5\t乙\nC\t2,4\t丙')
        self.assertEqual(self.preview(candidate, 'A\t2')['pages']['C'], 4)
        self.assertEqual(self.preview(candidate, 'B\t4')['pages']['C'], 2)
        self.assertIsNone(self.preview(candidate, 'A\t2\nB\t4', status=409)['pages'])
        denied = self.amend(candidate, status=409)
        self.assertEqual(denied['blocked'], [{'quote': 'A', 'page': 2}, {'quote': 'B', 'page': 4}])
        self.assertIn('引文 C', denied['reason'])
        self.assertEqual(self.current()['revision_id'], first)

    def test_both_issued_one_return(self):
        self.open_sample_round()
        left, right = self.sheet('left'), self.sheet('right')
        self.report(left, 3)
        self.assertEqual(self.scalar('SELECT count(*) FROM sheets'), 2)
        self.assertEqual(self.scalar('SELECT count(*) FROM print_returns'), 1)
        waiting = self.bind(status=409)
        self.assertIn('尚未报齐', waiting['reason'])
        self.assertEqual(self.scalar('SELECT count(*) FROM fixed_editions'), 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM fixed_pages'), 0)
        self.report(right, 5)
        first = self.bind()
        repeated = self.bind()
        self.assertFalse(first['repeated'])
        self.assertTrue(repeated['repeated'])
        self.assertEqual(first['edition'], repeated['edition'])
        self.assertEqual(_printed_index(first), [('left', 'A', 3, left.number), ('right', 'B', 5, right.number)])
        self.assertEqual(self.scalar('SELECT count(*) FROM fixed_editions'), 1)

    def test_print_to_bound_copy(self):
        first = self.open_sample_round()
        left = self.sheet('left')
        right = self.sheet('right')
        self.assertEqual(left.choice(3).number, right.choice(5).number)
        compatible_after_left = self.revise('A\t3\t过河先听铃。\nB\t4,5\t收摊后才点灯。\nC\t6\t录于榆桥社区口述史馆。')
        denied = self.amend(compatible_after_left, status=409)
        self.assertEqual(denied['current'], first)
        wrong = dict(left.hidden, option=right.choice(5).value)
        self.assertEqual(self.request('/return', form=wrong, status=409)['status'], 'foreign_option')
        self.assertEqual(self.scalar('SELECT count(*) FROM print_returns'), 0)
        self.assertEqual(self.amend(compatible_after_left, status=409)['current'], first)
        left_result = self.report(left, 3)
        self.assertEqual(left_result['status'], 'accepted')
        self.assertEqual((left_result['actual']['sheet'], left_result['actual']['page']), (left.number, 3))
        cuts_right = self.revise('A\t3\t过河先听铃。\nB\t4\t收摊后才点灯。\nC\t6\t馆藏备注')
        still_denied = self.amend(cuts_right, status=409)
        self.assertEqual(still_denied['blocked'], [{'quote': 'A', 'page': 3}, {'quote': 'B', 'page': 5}])
        accepted = self.amend(compatible_after_left)
        self.assertEqual(self.sheet('right').options, right.options)
        self.bind(status=409)
        right_result = self.report(right, 5)
        self.assertEqual(right_result['status'], 'accepted')
        self.assertEqual((right_result['actual']['sheet'], right_result['actual']['page']), (right.number, 5))
        bound = self.bind()
        view = self.read(bound['edition'])
        self.assertEqual(view['revision'], compatible_after_left)
        self.assertTrue(view['verified'])
        self.assertEqual(_page_map(bound), _page_map(view))
        self.assertEqual(
            _printed_index(view), [('left', 'A', 3, left.number), ('right', 'B', 5, right.number)],
        )
        self.assertEqual([item['option'] for item in view['citations']], [left.choice(3).value, right.choice(5).value])
        html = self.read(bound['edition'], html=True)
        self.assertIn('id="page-6"', html)
        self.assertIn('两席索引均与正文相符', html)
        self.scenario(
            'v7.current_layout',
            {'first_revision': first, 'candidate': compatible_after_left, 'reported': [left.choice(3).value, right.choice(5).value],
             'candidate_pages': {'A': [3], 'B': [4, 5], 'C': [6]}},
            {'initial_amend': False, 'retry_amend': True, 'fixed_pages': {'A': 3, 'B': 5, 'C': 6}},
            {'initial_amend': denied['accepted'], 'retry_amend': accepted['accepted'], 'fixed_pages': _page_map(bound)},
            {'pages': {'A': 3, 'B': 5, 'C': 6}, 'verified': True},
            {'pages': _page_map(view), 'verified': view['verified']},
            ['desk/returns.py', 'release/commitments.py', 'release/binding.py', 'reading/proof.py'],
            '两张实印固定 A 的第 3 页和 B 的第 5 页，获准稿将 C 限定在第 6 页。',
        )

    def test_reverse_order(self):
        first = self.open_sample_round()
        right = self.sheet('right')
        left = self.sheet('left')
        self.assertEqual(self.report(right, 5)['actual']['page'], 5)
        self.bind(status=409)
        cuts_left = self.revise('A\t3\t甲\nB\t5\t乙\nC\t1\t丙')
        self.assertEqual(self.amend(cuts_left, status=409)['current'], first)
        right_fixed = self.revise('A\t2,3\t甲\nB\t5\t乙\nC\t1\t丙')
        self.assertEqual(self.amend(right_fixed)['current'], right_fixed)
        self.assertEqual(self.report(left, 2)['actual']['page'], 2)
        view = self.read(self.bind()['edition'])
        self.assertTrue(view['verified'])
        self.assertEqual(_page_map(view), {'A': 2, 'B': 5, 'C': 1})
        self.assertEqual(_printed_index(view), [('left', 'A', 2, left.number), ('right', 'B', 5, right.number)])
