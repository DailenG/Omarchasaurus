"""Pure, one-shot valley choices; callers decide when to apply sparse intent."""
from __future__ import annotations

import copy
import random
from typing import Any

from configuration import settings
from population import GROUND_EXTENTS


DENSITIES = (
    'treeDensity', 'cycadDensity', 'fernDensity', 'rockDensity',
    'flowerDensity', 'lilyPadDensity', 'cloudDensity',
)


def randomize_document(document: dict[str, Any], seed: int) -> dict[str, Any]:
    """Return validated sparse choices without changing saved or running settings.

    Palette, scene seed, motion/accessibility, population ceilings, and integration
    choices stay untouched, including their absence from a sparse input. A local
    stream makes a supplied seed reproducible without touching simulation RNGs.
    """
    resolved = settings(document)
    if not isinstance(document, dict):
        raise ValueError('settings: expected an object')
    result = copy.deepcopy(document)
    rng = random.Random(seed)
    scenery = result.setdefault('scenery', {})
    densities = [rng.randrange(9) for _ in DENSITIES]
    # Quarter steps cover 0..2, with a shared density budget of nine across all
    # seven layers. Thin one shuffled layer at a time to avoid maximal clutter.
    thinning = list(range(len(densities)))
    rng.shuffle(thinning)
    while sum(densities) > 36:
        for index in thinning:
            if densities[index] and sum(densities) > 36:
                densities[index] -= 1
    scenery.update((key, value / 4) for key, value in zip(DENSITIES, densities))
    scenery['nestEnabled'] = bool(rng.getrandbits(1))

    animals = result.setdefault('animals', {})
    for key in resolved['animals']:
        animals[key] = bool(rng.getrandbits(1))
    maximum = resolved['population']['maxVisible']
    eligible = [species for species in GROUND_EXTENTS
                if species != 'parasaurolophus'
                or maximum >= 3 and resolved['population']['maxFamilies'] > 0]
    selected = set(rng.sample(eligible, rng.randint(2, len(eligible)))) if maximum > 1 else set()
    for species in GROUND_EXTENTS:
        animals[species + 'Enabled'] = species in selected
    # A permanent drinker must not monopolize the only optional visitor seat.
    # Residency remains an independent choice even when that animal is disabled.
    if maximum == 2 and animals['diplodocusResident']:
        animals['diplodocusEnabled'] = False
    result.setdefault('population', {})['randomVisitors'] = True
    settings(result)
    return result
