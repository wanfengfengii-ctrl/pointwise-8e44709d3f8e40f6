from tests.support import SavedSheet, WorkbenchCase, running_workbench


class PreprintCase(WorkbenchCase):
    def open_sheets(self, quotes, *, left=(2, 3), right=(5,)):
        rows = f"A\t{','.join(map(str, left))}\t渡口铃声\nB\t{','.join(map(str, right))}\t夜市点灯\n{quotes}"
        revision = self.revise(rows)
        self.assertEqual(self.amend(revision)['current'], revision)
        return revision, self.sheet('left'), self.sheet('right')

    def preprint(self, quotes, *, status=200):
        answer = self.request('/preprint', query={'book': self.book, 'quotes': quotes}, status=status)
        return answer

    def sign(self, preview, pins, *, revision=None, round_id=None, status=200):
        form = {
            'book': self.book,
            'round': str(preview['round'] if round_id is None else round_id),
            'revision': str(preview['revision'] if revision is None else revision),
            'pins': pins,
        }
        return self.request('/preprint', form=form, status=status)

    def sign_preview(self, preview, *, revision=None, round_id=None, status=200):
        pins = '\n'.join(f"{page['quote']}\t{page['page']}" for page in preview['pages'])
        return self.sign(preview, pins, revision=revision, round_id=round_id, status=status)

    def fetch_preprint(self, preprint_id, *, status=200):
        return self.request('/preprint', query={'book': self.book, 'id': str(preprint_id)}, status=status)

    @staticmethod
    def page_map(payload):
        return {page['quote']: page['page'] for page in payload['pages']}


class PreprintTests(PreprintCase):
    def test_single_branch_still_refuses(self):
        revision, left, right = self.open_sheets('C\t2,3\t渡口录音备注')
        refused = self.preprint('C', status=409)
        self.assertIn('找不到共同排法', refused['reason'])
        self.assertEqual(self.scalar('SELECT count(*) FROM preprints'), 0)
        # 常规试排仍随左席报回页给出各自页号。
        self.assertEqual(self.preview(revision, 'A\t2\nB\t5')['pages']['C'], 3)
        self.assertEqual(self.preview(revision, 'A\t3\nB\t5')['pages']['C'], 2)
        self.assertEqual(self.report(left, 3)['actual']['page'], 3)

    def test_competing_pair(self):
        revision, _, _ = self.open_sheets('C\t2,3,4\t丙\nD\t2,3,4\t丁')
        self.assertEqual(self.page_map(self.preprint('C'))['C'], 4)
        self.assertEqual(self.page_map(self.preprint('D'))['D'], 4)
        self.preprint('C D', status=409)

    def test_leftover_quote_can_be_starved(self):
        revision, _, _ = self.open_sheets(
            'C\t4,6\t录音备注\nD\t7,8\t馆藏说明\nE\t2,4,7\t访问时间',
        )
        self.assertEqual(self.page_map(self.preprint('C'))['C'], 4)
        self.assertEqual(self.page_map(self.preprint('D'))['D'], 7)
        joint = self.preprint('C D')
        self.assertEqual(joint['pages'], [
            {'quote': 'C', 'page': 4, 'text': '录音备注'},
            {'quote': 'D', 'page': 8, 'text': '馆藏说明'},
        ])
        signed = self.sign_preview(joint)
        self.assertEqual(self.page_map(signed), {'C': 4, 'D': 8})

    def test_requires_both_sheets(self):
        revision = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nC\t4,6\t录音备注')
        self.amend(revision)
        self.sheet('left')
        self.preprint('C', status=409)
        self.sheet('right')
        self.assertEqual(self.page_map(self.preprint('C'))['C'], 4)

    def test_preview_does_not_reserve_pages(self):
        revision, _, _ = self.open_sheets('C\t4,6\t录音备注')
        preview = self.preprint('C')
        self.assertEqual(self.scalar('SELECT count(*) FROM preprints'), 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM preprint_pages'), 0)
        html = self.request(
            '/preprint', query={'book': self.book, 'quotes': 'C'}, html=True,
        )
        self.assertIn('预览不授权印刷', html)
        self.assertIn('录音备注', html)

    def test_sign_after_b_correction(self):
        revision, left, right = self.open_sheets('C\t2,3,4,6\t录音备注')
        first = self.preprint('C')
        # 网页稳定取得指定页：独立初稿只给 C 第 4 页。
        self.assertIn(self.page_map(first)['C'], (4, 6))
        second = self.preprint('C')
        self.assertEqual(second, first)
        changed = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市换了文字\nC\t2,3,4,6\t录音备注')
        self.assertEqual(self.amend(changed)['current'], changed)
        # 原预览仍可签领，来源稿号仍记第一次审过的稿。
        signed = self.sign_preview(first)
        self.assertEqual(signed['revision'], revision)
        self.assertEqual(signed['preprint'], 1)
        moved = self.sign_preview(second)
        self.assertEqual(moved['preprint'], 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM preprints'), 1)

    def test_preview_void_when_own_text_changes(self):
        revision, _, _ = self.open_sheets('C\t2,3,4,6\t录音备注')
        preview = self.preprint('C')
        changed = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nC\t2,3,4,6\t录音改了原文')
        self.assertEqual(self.amend(changed)['current'], changed)
        refused = self.sign_preview(preview, status=409)
        self.assertIn('原文', refused['reason'])
        self.assertEqual(self.scalar('SELECT count(*) FROM preprints'), 0)

    def test_one_signature_per_round(self):
        revision, _, _ = self.open_sheets('C\t2,3,4,6\t录音备注\nD\t4,6\t另注')
        first = self.preprint('C')
        signed = self.sign_preview(first)
        # 重提同一组页（换行次序不影响）复领原底稿。
        reordered = '\n'.join(list(reversed([
            f"{page['quote']}\t{page['page']}" for page in first['pages']
        ])))
        again = self.sign(first, reordered)
        self.assertEqual(again['preprint'], signed['preprint'])
        other = self.preprint('D')
        conflict = self.sign_preview(other, status=409)
        self.assertIn('另一份', conflict['reason'])
        self.assertEqual(self.scalar('SELECT count(*) FROM preprints'), 1)

    def test_sign_needs_current_round(self):
        revision, _, _ = self.open_sheets('C\t4,6\t录音备注')
        preview = self.preprint('C')
        wrong = self.sign_preview(preview, round_id=preview['round'] + 5, status=404)
        self.assertIn('error', wrong)
        stale = self.sign_preview(preview, revision=preview['revision'] + 5, status=404)
        self.assertIn('error', stale)

    def test_signed_pages_hold_through_amendment_and_binding(self):
        revision, left, right = self.open_sheets('C\t4,6\t录音备注')
        preview = self.preprint('C')
        signed = self.sign_preview(preview)
        signed_page = self.page_map(signed)['C']
        self.assertEqual(signed_page, 4)
        # 候选稿只留 C 在第 6 页时，签第 4 页的轮必须拒绝。
        only_six = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nC\t6\t录音备注')
        denied = self.amend(only_six, status=409)
        self.assertFalse(denied['accepted'])
        self.assertIn('C', denied['reason'])
        self.assertEqual(self.current()['revision_id'], revision)
        # 保留第 4 页的候选稿在原单组合下仍可发布。
        keeps = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nC\t4\t录音备注')
        self.assertEqual(self.amend(keeps)['current'], keeps)
        self.report(left, 3)
        self.report(right, 5)
        bound = self.bind()
        self.assertEqual(bound['preprint'], signed['preprint'])
        view = self.read(bound['edition'])
        self.assertTrue(view['verified'])
        self.assertEqual(view['preprint'], signed['preprint'])
        self.assertEqual(self.page_map(view)['C'], 4)
        self.assertEqual(self.page_map(view)['A'], 3)
        # 按底稿号领回当时原文与页号。
        recovered = self.fetch_preprint(signed['preprint'])
        self.assertEqual(recovered['pages'], [
            {'quote': 'C', 'page': 4, 'text': '录音备注'},
        ])

    def test_new_round_keeps_old_preprint(self):
        revision, left, right = self.open_sheets('C\t4,6\t录音备注')
        signed = self.sign_preview(self.preprint('C'))
        self.report(left, 3)
        self.report(right, 5)
        bound = self.bind()
        next_revision = self.revise('A\t10\t新访谈。\nB\t9\t新夜市。\nC\t2\t新备注。')
        opened = self.amend(next_revision)
        self.assertNotEqual(opened['round'], bound['round'])
        # 已成册轮仍可重提原签领。
        again = self.sign_preview(self.preprint_record(signed['preprint']))
        self.assertEqual(again['preprint'], signed['preprint'])
        # 旧底稿按号仍能领回。
        self.assertEqual(self.fetch_preprint(signed['preprint'])['revision'], revision)

    def preprint_record(self, preprint_id):
        data = self.fetch_preprint(preprint_id)
        return {'round': data['round'], 'revision': data['revision'], 'pages': data['pages']}

    def test_unknown_and_invalid(self):
        self.open_sheets('C\t4,6\t录音备注')
        self.request('/preprint', query={'book': self.book, 'quotes': 'Z'}, status=404)
        self.request('/preprint', query={'book': 'nope', 'quotes': 'C'}, status=404)
        self.request('/preprint', query={'book': self.book, 'id': '999'}, status=404)
        self.request('/preprint', query={'book': self.book, 'quotes': ''}, status=409)
        self.request('/preprint', form={'book': self.book, 'round': '1', 'revision': '1'}, status=400)
        self.request('/preprint', form={
            'book': self.book, 'round': '1', 'revision': '1', 'pins': '',
        }, status=409)


class PreprintPageChoiceTests(PreprintCase):
    """从网页稳定取得指定页：初稿只给 C 该页即可签该页。"""

    def open_with_single_c_page(self, page):
        rows = f'A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nC\t{page}\t录音备注'
        revision = self.revise(rows)
        self.assertEqual(self.amend(revision)['current'], revision)
        self.sheet('left')
        self.sheet('right')
        return revision

    def test_four_page_signature_rejects_six_only_candidate(self):
        revision = self.open_with_single_c_page(4)
        preview = self.preprint('C')
        self.assertEqual(self.page_map(preview)['C'], 4)
        signed = self.sign(preview, 'C\t4')
        self.assertEqual(self.page_map(signed), {'C': 4})
        six_only = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nC\t6\t录音备注')
        denied = self.amend(six_only, status=409)
        self.assertFalse(denied['accepted'])
        self.assertIn('C', denied['reason'])
        self.assertEqual(self.current()['revision_id'], revision)
        self.assertEqual(signed['preprint'], self.scalar('SELECT id FROM preprints'))

    def test_six_page_signature_allows_six_only_candidate(self):
        revision = self.open_with_single_c_page(6)
        preview = self.preprint('C')
        self.assertEqual(self.page_map(preview)['C'], 6)
        signed = self.sign(preview, 'C\t6')
        self.assertEqual(self.page_map(signed), {'C': 6})
        six_only = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nC\t6\t录音备注')
        self.assertEqual(self.amend(six_only)['current'], six_only)


class PreprintDemoTests(PreprintCase):
    def test_preprint_to_bound_copy(self):
        revision, left, right = self.open_sheets('C\t4,6\t录音备注')
        first = self.preprint('C')
        second = self.preprint('C')
        self.assertEqual(first, second)
        errata = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市改了文字\nC\t4,6\t录音备注')
        self.assertEqual(self.amend(errata)['current'], errata)
        signed = self.sign_preview(first)
        again = self.sign_preview(second)
        self.assertEqual(again['preprint'], signed['preprint'])
        keeps_six = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市改了文字\nC\t6\t录音备注')
        stays = self.amend(keeps_six, status=409)
        keeps_four = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市改了文字\nC\t4\t录音备注')
        accepted = self.amend(keeps_four)
        self.assertEqual(self.report(left, 3)['actual']['page'], 3)
        self.assertEqual(self.report(right, 5)['actual']['page'], 5)
        bound = self.bind()
        view = self.read(bound['edition'])
        recovered = self.fetch_preprint(signed['preprint'])
        self.scenario(
            'preprint.to_bound_copy',
            {'preview_pages': first['pages'], 'signed': signed['preprint'],
             'errata_revision': errata, 'candidate_six_only': keeps_six,
             'candidate_keeps_four': keeps_four},
            {'sign_page': 4, 'resubmit_same': True, 'six_only_blocked': True,
             'keeps_four': True, 'edition_pages': {'A': 3, 'B': 5, 'C': 4},
             'preprint': signed['preprint']},
            {'sign_page': self.page_map(signed)['C'], 'resubmit_same': again['preprint'] == signed['preprint'],
             'six_only_blocked': not stays['accepted'], 'keeps_four': accepted['accepted'],
             'edition_pages': self.page_map(view), 'preprint': view['preprint']},
            {'recovered_pages': [{'quote': 'C', 'page': 4, 'text': '录音备注'}], 'verified': True},
            {'recovered_pages': recovered['pages'], 'verified': view['verified']},
            ['release/preprints.py', 'release/amendments.py', 'release/binding.py',
             'reading/proof.py'],
            '两份相同预览，改 B 原文后原预览仍可签领且重提复领原底稿；签 C→4 后，'
            '仅留 C 第 6 页的候选稿被拒，保留第 4 页的候选稿获准，成册沿用先印页并固定底稿号。',
        )


class PreprintAmendmentTests(PreprintCase):
    def test_amendment_must_honour_signed_pages_and_every_combination(self):
        revision, _, _ = self.open_sheets(
            'C\t4,6\t丙\nD\t7,8\t丁\nE\t2,4,7\t戊',
        )
        joint = self.preprint('C D')
        self.assertEqual(self.page_map(joint), {'C': 4, 'D': 8})
        self.sign_preview(joint)
        # 只改动非签领引文，但仍让某组合把 E 挤掉：须拒。
        starves = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nC\t4\t丙\nD\t8\t丁\nE\t2\t戊')
        denied = self.amend(starves, status=409)
        self.assertFalse(denied['accepted'])
        self.assertIn('E', denied['reason'])
        # 同时兑现已签页和两席所有组合的候选稿可发布。
        keeps = self.revise('A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nC\t4\t丙\nD\t8\t丁\nE\t2,7\t戊')
        self.assertEqual(self.amend(keeps)['current'], keeps)

    def test_signed_quote_cannot_be_removed_moved_or_rewritten(self):
        self.open_sheets('C\t4,6\t丙\nD\t7,8\t丁\nE\t2,4,7\t戊')
        joint = self.preprint('C D')
        self.sign_preview(joint)
        cases = {
            'removed': ('A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nD\t8\t丁\nE\t2,7\t戊', '已签页 C→4'),
            'moved': ('A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nC\t6\t丙\nD\t8\t丁\nE\t2,4\t戊', '已签页 C→4'),
            'rewritten': ('A\t2,3\t渡口铃声\nB\t5\t夜市点灯\nC\t4\t丙改\nD\t8\t丁\nE\t2,7\t戊', '已签页 C→4'),
        }
        for name, (rows, expected) in cases.items():
            with self.subTest(name=name):
                candidate = self.revise(rows)
                denied = self.amend(candidate, status=409)
                self.assertIn(expected, denied['reason'])


class PreprintBrowserTests(PreprintCase):
    def test_browser_preview_and_sign_form(self):
        self.open_sheets('C\t4,6\t录音备注')
        html = self.request('/preprint', query={'book': self.book, 'quotes': 'C'}, html=True)
        form = SavedSheet(html)
        self.assertIsNotNone(form.action)
        self.assertEqual(form.hidden['book'], self.book)
        # 预览表单自带轮次、来源稿号与整组页码，提交即签领。
        self.assertEqual(form.hidden['round'], '1')
        payload = dict(form.hidden, pins='C\t4')
        answer = self.request('/preprint', form=payload)
        self.assertEqual(self.page_map(answer), {'C': 4})
        self.assertEqual(answer['preprint'], 1)

    def test_bound_html_shows_preprint_number(self):
        revision, left, right = self.open_sheets('C\t4,6\t录音备注')
        signed = self.sign_preview(self.preprint('C'))
        self.report(left, 3)
        self.report(right, 5)
        bound = self.bind()
        html = self.read(bound['edition'], html=True)
        self.assertIn(f'先印底稿', html)
        self.assertIn(f'#{signed["preprint"]}', html)
        self.assertIn('两席索引均与正文相符', html)

    def test_restart_keeps_preprint_and_bound_copy(self):
        revision, left, right = self.open_sheets('C\t4,6\t录音备注')
        signed = self.sign_preview(self.preprint('C'))
        self.report(left, 3)
        self.report(right, 5)
        bound = self.bind()
        view = self.read(bound['edition'])
        with running_workbench(self.database) as new_port:
            previous_port, self.port = self.port, new_port
            try:
                recovered = self.fetch_preprint(signed['preprint'])
                reopened = self.read(bound['edition'])
            finally:
                self.port = previous_port
        self.assertEqual(recovered['pages'], [{'quote': 'C', 'page': 4, 'text': '录音备注'}])
        self.assertEqual(recovered['revision'], revision)
        self.assertEqual(reopened, view)
        self.assertEqual(reopened['preprint'], signed['preprint'])

