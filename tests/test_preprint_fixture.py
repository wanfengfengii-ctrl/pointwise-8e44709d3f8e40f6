from tests.support import WorkbenchCase


class PreprintFixtureTests(WorkbenchCase):
    def open_sheets(self, ordinary_quotes):
        rows = "A\t2,3\t渡口铃声\nB\t5\t夜市点灯\n" + ordinary_quotes
        revision = self.revise(rows)
        self.assertEqual(self.amend(revision)["current"], revision)
        left, right = self.sheet("left"), self.sheet("right")
        self.assertEqual([item.page for item in left.options], [2, 3])
        self.assertEqual([item.page for item in right.options], [5])
        return revision, left, right

    def layout_for(self, revision, left_page, additional_pins="", *, status=200):
        pins = f"A\t{left_page}\nB\t5"
        if additional_pins:
            pins += "\n" + additional_pins
        return self.preview(revision, pins, status=status)["pages"]

    def test_independent_layouts(self):
        revision, left, right = self.open_sheets("C\t2,3\t渡口录音备注")
        first = self.layout_for(revision, 2)
        second = self.layout_for(revision, 3)
        self.assertEqual(first, {"A": 2, "B": 5, "C": 3})
        self.assertEqual(second, {"A": 3, "B": 5, "C": 2})
        self.layout_for(revision, 3, "C\t3", status=409)
        self.report(left, 3)
        self.report(right, 5)
        bound = self.bind()
        final_pages = {item["quote"]: item["page"] for item in self.read(bound["edition"])["pages"]}
        self.scenario(
            "fixture.preprint.independent",
            {"left": [2, 3], "right": [5], "quote": "C"},
            [3, 2], [first["C"], second["C"]],
            {"A": 3, "B": 5, "C": 2}, final_pages,
            ["layout/proof.py", "release/binding.py"],
            "两次原试排各自能排完，成册按实际的左席第 3 页完成。",
        )

    def test_individual_page_checks_can_starve_unprinted_quote(self):
        revision, _, _ = self.open_sheets("C\t4,6\t录音备注\nD\t7,8\t馆藏说明\nE\t2,4,7\t访问时间")
        for left_page in (2, 3):
            with self.subTest(left_page=left_page):
                self.assertEqual(self.layout_for(revision, left_page, "C\t4")["C"], 4)
                self.assertEqual(self.layout_for(revision, left_page, "D\t7")["D"], 7)
                self.assertEqual(self.layout_for(revision, left_page, "C\t4\nD\t8")["E"], 7 if left_page == 2 else 2)
        self.assertIsNone(self.layout_for(revision, 2, "C\t4\nD\t7", status=409))
        self.assertEqual(self.layout_for(revision, 3, "C\t4\nD\t7")["E"], 2)
