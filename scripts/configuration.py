"""Strict sparse settings resolution, independent of rendering and terminal I/O."""
from __future__ import annotations

import copy
import math
from pathlib import Path
import os
from safe_io import Directory, MAX_JSON_BYTES, parse_json, read_json
from typing import Literal, TypedDict


class MotionSettings(TypedDict):
    parallaxStrength: float
    speed: float
    reducedMotion: bool


class ScenerySettings(TypedDict):
    treeDensity: float
    cycadDensity: float
    fernDensity: float
    rockDensity: float
    flowerDensity: float
    lilyPadDensity: float
    cloudDensity: float
    nestEnabled: bool


class AnimalSettings(TypedDict):
    trexEnabled: bool
    triceratopsEnabled: bool
    stegosaurusEnabled: bool
    ankylosaurusEnabled: bool
    parasaurolophusEnabled: bool
    plesiosaurusEnabled: bool
    diplodocusEnabled: bool
    diplodocusResident: bool
    pteranodonEnabled: bool


class PopulationSettings(TypedDict):
    maxVisible: int
    maxFamilies: int
    randomVisitors: bool


class SoundSettings(TypedDict):
    enabled: bool
    volume: int


class IntegrationSettings(TypedDict):
    idleEnabled: bool
    exitOnPointerMotion: bool


class Settings(TypedDict):
    schemaVersion: int
    seed: int
    preset: Literal['morning', 'dusk']
    motion: MotionSettings
    scenery: ScenerySettings
    animals: AnimalSettings
    population: PopulationSettings
    sound: SoundSettings
    integration: IntegrationSettings


DEFAULTS: Settings = {
    'schemaVersion': 1,
    'seed': 42,
    'preset': 'morning',
    'motion': {'parallaxStrength': 1.0, 'speed': 1.0, 'reducedMotion': False},
    'scenery': {
        'treeDensity': 1.0,
        'cycadDensity': 1.0,
        'fernDensity': 1.0,
        'rockDensity': 1.0,
        'flowerDensity': 1.0,
        'lilyPadDensity': 1.0,
        'cloudDensity': 1.0,
        'nestEnabled': True,
    },
    'animals': {
        'trexEnabled': True,
        'triceratopsEnabled': True,
        'stegosaurusEnabled': True,
        'ankylosaurusEnabled': True,
        'parasaurolophusEnabled': True,
        'plesiosaurusEnabled': True,
        'diplodocusEnabled': True,
        'diplodocusResident': False,
        'pteranodonEnabled': True,
    },
    'population': {'maxVisible': 8, 'maxFamilies': 1, 'randomVisitors': False},
    'sound': {'enabled': False, 'volume': 20},
    'integration': {'idleEnabled': False, 'exitOnPointerMotion': True},
}

PALETTES = ('morning', 'dusk')

_LIMITS = {
    'schemaVersion': (1, 1),
    'seed': (0, 2**53 - 1),
    'population.maxVisible': (1, 128),
    'population.maxFamilies': (0, 2),
    'motion.parallaxStrength': (0, 2),
    'motion.speed': (.25, 2),
    'scenery.treeDensity': (0, 2),
    'scenery.cycadDensity': (0, 2),
    'scenery.fernDensity': (0, 2),
    'scenery.rockDensity': (0, 2),
    'scenery.flowerDensity': (0, 2),
    'scenery.lilyPadDensity': (0, 2),
    'scenery.cloudDensity': (0, 2),
    'sound.volume': (0, 100),
}
_MAX_SETTINGS_BYTES = MAX_JSON_BYTES


def _validate(patch, schema, trail=''):
    if not isinstance(patch, dict):
        raise ValueError(f'{trail or "settings"}: expected an object')
    for key, value in patch.items():
        path = f'{trail}.{key}' if trail else key
        if key not in schema:
            raise ValueError(f'{path}: unknown setting')
        expected = schema[key]
        if isinstance(expected, dict):
            _validate(value, expected, path)
        elif isinstance(expected, bool):
            if not isinstance(value, bool):
                raise ValueError(f'{path}: expected true or false')
            if value and path in ('sound.enabled', 'integration.idleEnabled'):
                raise ValueError(f'{path}: this feature is not implemented')
        elif isinstance(expected, (int, float)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f'{path}: expected a number')
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f'{path}: expected a finite number')
            if path in ('seed', 'schemaVersion', 'population.maxVisible',
                        'population.maxFamilies') and not isinstance(value, int):
                raise ValueError(f'{path}: expected an integer')
            low, high = _LIMITS[path]
            if not low <= value <= high:
                raise ValueError(f'{path}: expected {low}..{high}')
        elif not isinstance(value, str):
            raise ValueError(f'{path}: expected text')
        elif path == 'preset' and value not in PALETTES:
            raise ValueError('preset: expected morning or dusk')


def _merge(result, patch):
    for key, value in patch.items():
        if isinstance(value, dict):
            _merge(result[key], value)
        else:
            result[key] = value


def settings(document=None, overrides=None) -> Settings:
    """Resolve defaults < document < explicit overrides; palettes are color only.

    Inputs stay sparse and untouched. Validate each layer independently so an
    override cannot conceal an invalid configuration file.
    """
    document = {} if document is None else document
    overrides = {} if overrides is None else overrides
    _validate(document, DEFAULTS)
    _validate(overrides, DEFAULTS)
    result = copy.deepcopy(DEFAULTS)
    _merge(result, document)
    _merge(result, overrides)
    return result


def config_path():
    base = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    if not base.is_absolute():
        raise ValueError('XDG_CONFIG_HOME must be absolute')
    return base / 'omarchasaurus/settings.json'


def parse_document(raw):
    document = parse_json(raw, _MAX_SETTINGS_BYTES)
    if not isinstance(document, dict):
        raise ValueError('settings: expected an object')
    settings(document)
    return document


def load_document(path):
    """Read sparse intent through held, no-follow parent and file descriptors."""
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        with Directory.open(path.parent) as directory:
            document = read_json(directory.fd, path.name, blank=True, missing=True)
    except FileNotFoundError:
        return {}
    if not isinstance(document, dict):
        raise ValueError('settings: expected an object')
    settings(document)
    return document


def load_settings(path, overrides=None) -> Settings:
    """Load and resolve sparse settings; missing or blank files use defaults."""
    return settings(load_document(path), overrides)
