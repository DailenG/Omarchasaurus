import copy
from dataclasses import replace
import math
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import settings
from canvas import Canvas
from engine import World
from layout import generate_layout
from character_art import visible_cast_members
from population import GROUND_EXTENTS, parasaurolophus_family_pose


class ParasaurolophusBehavior(unittest.TestCase):
    def world(self, seed=42, limit=8, families=1, visitors=False, flyers=False):
        config = settings({
            'seed': seed,
            'animals': {species + 'Enabled': species == 'parasaurolophus'
                        for species in GROUND_EXTENTS} | {
                            'pteranodonEnabled': flyers, 'plesiosaurusEnabled': False,
                            'diplodocusEnabled': False},
            'population': {'maxVisible': limit, 'maxFamilies': families,
                           'randomVisitors': visitors},
        })
        world = World(config, visitor_seed=17)
        world.set_viewport(Canvas(160, 48).world_bounds)
        return world

    def advance(self, world, seconds):
        remaining = round(seconds * 1_000_000_000)
        while remaining:
            delta = min(250_000_000, remaining)
            world.advance(delta)
            remaining -= delta

    def family_ids(self, selected):
        return tuple(identity for identity in selected if identity.startswith('parasaurolophus:'))

    def test_seeded_families_have_bounded_distinct_juveniles_without_changing_other_streams(self):
        state = random.getstate()
        for seed in (0, 1, 17, 42, 2**53 - 1):
            layout = generate_layout(seed, {})
            changed_scenery = generate_layout(seed, {'treeDensity': 2, 'cloudDensity': 0})
            self.assertEqual(layout.parasaurolophus_families, changed_scenery.parasaurolophus_families)
            identities = set()
            for family in layout.parasaurolophus_families:
                self.assertGreaterEqual(len(family.members), 2)
                self.assertLessEqual(len(family.members), 4)
                self.assertEqual(family.members[0].scale, 1)
                for follower in family.members[1:]:
                    self.assertLess(follower.scale, family.members[0].scale)
                for member in family.members:
                    self.assertNotIn(member.id, identities)
                    identities.add(member.id)
        self.assertEqual(random.getstate(), state)

    def test_followers_keep_gaps_and_shared_displacement(self):
        family = self.world().layout.parasaurolophus_families[0]
        baseline = parasaurolophus_family_pose(family, 0, family.phase, family.start_x, 0, {})['members']
        offsets = [member['x'] - baseline[0]['x'] for member in baseline]
        for seconds in range(0, 950, 7):
            members = parasaurolophus_family_pose(family, seconds, family.phase, family.start_x, seconds, {})['members']
            for index, member in enumerate(members):
                self.assertAlmostEqual(member['x'] - members[0]['x'], offsets[index])
                if index:
                    ahead = members[index - 1]
                    gap = (ahead['x'] - 15 * ahead['scale']) - (member['x'] + 15 * member['scale'])
                    self.assertGreaterEqual(gap, 3 - 1e-10)
        later = parasaurolophus_family_pose(family, 30, family.phase, family.start_x, 30, {})['members']
        travel = later[0]['x'] - baseline[0]['x']
        self.assertGreater(travel, 0)
        for before, after in zip(baseline, later):
            self.assertAlmostEqual(after['x'] - before['x'], travel)

    def test_two_family_routes_keep_unrelated_groups_apart(self):
        world = self.world(families=2, limit=128)
        for seconds in range(0, 950, 23):
            families = World(world.config, elapsed_ns=seconds * 1_000_000_000).snapshot()['parasaurolophus_families']
            bounds = sorted((family['members'][-1]['x'] - 15 * family['members'][-1]['scale'],
                             family['members'][0]['x'] + 15) for family in families)
            self.assertGreaterEqual(bounds[1][0] - bounds[0][1], 3)
            self.assertGreaterEqual(bounds[0][0] + 600 - bounds[1][1], 3)

    def test_drinking_stops_travel_and_only_lowers_bills_at_water(self):
        family = replace(self.world().layout.parasaurolophus_families[0], start_x=50)
        stop = 44 - family.phase * 24 / math.tau
        a = parasaurolophus_family_pose(family, stop, family.phase, family.start_x, stop, {})['members']
        b = parasaurolophus_family_pose(family, stop + 1, family.phase, family.start_x, stop + 1, {})['members']
        for before, after in zip(a, b):
            self.assertEqual(before['x'], after['x'])
            self.assertEqual(before['phase'], after['phase'])
            self.assertEqual(before['stride'], 0)
            self.assertEqual(before['drink'], 1)
            self.assertEqual(before['state'], 'drinking')
            self.assertGreaterEqual(before['foot_y'], 48)
        dry = parasaurolophus_family_pose(family, stop, family.phase, 200, stop, {})
        self.assertTrue(all(member['drink'] == 0 and member['state'] == 'resting'
                            for member in dry['members']))
        walking = parasaurolophus_family_pose(family, stop + 5, family.phase, family.start_x, stop + 5, {})['members']
        for parked, moving in zip(a, walking):
            self.assertGreater(moving['x'], parked['x'])
            self.assertEqual(moving['drink'], 0)
            self.assertEqual(moving['state'], 'following')

    def test_family_caps_count_individuals_and_never_admit_a_budget_orphan(self):
        canvas = Canvas(500, 10)
        for maximum in (1, 2, 3, 4, 8, 128):
            world = self.world(limit=maximum)
            pose = world.snapshot()
            selected = visible_cast_members(canvas, pose, world.config)
            count = min(len(pose['parasaurolophus_families'][0]['members']), maximum - 1)
            self.assertEqual(len(self.family_ids(selected)), count if count >= 2 else 0)
            self.assertLessEqual(len(selected), maximum)
        world = World(self.world(limit=128, families=2).config, visitor_seed=17)
        world.set_viewport(canvas.world_bounds)
        pose = world.snapshot()
        selected = visible_cast_members(canvas, pose, world.config)
        expected = {member['id'] for family in pose['parasaurolophus_families'] for member in family['members']}
        self.assertEqual(set(self.family_ids(selected)), expected)
        config = copy.deepcopy(world.config)
        config['population']['maxFamilies'] = 0
        world.reconfigure(config)
        self.assertEqual(self.family_ids(visible_cast_members(canvas, world.snapshot(), config)), ())
        self.assertEqual(dict(world.snapshot(), admitted=()), dict(pose, admitted=()))
        for limit in (3, 4):
            world = self.world(limit=limit)
            before = world.snapshot()['admitted']
            self.assertFalse(world.spawn_water_jump(20, 44))
            self.assertEqual(world.snapshot()['admitted'], before)
            self.assertLessEqual(len(visible_cast_members(canvas, world.snapshot(), world.config)), limit)


    def test_pause_resize_and_unrelated_reload_preserve_family_poses_and_member_cooldowns(self):
        world = self.world(families=2, limit=128)
        leader, follower = world.snapshot()['parasaurolophus_families'][0]['members'][:2]
        self.assertTrue(world.react(leader['id']))
        self.assertFalse(world.react(leader['id']))
        self.assertTrue(world.react(follower['id']))
        self.advance(world, .5)
        world.paused = True
        before = world.snapshot()['parasaurolophus_families']
        self.advance(world, 3)
        world.set_viewport(Canvas(80, 80).world_bounds)
        config = copy.deepcopy(world.config)
        config['preset'] = 'dusk'
        config['scenery']['treeDensity'] = 0
        world.reconfigure(config)
        self.assertEqual(world.snapshot()['parasaurolophus_families'], before)
        config['animals']['parasaurolophusEnabled'] = False
        world.reconfigure(config)
        self.assertFalse(world.react(leader['id']))
        self.assertEqual(self.family_ids(visible_cast_members(Canvas(160, 48), world.snapshot(), config)), ())
        self.assertFalse(world.react('parasaurolophus'))
        self.assertFalse(world.react('parasaurolophus:2:0'))
        self.assertFalse(world.react('parasaurolophus:0:4'))

    def test_random_family_retires_after_its_last_admitted_follower_and_reserves_reentry_slots(self):
        world = self.world(limit=3, families=2, visitors=True, flyers=True)
        self.assertEqual(world.snapshot()['visitor']['species'], 'parasaurolophus')
        self.assertFalse(world.react('parasaurolophus:1:0'))
        clicked = False
        for _ in range(1600):
            before = world.snapshot()
            last = before['parasaurolophus_families'][0]['members'][1]
            _, edge = world.visitors.edges('parasaurolophus')
            rear = last['x'] - 15 * last['scale']
            if rear > edge + 1 and not clicked:
                clicked = world.react(last['id'])
            self.advance(world, .25)
            after = world.snapshot()
            if after['visitor']['generation'] != before['visitor']['generation']:
                self.assertGreater(rear, edge)
                self.assertTrue(clicked)
                self.assertTrue(world.react(last['id']), 'replacement inherited an old member cooldown')
                self.assertEqual(visible_cast_members(Canvas(160, 48), after, world.config), ('brachiosaurus',))
                self.assertLessEqual(after['visitor']['age'], .25)
                break
        else:
            self.fail('family did not depart and restart')
        config = copy.deepcopy(world.config)
        config['population']['maxFamilies'] = 0
        world.reconfigure(config)
        self.assertIsNone(world.snapshot()['visitor'])
        config['population']['maxFamilies'] = 2
        config['population']['maxVisible'] = 2
        world.reconfigure(config)
        self.assertIsNone(world.snapshot()['visitor'])

    def test_family_clocks_are_independent_of_frame_rate_and_reduced_motion_slows_travel(self):
        outcomes = []
        for fps in (15, 60, 144):
            world = self.world()
            config = copy.deepcopy(world.config)
            config['motion'].update(speed=.75, reducedMotion=True)
            world.reconfigure(config)
            for frame in range(fps * 5):
                world.advance((frame + 1) * 5_000_000_000 // (fps * 5)
                              - frame * 5_000_000_000 // (fps * 5))
            outcomes.append(world.snapshot()['parasaurolophus_families'])
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0], outcomes[2])
        normal = self.world()
        calm = self.world()
        config = copy.deepcopy(calm.config)
        config['motion']['reducedMotion'] = True
        calm.reconfigure(config)
        self.advance(normal, 30)
        self.advance(calm, 60)
        self.assertEqual(normal.snapshot()['parasaurolophus_families'][0]['members'][0]['x'],
                         calm.snapshot()['parasaurolophus_families'][0]['members'][0]['x'])


if __name__ == '__main__':
    unittest.main()
