"""Continuous right-moving routes whose wraps are always outside the viewport."""
from __future__ import annotations
from collections.abc import Iterable, Mapping, Sequence
from scene_types import HorizontalBounds, RouteDescriptor, RouteRecord
import math


class Routes:
    def __init__(self, descriptors: Iterable[RouteDescriptor],
                 distances: Mapping[str, float], bounds: HorizontalBounds) -> None:
        descriptors = tuple(descriptors)
        self._bounds = bounds
        self._records: dict[str, RouteRecord] = {}
        self._lanes: dict[str, list[str]] = {}
        geometry = self._geometries(descriptors, bounds)
        for descriptor in descriptors:
            key = descriptor['key']
            entry, span = geometry[key]
            distance = distances[key]
            wraps = math.floor((descriptor['start_x'] + distance - entry) / span)
            self._records[key] = dict(
                descriptor=descriptor, entry=entry, span=span, base_shift=0.0,
                wraps=wraps, pending=None, target=None,
                x=descriptor['start_x'] + distance - wraps * span)
            lane = descriptor.get('lane')
            if lane is not None:
                self._lanes.setdefault(lane, []).append(key)

    @staticmethod
    def _geometries(descriptors: Sequence[RouteDescriptor],
                    bounds: HorizontalBounds) -> dict[str, HorizontalBounds]:
        geometry: dict[str, HorizontalBounds] = {}
        lane_spans: dict[str, float] = {}
        for descriptor in descriptors:
            guard = 3.5 * descriptor['depth'] + 1
            entry = bounds[0] - descriptor['nose'] - guard
            exit_ = bounds[1] - descriptor['rear'] + guard
            span = max(descriptor['minimum_span'], exit_ - entry)
            geometry[descriptor['key']] = (entry, span)
            lane = descriptor.get('lane')
            if lane is not None:
                lane_spans[lane] = max(lane_spans.get(lane, 0), span)
        for descriptor in descriptors:
            lane = descriptor.get('lane')
            if lane is not None:
                key = descriptor['key']
                geometry[key] = (geometry[key][0], lane_spans[lane])
        return geometry

    def origin(self, key: str) -> float:
        record = self._records[key]
        return (record['descriptor']['start_x'] - record['base_shift']
                - record['wraps'] * record['span'])

    def position(self, key: str) -> float:
        return self._records[key]['x']

    def set_viewport(self, bounds: HorizontalBounds, distances: Mapping[str, float]) -> None:
        if bounds == self._bounds:
            return
        self._bounds = bounds
        geometry = self._geometries(
            tuple(record['descriptor'] for record in self._records.values()), bounds)
        for key, record in self._records.items():
            entry, span = geometry[key]
            if record['descriptor'].get('lane') is not None and span != record['span']:
                # Changing only one cohort's period would make it catch another.
                # Drain this lane rightward, then change its period while hidden.
                record['target'] = entry, span
                record['pending'] = None
                continue
            record['base_shift'] += record['wraps'] * record['span']
            record['entry'] = entry
            record['span'] = span
            record['wraps'] = 0
            record['target'] = None
            record['pending'] = distances[key] if record['x'] >= entry + span else None


    def advance(self, distances: Mapping[str, float]) -> None:
        for key, record in self._records.items():
            start = record['descriptor']['start_x']
            if record['pending'] is not None:
                if record['descriptor'].get('lane') is not None:
                    record['wraps'] = math.ceil(
                        (start + distances[key] - record['base_shift'] - record['entry'])
                        / record['span'])
                else:
                    record['base_shift'] = start + record['pending'] - record['entry']
                    record['wraps'] = 0
                record['pending'] = None
            x = start + distances[key] - record['base_shift'] - record['wraps'] * record['span']
            exit_ = record['entry'] + record['span']
            if record['target'] is None and x >= exit_:
                count = math.floor((x - exit_) / record['span']) + 1
                record['wraps'] += count
                x = start + distances[key] - record['base_shift'] - record['wraps'] * record['span']
            record['x'] = x
        for keys in self._lanes.values():
            if self._records[keys[0]]['target'] is None:
                continue
            if not all(self._records[key]['x'] + self._records[key]['descriptor']['rear']
                       > self._bounds[1] + 3.5 * self._records[key]['descriptor']['depth'] + 1
                       for key in keys):
                continue
            for key in keys:
                record = self._records[key]
                target = record['target']
                assert target is not None, 'every cohort in a draining lane has a target'
                entry, span = target
                start = record['descriptor']['start_x']
                wraps = math.ceil((start + distances[key] - entry) / span)
                record['entry'] = entry
                record['span'] = span
                record['base_shift'] = 0.0
                record['wraps'] = wraps
                record['pending'] = None
                record['target'] = None
                record['x'] = start + distances[key] - wraps * span
