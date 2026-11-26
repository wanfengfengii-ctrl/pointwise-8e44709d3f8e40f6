from tests.support import WorkbenchCase


class DeskTests(WorkbenchCase):
    def test_old_form_http(self):
        self.open_sample_round()
        original = self.sheet('left')
        later = self.sheet('right')
        self.assertEqual(original.choice(3).number, later.choice(5).number)
        self.assertNotEqual(original.choice(3).value, later.choice(5).value)
        answer = self.report(original, 3)
        self.assertEqual(answer['status'], 'accepted')
        actual = answer['actual']
        stored = self.scalar('SELECT short_no FROM print_returns WHERE sheet = ?', (original.number,))
        self.scenario(
            'v3.old_form_http', {'left': original.hidden, 'picked': original.choice(3).value,
                                 'reused_short_number': later.choice(5).number},
            [original.number, 'left', 'A', 3], [actual['sheet'], actual['seat'], actual['quote'], actual['page']],
            2, stored, ['desk/forms.py', 'desk/http.py', 'desk/returns.py'],
            '左单第 2 项是 A 的第 3 页，右单第 2 项是 B 的第 5 页。',
        )
        repeated_page = self.report(original, 3, html=True)
        self.assertIn(f'左席纸单 #{original.number}', repeated_page)
        self.assertIn('A → 第 3 页', repeated_page)

    def test_issue_stability(self):
        self.open_sample_round()
        left = self.sheet('left')
        right = self.sheet('right')
        reopened = self.sheet('left')
        self.assertNotEqual(left.number, right.number)
        self.assertEqual(reopened.hidden, left.hidden)
        self.assertEqual(reopened.options, left.options)
        self.assertEqual(self.sheet('right').options, right.options)
        self.assertEqual(self.scalar('SELECT count(*) FROM sheets'), 2)
        self.request('/sheet', query={'book': self.book, 'seat': 'middle'}, status=404)

    def test_foreign_option(self):
        self.open_sample_round()
        left, right = self.sheet('left'), self.sheet('right')
        form = dict(left.hidden, option=right.choice(5).value)
        answer = self.request('/return', form=form, status=409)
        self.assertEqual(answer, {'status': 'foreign_option', 'message': '提交选项不属于这张原纸单。', 'actual': None})
        wrong_seat = dict(left.fields_for(3), seat='right')
        self.assertEqual(self.request('/return', form=wrong_seat, status=409)['status'], 'wrong_sheet')
        repeated_parameter = list(left.fields_for(3).items()) + [('option', left.choice(2).value)]
        self.request('/return', form=repeated_parameter, status=400)
        self.request('/return', form=left.hidden, status=400)
        self.assertEqual(self.scalar('SELECT count(*) FROM print_returns'), 0)
        self.assertEqual(self.report(left, 2)['actual']['page'], 2)
        self.assertEqual(self.report(right, 5)['actual']['page'], 5)

    def test_first_return(self):
        self.open_sample_round()
        left = self.sheet('left')
        self.sheet('right')
        first = self.report(left, 3)
        repeated = self.report(left, 3)
        change = self.report(left, 2, status=409)
        self.assertEqual((first['status'], repeated['status'], change['status']),
                         ('accepted', 'repeated', 'already_reported'))
        self.assertEqual(repeated['actual'], first['actual'])
        self.assertEqual(change['actual'], first['actual'])
        self.assertEqual(self.scalar('SELECT count(*) FROM print_returns'), 1)
        self.assertEqual(self.scalar('SELECT short_no FROM print_returns WHERE sheet = ?', (left.number,)), 2)

    def test_new_sheet_checks_every_open_choice(self):
        first = self.revise('A\t2,3\t甲\nB\t2,4,5\t乙\nC\t1\t丙')
        self.amend(first)
        left = self.sheet('left')
        self.assertEqual([item.page for item in left.options], [2, 3])
        right = self.sheet('right')
        self.assertEqual([item.page for item in right.options], [4, 5])

    def test_unavailable_seat_can_claim_after_other_reports(self):
        first = self.revise('A\t2,3\t甲\nB\t2,3\t乙')
        self.amend(first)
        left = self.sheet('left')
        self.request('/sheet', query={'book': self.book, 'seat': 'right'}, status=409)
        self.assertEqual(self.scalar('SELECT count(*) FROM sheets'), 1)
        self.assertEqual(self.report(left, 3)['actual']['page'], 3)
        right = self.sheet('right')
        self.assertEqual([(item.quote, item.page) for item in right.options], [('B', 2)])
        self.assertEqual(self.report(right, 2)['actual']['sheet'], right.number)
