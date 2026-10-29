"""Bounded, non-preemptive occupancy for right-moving animal encounters."""
from __future__ import annotations
from collections.abc import Hashable, Iterable, Sequence
from configuration import Settings
from scene_types import ActorBounds, CastGroup, CastMember, SceneSnapshot, ViewportBounds
from population import GROUND_EXTENTS, PARASAUROLOPHUS_DEPTH
from pteranodon import pteranodon_bounds
from hatching import young_brachiosaurus_bounds


class Cast:
    def __init__(self) -> None:
        self._holds: dict[str, tuple[Hashable, tuple[str, ...]]] = {}
        self._previous: dict[str, tuple[Hashable, float]] = {}
        self._view: ViewportBounds | None = None
        # Remember only the latest flock generation, including explicit release.
        # An Off/cap round-trip must not grow or re-admit that same pass.
        self._flock_token: Hashable | None = None
        self._hatching_token: Hashable | None = None

    @property
    def members(self) -> tuple[str, ...]:
        return ('brachiosaurus', *(identity for _, ids in self._holds.values()
                                  for identity in ids))

    def count(self, key: str) -> int:
        held = self._holds.get(key)
        return len(held[1]) if held is not None else 0

    def available(self, maximum: int) -> int:
        return max(0, maximum - 1 - sum(len(ids) for _, ids in self._holds.values()))

    @staticmethod
    def _within_admission_guard(member: CastMember, view: ViewportBounds) -> bool:
        left, top, right, bottom, depth = member['bounds']
        return (left <= view[2] + 3.5 * depth and right >= view[0] - 3.5 * depth
                and top <= view[3] + .42 * depth and bottom >= view[1] - .42 * depth)

    @staticmethod
    def _nose(members: Sequence[CastMember], view: ViewportBounds) -> float:
        return max(member['bounds'][2] - view[0] + 3.5 * member['bounds'][4]
                   for member in members)

    @staticmethod
    def _departed(members: Sequence[CastMember], view: ViewportBounds) -> bool:
        return all(member['bounds'][0] > view[2] + 3.5 * member['bounds'][4]
                   for member in members)

    def update(self, groups: Sequence[CastGroup], maximum: int, view: ViewportBounds,
               *, initial: bool = False, refresh: bool = False) -> tuple[str, ...]:
        remaining = maximum - 1
        retained: dict[str, tuple[Hashable, tuple[str, ...]]] = {}
        # Existing occupants are never displaced by a newly eligible group.
        # Explicitly lowering the ceiling may shorten a leader-first prefix.
        for group in groups:
            held = self._holds.get(group['key'])
            if not group['active'] or held is None or held[0] != group['token']:
                continue
            ids = held[1]
            candidates = {member['id']: member for member in group['members']}
            members = tuple(candidates[identity] for identity in ids if identity in candidates)
            if not members or (group['key'] != 'brachiosaurus:young'
                               and self._departed(members, view)):
                continue
            count = min(len(members), remaining)
            if count < group['minimum']:
                continue
            ids = tuple(member['id'] for member in members[:count])
            retained[group['key']] = (group['token'], ids)
            remaining -= count

        same_view = self._view == view
        for group in groups:
            if not group['active']:
                continue
            members = group['members']
            held = retained.get(group['key'])
            if held is not None:
                if refresh and remaining and group['key'] != 'pteranodon:flock':
                    count = min(len(members), len(held[1]) + remaining)
                    ids = tuple(member['id'] for member in members[:count])
                    remaining -= count - len(held[1])
                    retained[group['key']] = (group['token'], ids)
                continue
            if group['key'] == 'pteranodon:flock' and group['token'] == self._flock_token:
                continue
            if group['key'] == 'brachiosaurus:young':
                if group['token'] == self._hatching_token:
                    continue
                self._hatching_token = group['token']
            previous = self._previous.get(group['key'])
            crossing = (same_view and group['entry'] is None and previous is not None
                        and previous[0] == group['token'] and previous[1] < 0
                        and self._nose(members, view) >= 0)
            entering = group['entry'] is True or crossing
            if not entering and not ((initial or refresh) and group['key'] != 'pteranodon:flock'
                                     and any(self._within_admission_guard(member, view) for member in members)):
                continue
            count = min(len(members), remaining)
            if count < group['minimum']:
                continue
            # A group already beyond the guarded exit cannot occupy a new seat.
            if self._departed(members[:count], view):
                continue
            retained[group['key']] = (group['token'], tuple(member['id'] for member in members[:count]))
            if group['key'] == 'pteranodon:flock':
                self._flock_token = group['token']
            remaining -= count

        self._holds = retained
        self._previous = {group['key']: (group['token'], self._nose(group['members'], view))
                          for group in groups if group['members']}
        self._view = view
        return self.members


def cast_groups(snapshot: SceneSnapshot, config: Settings, view: ViewportBounds) -> list[CastGroup]:
    """Describe encounters without allocating seats or mutating simulation."""
    groups: list[CastGroup] = []
    seed = config['seed']
    visitor = snapshot['visitor'] if config['population']['randomVisitors'] else None

    def add(key: str, members: Iterable[tuple[str, ActorBounds]], minimum: int = 1,
            active: bool = True, entry: bool | None = None, token: Hashable | None = None) -> None:
        records = tuple(CastMember(id=identity, bounds=bounds) for identity, bounds in members)
        if visitor is not None and (key == visitor['species']
                                    or key == 'parasaurolophus:0' and visitor['species'] == 'parasaurolophus'):
            token = visitor['generation']
            if records[0]['bounds'][2] < view[0] - 3.5 * records[0]['bounds'][4]:
                entry = True
        groups.append(CastGroup(key=key, token=(seed, token), members=records,
                                minimum=minimum, active=active, entry=entry))

    jump = snapshot['water_jump']
    if jump is not None:
        add('water_jump', (('water_jump', (jump['x']-3, jump['y']-3,
                                          jump['x']+3, jump['y']+2, .24)),),
            entry=True, token=jump['born'])
    young = snapshot['hatching']
    if young is not None:
        # Reserve the seat from the first wobble, before any other new arrival.
        # Visibility of the nest was checked by the lifecycle at its deadline.
        add('brachiosaurus:young', ((young['id'], young_brachiosaurus_bounds(young)),),
            entry=True, token=young['generation'])
    swimmer = snapshot['plesiosaurus']
    if config['animals']['plesiosaurusEnabled']:
        add('plesiosaurus', ((swimmer['id'], (
            swimmer['x']-12, min(swimmer['body_y']-14, swimmer['water_y']),
            swimmer['x']+12, swimmer['water_y'], swimmer['depth'])),),
            active=swimmer['visible'] or swimmer['state'] == 'surfacing',
            entry=swimmer['state'] == 'surfacing' and not swimmer['visible'],
            token=swimmer['cycle'])
    diplodocus = snapshot['diplodocus']
    if config['animals']['diplodocusEnabled'] and diplodocus is not None:
        add('diplodocus', ((diplodocus['id'], (
            diplodocus['x']-42, diplodocus['foot_y']-20,
            diplodocus['x']+40, diplodocus['foot_y']+5, diplodocus['depth'])),),
            entry=True if diplodocus['x']+40 < view[0]-3.5*diplodocus['depth'] else None,
            token=diplodocus['generation'])
    if config['animals']['parasaurolophusEnabled']:
        for index, family in enumerate(
                snapshot['parasaurolophus_families'][:config['population']['maxFamilies']]):
            if config['population']['randomVisitors'] and (
                    visitor is None or visitor['species'] != 'parasaurolophus' or index != 0):
                continue
            add(family['id'], ((member['id'], (
                member['x']-15*member['scale'], member['foot_y']-20*member['scale'],
                member['x']+15*member['scale'], member['foot_y'], PARASAUROLOPHUS_DEPTH))
                for member in family['members']), minimum=2)
    for identity, x, enabled in (
            ('trex', snapshot['trex_x'], config['animals']['trexEnabled']),
            ('triceratops', snapshot['herbivores']['triceratops']['x'], config['animals']['triceratopsEnabled']),
            ('stegosaurus', snapshot['herbivores']['stegosaurus']['x'], config['animals']['stegosaurusEnabled']),
            ('ankylosaurus', snapshot['ankylosaurus']['x'], config['animals']['ankylosaurusEnabled'])):
        if not enabled or (
                config['population']['randomVisitors']
                and (visitor is None or visitor['species'] != identity)):
            continue
        if identity == 'triceratops':
            add(identity, ((member['id'], (
                member['x']-15*member['scale'], member['foot_y']-15*member['scale'],
                member['x']+15*member['scale'], member['foot_y']+.5, .55))
                for member in (snapshot['herbivores']['triceratops'], snapshot['triceratops_calf'])))
        else:
            left, top, right, bottom, depth = GROUND_EXTENTS[identity]
            add(identity, ((identity, (x+left, top, x+right, bottom, depth)),))
    if config['animals']['pteranodonEnabled']:
        for bird in snapshot['pteranodons']:
            add(bird['id'], ((bird['id'], pteranodon_bounds(bird)),))
        flock = snapshot['pteranodon_flock']
        if flock is not None:
            members = tuple((bird['id'], pteranodon_bounds(bird))
                            for bird in flock['members'])
            offleft = all(bounds[2] < view[0] - 3.5 * bounds[4]
                          for _, bounds in members)
            add('pteranodon:flock', members, minimum=2, entry=offleft,
                token=flock['generation'])
    return groups


