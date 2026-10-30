"""Seeded world-space scenery, independent of clocks and terminal projection."""

from dataclasses import dataclass
import hashlib
import math
import random

METEOR_DEPTH = .055
WEATHER_DEPTH = .04
WATER_DEPTH = .24
HORIZON_Y = 35

# The browsing adult and its tree share one authored horizontal translation.
FOCAL_OFFSET_X = 8.0
FOCAL_BOUNDS = (44 + FOCAL_OFFSET_X, 7, 102 + FOCAL_OFFSET_X, 55)


@dataclass(frozen=True, slots=True)
class Cloud:
    id: str
    x: float
    y: float
    size: float
    speed: float
    phase: float


@dataclass(frozen=True, slots=True)
class RainDrop:
    id: str
    offset: float
    phase: float
    period: float
    slant: float
    length: float


@dataclass(frozen=True, slots=True)
class Tree:
    id: str
    x: float
    base: float
    height: float
    phase: float


@dataclass(frozen=True, slots=True)
class Fern:
    id: str
    x: float
    y: float
    height: float
    phase: float


@dataclass(frozen=True, slots=True)
class Rock:
    id: str
    x: float
    y: float
    scale: float
    kind: str



@dataclass(frozen=True, slots=True)
class Cycad:
    id: str
    x: float
    y: float
    height: float
    phase: float


@dataclass(frozen=True, slots=True)
class Flower:
    id: str
    x: float
    y: float
    height: float
    phase: float
    tint: str


@dataclass(frozen=True, slots=True)
class LilyPad:
    id: str
    x: float
    y: float
    radius: float
    phase: float
    bloom: bool


@dataclass(frozen=True, slots=True)
class Nest:
    id: str
    x: float
    y: float
    radius: float
    eggs: int

@dataclass(frozen=True, slots=True)
class Ripple:
    id: str
    x: float
    y: float
    width: float
    speed: float
    phase: float


@dataclass(frozen=True, slots=True)
class Pteranodon:
    id: str
    start_x: float
    y: float
    span: float
    depth: float
    speed: float
    phase: float


@dataclass(frozen=True, slots=True)
class Plesiosaurus:
    id: str
    x: float
    water_y: float
    phase: float
    look_phase: float


@dataclass(frozen=True, slots=True)
class Diplodocus:
    id: str
    shore_x: float
    foot_y: float
    depth: float
    phase: float
    look_phase: float
    blink_phase: float
    visit_seed: int


@dataclass(frozen=True, slots=True)
class ParasaurolophusMember:
    id: str
    scale: float
    offset: float
    blink_phase: float


@dataclass(frozen=True, slots=True)
class ParasaurolophusFamily:
    id: str
    start_x: float
    phase: float
    members: tuple[ParasaurolophusMember, ...]


@dataclass(frozen=True, slots=True)
class ValleyLayout:
    clouds: tuple[Cloud, ...]
    trees: tuple[Tree, ...]
    cycads: tuple[Cycad, ...]
    ferns: tuple[Fern, ...]
    rocks: tuple[Rock, ...]
    flowers: tuple[Flower, ...]
    lily_pads: tuple[LilyPad, ...]
    nest: Nest | None
    ripples: tuple[Ripple, ...]
    pteranodons: tuple[Pteranodon, ...]
    pteranodon_flock: tuple[Pteranodon, ...]
    pteranodon_visit_seed: int
    hatching_seed: int
    hatching_phase: float
    volcano_puff_seed: int
    rain_drops: tuple[RainDrop, ...]
    weather_seed: int
    parasaurolophus_families: tuple[ParasaurolophusFamily, ...]
    plesiosaurus: Plesiosaurus
    diplodocus: Diplodocus
    wind_phase: float
    smoke_phase: float
    brachiosaurus_phase: float
    trex_phase: float
    triceratops_phase: float
    triceratops_calf_phase: float
    stegosaurus_phase: float
    ankylosaurus_phase: float
    brachiosaurus_blink_phase: float
    trex_blink_phase: float
    trex_start: float
    water_bounds: tuple[float, float, float, float]
    walking_bounds: tuple[float, float, float, float]
    focal_bounds: tuple[float, float, float, float]


def _rng(seed, namespace):
    # Neither Python's salted hash nor the process-wide random stream participates.
    key = f"omarchasaurus-layout-v1:{seed}:{namespace}".encode("ascii")
    return random.Random(int.from_bytes(hashlib.sha256(key).digest(), "big"))


def _phase(seed, namespace):
    return _rng(seed, namespace).uniform(0.0, math.tau)


def _select(candidates, density, rng):
    """Activate floor(default_count * density) stable, spatially spread poses.

    Candidates are arranged in neighboring pairs. The first activation stratum
    takes one randomly chosen member of every pair, and the second takes its
    partner. Separate shuffling within each stratum gives every candidate a
    fixed activation rank without moving or regenerating any candidate.
    """
    first, second = [], []
    for index in range(0, len(candidates), 2):
        pair = [index, index + 1]
        rng.shuffle(pair)
        first.append(pair[0])
        second.append(pair[1])
    rng.shuffle(first)
    rng.shuffle(second)
    count = min(len(candidates), max(0, int(density * (len(candidates) // 2))))
    active = set((first + second)[:count])
    return tuple(candidate for index, candidate in enumerate(candidates)
                 if index in active)


def _pteranodon_candidates(seed):
    pteranodons = []
    for index, (x, y, span, depth, speed) in enumerate(
            ((13, 13, 4.0, .07, .42), (44, 8, 3.0, .12, .53),
             (61, 23, 3.3, .28, .64))):
        rng = _rng(seed, f"pteranodon:{index}")
        pteranodons.append(Pteranodon(
            f"pteranodon:{index}", x + rng.uniform(-1, 1),
            y + rng.uniform(-.6, .6), span, depth,
            speed * rng.uniform(.9, 1.1), rng.uniform(0, math.tau)))
    return tuple(pteranodons)


def _pteranodon_flock_candidates(seed):
    # Ordered V; smaller wings keep even the same-column partners separated.
    return tuple(Pteranodon(
        f"pteranodon:{index + 3}", x, 16 + y, 2.1, .18, 1.2,
        _phase(seed, f"pteranodon:flock:{index}:flight"))
        for index, (x, y) in enumerate(
            ((0, 0), (-11, -4.5), (-11, 4.5), (-22, -9), (-22, 9))))


def _parasaurolophus_candidates(seed):
    families = []
    for index in range(2):
        identity = f"parasaurolophus:{index}"
        rng = _rng(seed, identity)
        scales = (1.0, .60, .72, .50)[:rng.randint(2, 4)]
        members = []
        offset = 0.0
        for member_index, scale in enumerate(scales):
            if member_index:
                # Full conservative silhouettes plus a land-path gap.
                offset -= 15 * (scales[member_index - 1] + scale) + 3
            member_id = f"{identity}:{member_index}"
            members.append(ParasaurolophusMember(
                member_id, scale, offset, _phase(seed, member_id + ":blink")))
        families.append(ParasaurolophusFamily(
            identity, 80 + index * 300 + rng.uniform(-1, 1),
            _phase(seed, identity + ":gait"), tuple(members)))
    return tuple(families)


def _rain_candidates(seed):
    drops = []
    for index in range(48):
        rng = _rng(seed, f"weather:rain:{index}")
        drops.append(RainDrop(
            f"rain:{index}", rng.uniform(0, 1), rng.uniform(0, 1),
            rng.uniform(3.2, 4.6), rng.uniform(-.15, .2),
            rng.uniform(.5, 1)))
    return tuple(drops)


def generate_layout(seed: int, scenery) -> ValleyLayout:
    """Return immutable poses for a seed and resolved scenery density settings.

    Every category builds its complete bounded candidate pool before selecting
    density. Pose and activation streams are separate, and ambient actors each
    have their own namespaces, so changing a density cannot retime the valley.
    """
    rng = _rng(seed, "clouds")
    clouds = tuple(
        Cloud(f"cloud:{index}",
              -15 + (index + .5) * (140 / 6) + rng.uniform(-5, 5),
              rng.uniform(4, 9), rng.uniform(6, 10),
              rng.uniform(.06, .18), rng.uniform(0, math.tau))
        for index in range(6)
    )

    rng = _rng(seed, "trees")
    # Bin spacing is 6.65; +/-1 jitter leaves at least 4.65 between trunks.
    trees = tuple(
        Tree(f"tree:{index}",
             -8 + (index + .5) * (133 / 20) + rng.uniform(-1, 1),
             rng.uniform(35.5, 36.5), rng.uniform(6, 10),
             rng.uniform(0, math.tau))
        for index in range(20)
    )

    rng = _rng(seed, "ferns")
    # Candidate positions reserve the complete nest (including raster margins)
    # and the relocated adult's feet before density activation. Keeping the
    # pools intact preserves candidate IDs, counts and density-independent poses.
    ferns = tuple(
        Fern(f"fern:{index}", x + rng.uniform(-1, 1),
             rng.uniform(57.8, 58.8), rng.uniform(3, 5),
             rng.uniform(0, math.tau))
        for index, x in enumerate((-2, 6, 15, 24, 31, 97, 108, 119))
    )

    rng = _rng(seed, "rocks")
    # Pair activation retains a left boulder and right pebble at normal density.
    # Even the tallest boulder crown is >= 57 - 5.8*1.1 = 50.62.
    rocks = tuple(
        Rock(f"rock:{index}", x + rng.uniform(-1, 1),
             rng.uniform(57, 58), rng.uniform(.7, 1.1),
             "boulder" if index < 2 else "pebble")
        for index, x in enumerate((8, 24, 103, 119))
    )

    rng = _rng(seed, "cycads")
    cycads = tuple(
        Cycad(f"cycad:{index}", x + rng.uniform(-1, 1),
              rng.uniform(55.4, 56.4), rng.uniform(3.2, 4.4),
              rng.uniform(0, math.tau))
        for index, x in enumerate((3, 19, 31, 54, 96, 114))
    )

    rng = _rng(seed, "flowers")
    flowers = tuple(
        Flower(f"flower:{index}", x + rng.uniform(-.8, .8),
               rng.uniform(56.6, 58.2), rng.uniform(1.4, 2.2),
               rng.uniform(0, math.tau),
               "warm" if index % 2 == 0 else "cool")
        for index, x in enumerate((-4, 4, 11, 21, 29, 36, 51, 85, 92, 100, 111, 121))
    )

    rng = _rng(seed, "lily_pads")
    lily_pads = tuple(
        LilyPad(f"lily_pad:{index}", x + rng.uniform(-1.2, 1.2),
                rng.uniform(40.2, 45.2), rng.uniform(1.2, 2.0),
                rng.uniform(0, math.tau), index % 3 == 0)
        for index, x in enumerate((0, 9, 18, 28, 38, 49, 61, 73, 85, 97, 106, 112))
    )

    rng = _rng(seed, "nest")
    nest_candidate = Nest(
        "nest:0",
        43.5 + rng.uniform(-.8, .8),
        56.0 + rng.uniform(-.3, .3),
        rng.uniform(2.6, 3.1),
        rng.choice((3, 4)),
    )

    rng = _rng(seed, "ripples")
    # The entire curve stays inside water, including +/- .65 animated drift,
    # its full width, and the -.25/+.3 vertical Bezier control offsets.
    ripples = tuple(
        Ripple(f"ripple:{index}", rng.uniform(-4, 114),
               rng.uniform(38.2, 46.5), rng.uniform(.9, 2.5),
               rng.uniform(.32, .5), rng.uniform(0, math.tau))
        for index in range(28)
    )

    rng = _rng(seed, "plesiosaurus")
    plesiosaurus = Plesiosaurus(
        "plesiosaurus", 35 + rng.uniform(-2, 2),
        42.5 + rng.uniform(-.25, .25), rng.uniform(4, 12),
        _phase(seed, "plesiosaurus:look"))

    diplodocus = Diplodocus(
        "diplodocus", 65 + _rng(seed, "diplodocus:shore").uniform(-1, 1),
        36.5, .21, _phase(seed, "diplodocus:gait"),
        _phase(seed, "diplodocus:look"), _phase(seed, "diplodocus:blink"),
        _rng(seed, "diplodocus:visits").getrandbits(256))

    return ValleyLayout(
        clouds=_select(clouds, scenery.get("cloudDensity", 1),
                       _rng(seed, "clouds:activation")),
        trees=_select(trees, scenery.get("treeDensity", 1),
                      _rng(seed, "trees:activation")),
        cycads=_select(cycads, scenery.get("cycadDensity", 1),
                       _rng(seed, "cycads:activation")),
        ferns=_select(ferns, scenery.get("fernDensity", 1),
                      _rng(seed, "ferns:activation")),
        rocks=_select(rocks, scenery.get("rockDensity", 1),
                      _rng(seed, "rocks:activation")),
        flowers=_select(flowers, scenery.get("flowerDensity", 1),
                        _rng(seed, "flowers:activation")),
        lily_pads=_select(lily_pads, scenery.get("lilyPadDensity", 1),
                          _rng(seed, "lily_pads:activation")),
        nest=nest_candidate if scenery.get("nestEnabled", True) else None,
        ripples=ripples,
        pteranodons=_pteranodon_candidates(seed),
        pteranodon_flock=_pteranodon_flock_candidates(seed),
        pteranodon_visit_seed=_rng(seed, "pteranodon:flock:visits").getrandbits(256),
        hatching_seed=_rng(seed, "brachiosaurus:young:visits").getrandbits(256),
        hatching_phase=_phase(seed, "brachiosaurus:young:gait"),
        volcano_puff_seed=_rng(seed, "volcano:puffs").getrandbits(256),
        rain_drops=_rain_candidates(seed),
        weather_seed=_rng(seed, "weather:intervals").getrandbits(256),
        parasaurolophus_families=_parasaurolophus_candidates(seed),
        plesiosaurus=plesiosaurus,
        diplodocus=diplodocus,
        wind_phase=_phase(seed, "wind"),
        smoke_phase=_phase(seed, "smoke"),
        brachiosaurus_phase=_phase(seed, "brachiosaurus"),
        trex_phase=_phase(seed, "trex"),
        triceratops_phase=_phase(seed, "triceratops"),
        triceratops_calf_phase=_phase(seed, "triceratops:calf"),
        stegosaurus_phase=_phase(seed, "stegosaurus"),
        ankylosaurus_phase=_phase(seed, "ankylosaurus"),
        brachiosaurus_blink_phase=_phase(seed, "brachiosaurus:blink"),
        trex_blink_phase=_phase(seed, "trex:blink"),
        trex_start=_rng(seed, "trex:start").uniform(-2, 2),
        water_bounds=(-8, 37, 119, 48),
        walking_bounds=(-200, 48, 400, 55),
        focal_bounds=FOCAL_BOUNDS,
    )
