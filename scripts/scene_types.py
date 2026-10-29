"""Static contracts for scene snapshots, occupancy and continuous routes."""
from __future__ import annotations
from collections.abc import Hashable
from fractions import Fraction
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from layout import ValleyLayout

Nanoseconds = int | Fraction
Scalar = float | Fraction
Point = tuple[Scalar, Scalar]
HorizontalBounds = tuple[float, float]
ViewportBounds = tuple[float, float, float, float]
ActorBounds = tuple[float, float, float, float, float]


class CastMember(TypedDict):
    id: str
    bounds: ActorBounds


class CastGroup(TypedDict):
    key: str
    token: Hashable
    members: tuple[CastMember, ...]
    minimum: int
    active: bool
    entry: bool | None


class _RouteOptions(TypedDict, total=False):
    lane: str


class RouteDescriptor(_RouteOptions):
    key: str
    start_x: float
    rear: float
    nose: float
    depth: float
    minimum_span: float


class RouteRecord(TypedDict):
    descriptor: RouteDescriptor
    entry: float
    span: float
    base_shift: float
    wraps: int
    pending: float | None
    target: HorizontalBounds | None
    x: float


class WalkingPose(TypedDict):
    x: float
    phase: float
    stride: float
    reaction: float
    blink: bool


class HerbivorePose(WalkingPose):
    graze: float


class _TriceratopsOptions(TypedDict, total=False):
    state: str


class TriceratopsPose(HerbivorePose, _TriceratopsOptions):
    id: str
    scale: float
    foot_y: float
    juvenile: bool
    calf_near: float
    nuzzle: float


class AnkylosaurusPose(WalkingPose):
    sleep: float
    state: str
    nap_cycle: int


class FamilyMemberPose(WalkingPose):
    id: str
    scale: float
    foot_y: float
    drink: float
    state: str


class FamilyPose(TypedDict):
    id: str
    members: tuple[FamilyMemberPose, ...]


class PlesiosaurusPose(TypedDict):
    id: str
    x: float
    water_y: float
    body_y: float
    emergence: float
    look: float
    reaction: float
    blink: bool
    state: str
    cycle: int
    visible: bool
    depth: float


class DiplodocusPose(WalkingPose):
    id: str
    foot_y: float
    depth: float
    drink: float
    look: float
    state: str
    generation: int


class HatchingPose(WalkingPose):
    id: str
    generation: int
    state: str
    egg_index: int
    egg_x: float
    egg_y: float
    wobble: float
    crack: float
    emerge: float
    reset: float
    foot_y: float
    depth: float


class PteranodonPose(TypedDict):
    id: str
    depth: float
    span: float
    x: float
    y: float
    tip_y: float
    bank: float


class PteranodonFlockPose(TypedDict):
    generation: int
    members: tuple[PteranodonPose, ...]


class VolcanoPuffPose(TypedDict):
    generation: int
    progress: float
    strength: float
    calm: bool


class RainStreakPose(TypedDict):
    id: str
    cycle: int
    head: Point
    tail: Point


class WeatherPose(TypedDict):
    generation: int
    state: str
    age: float
    calm: bool
    cloud_x: float
    cloud_y: float
    cloud_width: float
    cloud_height: float
    cloud_strength: float
    rain_strength: float
    rainbow_strength: float
    rain: tuple[RainStreakPose, ...]


class MeteorPose(TypedDict):
    head: Point
    tail: Point
    fade: float


class WaterJumpPose(TypedDict):
    born: Nanoseconds
    x: float
    y: float
    origin: Point
    progress: Scalar
    calm: bool


class VisitorPose(TypedDict):
    species: str
    generation: int
    age: float
    phase: float
    x: float


class TyrannosaurusPose(TypedDict):
    trex_x: float
    phase: float
    trex_blink: bool
    trex_reaction: float
    trex_stride: float
    trex_look: float
    trex_roar: float
    trex_sit: float
    trex_state: str


class Herbivores(TypedDict):
    triceratops: TriceratopsPose
    stegosaurus: HerbivorePose


class SceneSnapshot(TyrannosaurusPose):
    time: float
    camera: Point
    brachiosaurus_blink: bool
    brachiosaurus_reaction: float
    meteor: MeteorPose | None
    water_jump: WaterJumpPose | None
    volcano_puff: VolcanoPuffPose | None
    weather: WeatherPose | None
    smoke_lift: float
    herbivores: Herbivores
    triceratops_calf: TriceratopsPose
    ankylosaurus: AnkylosaurusPose
    plesiosaurus: PlesiosaurusPose
    diplodocus: DiplodocusPose | None
    hatching: HatchingPose | None
    parasaurolophus_families: tuple[FamilyPose, ...]
    pteranodons: tuple[PteranodonPose, ...]
    pteranodon_flock: PteranodonFlockPose | None
    layout: ValleyLayout
    visitor: VisitorPose | None
    visitor_seed: int | None
    admitted: tuple[str, ...]
