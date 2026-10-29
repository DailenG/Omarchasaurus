from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cast import Cast, cast_groups
from configuration import settings
from canvas import Canvas
from engine import World
from character_art import draw_scene, visible_cast_members


class CastBehavior(unittest.TestCase):
    view = (0, 0, 100, 60)

    def group(self, key, x, count=1, minimum=1, entry=None, token=0, active=True):
        return dict(key=key, token=token, minimum=minimum, entry=entry, active=active,
                    members=tuple(dict(id=f'{key}:{i}', bounds=(x-i*15-5, 40, x-i*15+5, 54, .5))
                                  for i in range(count)))

    def test_visible_incumbent_is_not_evicted_by_new_higher_priority_candidate(self):
        cast = Cast()
        resident = self.group('resident', 40)
        cast.update([resident], 2, self.view, initial=True)
        arriving = self.group('newcomer', -10)
        cast.update([arriving, resident], 2, self.view)
        arriving = self.group('newcomer', 1)
        self.assertEqual(cast.update([arriving, resident], 2, self.view),
                         ('brachiosaurus', 'resident:0'))
        cast.update([self.group('newcomer', 45), self.group('resident', 110)], 2, self.view)
        self.assertEqual(cast.members, ('brachiosaurus',))
        # A vacancy does not make the blocked animal pop in mid-traversal.
        cast.update([self.group('newcomer', 60)], 2, self.view)
        self.assertEqual(cast.members, ('brachiosaurus',))
        cast.update([self.group('newcomer', -10)], 2, self.view)
        cast.update([self.group('newcomer', 0)], 2, self.view)
        self.assertIn('newcomer:0', cast.members)

    def test_fixed_family_prefix_never_grows_mid_view_and_no_budget_orphan(self):
        cast = Cast()
        family = self.group('family', 50, count=4, minimum=2)
        cast.update([family], 4, self.view, initial=True)
        self.assertEqual(cast.count('family'), 3)
        cast.update([family], 6, self.view)
        self.assertEqual(cast.count('family'), 3)
        cast.update([family], 6, self.view, refresh=True)
        self.assertEqual(cast.count('family'), 4)
        cast.update([family], 2, self.view, refresh=True)
        self.assertEqual(cast.members, ('brachiosaurus',))
        self.assertEqual(cast.available(2), 1)

    def test_entering_pair_reserves_both_seats_until_its_guarded_rear_exits(self):
        cast = Cast()
        pair = self.group('pair', -10, count=2, entry=True)
        cast.update([pair], 3, self.view)
        self.assertEqual(cast.available(3), 0)
        cast.update([self.group('pair', 110, count=2)], 3, self.view)
        self.assertEqual(cast.count('pair'), 2)
        cast.update([self.group('pair', 122, count=2)], 3, self.view)
        self.assertEqual(cast.count('pair'), 0)

    def test_resize_does_not_create_a_false_entrance_or_move_occupants(self):
        cast = Cast()
        cast.update([self.group('candidate', -20)], 2, self.view)
        cast.update([self.group('candidate', -20)], 2, (-50, 0, 150, 60))
        self.assertEqual(cast.members, ('brachiosaurus',))
        cast.update([self.group('candidate', -15)], 2, (-50, 0, 150, 60))
        self.assertEqual(cast.members, ('brachiosaurus',))
        cast.update([self.group('candidate', -15)], 2, (-50, 0, 150, 60), refresh=True)
        self.assertIn('candidate:0', cast.members)

    def test_inactive_encounter_and_new_token_release_old_occupancy(self):
        cast = Cast()
        cast.update([self.group('swimmer', 40, entry=True)], 2, self.view)
        cast.update([self.group('swimmer', 40, active=False)], 2, self.view)
        self.assertEqual(cast.available(2), 1)
        cast.update([self.group('swimmer', 40, token=1, entry=False)], 2, self.view)
        self.assertEqual(cast.members, ('brachiosaurus',))
        cast.update([self.group('swimmer', 40, token=2, entry=True)], 2, self.view)
        self.assertIn('swimmer:0', cast.members)
        cast.update([], 2, self.view)
        self.assertEqual(cast.members, ('brachiosaurus',))

    def test_saved_resident_cast_has_no_interior_evictions_or_delayed_middle_entries(self):
        config = settings({'preset': 'dusk', 'animals': {'pteranodonEnabled': True,
                                                        'diplodocusResident': True}})
        world = World(config, visitor_seed=17)
        canvas = Canvas(160, 48)
        world.set_viewport(canvas.world_bounds)
        previous = world.snapshot()
        view = world._cast_view
        for _ in range(2400):
            world.advance(250_000_000)
            current = world.snapshot()
            before = {member['id']: member['bounds'] for group in cast_groups(previous, config, view)
                      for member in group['members']}
            after = {member['id']: member['bounds'] for group in cast_groups(current, config, view)
                     for member in group['members']}
            for identity in set(previous['admitted']) - set(current['admitted']):
                if identity in ('brachiosaurus', 'plesiosaurus', 'water_jump'):
                    continue
                if identity == 'brachiosaurus:young':
                    frame = Canvas(160, 48, camera=previous['camera'])
                    draw_scene(frame, previous, config)
                    self.assertIsNone(frame.bounds(identity),
                                      'young must be concealed before its reserved seat retires')
                    continue
                left, _, right, _, _ = before[identity]
                self.assertFalse(view[0]+2 < left and right < view[2]-2,
                                 (world.elapsed_ns, identity, before[identity]))
            for identity in set(current['admitted']) - set(previous['admitted']):
                if identity in ('brachiosaurus', 'plesiosaurus', 'water_jump') or identity not in before:
                    continue
                self.assertFalse(view[0]+2 < before[identity][0] and before[identity][2] < view[2]-2
                                 and view[0]+2 < after[identity][0] and after[identity][2] < view[2]-2,
                                 (world.elapsed_ns, identity, before[identity], after[identity]))
            self.assertLessEqual(len(current['admitted']), config['population']['maxVisible'])
            previous = current

    def test_lake_jump_requires_a_vacancy_instead_of_despawning_a_visible_animal(self):
        config = settings({'animals': {key: key == 'trexEnabled' for key in settings()['animals']},
                           'population': {'maxVisible': 2}})
        world = World(config)
        frame = Canvas(160, 48)
        world.set_viewport(frame.world_bounds)
        self.assertIn('trex', visible_cast_members(frame, world.snapshot(), config))
        self.assertFalse(world.spawn_water_jump(30, 44))
        self.assertIn('trex', visible_cast_members(frame, world.snapshot(), config))
        config['population']['maxVisible'] = 3
        world.reconfigure(config)
        self.assertTrue(world.spawn_water_jump(30, 44))
        self.assertEqual(set(visible_cast_members(frame, world.snapshot(), config)),
                         {'brachiosaurus', 'trex', 'water_jump'})


if __name__ == '__main__':
    unittest.main()
