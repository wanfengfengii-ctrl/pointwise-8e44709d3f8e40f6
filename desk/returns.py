from dataclasses import dataclass

from desk.forms import ReturnSubmission
from desk.options import PrintOption
from desk.sheets import find_sheet


@dataclass(frozen=True)
class PrintReturn:
    book: str
    seat: str
    round_id: int
    sheet_id: int
    option: PrintOption


@dataclass(frozen=True)
class ReturnDecision:
    status: str
    message: str
    actual: PrintReturn | None = None

    @property
    def accepted(self):
        return self.status in ('accepted', 'repeated')


def find_return(db, sheet_id):
    row = db.execute(
        '''SELECT s.book, s.seat, s.round_id, o.short_no, o.quote, o.page
             FROM print_returns AS r
             JOIN sheets AS s ON s.id = r.sheet
             JOIN sheet_options AS o ON o.sheet = r.sheet AND o.short_no = r.short_no
            WHERE r.sheet = ?''',
        (sheet_id,),
    ).fetchone()
    if row is None:
        return None
    option = PrintOption(sheet_id, row['short_no'], row['quote'], int(row['page']))
    return PrintReturn(row['book'], row['seat'], row['round_id'], sheet_id, option)


def accept_return(db, submission: ReturnSubmission):
    sheet = find_sheet(db, submission.sheet_id)
    if sheet is None or (sheet.book, sheet.seat) != (submission.book, submission.seat):
        return ReturnDecision('wrong_sheet', '纸单与提交的册或印席不符。')
    chosen = next((option for option in sheet.options if option.value == submission.option), None)
    if chosen is None:
        return ReturnDecision('foreign_option', '提交选项不属于这张原纸单。')
    previous = find_return(db, sheet.id)
    if previous is not None:
        if previous.option == chosen:
            return ReturnDecision('repeated', '已登记此实印，返回原记录。', previous)
        return ReturnDecision('already_reported', '已登记另一选项，保留首次实印。', previous)
    db.execute('INSERT INTO print_returns(sheet, short_no) VALUES (?, ?)', (sheet.id, chosen.number))
    actual = PrintReturn(sheet.book, sheet.seat, sheet.round_id, sheet.id, chosen)
    return ReturnDecision('accepted', '实印已接纳。', actual)
