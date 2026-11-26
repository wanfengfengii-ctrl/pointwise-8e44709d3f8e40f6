from dataclasses import dataclass

from layout.placements import PlacementConflict, build_placement_problem
from layout.solver import Layout, LayoutConflict, solve_layout


@dataclass(frozen=True)
class PreviewResult:
    layout: Layout | None
    conflict: PlacementConflict | LayoutConflict | None = None


def preview(revision, pins=()):
    try:
        problem = build_placement_problem(revision, pins)
    except PlacementConflict as conflict:
        return PreviewResult(None, conflict)
    result = solve_layout(problem)
    if isinstance(result, LayoutConflict):
        return PreviewResult(None, result)
    return PreviewResult(result)


def describe_conflict(conflict):
    if conflict is None:
        return None
    if isinstance(conflict, LayoutConflict):
        candidates = '、'.join(str(page) for page in conflict.candidates)
        return f'引文 {conflict.quote} 的候选页为 {candidates}，无法为它腾出页格并完成整稿。'
    return str(conflict)
