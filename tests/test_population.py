import copy
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configuration import settings
from canvas import Canvas
from engine import ACTOR_NAMES, World
from character_art import draw_scene, visible_cast_members
from population import herbivore_pose, triceratops_extents


class PopulationBehavior(unittest.TestCase):
    def frame(self, world, pose=None, width=320, height=96):
        pose = world.snapshot() if pose is None else pose
        canvas = Canvas(width, height, pose['camera'])
        draw_scene(canvas, pose, world.config)
        return canvas

    def animal_owners(self, canvas):
        return {owner for row in canvas.owners for owner in row
                if owner in ACTOR_NAMES or (owner and owner.startswith('pteranodon:'))}

    def test_every_view_and_ceiling_bounds_rendered_individuals_including_lake_visitor(self):
        for seed in (0, 42):
            for seconds in (0, 80, 400):
                for limit in (1, 2, 3, 8, 128):
                    world = World(settings({'seed': seed,
                                            'animals': {'diplodocusResident': True},
                                            'population': {'maxVisible': limit}}),
                                  elapsed_ns=seconds * 1_000_000_000)
                    occupied = len(world.snapshot()['admitted'])
                    spawned = world.spawn_water_jump(20, 44)
                    self.assertEqual(spawned, occupied < limit)
                    for width, height in ((80, 24), (160, 48), (320, 96), (500, 40)):
                        with self.subTest(seed=seed, seconds=seconds, limit=limit, size=(width, height)):
                            pose = world.snapshot()
                            canvas = self.frame(world, width=width, height=height)
                            selected = set(visible_cast_members(canvas, pose, world.config))
                            self.assertIn('brachiosaurus', selected)
                            self.assertLessEqual(len(selected), limit)
                            self.assertLessEqual(self.animal_owners(canvas), selected)
                            self.assertLessEqual(len(self.animal_owners(canvas)) + int('water_jump' in selected), limit)
                            self.assertEqual(world.snapshot(), pose)

    def test_disabling_each_species_removes_its_rendered_ownership_and_click_reaction_only(self):
        for species, seconds in (('trex', 0), ('triceratops', 80),
                                 ('stegosaurus', 0), ('pteranodon', 0), ('ankylosaurus', 0),
                                 ('parasaurolophus', 0)):
            config = settings({'population': {'maxVisible': 128}})
            world = World(config, elapsed_ns=seconds * 1_000_000_000)
            before = world.snapshot()
            visible = self.animal_owners(self.frame(world))
            self.assertTrue(any(owner == species or owner.startswith(species + ':') for owner in visible))
            disabled_config = copy.deepcopy(config)
            disabled_config['animals'][species + 'Enabled'] = False
            world.reconfigure(disabled_config)
            self.assertEqual(dict(world.snapshot(), admitted=()), dict(before, admitted=()))
            disabled = self.animal_owners(self.frame(world))
            self.assertFalse(any(owner == species or owner.startswith(species + ':') for owner in disabled))
            for identity in visible:
                if identity == species or identity.startswith(species + ':'):
                    self.assertFalse(world.react(identity))
            world.reconfigure(config)
            self.assertEqual(self.animal_owners(self.frame(world)), visible)
            self.assertEqual(dict(world.snapshot(), admitted=()), dict(before, admitted=()))

    def test_flyer_tips_inside_edge_cell_footprints_are_not_culled(self):
        config = settings({
            'animals': {key: key == 'pteranodonEnabled' for key in settings()['animals']},
            'population': {'maxVisible': 4},
            'motion': {'parallaxStrength': 0},
        })
        world = World(config, visitor_seed=17)
        for pixel, column in ((-.25, 0), (319.25, 319)):
            with self.subTest(column=column):
                canvas = Canvas(320, 96)
                snapshot = world.snapshot()
                bird = dict(snapshot['pteranodons'][0])
                tip = canvas.unproject(pixel, 16, bird['depth'])[0]
                bird.update(x=tip-bird['span'] if column == 0 else tip+bird['span'],
                            y=10, tip_y=10, bank=0)
                snapshot.update(pteranodons=(bird,), camera=(0, 0),
                                admitted=('brachiosaurus', bird['id']))
                self.assertIn(bird['id'], visible_cast_members(canvas, snapshot, config))
                draw_scene(canvas, snapshot, config)
                self.assertEqual(canvas.owners[16][column], bird['id'])

    def test_retired_ground_animal_leaves_room_for_a_naturally_entering_flyer(self):
        config = settings({'animals': {key: key in ('trexEnabled', 'pteranodonEnabled')
                                       for key in settings()['animals']},
                           'population': {'maxVisible': 2}})
        world = World(config)
        canvas = Canvas(320, 96)
        world.set_viewport(canvas.world_bounds)
        self.assertIn('trex', world.snapshot()['admitted'])
        for _ in range(2400):
            world.advance(250_000_000)
            pose = world.snapshot()
            canvas.camera = pose['camera']
            if any(identity.startswith('pteranodon:') for identity in visible_cast_members(canvas, pose, config)):
                frame = self.frame(world)
                if any(owner.startswith('pteranodon:') for owner in self.animal_owners(frame)):
                    break
        self.assertNotIn('trex', world.snapshot()['admitted'])
        self.assertTrue(any(owner.startswith('pteranodon:') for owner in self.animal_owners(frame)))
        self.assertLessEqual(len(self.animal_owners(frame)), 2)


    def test_live_cap_changes_preserve_pose_pause_and_active_effects(self):
        config = settings({'population': {'maxVisible': 128}})
        world = World(config, elapsed_ns=80_000_000_000)
        world.react('triceratops')
        self.assertTrue(world.spawn_water_jump(40, 44))
        world.spawn_meteor(5, 4)
        world.paused = True
        before = world.snapshot()
        world.reconfigure(settings({'population': {'maxVisible': 1}}))
        self.assertEqual(dict(world.snapshot(), admitted=()), dict(before, admitted=()))
        self.assertTrue(world.paused)
        canvas = self.frame(world)
        self.assertEqual(self.animal_owners(canvas), {'brachiosaurus'})
        no_jump = self.frame(world, dict(before, water_jump=None))
        self.assertEqual(canvas.chars, no_jump.chars)
        self.assertEqual(canvas.colors, no_jump.colors)
        world.reconfigure(config)
        self.assertEqual(dict(world.snapshot(), admitted=()), dict(before, admitted=()))
        self.assertIn('water_jump', visible_cast_members(self.frame(world), before, world.config))


    def test_same_elapsed_time_preserves_new_walker_pose_across_frame_rates(self):
        poses = []
        for fps in (15, 60, 144):
            world = World(settings({'motion': {'speed': .75, 'reducedMotion': True}}))
            for frame in range(fps * 5):
                world.advance((frame + 1) * 1_000_000_000 // fps - frame * 1_000_000_000 // fps)
            poses.append((world.snapshot()['herbivores'], world.snapshot()['ankylosaurus']))
        self.assertEqual(poses[0], poses[1])
        self.assertEqual(poses[0], poses[2])

    def test_walking_grazing_transitions_are_continuous_and_forward_facing(self):
        for boundary in (0, 1, 17, 18, 21, 24, 25):
            before = herbivore_pose(boundary - .001, 0, 0, 0, False)
            after = herbivore_pose(boundary + .001, 0, 0, 0, False)
            self.assertGreaterEqual(after['x'], before['x'])
            self.assertLess(after['x'] - before['x'], .003)
            self.assertLess(abs(after['graze'] - before['graze']), .002)
            self.assertLess(abs(after['stride'] - before['stride']), .003)
        resting = [herbivore_pose(t, 0, 0, 0, False) for t in (19, 21, 23)]
        self.assertEqual(resting[0]['x'], resting[2]['x'])
        self.assertEqual(resting[0]['phase'], resting[2]['phase'])
        self.assertGreater(resting[1]['graze'], resting[0]['graze'])
        self.assertGreater(resting[1]['graze'], resting[2]['graze'])

    def test_walker_footprints_keep_collision_gaps_over_multiple_route_wraps(self):
        triceratops_left, _, triceratops_right, _, _ = triceratops_extents(2)
        for seed in (0, 42, 2026):
            for second in range(0, 1800, 3):
                pose = World(settings({'seed': seed}), elapsed_ns=second * 1_000_000_000).snapshot()
                walkers = sorted(((pose['trex_x'], -18, 23),
                                  (pose['herbivores']['triceratops']['x'], triceratops_left, triceratops_right),
                                  (pose['herbivores']['stegosaurus']['x'], -18, 16)))
                for index, (x, left, right) in enumerate(walkers):
                    other, other_left, _ = walkers[(index + 1) % len(walkers)]
                    gap = (other - x) % 600 + other_left - right
                    self.assertGreater(gap, 8, (seed, second, gap))

    def test_new_head_reactions_move_the_eye_without_changing_torso_columns(self):
        for species in ('triceratops', 'stegosaurus'):
            displacements = {}
            for calm in (False, True):
                config = settings({'animals': {'trexEnabled': False, 'pteranodonEnabled': False,
                                               'ankylosaurusEnabled': False,
                                               'plesiosaurusEnabled': False,
                                               ('stegosaurus' if species == 'triceratops' else 'triceratops') + 'Enabled': False},
                                   'motion': {'reducedMotion': calm}})
                world = World(config)
                baseline = world.snapshot()
                baseline['admitted'] = ('brachiosaurus', species)
                baseline['herbivores'][species].update(x=15, graze=0, blink=False)
                active = copy.deepcopy(baseline)
                active['herbivores'][species]['reaction'] = 1
                frames = [self.frame(world, pose, width=500, height=120) for pose in (baseline, active)]
                eyes = [next((x, y) for y, row in enumerate(frame.chars) for x, ch in enumerate(row)
                             if ch == 'o' and frame.owners[y][x] == species) for frame in frames]
                displacements[calm] = math.hypot(eyes[1][0] - eyes[0][0], (eyes[1][1] - eyes[0][1]) * frames[0].aspect)
                columns = []
                for frame in frames:
                    frame.depth = .55
                    low, _ = map(round, frame.project(10, 46))
                    high, _ = map(round, frame.project(13, 46))
                    columns.append([sum(row[x] == species for row in frame.owners) for x in range(low, high + 1)])
                self.assertEqual(columns[0], columns[1])
            self.assertGreater(displacements[False], displacements[True])
            self.assertGreater(displacements[False], 3)


if __name__ == '__main__':
    unittest.main()
