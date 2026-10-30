"""Terminal-independent character world and bounded encounter lifecycles.

Original dinosaur implementation. Terminal lifecycle follows Omarcharium's MIT-
licensed approach; see LICENSE. Coordinates describe strokes, never pixel images.
"""
from __future__ import annotations
import copy
import math
import secrets
from fractions import Fraction

from cast import Cast, cast_groups
from configuration import Settings
from diplodocus import DiplodocusVisits
from hatching import NestHatching, egg_offsets
from layout import WATER_DEPTH, generate_layout
from population import (GROUND_EXTENTS, ankylosaurus_pose, herbivore_pose,
                        parasaurolophus_extents, parasaurolophus_family_pose,
                        plesiosaurus_pose, triceratops_extents,
                        triceratops_poses, walking_distance)
from pteranodon import PteranodonFlocks, flight_radius, pteranodon_pose
from routes import Routes
from scene_types import MeteorPose, Nanoseconds, SceneSnapshot, ViewportBounds, VisitorPose, WaterJumpPose
from visitors import RandomVisitors
from tyrannosaurus import tyrannosaurus_pose
from volcano import VolcanoPuffs
from weather import ValleyWeather

ACTOR_NAMES = {
    'brachiosaurus': 'Brachiosaurus',
    'brachiosaurus:young': 'Young Brachiosaurus',
    'trex': 'Tyrannosaurus rex',
    'triceratops': 'Triceratops',
    'triceratops:calf': 'Triceratops calf',
    'stegosaurus': 'Stegosaurus',
    'ankylosaurus': 'Ankylosaurus',
    'plesiosaurus': 'Plesiosaurus',
    'diplodocus': 'Diplodocus',
}
ACTOR_NAMES.update({
    f'parasaurolophus:{family}:{member}':
        'Parasaurolophus' if member == 0 else 'Parasaurolophus juvenile'
    for family in range(2) for member in range(4)
})

class World:
    def __init__(self, config: Settings, elapsed_ns: Nanoseconds = 0, *, visitor_seed: int | None = None) -> None:
        self.config = copy.deepcopy(config)
        self.layout = generate_layout(config['seed'], config['scenery'])
        self._elapsed_ns = elapsed_ns
        self._speed = Fraction(str(config['motion']['speed']))
        self._motion_ns = elapsed_ns*self._speed
        self._walk_ns = self._motion_ns * (Fraction(1, 2) if config['motion']['reducedMotion'] else 1)
        self.paused = False
        self.reactions: dict[str, int] = {}
        self.meteor: tuple[Nanoseconds, float, float, int, bool] | None = None
        self.water_jump: tuple[Nanoseconds, float, float, int, bool] | None = None
        self.ankylosaurus_wake: tuple[int, Nanoseconds, float, float] | None = None
        self.visitor_seed = secrets.randbits(64) if visitor_seed is None else visitor_seed
        self._visitor_bounds = (23.0, 123.0)
        self._visitors_scene_seed: int | None = None
        self.visitors: RandomVisitors | None = None
        self._configure_visitors(start_in_view=True)
        self._diplodocus_initial_placement = True
        self.diplodocus = DiplodocusVisits(
            self.layout.diplodocus, config['animals']['diplodocusResident'], self._visitor_bounds)
        self.diplodocus.advance(self._elapsed_ns, self._walk_ns)
        self._flock_initial_placement = True
        self.pteranodon_flocks = PteranodonFlocks(
            self.layout.pteranodon_flock, self.layout.pteranodon_visit_seed,
            self._visitor_bounds, enabled=config['animals']['pteranodonEnabled'])
        self.pteranodon_flocks.advance(self._elapsed_ns, self._motion_ns)
        self.hatching = NestHatching(
            self.layout.nest, self.layout.hatching_seed, self.layout.hatching_phase)
        # Historical construction has no historical Cast budget to admit births.
        self.hatching.advance(self._elapsed_ns, self._walk_ns, can_start=False)
        self.volcano_puffs = VolcanoPuffs(self.layout.volcano_puff_seed)
        # Scenery needs no historical Cast admission; replay its complete clocks.
        self.volcano_puffs.advance(
            self._elapsed_ns, self._motion_ns, calm=config['motion']['reducedMotion'])
        self.weather = ValleyWeather(self.layout.rain_drops, self.layout.weather_seed)
        self.weather.advance(
            self._elapsed_ns, self._motion_ns, calm=config['motion']['reducedMotion'])
        self.cast = Cast()
        self._cast_view = (23.0, 0.0, 123.0, 60.0)
        self._cast_initial_view = True
        self._route_initial_placement = True
        self._configure_routes()
        self._update_cast(initial=True)

    def _configure_routes(self):
        self._route_phases = {
            'trex': self.layout.trex_phase,
            'triceratops': self.layout.triceratops_phase,
            'stegosaurus': self.layout.stegosaurus_phase,
            'ankylosaurus': self.layout.ankylosaurus_phase,
        }
        starts = {'trex': 30 + self.layout.trex_start,
                  'triceratops': -35 + self.layout.trex_start,
                  'stegosaurus': 105 + self.layout.trex_start,
                  'ankylosaurus': 32 + self.layout.trex_start}
        descriptors = []
        for key, start in starts.items():
            left, _, right, _, depth = (triceratops_extents(2) if key == 'triceratops'
                                        else GROUND_EXTENTS[key])
            descriptors.append(dict(key=key, start_x=start, rear=left, nose=right,
                                    depth=depth, minimum_span=600, lane='ground'))
        for family in self.layout.parasaurolophus_families:
            self._route_phases[family.id] = family.phase
            left, _, right, _, depth = parasaurolophus_extents(family, len(family.members))
            descriptors.append(dict(key=family.id, start_x=family.start_x,
                                    rear=left, nose=right, depth=depth, minimum_span=600, lane='ground'))
        for bird in self.layout.pteranodons:
            descriptors.append(dict(key=bird.id, start_x=bird.start_x,
                                    rear=-flight_radius(bird.span), nose=flight_radius(bird.span),
                                    depth=bird.depth, minimum_span=134))
        self._routes = Routes(descriptors, self._route_distances(), self._visitor_bounds)

    def _route_distances(self):
        walk = float(self._walk_ns / 1_000_000_000)
        time = float(self._motion_ns / 1_000_000_000)
        distances = {key: walking_distance(walk, phase) - walking_distance(0, phase)
                     for key, phase in self._route_phases.items()}
        distances.update((bird.id, time * bird.speed) for bird in self.layout.pteranodons)
        return distances

    def _update_cast(self, *, initial=False, refresh=False):
        pose = self.snapshot()
        self.cast.update(cast_groups(pose, self.config, self._cast_view),
                         self.config['population']['maxVisible'], self._cast_view,
                         initial=initial, refresh=refresh)
        self.pteranodon_flocks.latch_prefix(self.cast.count('pteranodon:flock'))
        if not self.hatching.active or not self.cast.count('brachiosaurus:young'):
            self.hatching.cancel()
            self.reactions.pop('brachiosaurus:young', None)
        if self.visitors is not None and self.visitors.species in ('parasaurolophus', 'triceratops'):
            species = self.visitors.species
            key = 'parasaurolophus:0' if species == 'parasaurolophus' else species
            count = self.cast.count(key)
            if count:
                extent = (parasaurolophus_extents(self.layout.parasaurolophus_families[0], count)
                          if species == 'parasaurolophus' else triceratops_extents(count))
                if self.visitors.extents[species] != extent:
                    extents = dict(self.visitors.extents)
                    extents[species] = extent
                    self.visitors.change_pool(self.visitors.pool,
                                              float(self._walk_ns / 1_000_000_000), extents)

    @property
    def elapsed_ns(self) -> Nanoseconds:
        return self._elapsed_ns

    def reconfigure(self, config: Settings) -> None:
        """Apply resolved intent without retiming history or moving unchanged layout."""
        previous_visitor = self._visitor_token()
        previous_diplodocus = self._diplodocus_token()
        scene_changed = config['seed'] != self.config['seed']
        refresh = (scene_changed or config['animals'] != self.config['animals']
                   or config['population'] != self.config['population'])
        self._cast_initial_view = False
        self._route_initial_placement = False
        self._diplodocus_initial_placement = False
        self._flock_initial_placement = False
        if config['seed'] != self.config['seed'] or config['scenery'] != self.config['scenery']:
            self.layout = generate_layout(config['seed'], config['scenery'])
        if config['seed'] != self.config['seed']:
            self.ankylosaurus_wake = None
        if scene_changed:
            self._configure_routes()
        self.config = copy.deepcopy(config)
        self._speed = Fraction(str(config['motion']['speed']))
        self._configure_visitors(start_in_view=False)
        self._visitor_changed(previous_visitor)
        if scene_changed:
            self.diplodocus = DiplodocusVisits(
                self.layout.diplodocus, config['animals']['diplodocusResident'], self._visitor_bounds,
                self._elapsed_ns, self._walk_ns)
        else:
            self.diplodocus.set_resident(config['animals']['diplodocusResident'])
        self._diplodocus_changed(previous_diplodocus)
        if scene_changed:
            self.pteranodon_flocks = PteranodonFlocks(
                self.layout.pteranodon_flock, self.layout.pteranodon_visit_seed,
                self._visitor_bounds, self._elapsed_ns, self._motion_ns,
                enabled=config['animals']['pteranodonEnabled'])
        else:
            self.pteranodon_flocks.set_enabled(config['animals']['pteranodonEnabled'])
        if scene_changed:
            self.hatching = NestHatching(
                self.layout.nest, self.layout.hatching_seed, self.layout.hatching_phase,
                self._cast_view, self._elapsed_ns, self._walk_ns)
            self.reactions.pop('brachiosaurus:young', None)
            self.volcano_puffs = VolcanoPuffs(
                self.layout.volcano_puff_seed, self._elapsed_ns, self._motion_ns)
            self.weather = ValleyWeather(
                self.layout.rain_drops, self.layout.weather_seed,
                self._elapsed_ns, self._motion_ns)
        else:
            self.hatching.set_nest(self.layout.nest)
            if not self.hatching.active:
                self.reactions.pop('brachiosaurus:young', None)
        self._update_cast(refresh=refresh)

    def _diplodocus_token(self):
        return self.config['seed'], self.diplodocus.token

    def _diplodocus_changed(self, previous):
        if previous != self._diplodocus_token():
            self.reactions.pop('diplodocus', None)

    def _visitor_token(self):
        return (self._visitors_scene_seed, *self.visitors.token) if self.visitors else None

    def _configure_visitors(self, start_in_view):
        if not self.config['population']['randomVisitors']:
            self.visitors = None
            return
        family_count = min(len(self.layout.parasaurolophus_families[0].members),
                           self.config['population']['maxVisible'] - 1)
        allow_family = self.config['population']['maxFamilies'] > 0 and family_count >= 2
        pool = tuple(species for species in GROUND_EXTENTS
                     if self.config['animals'][species + 'Enabled']
                     and (species != 'parasaurolophus' or allow_family))
        extents = dict(GROUND_EXTENTS)
        if allow_family:
            extents['parasaurolophus'] = parasaurolophus_extents(
                self.layout.parasaurolophus_families[0], family_count)
        extents['triceratops'] = triceratops_extents(
            min(2, self.config['population']['maxVisible'] - 1))
        walk_time = float(self._walk_ns / 1_000_000_000)
        if self.visitors is None or self._visitors_scene_seed != self.config['seed']:
            self.visitors = RandomVisitors(
                self.config['seed'], self.visitor_seed, pool, walk_time,
                self._visitor_bounds, start_in_view, extents)
            self._visitors_scene_seed = self.config['seed']
        else:
            self.visitors.change_pool(pool, walk_time, extents)

    def _visitor_changed(self, previous):
        current = self._visitor_token()
        if previous == current:
            return
        for token in (previous, current):
            if token is not None and token[-1] is not None:
                for actor in tuple(self.reactions):
                    if actor.partition(':')[0] == token[-1]:
                        del self.reactions[actor]
                if token[-1] == 'ankylosaurus':
                    self.ankylosaurus_wake = None

    def set_viewport(self, bounds: ViewportBounds) -> None:
        """Accept world-space bounds; resizing never moves a current visitor."""
        self._visitor_bounds = bounds[0], bounds[2]
        self._cast_view = bounds
        self.hatching.set_viewport(bounds)
        if self._route_initial_placement:
            self._configure_routes()
            self._route_initial_placement = False
        else:
            self._routes.set_viewport(self._visitor_bounds, self._route_distances())
        if self.visitors is not None:
            self.visitors.set_viewport(
                self._visitor_bounds, float(self._walk_ns / 1_000_000_000))
        if self._diplodocus_initial_placement:
            previous = self._diplodocus_token()
            self.diplodocus = DiplodocusVisits(
                self.layout.diplodocus, self.config['animals']['diplodocusResident'], self._visitor_bounds)
            self.diplodocus.advance(self._elapsed_ns, self._walk_ns)
            self._diplodocus_initial_placement = False
            self._diplodocus_changed(previous)
        else:
            self.diplodocus.set_viewport(self._visitor_bounds)
        if self._flock_initial_placement:
            self.pteranodon_flocks = PteranodonFlocks(
                self.layout.pteranodon_flock, self.layout.pteranodon_visit_seed,
                self._visitor_bounds,
                enabled=self.config['animals']['pteranodonEnabled'])
            self.pteranodon_flocks.advance(self._elapsed_ns, self._motion_ns)
            self._flock_initial_placement = False
        else:
            self.pteranodon_flocks.set_viewport(self._visitor_bounds)
        if self._cast_initial_view:
            self.cast = Cast()
        self._update_cast(initial=self._cast_initial_view)
        self._cast_initial_view = False

    @property
    def tick(self) -> int:
        return self.elapsed_ns * 60 // 1_000_000_000

    def advance(self, nanoseconds: Nanoseconds) -> None:
        if not self.paused:
            delta = min(max(0, nanoseconds), 250_000_000)
            self._diplodocus_initial_placement = False
            self._cast_initial_view = False
            self._route_initial_placement = False
            self._flock_initial_placement = False
            previous_diplodocus = self._diplodocus_token()
            previous_hatching = self.hatching.generation, self.hatching.active
            self._elapsed_ns += delta
            motion_delta = delta*self._speed
            self._motion_ns += motion_delta
            self._walk_ns += motion_delta * (Fraction(1, 2) if self.config['motion']['reducedMotion'] else 1)
            self._routes.advance(self._route_distances())
            self.diplodocus.advance(self._elapsed_ns, self._walk_ns)
            self.pteranodon_flocks.advance(self._elapsed_ns, self._motion_ns)
            self.volcano_puffs.advance(
                self._elapsed_ns, self._motion_ns,
                calm=self.config['motion']['reducedMotion'])
            self.weather.advance(
                self._elapsed_ns, self._motion_ns,
                calm=self.config['motion']['reducedMotion'])
            self.hatching.advance(
                self._elapsed_ns, self._walk_ns,
                can_start=self.cast.available(self.config['population']['maxVisible']) > 0)
            if previous_hatching != (self.hatching.generation, self.hatching.active):
                self.reactions.pop('brachiosaurus:young', None)
            self._diplodocus_changed(previous_diplodocus)
            if self.visitors is not None:
                previous_visitor = self._visitor_token()
                self.visitors.advance(float(self._walk_ns / 1_000_000_000))
                self._visitor_changed(previous_visitor)
            if self.meteor is not None:
                born, _, _, duration, _ = self.meteor
                if self.elapsed_ns - born >= duration:
                    self.meteor = None
            if self.water_jump is not None:
                born, _, _, duration, _ = self.water_jump
                if self.elapsed_ns - born >= duration:
                    self.water_jump = None
            self._update_cast()

    def react(self, actor):
        if actor not in ACTOR_NAMES:
            return False
        if actor == 'brachiosaurus:young':
            young = self.hatching.current()
            if (young is None or young['emerge'] <= 0
                    or actor not in self.cast.members):
                return False
        species = actor.partition(':')[0]
        if species != 'brachiosaurus' and not self.config['animals'][species + 'Enabled']:
            return False
        if species == 'parasaurolophus':
            family, member = map(int, actor.split(':')[1:])
            if (family >= self.config['population']['maxFamilies']
                    or member >= len(self.layout.parasaurolophus_families[family].members)
                    or (self.visitors is not None and family != 0)):
                return False
        if actor == 'triceratops:calf' and self.config['population']['maxVisible'] < 3:
            return False
        if species in GROUND_EXTENTS and self.visitors is not None:
            if self.visitors.species != species:
                return False
        if species == 'plesiosaurus' and not plesiosaurus_pose(
                self.layout.plesiosaurus, float(self._walk_ns / 1_000_000_000),
                float(self._motion_ns / 1_000_000_000), 0, WATER_DEPTH)['visible']:
            return False
        if species == 'diplodocus' and self.diplodocus.state is None:
            return False
        if self.tick - self.reactions.get(actor, -1000) < 180:
            return False
        if actor == 'ankylosaurus':
            pose = self._ankylosaurus_pose(0)
            if pose['sleep'] > 0:
                self.ankylosaurus_wake = (
                    pose['nap_cycle'], self.elapsed_ns, pose['sleep'],
                    1.5 if self.config['motion']['reducedMotion'] else .9)
        self.reactions[actor] = self.tick
        if actor == 'diplodocus':
            self._diplodocus_initial_placement = False
        return True

    def hatch_egg(self, x: float) -> bool:
        """Hatch the nearest egg now without queuing or displacing an animal."""
        nest = self.hatching.nest
        if (self.paused or nest is None or not math.isfinite(x)
                or not self.cast.available(self.config['population']['maxVisible'])):
            return False
        offsets = egg_offsets(nest)
        egg_index = min(range(len(offsets)),
                        key=lambda index: abs(nest.x + offsets[index] - x))
        if not self.hatching.start(egg_index):
            return False
        self.reactions.pop('brachiosaurus:young', None)
        self._update_cast()
        return bool(self.cast.count('brachiosaurus:young'))

    def spawn_meteor(self, x, y):
        """One playful background meteor; repeated clicks never build a queue."""
        if self.meteor is not None:
            return False
        calm = self.config['motion']['reducedMotion']
        self.meteor = (self.elapsed_ns, x, y,
                       6_000_000_000 if calm else 3_500_000_000, calm)
        return True

    def spawn_water_jump(self, x, y):
        """One playful lake leap; concurrent with meteor, never queued."""
        if self.water_jump is not None or not self.cast.available(self.config['population']['maxVisible']):
            return False
        calm = self.config['motion']['reducedMotion']
        cx = max(-2.0, min(110.0, float(x)))
        cy = max(39.0, min(46.0, float(y)))
        self.water_jump = (self.elapsed_ns, cx, cy,
                           3_600_000_000 if calm else 2_200_000_000, calm)
        self._update_cast()
        return True

    def _ground_route(self, key: str, walk_time: float,
                      visitor: VisitorPose | None) -> tuple[float, float, float]:
        """Translate one visitor lifecycle into the ordinary pure-pose inputs."""
        if visitor is not None and self.visitors is not None and (
                visitor['species'] == key
                or key == 'parasaurolophus:0' and visitor['species'] == 'parasaurolophus'):
            return visitor['age'], visitor['phase'], self.visitors.start_x
        return walk_time, self._route_phases[key], self._routes.origin(key)

    def _ankylosaurus_pose(self, reaction):
        time = float(self._motion_ns / 1_000_000_000)
        walk_time = float(self._walk_ns / 1_000_000_000)
        visitor = self.visitors.current(walk_time) if self.visitors is not None else None
        walk_time, phase, start_x = self._ground_route('ankylosaurus', walk_time, visitor)
        wake = None
        if self.ankylosaurus_wake is not None:
            cycle, born, sleep, duration = self.ankylosaurus_wake
            wake = (cycle, (self.elapsed_ns - born) / 1_000_000_000, sleep, duration)
        return ankylosaurus_pose(
            walk_time, phase, start_x, reaction,
            (time + phase) % 6.7 > 6.5, wake)


    def snapshot(self) -> SceneSnapshot:
        motion = self.config['motion']
        t = float(self._motion_ns / 1_000_000_000)
        walk_time = float(self._walk_ns / 1_000_000_000)
        calm = motion['reducedMotion']
        camera_strength = 0 if calm else motion['parallaxStrength']
        def envelope(actor):
            age = (self.tick - self.reactions.get(actor, -1000)) / 60
            return math.sin(age * math.pi / 2)**2 if 0 <= age < 2 else 0
        meteor: MeteorPose | None = None
        if self.meteor is not None:
            born, x, y, duration, meteor_calm = self.meteor
            progress = (self.elapsed_ns - born) / duration
            def position(p):
                return (x + (12 if meteor_calm else 24)*p,
                        y + 48*(.25*p + .75*p*p))
            meteor = {
                'head': position(progress),
                'tail': position(max(0, progress - (.08 if meteor_calm else .16))),
                'fade': min(1, (progress + .03)/.1, (1-progress)/.2),
            }
        water_jump: WaterJumpPose | None = None
        if self.water_jump is not None:
            born, x, y, duration, jump_calm = self.water_jump
            progress = (self.elapsed_ns - born) / duration
            span = 2.6 if jump_calm else 5.2
            lift = (2.2 if jump_calm else 4.2) * 4 * progress * (1 - progress)
            water_jump = {
                'born': born,
                'x': x + (progress - .5) * span,
                'y': y - lift,
                'origin': (x, y),
                'progress': progress,
                'calm': jump_calm,
            }
        visitor = self.visitors.current(walk_time) if self.visitors is not None else None
        family_reactions = {member.id: envelope(member.id)
                            for family in self.layout.parasaurolophus_families
                            for member in family.members}
        rex_age, rex_phase, rex_start = self._ground_route('trex', walk_time, visitor)
        rex = tyrannosaurus_pose(
            rex_age, t, rex_phase, rex_start,
            envelope('trex'), self.layout.trex_blink_phase, calm)
        triceratops, calf = triceratops_poses(
            *self._ground_route('triceratops', walk_time, visitor),
            t, self.layout.triceratops_calf_phase, envelope('triceratops'),
            envelope('triceratops:calf'))
        stego_age, stego_phase, stego_start = self._ground_route('stegosaurus', walk_time, visitor)
        stego_visiting = visitor is not None and visitor['species'] == 'stegosaurus'
        stego_blink = (t + stego_phase) % (6.3 if stego_visiting else 7.1) > (6.1 if stego_visiting else 6.9)
        snapshot: SceneSnapshot = {
            'time': t, 'camera': (math.sin(t * math.tau / 110) * 1.75 * camera_strength, math.sin(t * math.tau / 167) * .21 * camera_strength),
            **rex,
            'brachiosaurus_blink': (t + self.layout.brachiosaurus_blink_phase) % 6.9 > 6.7,
            'brachiosaurus_reaction': envelope('brachiosaurus'),
            'meteor': meteor,
            'water_jump': water_jump,
            'volcano_puff': self.volcano_puffs.current(),
            'weather': self.weather.current(),
            'smoke_lift': self.volcano_puffs.smoke_lift,
            'herbivores': {
                'triceratops': triceratops,
                'stegosaurus': herbivore_pose(
                    stego_age, stego_phase, stego_start, envelope('stegosaurus'), stego_blink),
            },
            'triceratops_calf': calf,
            'ankylosaurus': self._ankylosaurus_pose(envelope('ankylosaurus')),
            'plesiosaurus': plesiosaurus_pose(
                self.layout.plesiosaurus, walk_time, t, envelope('plesiosaurus'), WATER_DEPTH),
            'diplodocus': self.diplodocus.current(t, envelope('diplodocus')),
            'hatching': self.hatching.current(envelope('brachiosaurus:young'), calm),
            'parasaurolophus_families': tuple(
                parasaurolophus_family_pose(
                    family, *self._ground_route(family.id, walk_time, visitor), t, family_reactions)
                for family in self.layout.parasaurolophus_families),
            'pteranodons': tuple(pteranodon_pose(bird, t, .18 if calm else 1,
                                                self._routes.position(bird.id))
                                 for bird in self.layout.pteranodons),
            'pteranodon_flock': self.pteranodon_flocks.current(t, .18 if calm else 1),
            'layout': self.layout,
            'visitor': visitor,
            'visitor_seed': self.visitor_seed if self.visitors is not None else None,
            'admitted': self.cast.members,
        }
        return snapshot


