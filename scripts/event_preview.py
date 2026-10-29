"""Session-only event previews; importing the event names never loads rendering."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from configuration import Settings
    from engine import World
    from scene_types import Nanoseconds, ViewportBounds

EVENTS = ('shower', 'rainbow', 'hatching', 'flock', 'diplodocus', 'volcano')


def preview_settings(document: dict[str, Any] | None, overrides: dict[str, Any] | None,
                     event: str | None = None) -> Settings:
    """Resolve normal intent, then protect a test's prerequisites without writes."""
    from configuration import settings

    config = settings(document, overrides)
    if event is None:
        return config
    if event not in EVENTS:
        raise ValueError(f'unknown test event: {event}')
    # Brachiosaurus always occupies one seat. Flocks share their enable switch
    # with three resident flyers; reserve seats for those and the full V of five.
    seats = 9 if event == 'flock' else 2 if event in ('hatching', 'diplodocus') else 1
    patch: dict[str, Any] = {
        'animals': {key: False for key in config['animals']},
        'population': {
            'randomVisitors': False,
            'maxFamilies': 0,
            'maxVisible': max(seats, config['population']['maxVisible']),
        },
        'scenery': {'nestEnabled': event == 'hatching'},
    }
    if event == 'flock':
        patch['animals']['pteranodonEnabled'] = True
    elif event == 'diplodocus':
        patch['animals']['diplodocusEnabled'] = True
        patch['animals']['diplodocusResident'] = False
    return settings(config, patch)


def event_world(config: Settings, event: str, bounds: ViewportBounds) -> World:
    """Seek before the real first deadline, then retain normal live World clocks.

    The initial Canvas supplies bounds before any live admission. Historical
    construction ends before the chosen event: in particular it cannot fabricate
    a hatched animal without a Cast seat. Rainbow alone plays forward to its
    visible phase, using the same bounded live steps as an interactive preview.
    """
    from engine import World

    if event not in EVENTS:
        raise ValueError(f'unknown test event: {event}')
    probe = World(config)
    deadline: Nanoseconds | None
    if event in ('shower', 'rainbow'):
        deadline = probe.weather.deadline
    elif event == 'hatching':
        deadline = probe.hatching.deadline
    elif event == 'flock':
        deadline = probe.pteranodon_flocks.deadline
    elif event == 'diplodocus':
        deadline = probe.diplodocus.deadline
    else:
        deadline = probe.volcano_puffs.deadline
    assert deadline is not None, "event preview requires its resolved session settings"
    world = World(config, elapsed_ns=max(0, int(deadline) - 1_000_000_000))
    world.set_viewport(bounds)
    if event == 'rainbow':
        # At full fade-in the actual weather controller supplies a visible arc.
        motion_age = 50 if config['motion']['reducedMotion'] else 34
        from fractions import Fraction
        duration = 1_000_000_000 + int(Fraction(motion_age * 1_000_000_000)
                                     / Fraction(str(config['motion']['speed'])))
        end = world.elapsed_ns + duration
        while world.elapsed_ns < end:
            world.advance(min(250_000_000, end - world.elapsed_ns))
    return world
