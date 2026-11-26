import json
from pathlib import Path

from desk.briefs import store_seat_briefs
from release.editions import register_booklet
from release.storage import create_schema, write_transaction


SAMPLE_PATH = Path(__file__).resolve().parents[1] / 'samples' / 'yuqiao.json'
SAMPLE_BOOK = 'yuqiao-01'
_SAMPLE_MARK = 'yuqiao-workbench-v1'


def initialize_workspace(db, sample_path=SAMPLE_PATH):
    create_schema(db)
    with write_transaction(db):
        mark = db.execute('SELECT 1 FROM seed_marks WHERE name = ?', (_SAMPLE_MARK,)).fetchone()
        if mark is not None:
            return False
        sample = json.loads(Path(sample_path).read_text(encoding='utf-8'))
        book = sample['book']
        register_booklet(db, book, sample['title'])
        store_seat_briefs(db, book, sample['seats'])
        db.execute('INSERT INTO seed_marks(name) VALUES (?)', (_SAMPLE_MARK,))
        return True
