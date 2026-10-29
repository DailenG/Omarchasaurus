"""Rigid-action intent on the shared, distance-derived ground walking clock."""
import math
from population import walking_distance
from scene_types import TyrannosaurusPose


def _ease(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def tyrannosaurus_pose(walk_time: float, time: float, phase: float, start_x: float,
                      reaction: float, blink_phase: float,
                      reduced_motion: bool = False) -> TyrannosaurusPose:
    travel = walking_distance(walk_time, phase) - walking_distance(0, phase)
    cycle, cycle_age = divmod(walk_time + phase * 24 / math.tau, 24)
    stride = max(0.0, min(1.0, cycle_age, 18 - cycle_age))
    look = roar = sit = 0.0
    state = 'walking'
    if cycle_age >= 18:
        stop_age = cycle_age - 18
        action = int(cycle) % 3
        if action == 0:
            state = 'looking'
            look = .14 * math.sin(stop_age * math.tau / 6) * _ease(stop_age) * _ease(6-stop_age)
        elif action == 1:
            amount = _ease(stop_age) * _ease((6-stop_age) / 2)
            if reduced_motion:
                state = 'looking'
                look = -.10 * amount
            else:
                state = 'roaring'
                roar = amount
        else:
            state = 'sitting'
            sit = _ease(stop_age / 1.5) * _ease((6-stop_age) / 1.5)
    return {
        'trex_x': start_x + travel,
        'phase': travel * 2.4 / .9 + phase,
        'trex_blink': (time + blink_phase) % 7.7 > 7.5,
        'trex_reaction': reaction,
        'trex_stride': stride, 'trex_look': look,
        'trex_roar': roar, 'trex_sit': sit, 'trex_state': state,
    }
