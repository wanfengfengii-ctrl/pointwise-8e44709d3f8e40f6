from release.editions import find_fixed_edition_snapshot


def find_bound_copy(db, edition_id):
    snapshot = find_fixed_edition_snapshot(db, edition_id)
    if snapshot is None:
        raise LookupError('找不到这个固定册号。')
    return snapshot
