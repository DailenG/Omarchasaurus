"""Original, scalable ASCII stroke artwork for the terminal valley.

All geometry is in the shared 110 by 60 world, never terminal pixel space.
The selectable cast includes Tyrannosaurus rex, Triceratops, Stegosaurus,
Ankylosaurus and Parasaurolophus families around the mandatory Brachiosaurus.
Pteranodon are pterosaurs; Plesiosaurus is a marine reptile, not a dinosaur.
"""
from __future__ import annotations

import math
from cast import cast_groups
from canvas import Canvas
from configuration import Settings
from scene_types import SceneSnapshot
from layout import FOCAL_OFFSET_X, HORIZON_Y, METEOR_DEPTH, WATER_DEPTH, WEATHER_DEPTH
from hatching import NEST_DEPTH, egg_offsets, YOUNG_HEIGHT
from population import (ANKYLOSAURUS_DEPTH, ANKYLOSAURUS_FOOT_Y,
                        PARASAUROLOPHUS_DEPTH)


_PALETTES = {
    "morning": {
        "cloud": (84, 122, 135),
        "cloud_light": (125, 157, 162),
        "rain": (99, 142, 154),
        "rainbow_red": (160, 100, 103),
        "rainbow_orange": (169, 124, 91),
        "rainbow_yellow": (167, 151, 99),
        "rainbow_green": (110, 152, 112),
        "rainbow_blue": (99, 138, 167),
        "rainbow_indigo": (117, 115, 160),
        "rainbow_violet": (151, 113, 159),
        "mountain": (63, 91, 111),
        "snow": (151, 181, 185),
        "volcano": (94, 103, 119),
        "smoke": (87, 104, 118),
        "far_tree": (38, 83, 76),
        "shore": (59, 106, 96),
        "water": (44, 130, 140),
        "water_light": (83, 173, 169),
        "trunk": (137, 118, 77),
        "tree": (79, 146, 97),
        "tree_light": (139, 180, 105),
        "brachiosaurus": (153, 189, 119),
        "brachiosaurus_shade": (83, 130, 88),
        "brachiosaurus_light": (199, 214, 145),
        "diplodocus": (156, 173, 146),
        "diplodocus_shade": (87, 119, 109),
        "diplodocus_light": (205, 209, 168),
        "trex": (210, 162, 99),
        "trex_shade": (142, 108, 73),
        "trex_light": (239, 202, 143),
        "eye": (236, 232, 188),
        "pteranodon": (151, 139, 165),
        "triceratops": (114, 173, 175),
        "triceratops_shade": (65, 118, 130),
        "triceratops_juvenile": (135, 189, 181),
        "triceratops_juvenile_shade": (77, 130, 136),
        "stegosaurus": (165, 168, 107),
        "stegosaurus_shade": (109, 125, 75),
        "ankylosaurus": (154, 151, 112),
        "ankylosaurus_shade": (94, 111, 81),
        "parasaurolophus": (189, 165, 119),
        "parasaurolophus_shade": (126, 117, 82),
        "parasaurolophus_light": (223, 202, 147),
        "plesiosaurus": (119, 186, 178),
        "plesiosaurus_shade": (65, 130, 137),
        "plesiosaurus_light": (188, 220, 192),
        "armor": (208, 181, 126),
        "plates": (203, 143, 121),
        "ground": (62, 94, 74),
        "rock": (116, 133, 133),
        "rock_shade": (68, 90, 94),
        "fern": (80, 143, 100),
        "fern_light": (118, 173, 110),
        "cycad_trunk": (124, 102, 71),
        "lily_pad": (66, 148, 114),
        "flower_warm": (224, 154, 112),
        "flower_cool": (196, 152, 206),
        "nest": (146, 121, 82),
        "egg": (226, 220, 188),
    },
    "dusk": {
        "cloud": (105, 97, 131),
        "cloud_light": (158, 126, 154),
        "rain": (119, 133, 162),
        "rainbow_red": (165, 99, 115),
        "rainbow_orange": (174, 120, 101),
        "rainbow_yellow": (167, 145, 108),
        "rainbow_green": (108, 143, 124),
        "rainbow_blue": (101, 130, 167),
        "rainbow_indigo": (121, 109, 161),
        "rainbow_violet": (155, 111, 166),
        "mountain": (70, 78, 111),
        "snow": (157, 151, 182),
        "volcano": (112, 88, 117),
        "smoke": (116, 94, 123),
        "far_tree": (42, 70, 77),
        "shore": (59, 84, 103),
        "water": (52, 110, 140),
        "water_light": (112, 156, 178),
        "trunk": (143, 110, 90),
        "tree": (74, 125, 113),
        "tree_light": (143, 162, 123),
        "brachiosaurus": (160, 177, 123),
        "brachiosaurus_shade": (88, 116, 94),
        "brachiosaurus_light": (211, 200, 151),
        "diplodocus": (159, 151, 162),
        "diplodocus_shade": (93, 101, 127),
        "diplodocus_light": (209, 189, 184),
        "trex": (200, 140, 121),
        "trex_shade": (134, 95, 94),
        "trex_light": (237, 185, 153),
        "eye": (240, 221, 195),
        "pteranodon": (167, 135, 162),
        "triceratops": (127, 150, 187),
        "triceratops_shade": (77, 103, 144),
        "triceratops_juvenile": (151, 169, 202),
        "triceratops_juvenile_shade": (90, 117, 154),
        "stegosaurus": (166, 150, 130),
        "stegosaurus_shade": (106, 108, 91),
        "ankylosaurus": (161, 137, 128),
        "ankylosaurus_shade": (108, 92, 100),
        "parasaurolophus": (184, 149, 140),
        "parasaurolophus_shade": (121, 99, 106),
        "parasaurolophus_light": (222, 185, 161),
        "plesiosaurus": (137, 169, 194),
        "plesiosaurus_shade": (80, 111, 153),
        "plesiosaurus_light": (208, 202, 219),
        "armor": (203, 167, 159),
        "plates": (194, 125, 156),
        "ground": (64, 80, 83),
        "rock": (122, 116, 140),
        "rock_shade": (77, 77, 102),
        "fern": (76, 125, 111),
        "fern_light": (126, 155, 119),
        "cycad_trunk": (128, 96, 84),
        "lily_pad": (68, 128, 122),
        "flower_warm": (218, 142, 128),
        "flower_cool": (184, 140, 202),
        "nest": (142, 108, 88),
        "egg": (222, 208, 192),
    },
}


def _curve(a, b, c, d, steps=12):
    """Sample an authored cubic into an opaque silhouette's boundary."""
    points = []
    for index in range(steps + 1):
        t = index / steps
        u = 1.0 - t
        points.append((u*u*u*a[0] + 3*u*u*t*b[0] + 3*u*t*t*c[0] + t*t*t*d[0],
                       u*u*u*a[1] + 3*u*u*t*b[1] + 3*u*t*t*c[1] + t*t*t*d[1]))
    return points


def _outline(segments):
    points = []
    for segment in segments:
        points.extend(_curve(*segment)[:-1])
    points.append(segments[-1][-1])
    return points


def _cloud(canvas, x, y, size, palette):
    color = palette["cloud"]
    canvas.bezier(((x, y), (x - size*.1, y-size*.7),
                   (x + size*.3, y-size*.9), (x + size*.43, y-size*.3)), color)
    canvas.bezier(((x + size*.43, y-size*.3), (x + size*.65, y-size),
                   (x + size*.95, y-size*.35), (x + size, y)), color)
    canvas.line(x - size*.12, y+.35, x + size*.38, y+.35, palette["cloud_light"])
    canvas.line(x + size*.65, y+.35, x + size*1.18, y+.35, color)


def _weather(canvas, weather, palette):
    """Open sky strokes; the original semantic sky remains the click target."""
    if weather is None:
        return
    previous = canvas.depth, canvas.clip_bottom, canvas.default_owner
    try:
        canvas.depth, canvas.default_owner = WEATHER_DEPTH, "sky"
        # Projection rounding and parallax must not turn a non-sky target row
        # into sky. This is the initial owner plane, not the moving horizon.
        sky_bottom = math.ceil((HORIZON_Y-canvas.origin_y)*canvas.scale)-1
        # The lake's semantic plane can rise into those rows under parallax;
        # its empty water interiors must still occlude this background layer.
        water_bottom = math.ceil((HORIZON_Y-canvas.origin_y-
                                  canvas.camera[1]*WATER_DEPTH)*canvas.scale)-1
        sky_bottom = min(sky_bottom, water_bottom)
        canvas.clip_bottom = (sky_bottom if canvas.clip_bottom is None
                              else min(canvas.clip_bottom, sky_bottom))
        strength = weather["cloud_strength"]
        if strength > 0:
            x, y = weather["cloud_x"], weather["cloud_y"]
            width = weather["cloud_width"]*strength
            height = weather["cloud_height"]*strength
            if width*canvas.aspect*canvas.scale >= .5:
                # A low, asymmetric three-lobed outline, never a filled storm.
                canvas.bezier(((x-width*.5, y), (x-width*.56, y-height*.6),
                               (x-width*.25, y-height*.85),
                               (x-width*.18, y-height*.48)), palette["cloud"])
                canvas.bezier(((x-width*.18, y-height*.48),
                               (x-width*.14, y-height*1.18),
                               (x+width*.17, y-height*1.18),
                               (x+width*.24, y-height*.5)), palette["cloud"])
                canvas.bezier(((x+width*.24, y-height*.5),
                               (x+width*.43, y-height*.75),
                               (x+width*.57, y-height*.2),
                               (x+width*.5, y)), palette["cloud"])
                canvas.line(x-width*.5, y, x-width*.08, y, palette["cloud_light"])
                canvas.line(x+width*.13, y, x+width*.5, y, palette["cloud"])
        for streak in weather["rain"]:
            canvas.line(*streak["tail"], *streak["head"], palette["rain"])
        strength = weather["rainbow_strength"]
        if strength > 0:
            half_span = math.pi*.5*strength
            for band, name in enumerate(("red", "orange", "yellow", "green",
                                          "blue", "indigo", "violet")):
                rx, ry = 38-.8*band, 27-.6*band
                # Sub-cell slivers should disappear, not flash seven apex dots.
                if 2*rx*math.sin(half_span)*canvas.aspect*canvas.scale < 1:
                    continue
                count = min(96, max(3, math.ceil(
                    2*half_span*max(rx*canvas.aspect, ry)*canvas.scale)+1))
                points = ((68+rx*math.sin(-half_span+2*half_span*n/(count-1)),
                           36-ry*math.cos(-half_span+2*half_span*n/(count-1)))
                          for n in range(count))
                canvas.path(points, palette["rainbow_"+name])
    finally:
        canvas.depth, canvas.clip_bottom, canvas.default_owner = previous


def _volcano_smoke(canvas, snapshot, palette):
    """Swell the existing curls without rewinding their buoyant rise."""
    previous = canvas.depth, canvas.clip_bottom, canvas.default_owner
    try:
        canvas.depth, canvas.default_owner = .11, None
        puff = snapshot["volcano_puff"]
        swell = 1 + (.22 if puff["calm"] else .9)*puff["strength"] if puff is not None else 1
        smoke_time = snapshot["time"] + snapshot["layout"].smoke_phase
        for index in range(4):
            rise = (smoke_time*.22 + index*2.6 + snapshot["smoke_lift"]) % 11
            sx = 46 + math.sin(smoke_time*.23 + index*.9)*(.4 + rise*.12) + rise*.13
            sy = 19.1 - rise
            canvas.bezier(((sx-.8*swell, sy+.5), (sx-1.7*swell, sy-.3),
                           (sx+.8*swell, sy-1.2), (sx+1.5*swell, sy-.4)), palette["smoke"])
    finally:
        canvas.depth, canvas.clip_bottom, canvas.default_owner = previous


def _sky(canvas, snapshot, palette):
    time = snapshot["time"]
    layout = snapshot["layout"]
    canvas.default_owner = "sky"
    canvas.depth = .025
    for cloud in layout.clouds:
        drift = (cloud.x + (time+cloud.phase)*cloud.speed + 15) % 140 - 15
        _cloud(canvas, drift, cloud.y, cloud.size, palette)
    _weather(canvas, snapshot["weather"], palette)
    _meteor(canvas, snapshot["meteor"], palette)
    canvas.default_owner = None

    canvas.depth = .09
    mountain = palette["mountain"]
    canvas.polygon(((-12, 34), (4, 23), (10, 26), (21, 15),
                    (38, 33), (47, 24), (58, 34)), mountain, fill=" ")
    canvas.polygon(((5, 34), (13, 26), (23, 32), (31, 24), (42, 35)), mountain, fill=" ")
    canvas.polygon(((64, 34), (78, 22), (87, 30), (99, 19),
                    (112, 30), (124, 22), (137, 35)), mountain, fill=" ")
    snow = palette["snow"]
    canvas.path(((15.9, 20.7), (18.2, 21.4), (21, 15),
                 (24.3, 19.7), (26.6, 20.8)), snow)
    canvas.path(((18.2, 21.4), (20.3, 20), (22, 21.6), (24.3, 19.7)), snow)
    canvas.path(((94.6, 24.1), (97.3, 23.1), (99, 19),
                 (101.8, 21.8), (104.2, 24.2)), snow)
    canvas.line(10, 29, 14, 30, mountain)
    canvas.line(31, 30, 34, 33, mountain)
    canvas.line(77, 25, 82, 31, mountain)

    canvas.depth = .11
    canvas.polygon(((30, 34), (42, 21), (46, 20.5), (50, 21),
                    (61, 34)), palette["volcano"], fill=" ")
    canvas.bezier(((42, 21), (44, 22), (48, 22), (50, 21)), palette["snow"])
    canvas.path(((43, 24), (39.5, 29), (39, 31)), mountain)
    canvas.line(50, 25, 53, 29, mountain)
    _volcano_smoke(canvas, snapshot, palette)


def _meteor(canvas, meteor, palette):
    if meteor is None:
        return
    canvas.depth = METEOR_DEPTH
    tail, head = meteor["tail"], meteor["head"]
    # The whole effect is behind the land/water plane, even in ridge gaps.
    for index in range(8):
        a = tuple(tail[n] + (head[n]-tail[n])*index/8 for n in (0, 1))
        b = tuple(tail[n] + (head[n]-tail[n])*(index+1)/8 for n in (0, 1))
        if a[1] >= HORIZON_Y:
            break
        if b[1] > HORIZON_Y:
            fraction = (HORIZON_Y-a[1])/(b[1]-a[1])
            b = (a[0] + (b[0]-a[0])*fraction, HORIZON_Y)
        strength = meteor["fade"] * (.28 + .72*(index+1)/8)
        color = tuple(round(channel*strength) for channel in palette["trex_light"])
        canvas.line(*a, *b, color)
    if head[1] < HORIZON_Y:
        color = tuple(round(channel*meteor["fade"]) for channel in palette["eye"])
        canvas.char(*head, "@", color)


def _conifer(canvas, x, base, height, color, trunk, sway=0.0):
    top = base - height
    canvas.line(x, base, x+sway*.35, top+height*.12, trunk)
    for fraction, width in ((.10, .8), (.26, 1.55), (.43, 2.1), (.61, 2.7)):
        y = top + height*fraction
        spread = height*.18*width
        shift = sway*(1-fraction)
        canvas.path(((x-spread+shift, y+height*.15),
                     (x+shift, y), (x+spread+shift, y+height*.15)), color)
    canvas.line(x-.8, base, x+1.1, base, trunk)


def _lily_pad(canvas, pad, drift, palette):
    x = pad.x + drift
    canvas.ellipse(x, pad.y, pad.radius, pad.radius * .35,
                   palette["lily_pad"], owner="water", fill=" ")
    if pad.bloom:
        canvas.char(x, pad.y - .15, "*", palette["flower_warm"], owner="water")


def _water_jump(canvas, jump, palette):
    if jump is None:
        return
    ox, oy = jump["origin"]
    jx, jy = jump["x"], jump["y"]
    progress = jump["progress"]
    span = 2.6 if jump.get("calm") else 5.2
    ring = (.8 + 1.8 * min(progress, 1 - progress) * 2)
    canvas.line(ox - ring, oy, ox - .3, oy, palette["water_light"], owner="water")
    canvas.line(ox + .3, oy, ox + ring, oy, palette["water_light"], owner="water")
    if progress < .22 or progress > .78:
        splash_x = ox - span * .38 if progress < .22 else ox + span * .38
        canvas.char(splash_x - .6, oy - .6, "'", palette["water_light"], owner="water")
        canvas.char(splash_x + .6, oy - .6, "'", palette["water_light"], owner="water")
    if .06 <= progress <= .94:
        slope = (1 - 2 * progress) * 1.1
        canvas.bezier(((jx - 1.3, jy + slope * .55),
                       (jx - .3, jy - .65),
                       (jx + .5, jy - .55),
                       (jx + 1.3, jy - slope * .55)),
                      palette["water_light"], owner="water")
        canvas.line(jx - 1.3, jy + slope * .55,
                    jx - 1.8, jy + slope * .55 - .35,
                    palette["water"], owner="water")
        canvas.char(jx + .9, jy - slope * .3, ".", palette["eye"], owner="water")


def _distance_and_lake(canvas, water_jump, plesiosaurus, diplodocus,
                       time, motion, layout, palette):
    # Semantic lake coverage follows its parallax plane, not screen rows.
    # Later trees, banks and opaque animal interiors remove occluded coverage.
    canvas.depth = WATER_DEPTH
    left, top, right, bottom = layout.water_bounds
    x0, y0 = canvas.project(left, top)
    x1, y1 = canvas.project(right, bottom)
    for row in range(max(0, math.ceil(y0)), min(canvas.height, math.ceil(y1))):
        for column in range(max(0, math.ceil(x0)), min(canvas.width, math.ceil(x1))):
            canvas.owners[row][column] = "water"
    canvas.depth = .18
    for tree in layout.trees:
        sway = math.sin(time*.37 + layout.wind_phase + tree.phase)*.22*motion
        _conifer(canvas, tree.x, tree.base, tree.height,
                 palette["far_tree"], palette["far_tree"], sway)
    canvas.bezier(((-8, 37), (13, 34), (35, 36), (52, 37)), palette["shore"])
    canvas.bezier(((53, 37), (74, 35), (100, 36), (119, 37)), palette["shore"])
    _diplodocus(canvas, diplodocus, motion, palette)

    canvas.depth = WATER_DEPTH
    # Separate ripple speeds and phases, not an entire row moving in lockstep.
    for index, ripple in enumerate(layout.ripples):
        x, y, width = ripple.x, ripple.y, ripple.width
        drift = math.sin(time*ripple.speed + ripple.phase)*.65
        color = palette["water_light"] if index % 5 == 0 else palette["water"]
        canvas.bezier(((x+drift, y), (x+width*.3+drift, y-.25),
                       (x+width*.6+drift, y+.3), (x+width+drift, y)),
                      color, owner="water")
    _plesiosaurus(canvas, plesiosaurus, motion, palette)
    for pad in layout.lily_pads:
        drift = math.sin(time*.29 + pad.phase)*.35*motion
        _lily_pad(canvas, pad, drift, palette)
    _water_jump(canvas, water_jump, palette)
    canvas.bezier(((-8, 48), (9, 45), (25, 48), (40, 47)), palette["shore"])
    canvas.bezier(((43, 48), (66, 45), (96, 48), (119, 46)), palette["shore"])

def _pteranodon_strokes(bird):
    """Rotate the authored wing, torso and beak together about the flight root."""
    span, x, y = (bird[key] for key in ("span", "x", "y"))
    tip = bird["tip_y"] - y
    point = _pivot((0, 0), bird["bank"], origin=(x, y))

    def rotate(points):
        return tuple(point(dx, dy) for dx, dy in points)

    return (
        rotate(((-span, tip), (-span*.46, -.9), (0, .5),
                (span*.48, -1), (span, tip))),
        rotate(((-.4, .1), (.1, 1.2), (.8, .2))),
        rotate(((.3, .15), (1.2, -.25))),
    )


def _pteranodons(canvas, birds, selected, palette):
    previous_depth = canvas.depth
    try:
        for bird in birds:
            if bird["id"] not in selected:
                continue
            canvas.depth = bird["depth"]
            wing, body, beak = _pteranodon_strokes(bird)
            owner = bird["id"]
            canvas.path(wing, palette["pteranodon"], owner=owner)
            canvas.path(body, palette["pteranodon"], owner=owner)
            canvas.path(beak, palette["cloud_light"], owner=owner)
    finally:
        canvas.depth = previous_depth


def _focal_tree(canvas, time, motion, wind_phase, palette):
    canvas.depth = .40
    sway = math.sin(time*.37 + wind_phase)*.38*motion
    trunk = palette["trunk"]
    x = 94 + FOCAL_OFFSET_X
    # Tall araucaria-like trunk, umbrella whorls, and individually drawn needles.
    canvas.polygon(((x-.8, 54), (x-.5, 20), (x, 9),
                    (x+.6, 20), (x+1, 54)), trunk, fill=" ")
    canvas.line(x-.3, 51, x, 25, palette["tree"])
    canvas.path(((x-3.5, 54.3), (x-.6, 53.4), (x+2, 54), (x+4, 54.2)), trunk)
    for index, (y, spread) in enumerate(((8, 2.5), (11.4, 4.4),
                                       (15.3, 7.6), (19.5, 7.7),
                                       (26, 7), (33, 5.8))):
        shift = sway*(1-y/58)
        color = palette["tree_light"] if index < 3 else palette["tree"]
        center = x+shift
        canvas.bezier(((center-spread, y+2.6), (center-spread*.7, y+.5),
                       (center-1.4, y+1), (center, y)), color)
        canvas.bezier(((center, y), (center+1.4, y+1),
                       (center+spread*.7, y+.5), (center+spread, y+2.6)), color)
        canvas.line(x, y+4, center-spread*.74, y+1.6, trunk)
        canvas.line(x, y+4, center+spread*.74, y+1.6, trunk)
        for side in (-1, 1):
            for needle in range(1, 6):
                fraction = needle/6
                nx = center+side*spread*fraction
                ny = y+.7+fraction*1.1
                canvas.path(((nx-side*.65, ny+.7), (nx, ny-.5),
                             (nx+side*.75, ny+.5)), color)
    canvas.char(x-3.8+sway, 17.2, "'", palette["tree_light"])
    canvas.char(x-5.7+sway, 18.5, ",", palette["tree"])


def _pivot(anchor, angle, origin=None, parent=None):
    """Rigid rotation around anchor; parent/origin never scale or shear shapes."""
    c, s = math.cos(angle), math.sin(angle)
    ox, oy = anchor if origin is None else origin

    def point(x, y):
        rx, ry = x - anchor[0], y - anchor[1]
        result = (ox + c*rx - s*ry, oy + s*rx + c*ry)
        return parent(*result) if parent is not None else result

    return point


def _diplodocus_pose(pose, motion):
    """A low carriage and fixed-length neck links, not one shoulder-hinged bar."""
    body = lambda x, y: (pose["x"] + x, pose["foot_y"] + y)
    response = pose["reaction"] * motion
    drink = pose["drink"] * (1 - response)
    neck = [body(7, -12)]
    look = (1 - drink) * pose["look"] * motion - .13 * response
    for bend in (-.05, .20, .55, .90, 1.20):
        angle = -.025 * (1 - drink) + bend * drink + look
        x, y = neck[-1]
        neck.append((x + 5.6 * math.cos(angle), y + 5.6 * math.sin(angle)))
    # A small, mostly level skull articulates independently at the neck tip.
    head = _pivot((0, 0), .40 * drink + look - .025 * (1 - drink),
                  origin=neck[-1])
    # A firm, slightly raised root flows into a flexible, airborne whip.
    # Absolute link angles preserve length without concentrating the bend
    # at a single hinge. Idle swishes have smooth starts/ends and long rests.
    tail = [body(-9, -11)]
    for index, (bend, idle_amplitude) in enumerate(
            ((.18, .02), (.10, .045), (-.04, .09), (-.24, .16), (-.44, .26))):
        age = (pose["tail_time"] - index * .35) % 20
        idle = (math.sin(math.pi * age / 8)**2 * math.sin(math.tau * age / 8)
                if age < 8 else 0)
        gait = math.sin(pose["phase"] * .43 - index * .4) * pose["stride"]
        angle = (bend + motion * (idle_amplitude * idle + .008 * (index + 1) * gait)
                 + .04 * (index + 1) * response)
        x, y = tail[-1]
        tail.append((x - 6.2 * math.cos(angle), y - 6.2 * math.sin(angle)))
    legs = []
    for far in (True, False):
        for index, hip in enumerate((-7, 5)):
            phase = pose["phase"] + index * math.pi * .5 + (math.pi if far else 0)
            step = math.cos(phase) * .9 * pose["stride"] * motion
            lift = max(0, math.sin(phase)) * .65 * pose["stride"] * motion
            hip -= .9 if far else 0
            legs.append((far, tuple(body(x, y) for x, y in (
                (hip-1, -9), (hip+1.1, -9),
                (hip+.8+step*.4, -4.2),
                (hip+step+.6, -.6-lift), (hip+step+1.5, -.3-lift),
                (hip+step+1.5, -lift), (hip+step-.8, -lift),
                (hip-.9+step*.4, -4.3),
            ))))
    return {
        "body": body,
        "neck": neck,
        "head": head,
        "tail": tail,
        "legs": legs,
    }


def _tapered_rails(joints, widths):
    normals = []
    for a, b in zip(joints, joints[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        normals.append((-dy / length, dx / length))
    back, front = [], []
    for index, (joint, width) in enumerate(zip(joints, widths)):
        before, after = normals[max(0, index - 1)], normals[min(len(normals) - 1, index)]
        nx, ny = before[0] + after[0], before[1] + after[1]
        length = math.hypot(nx, ny)
        nx, ny = nx / length, ny / length
        back.append((joint[0] - width * nx, joint[1] - width * ny))
        front.append((joint[0] + width * nx, joint[1] + width * ny))
    return back, front


def _diplodocus(canvas, pose, motion, palette):
    if pose is None:
        return
    previous_depth, previous_clip = canvas.depth, canvas.clip_bottom
    try:
        canvas.depth = pose["depth"]
        owner = pose["id"]
        color, shade, light = (palette["diplodocus" + suffix]
                               for suffix in ("", "_shade", "_light"))
        joints = _diplodocus_pose(pose, motion)
        body, head = joints["body"], joints["head"]
        back, front = _tapered_rails(joints["tail"], (2.2, 1.6, .95, .48, .18, 0))
        canvas.polygon(_outline((
            *_catmull_beziers(back),
            *_catmull_beziers(front[::-1]),
            (front[0], front[0], back[0], back[0]),
        )), color, owner=owner, fill=" ")
        # Four columnar legs share the same hip height and grounded foot plane.
        # Each has a small independent swing, not a scaled/bouncing torso.
        for far, points in joints["legs"]:
            canvas.polygon(points, shade if far else color, owner=owner, fill=" ")
        canvas.polygon(_outline((
            (body(-11, -10.5), body(-11, -15.3), body(-1, -16), body(5, -14)),
            (body(5, -14), body(8, -13.5), body(9, -10), body(6, -7.3)),
            (body(6, -7.3), body(1, -5.7), body(-7, -6), body(-9, -7.8)),
            (body(-9, -7.8), body(-10, -8), body(-11, -9), body(-11, -10.5)),
        )), color, owner=owner, fill=" ")
        canvas.bezier((body(-8, -12.5), body(-4, -14), body(1, -14.3),
                       body(4.8, -12.8)), light, owner=owner)
        canvas.bezier((body(-8, -8.5), body(-4, -6.8), body(1, -6.7),
                       body(4.5, -8)), shade, owner=owner)
        # Tapered rails follow the articulated vertebral chain. Neither the
        # neck length nor torso changes as the muzzle lowers to the water.
        back, front = _tapered_rails(joints["neck"], (1.5, 1.3, 1.05, .85, .65, .5))
        back[-1], front[-1] = head(0, -.55), head(0, .55)
        canvas.polygon(_outline((
            *_catmull_beziers(back),
            (back[-1], back[-1], front[-1], front[-1]),
            *_catmull_beziers(front[::-1]),
            (front[0], front[0], back[0], back[0]),
        )), color, owner=owner, fill=" ")
        canvas.path(joints["neck"], shade, owner=owner)
        canvas.polygon(_outline((
            (head(-.25, -.55), head(.5, -.95), head(1.9, -.85), head(2.8, -.45)),
            (head(2.8, -.45), head(3.3, -.35), head(3.5, .05), head(3.25, .35)),
            (head(3.25, .35), head(2.1, .7), head(.5, .7), head(-.25, .55)),
            (head(-.25, .55), head(-.55, .3), head(-.55, -.3), head(-.25, -.55)),
        )), color, owner=owner, fill=" ")
        canvas.char(*head(1.1, -.35), "-" if pose["blink"] else "o",
                    palette["eye"], owner=owner)
        canvas.line(*head(2, .3), *head(3.15, .3), shade, owner=owner)
    finally:
        canvas.depth, canvas.clip_bottom = previous_depth, previous_clip


def _plesiosaurus_pose(pose, motion):
    """Translate the swimmer whole; its neck and small skull pivot rigidly."""
    body = lambda x, y: (pose["x"] + x, pose["body_y"] + y)
    return {
        "body": body,
        "neck": _pivot((2.5, -1.6),
                       (pose["look"] + .36 * pose["reaction"]) * motion,
                       parent=body),
    }


def _plesiosaurus(canvas, pose, motion, palette):
    if pose is None or not pose["visible"]:
        return
    previous_depth, previous_clip = canvas.depth, canvas.clip_bottom
    try:
        canvas.depth = pose["depth"]
        waterline = math.floor(canvas.project(0, pose["water_y"])[1])
        canvas.clip_bottom = (waterline if previous_clip is None
                              else min(previous_clip, waterline))
        owner = pose["id"]
        color, shade, light = (palette["plesiosaurus" + suffix]
                               for suffix in ("", "_shade", "_light"))
        joints = _plesiosaurus_pose(pose, motion)
        body, neck = joints["body"], joints["neck"]
        # Four broad, rounded paddles, not feet or claws. Their lower portions
        # disappear behind exactly the same water plane as the rigid torso.
        for hip, far in ((-3.2, True), (1.8, True), (-3.2, False), (1.8, False)):
            side = -1 if hip < 0 else 1
            reach = 2.6 if far else 3.5
            canvas.polygon(_outline((
                (body(hip-.7, -1.4), body(hip+side*1.2, -1.5),
                 body(hip+side*reach, -.1), body(hip+side*(reach+.3), .9)),
                (body(hip+side*(reach+.3), .9), body(hip+side*reach, 1.8),
                 body(hip+side*.8, .4), body(hip-.7, -1.4)),
            )), shade if far else color, owner=owner, fill=" ")
        # Tapered tail and rounded back keep fixed dimensions throughout dives.
        canvas.polygon(_outline((
            (body(-4, -2.1), body(-6, -2), body(-8.5, -.6), body(-11.4, -.4)),
            (body(-11.4, -.4), body(-9, .6), body(-6, .2), body(-4, -.2)),
            (body(-4, -.2), body(-3.6, -.8), body(-3.7, -1.5), body(-4, -2.1)),
        )), color, owner=owner, fill=" ")
        canvas.polygon(_outline((
            (body(-5.3, -1.2), body(-5.4, -3.7), body(1.6, -4), body(3.8, -2.1)),
            (body(3.8, -2.1), body(5, -.4), body(2.4, 1.4), body(-1, .9)),
            (body(-1, .9), body(-3.4, 1), body(-5.1, .4), body(-5.3, -1.2)),
        )), color, owner=owner, fill=" ")
        canvas.bezier((body(-4, -2.3), body(-2.4, -3), body(0, -3),
                       body(1.4, -2.5)), light, owner=owner)
        # One authored silhouette for the long neck and toothless rounded head.
        # Every control point shares one pivot: no neck scaling or body bloat.
        canvas.polygon(_outline((
            (neck(1.5, -1.6), neck(1.3, -4.8), neck(2, -8.2), neck(3, -10.4)),
            (neck(3, -10.4), neck(2.8, -12.4), neck(4.2, -13), neck(5.5, -12.1)),
            (neck(5.5, -12.1), neck(6.3, -11.6), neck(7.6, -12), neck(7.7, -11.2)),
            (neck(7.7, -11.2), neck(7.9, -10.3), neck(5.8, -10.1), neck(4.8, -10.5)),
            (neck(4.8, -10.5), neck(3.6, -8.2), neck(3.4, -4), neck(3.6, -1.6)),
            (neck(3.6, -1.6), neck(3.1, -1), neck(2, -1), neck(1.5, -1.6)),
        )), color, owner=owner, fill=" ")
        canvas.bezier((neck(3.1, -3), neck(2.9, -6.2), neck(3.3, -8.5),
                       neck(4.2, -10.2)), shade, owner=owner)
        canvas.char(*neck(4.6, -11.7), "-" if pose["blink"] else "o",
                    palette["eye"], owner=owner)
        canvas.char(*neck(7.1, -11.3), ".", shade, owner=owner)
        canvas.bezier((neck(5.8, -10.9), neck(6.1, -10.6),
                       neck(6.8, -10.6), neck(7.2, -10.9)), shade, owner=owner)
        # Wakes sit on the fixed plane, never move down with the animal, and
        # remain water click targets instead of extending its silhouette.
        wake_y = canvas.unproject(0, waterline, pose["depth"])[1]
        for left, right in ((-7.3, -5.8), (4.6, 6.5)):
            canvas.line(pose["x"]+left, wake_y, pose["x"]+right, wake_y,
                        palette["water_light"], owner="water")
    finally:
        canvas.depth, canvas.clip_bottom = previous_depth, previous_clip


def _catmull_beziers(points):
    segments = []
    for index in range(len(points) - 1):
        p0 = points[max(0, index - 1)]
        p1 = points[index]
        p2 = points[index + 1]
        p3 = points[min(len(points) - 1, index + 2)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        segments.append((p1, c1, c2, p2))
    return segments


def _brachiosaurus_pose(snapshot, motion):
    time = snapshot["time"] + snapshot["layout"].brachiosaurus_phase
    response = snapshot["brachiosaurus_reaction"] * motion
    sway = math.sin(time * .39) * .022 * motion
    body = lambda x, y: (x + FOCAL_OFFSET_X, y)
    joints = [body(78.6, 40.7)]
    # Three fixed-length links arc the neck forward/down without stretching it.
    for bend in (.24, .52, .84):
        angle = sway + bend * response
        c, s = math.cos(angle), math.sin(angle)
        jx, jy = joints[-1]
        joints.append((jx + c * .567 - s * -7.9, jy + s * .567 + c * -7.9))
    head = _pivot((80.3, 17.0), sway + .76 * response + math.sin(time * .71) * .012 * motion,
                  origin=joints[-1])
    return {
        "body": body,
        "neck": joints,
        "head": head,
        "jaw": _pivot((84.2, 16.2), .40 * response, parent=head),
        "tail": _pivot((56.5, 45.0), math.sin(time * .53) * .035 * motion + .28 * response,
                       parent=body),
        "response": response,
    }


def _trex_pose(snapshot, motion):
    response = snapshot["trex_reaction"] * motion
    sit = snapshot["trex_sit"]
    stride = snapshot["trex_stride"]
    bounce = -abs(math.sin(snapshot["phase"])) * .25 * motion * stride
    body = _pivot((-2, 46.7), -.07 * sit,
                  origin=(-2, 46.7 + 3.1 * sit + bounce),
                  parent=lambda dx, y: (snapshot["trex_x"] + dx, y))
    head = _pivot((3.5, 38.5), .54 * response + snapshot["trex_look"] * motion
                  - .10 * snapshot["trex_roar"],
                  origin=(3.5 + 1.8 * response, 38.5), parent=body)
    mouth = max(response, .85 * snapshot["trex_roar"])
    legs = []
    for offset, phase in ((1.7, snapshot["phase"] + math.pi),
                          (-1.8, snapshot["phase"])):
        step = math.sin(phase) * 1.9 * motion * stride
        lift = max(0, math.cos(phase)) * .8 * motion * stride
        hip = body(offset, 46.7)
        foot = (snapshot["trex_x"] + offset + step, 54 - lift)
        ankle = (foot[0] + .1, foot[1] - 1.1)
        dx, dy = ankle[0] - hip[0], ankle[1] - hip[1]
        distance = math.hypot(dx, dy)
        along = (3.4**2 - 3.7**2 + distance**2) / (2 * distance)
        across = math.sqrt(max(0.0, 3.4**2 - along**2))
        knee = (hip[0] + (along * dx + across * dy) / distance,
                hip[1] + (along * dy - across * dx) / distance)
        points = ((hip[0]-1.2, hip[1]), (hip[0]+1.4, hip[1]+.3),
                  (knee[0]+1, knee[1]-.1), (ankle[0]+.2, ankle[1]),
                  (foot[0]+2.4, foot[1]-.6), (foot[0]+2.8, foot[1]),
                  (foot[0]-.9, foot[1]), (ankle[0]-.8, ankle[1]),
                  (knee[0]-.8, knee[1]+.6))
        legs.append(dict(hip=hip, knee=knee, ankle=ankle, foot=foot, points=points))
    return {
        "body": body, "head": head,
        "jaw": _pivot((11.5, 36.8), .40 * mouth, parent=head),
        "tail": _pivot((-4.8, 43.8),
                       math.sin(snapshot["time"] * .67) * .045 * motion
                       + .35 * response + .16 * sit, parent=body),
        "response": response, "mouth_open": mouth, "legs": tuple(legs),
    }


def _parasaurolophus_pose(pose, motion):
    """Scale rigid local parts around the feet, never around the screen cells."""
    scale = pose["scale"]
    body = lambda x, y: (pose["x"] + x * scale, pose["foot_y"] + y * scale)
    response = pose["reaction"] * motion
    # Drinking stays functional in reduced motion; clicks smoothly lift the
    # head out of that posture instead of being ignored until drinking ends.
    drink = pose["drink"] * (1 - response)
    angle = drink * (.57 + .23 * scale)
    angle += (1 - drink) * (
        math.sin(pose["phase"] * .35) * .015 * motion - .32 * response)
    legs = []
    for far in (True, False):
        for fore, center in ((False, -3), (True, 3.5)):
            phase = pose["phase"] + (math.pi if far != fore else 0)
            step = math.sin(phase) * .8 * pose["stride"] * motion
            lift = max(0, math.cos(phase)) * .45 * pose["stride"] * motion
            hip = center + (1.2 if far else 0)
            foot = hip + step + (1 if fore else 0)
            if fore:
                points = ((hip-.55, -6.4), (hip+.65, -6.2),
                          (hip+.9+step*.4, -3), (foot+.45, -.6-lift),
                          (foot+1, -lift), (foot-.7, -lift),
                          (hip-.1+step*.4, -3))
            else:
                points = ((hip-1.2, -8.2), (hip+1.4, -8),
                          (hip+1.8+step*.3, -4.5), (foot+.3, -1-lift),
                          (foot+1.8, -.4-lift), (foot+1.8, -lift),
                          (foot-.8, -lift), (hip-.8+step*.3, -3.6))
            legs.append(dict(far=far, fore=fore, foot=body(foot, -lift),
                             points=tuple(body(x, y) for x, y in points)))
    return {
        "body": body,
        "head": _pivot((3, -6.5), angle, parent=body),
        "tail": _pivot((-6, -7.7),
                       math.sin(pose["phase"] * .4) * .025 * motion + .18 * response,
                       parent=body),
        "crest_tip": (-4, -15.4) if scale >= .9 else (3, -13.3),
        "legs": tuple(legs),
    }


def _parasaurolophus(canvas, pose, motion, palette):
    canvas.depth = PARASAUROLOPHUS_DEPTH
    owner = pose["id"]
    color, shade, light = (palette["parasaurolophus" + suffix]
                           for suffix in ("", "_shade", "_light"))
    joints = _parasaurolophus_pose(pose, motion)
    body, head, tail = (joints[key] for key in ("body", "head", "tail"))
    crest_x, crest_y = joints["crest_tip"]
    # The long tapered tail swings as one rigid counterweight.
    canvas.polygon(_outline((
        (tail(-6, -9), tail(-9, -9.2), tail(-12, -9.1), tail(-14.3, -8.6)),
        (tail(-14.3, -8.6), tail(-12, -8.1), tail(-8, -6.8), tail(-6, -6.5)),
        (tail(-6, -6.5), tail(-6, -7), tail(-6, -8), tail(-6, -9)),
    )), color, owner=owner, fill=" ")
    # The trunk conceals the limb roots; far feet remain slightly offset.
    for leg in joints["legs"]:
        canvas.polygon(leg["points"], shade if leg["far"] else color,
                       owner=owner, fill=" ")
    # A high pelvis slopes into the lower shoulder, not an upright kangaroo chest.
    # The torso is independent of head/tail reaction transforms.
    canvas.polygon(_outline((
        (body(-7, -7), body(-7, -11), body(-1, -11.3), body(3.5, -8.7)),
        (body(3.5, -8.7), body(5.2, -7), body(4.5, -4.7), body(1, -4.3)),
        (body(1, -4.3), body(-3.5, -3.8), body(-7, -4.7), body(-7, -7)),
    )), color, owner=owner, fill=" ")
    canvas.bezier((body(-5.5, -6), body(-2, -4.7),
                   body(1, -4.9), body(3.2, -6)), shade, owner=owner)
    # Neck, skull, crest and broad toothless bill share a single rigid pivot.
    # The adult's tube sweeps back, while young animals have a low short crest.
    canvas.polygon(_outline((
        (head(2.1, -6), head(1.9, -8.5), head(3.7, -10.8), head(5.9, -12.3)),
        (head(5.9, -12.3), head(3.5, -13.3),
         head(crest_x-.3, crest_y-.6), head(crest_x, crest_y)),
        (head(crest_x, crest_y), head(crest_x+.2, crest_y+.6),
         head(3.8, -11.9), head(6, -11.7)),
        (head(6, -11.7), head(7.2, -12.4), head(8.8, -11.8), head(10.2, -10.5)),
        (head(10.2, -10.5), head(11.4, -10.1), head(12.4, -10.7), head(12.8, -10)),
        (head(12.8, -10), head(13.1, -9.4), head(11.2, -9.2), head(9.5, -9.6)),
        (head(9.5, -9.6), head(7.1, -9.6), head(6.2, -6.5), head(4.3, -5.8)),
        (head(4.3, -5.8), head(3.4, -5.6), head(2.8, -5.7), head(2.1, -6)),
    )), color, owner=owner, fill=" ")
    canvas.bezier((head(5.9, -12.3), head(3.5, -13.2),
                   head(crest_x+.5, crest_y+.3), head(crest_x, crest_y)),
                  light, owner=owner)
    canvas.bezier((head(10, -9.9), head(11, -9.5),
                   head(12, -9.5), head(12.6, -9.8)), shade, owner=owner)
    canvas.char(*head(7.8, -11.3), "-" if pose["blink"] else "o",
                palette["eye"], owner=owner)
    canvas.char(*head(12, -10.1), ".", shade, owner=owner)
    for x, y in ((-3.5, -9.3), (-1.7, -8.5), (0, -9)):
        canvas.char(*body(x, y), ".", light, owner=owner)



def _brachiosaurus_neck_rails(joints, head):
    normals = []
    for a, b in zip(joints, joints[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        normals.append((-dy / length, dx / length))
    joint_normals = []
    for index in range(len(joints)):
        before = normals[max(0, index - 1)]
        after = normals[min(len(normals) - 1, index)]
        nx, ny = before[0] + after[0], before[1] + after[1]
        length = math.hypot(nx, ny)
        joint_normals.append((nx / length, ny / length))
    widths = (3.35, 2.75, 2.3, 1.9)
    back = [(j[0] - w * n[0], j[1] - w * n[1]) for j, w, n in zip(joints, widths, joint_normals)]
    front = [(j[0] + w * n[0], j[1] + w * n[1]) for j, w, n in zip(joints, widths, joint_normals)]
    back[0], front[0] = (75.3 + FOCAL_OFFSET_X, 39.0), (82.0 + FOCAL_OFFSET_X, 42.4)
    back[-1], front[-1] = head(78.4, 17.0), head(82.2, 17.1)
    return back, front


def _young_brachiosaurus_pose(pose, motion):
    """Rigid local anatomy; emergence translates the entire animal from below."""
    body = lambda x, y: (pose["x"] + x, pose["foot_y"] + y)
    reaction = pose["reaction"] * motion
    head = _pivot((1.15, -5.1),
                  -.10 * reaction + .015 * math.sin(pose["phase"]) * motion,
                  parent=body)
    tail = _pivot((-1.35, -2.2),
                  .04 * math.sin(pose["phase"] * .5) * motion + .12 * reaction,
                  parent=body)
    legs = []
    for x, hip_y, offset, far in ((-.65, -1.65, math.pi, True),
                                  (.55, -2.05, 0, True),
                                  (-1.35, -1.65, 0, False),
                                  (1.25, -2.05, math.pi, False)):
        phase = pose["phase"] + offset
        step = .22 * math.sin(phase) * pose["stride"]
        lift = .16 * max(0, math.cos(phase)) * pose["stride"]
        hip, foot = (x, hip_y), (x + step, -lift)
        # Two fixed links bend at the knee; stance feet never bob below ground.
        upper, lower = (.9, .95) if hip_y > -2 else (1.1, 1.15)
        dx, dy = foot[0] - hip[0], foot[1] - hip[1]
        distance = math.hypot(dx, dy)
        along = (upper * upper - lower * lower + distance * distance) / (2 * distance)
        across = math.sqrt(max(0, upper * upper - along * along))
        knee = (hip[0] + (along * dx - across * dy) / distance,
                hip[1] + (along * dy + across * dx) / distance)
        legs.append(dict(hip=body(*hip), knee=body(*knee), foot=body(*foot),
                         far=far, lengths=(upper, lower)))
    return dict(body=body, head=head, tail=tail, legs=tuple(legs))


def _young_brachiosaurus(canvas, pose, nest, motion, palette):
    if pose is None or pose["state"] not in ("hatching", "toddling", "lingering", "scurrying"):
        return
    previous = canvas.depth, canvas.clip_bottom, canvas.default_owner
    try:
        canvas.depth = pose["depth"]
        canvas.default_owner = pose["id"]
        if pose["state"] == "hatching" and nest is not None:
            surface_y = pose["foot_y"] - (1 - pose["emerge"]) * YOUNG_HEIGHT
            surface = math.floor(canvas.project(nest.x, surface_y)[1])
            canvas.clip_bottom = surface if previous[1] is None else min(surface, previous[1])
        color, shade, light = (palette["brachiosaurus" + suffix]
                               for suffix in ("", "_shade", "_light"))
        joints = _young_brachiosaurus_pose(pose, motion)
        body, head, tail = (joints[key] for key in ("body", "head", "tail"))
        # The long tapered tail is a counterweight, not a theropod's thick hip.
        canvas.polygon(_outline((
            (tail(-1.35, -2.5), tail(-2.1, -2.6), tail(-3.4, -2.2), tail(-4, -2.1)),
            (tail(-4, -2.1), tail(-3.1, -1.9), tail(-2, -1.8), tail(-1.35, -1.9)),
            (tail(-1.35, -1.9), tail(-1.3, -2), tail(-1.3, -2.3), tail(-1.35, -2.5)),
        )), color, fill=" ")
        for leg in joints["legs"]:
            hip, knee, foot = (leg[key] for key in ("hip", "knee", "foot"))
            canvas.polygon(((hip[0]-.14, hip[1]), (hip[0]+.14, hip[1]),
                            (knee[0]+.12, knee[1]), (foot[0]+.13, foot[1]-.12),
                            (foot[0]+.31, foot[1]), (foot[0]-.18, foot[1]),
                            (knee[0]-.12, knee[1])),
                           shade if leg["far"] else color, fill=" ")
        # A high shoulder, low rump and four weight-bearing legs define a
        # sauropod even when its tiny face occupies only a terminal cell.
        canvas.polygon(_outline((
            (body(-1.7, -2), body(-1.8, -2.9), body(-.2, -3.1), body(.75, -3.15)),
            (body(.75, -3.15), body(1.45, -3), body(1.55, -1.6), body(.9, -1.45)),
            (body(.9, -1.45), body(-.1, -1.15), body(-1.6, -1.2), body(-1.7, -2)),
        )), color, fill=" ")
        # The upright long neck is rigid and separate from the small skull.
        canvas.polygon(_outline((
            (body(.5, -2.7), body(.5, -3.6), body(.77, -4.7), body(.88, -5.25)),
            (body(.88, -5.25), body(1.1, -5.4), body(1.35, -5.3), body(1.4, -5.1)),
            (body(1.4, -5.1), body(1.25, -4.3), body(1.1, -3.1), body(1.3, -2.5)),
            (body(1.3, -2.5), body(1.05, -2.4), body(.7, -2.5), body(.5, -2.7)),
        )), color, fill=" ")
        canvas.polygon(_outline((
            (head(.85, -5.2), head(.8, -5.6), head(1.5, -5.65), head(1.8, -5.45)),
            (head(1.8, -5.45), head(2.05, -5.4), head(2.35, -5.4), head(2.35, -5.15)),
            (head(2.35, -5.15), head(2.3, -4.95), head(1.3, -4.95), head(.85, -5.2)),
        )), color, fill=" ")
        canvas.path((body(.95, -4.7), body(.75, -3.6), body(.85, -2.8)), shade)
        canvas.bezier((body(-1.2, -1.9), body(-.5, -1.4),
                       body(.4, -1.5), body(.9, -1.8)), shade)
        canvas.char(*head(1.55, -5.37), "-" if pose["blink"] else "o", palette["eye"])
        canvas.line(*head(1.95, -5.08), *head(2.25, -5.08), shade)
        canvas.char(*body(-.6, -2.65), ".", light)
    finally:
        canvas.depth, canvas.clip_bottom, canvas.default_owner = previous


def _brachiosaurus(canvas, snapshot, motion, palette):
    canvas.depth = .40
    time = snapshot["time"] + snapshot["layout"].brachiosaurus_phase
    pose = _brachiosaurus_pose(snapshot, motion)
    body = pose["body"]
    joints = pose["neck"]
    head, jaw, tail = pose["head"], pose["jaw"], pose["tail"]
    response = pose["response"]
    owner = "brachiosaurus"
    color = palette["brachiosaurus"]
    shade = palette["brachiosaurus_shade"]
    light = palette["brachiosaurus_light"]

    # Four feet remain on the bank; the far pair is deliberately subdued.
    for x, bottom, leg_color in ((65.0, 53.4, shade), (77, 53.5, shade),
                                  (60.5, 54, color), (73.1, 54, color)):
        canvas.polygon(tuple(body(px, py) for px, py in (
            (x-.9, 46), (x+1.2, 46.5), (x+1, bottom-1),
            (x+1.8, bottom-.2), (x+1.7, bottom),
            (x-1.1, bottom), (x-1.3, bottom-1.1))),
            leg_color, owner=owner, fill=" ")
        canvas.line(*body(x+.1, bottom-.7), *body(x+.1, bottom), light, owner=owner)

    # One continuous tail/body/neck/head silhouette keeps torso vertices fixed
    # while the fixed-length neck, skull/jaw and tail articulate around joints.
    back_rail, front_rail = _brachiosaurus_neck_rails(joints, head)
    if response > .05:
        head_segments = (
            (head(78.4, 17), head(78.2, 13.4), head(80, 12.9), head(83.4, 13)),
            (head(83.4, 13), head(87, 12.7), head(89.2, 13.8), head(89.1, 15.2)),
            (head(89.1, 15.2), head(88.2, 15.8), head(86.2, 15.9), head(84.4, 15.9)),
            (head(84.4, 15.9), jaw(85.8, 16.3), jaw(87.6, 16.4), jaw(88.7, 16.3)),
            (jaw(88.7, 16.3), jaw(88.4, 17.6), jaw(85.0, 17.5), head(82.2, 17.1)),
        )
    else:
        head_segments = (
            (head(78.4, 17), head(78.2, 13.4), head(80, 12.9), head(83.4, 13)),
            (head(83.4, 13), head(87, 12.7), head(89.2, 13.8), head(89.1, 15.5)),
            (head(89.1, 15.5), head(88.8, 17.6), head(85, 17.5), head(82.2, 17.1)),
        )
    segments = (
        (tail(44, 49), tail(48, 48.6), tail(52, 44.5), body(57, 43)),
        (body(57, 43), body(58, 37.2), body(69, 35.7), body(75.3, 39)),
        *_catmull_beziers(back_rail),
        *head_segments,
        *_catmull_beziers(front_rail[::-1]),
        (body(82, 42.4), body(83.7, 47.6), body(77, 50), body(69, 50)),
        (body(69, 50), body(62, 50), body(59, 47.1), body(56, 47)),
        (body(56, 47), tail(51, 48.1), tail(47, 50.5), tail(44, 49)),
    )
    canvas.polygon(_outline(segments), color, owner=owner, fill=" ")
    canvas.bezier(tuple(body(x, y) for x, y in (
        (60, 46.3), (64, 48.4), (73, 49.2), (78, 46.3))), shade, owner=owner)
    canvas.bezier((joints[0], joints[1], joints[2], joints[3]), shade, owner=owner)
    for x, y in ((59.5, 42.5), (62, 40), (65.6, 39.3), (69, 39.9),
                 (72.8, 41), (76, 43), (63, 44.4), (67, 42.2),
                 (70.5, 45), (74, 46.3), (60.5, 45.8)):
        canvas.char(*body(x, y), ".", shade, owner=owner)
    for jx, jy in joints[1:-1]:
        canvas.char(jx - .6, jy, ".", light, owner=owner)
    canvas.char(*head(83, 14.6), "-" if snapshot["brachiosaurus_blink"] else "o",
                palette["eye"], owner=owner)
    canvas.char(*head(87.7, 14.7), ".", shade, owner=owner)
    canvas.line(*head(81.5, 13.7), *head(82.7, 13.5), light, owner=owner)
    if response <= .05:
        canvas.bezier((head(84.9, 16), head(86, 16.8),
                       head(87.1, 16.5), head(87.9, 15.9)), light, owner=owner)
        if math.sin(time * 2.7) > .25:
            canvas.line(*head(88.6, 16.2), *head(89.6, 15.9), palette["tree_light"], owner=owner)


def _trex(canvas, snapshot, motion, palette):
    canvas.depth = .55
    # The torso/skull retain their authored size while the seated legs fold.
    pose = _trex_pose(snapshot, motion)
    body, head, jaw, tail = (pose[key] for key in ("body", "head", "jaw", "tail"))
    mouth = pose["mouth_open"]
    owner = "trex"
    color, shade, light = (palette["trex"], palette["trex_shade"], palette["trex_light"])

    for index, leg in enumerate(pose["legs"]):
        canvas.polygon(leg["points"], shade if index == 0 else color, owner=owner, fill=" ")
        foot = leg["foot"]
        canvas.line(foot[0]+1.4, foot[1]-.4, foot[0]+1.4, foot[1], light, owner=owner)

    # One continuous concave mouth contour: the lower jaw is a rigid link,
    # not a second, inflated silhouette switched in above a click threshold.
    mouth_and_jaw = (
        (head(17.8, 35), head(19.2, 35.3), head(19.1, 36.6), head(17.2, 36.8)),
        (head(17.2, 36.8), head(14.8, 36.8), head(13.0, 36.8), head(11.8, 36.8)),
        (head(11.8, 36.8), jaw(13.5, 37.3), jaw(16.0, 37.4), jaw(18.0, 37.3)),
        (jaw(18.0, 37.3), jaw(18.3, 38.4), jaw(17.5, 39.0), jaw(16.2, 39.1)),
        (jaw(16.2, 39.1), jaw(13.3, 39.9), head(11, 39.8), body(9.2, 39)),
    )
    segments = (
        (tail(-16, 47), tail(-11, 46), tail(-8, 42), body(-4, 41)),
        (body(-4, 41), body(-2, 38.8), body(.8, 39), body(3.5, 38)),
        (body(3.5, 38), head(3.4, 33), head(6, 31), head(10, 31)),
        (head(10, 31), head(14, 30.8), head(17.8, 32.6), head(17.8, 35)),
        *mouth_and_jaw,
        (body(9.2, 39), body(8.7, 42.2), body(7.1, 46.7), body(4.7, 48.3)),
        (body(4.7, 48.3), body(1.9, 50.8), body(-3.6, 49.6), body(-6, 46.6)),
        (body(-6, 46.6), tail(-10, 47.9), tail(-14, 48.3), tail(-16, 47)),
    )
    canvas.polygon(_outline(segments), color, owner=owner, fill=" ")
    canvas.bezier((body(-4.3, 45.8), body(-1, 48.8),
                   body(2.4, 49), body(5.4, 46.3)), shade, owner=owner)
    canvas.bezier((body(7.8, 40.6), body(8, 43), body(7, 44), body(5.5, 45.8)), light, owner=owner)
    # A short far arm and a brighter near arm; no claws or tooth-filled mouth.
    canvas.path((body(7.4, 41), body(9.3, 42.6), body(10.5, 42.1)), shade, owner=owner)
    canvas.path((body(5.7, 42), body(7.2, 44.5), body(9.5, 44)), color, owner=owner)
    canvas.line(*body(9.4, 44), *body(9.8, 44.6), light, owner=owner)
    for dx, y in ((-3, 41), (-.5, 40.8), (1.5, 42.2), (-2.4, 44.7),
                   (.7, 45.5), (4.3, 44.8)):
        canvas.char(*body(dx, y), ".", shade, owner=owner)
    for dx, y in ((6.7, 35), (9.4, 33)):
        canvas.char(*head(dx, y), ".", shade, owner=owner)
    canvas.char(*head(12.1, 34.2), "-" if snapshot["trex_blink"] else "o",
                palette["eye"], owner=owner)
    canvas.line(*head(11.2, 32.9), *head(12.9, 32.7), light, owner=owner)
    canvas.char(*head(17.2, 35.5), ".", shade, owner=owner)
    if mouth <= .05:
        canvas.bezier((head(12.4, 37.4), head(13.7, 38.7),
                       head(16.1, 38.2), head(17.5, 37.3)), light, owner=owner)


def _quadruped_legs(canvas, pose, centers, motion, color, shade, owner, body):
    for far in (True, False):
        for index, center in enumerate(centers):
            phase = pose["phase"] + index * math.pi + (math.pi if far else 0)
            step = math.sin(phase) * .65 * motion * pose["stride"]
            lift = max(0, math.cos(phase)) * .3 * motion * pose["stride"]
            hip = center + (.8 if far else 0)
            foot = hip + step
            points = tuple(body(x, y) for x, y in (
                (hip-.8, 48), (hip+.9, 48), (foot+.7, 53.8-lift),
                (foot+1.3, 54.5-lift), (foot-1, 54.5-lift)))
            canvas.polygon(points, shade if far else color, owner=owner, fill=" ")


def _triceratops_pose(pose, motion):
    """Scale around grounded feet; articulate skull and tail without body squash."""
    scale = pose["scale"]
    body = lambda x, y: (pose["x"] + x * scale, pose["foot_y"] + (y - 54.5) * scale)
    response = pose["reaction"] * motion
    grazing = pose["graze"] * (.5 + .08 * math.sin(pose["phase"] * .6)) * motion
    head_angle = (-.32 * response if pose["juvenile"]
                  else min(.6, grazing + .36 * response))
    return {
        "body": body,
        "head": _pivot((4, 47), head_angle, parent=body),
        "tail": _pivot((-8, 48), -.12 * math.sin(pose["phase"] * .4) * motion
                       - .35 * response, parent=body),
    }


def _triceratops(canvas, pose, motion, palette):
    previous_depth = canvas.depth
    try:
        canvas.depth = .55
        owner = pose["id"]
        palette_key = "triceratops_juvenile" if pose["juvenile"] else "triceratops"
        color, shade = palette[palette_key], palette[palette_key + "_shade"]
        joints = _triceratops_pose(pose, motion)
        body, head, tail = (joints[key] for key in ("body", "head", "tail"))
        canvas.polygon(_outline((
            (tail(-8, 47), tail(-11, 47.4), tail(-13, 48), tail(-14, 49)),
            (tail(-14, 49), tail(-12, 49.8), tail(-10, 49.5), tail(-8, 49)),
            (tail(-8, 49), tail(-8, 48.5), tail(-8, 47.5), tail(-8, 47)),
        )), shade, owner=owner, fill=" ")
        _quadruped_legs(canvas, pose, (-5, 3), motion, color, shade, owner, body)
        canvas.polygon(_outline((
            (body(-9, 48), body(-9, 43), body(0, 42), body(5, 45)),
            (body(5, 45), body(8, 48), body(6, 51), body(0, 51)),
            (body(0, 51), body(-6, 51.5), body(-9, 51), body(-9, 48)),
        )), color, owner=owner, fill=" ")
        canvas.bezier((body(-7, 48), body(-3, 50.5), body(2, 50.5), body(4, 48.5)),
                      shade, owner=owner)
        # Broad frill and three horns remain recognizable on the smaller calf.
        # Its softer, shorter frill and stubby horns are juvenile proportions.
        frill = (
            ((4, 49), (1.7, 47.2), (2.4, 43.2), (4.2, 42.8)),
            ((4.2, 42.8), (6.7, 42.4), (8, 46.5), (7, 49)),
            ((7, 49), (6, 50), (5, 50), (4, 49)),
        ) if pose["juvenile"] else (
            ((4, 49), (1, 47), (1.7, 42), (4.2, 41.5)),
            ((4.2, 41.5), (7.5, 41), (8.5, 46.5), (7, 49)),
            ((7, 49), (6, 50), (5, 50), (4, 49)),
        )
        canvas.polygon(_outline(tuple(tuple(head(*point) for point in segment)
                                      for segment in frill)),
                       shade, owner=owner, fill=" ")
        canvas.bezier((head(3.4, 47.5), head(2.6, 44), head(4.5, 42.5), head(5.8, 43.5)),
                      color, owner=owner)
        canvas.polygon(_outline((
            (head(5, 47), head(7.5, 45.6), head(10.4, 46.5), head(12, 48)),
            (head(12, 48), head(14, 49.5), head(12, 50.5), head(10, 50.5)),
            (head(10, 50.5), head(7, 51), head(5, 49.5), head(5, 47)),
        )), color, owner=owner, fill=" ")
        horn_fraction = .38 if pose["juvenile"] else 1.0
        for base, tip in (((7.6, 46.6), (10.5, 44.2)), ((8.8, 46.6), (12.1, 44.8)),
                          ((12, 48.4), (13.3, 47))):
            tip = tuple(a + (b - a) * horn_fraction for a, b in zip(base, tip))
            canvas.line(*head(*base), *head(*tip), palette["eye"], owner=owner)
        canvas.char(*head(9.4, 47.9), "-" if pose["blink"] else "o", palette["eye"], owner=owner)
        canvas.line(*head(11.6, 50), *head(13, 49.8), shade, owner=owner)
        for point in ((-5, 46), (-2, 45), (1, 46.5), (-4, 48)):
            canvas.char(*body(*point), ".", shade, owner=owner)
    finally:
        canvas.depth = previous_depth




def _stegosaurus(canvas, pose, motion, palette):
    canvas.depth = .55
    owner = "stegosaurus"
    color, shade = palette[owner], palette[owner + "_shade"]
    response = pose["reaction"] * motion
    body = lambda x, y: (pose["x"] + x, y)
    grazing = pose["graze"] * (.35 + .07 * math.sin(pose["phase"]*.5)) * motion
    head = _pivot((7.5, 47.5), min(.5, grazing + .35*response), parent=body)
    tail = _pivot((-8, 47), .12*math.sin(pose["phase"]*.35)*motion + .4*response, parent=body)
    canvas.polygon(_outline((
        (tail(-8, 46), tail(-12, 46.5), tail(-16, 48), tail(-18, 48.4)),
        (tail(-18, 48.4), tail(-15, 49.2), tail(-11, 49.5), tail(-8, 49)),
        (tail(-8, 49), tail(-8, 48), tail(-8, 47), tail(-8, 46)),
    )), color, owner=owner, fill=" ")
    for base, tip in (((-16.8, 48.1), (-17.5, 46.5)), ((-15.2, 47.6), (-15.5, 45.9)),
                      ((-16.6, 48.6), (-17.1, 49.9)), ((-14.8, 48.7), (-14.9, 50.2))):
        canvas.line(*tail(*base), *tail(*tip), palette["plates"], owner=owner)
    _quadruped_legs(canvas, pose, (-5, 4), motion, color, shade, owner, body)
    # Alternating plates follow the arched back; skull stays small and low.
    for x, base_y, height, width in ((-9, 46, 2.6, 1.6), (-6, 44, 4.1, 1.8),
                                     (-2, 43, 5, 2), (2.3, 43.6, 4.7, 2),
                                     (6, 45.5, 3.5, 1.7)):
        canvas.polygon((body(x-width, base_y+.7), body(x-width*.7, base_y-height*.7),
                        body(x, base_y-height), body(x+width, base_y-height*.35),
                        body(x+width, base_y+.9)), palette["plates"], owner=owner, fill=" ")
        canvas.line(*body(x, base_y-.4), *body(x, base_y-height+.7), shade, owner=owner)
    canvas.polygon(_outline((
        (body(-10, 48), body(-10, 42), body(-2, 41), body(4, 44)),
        (body(4, 44), body(8, 45), head(9, 48), head(12, 48)),
        (head(12, 48), head(16, 48), head(16, 51), head(12.8, 51)),
        (head(12.8, 51), head(10, 51), body(8, 50), body(5, 50.5)),
        (body(5, 50.5), body(-3, 52), body(-10, 51.5), body(-10, 48)),
    )), color, owner=owner, fill=" ")
    canvas.bezier((body(-8, 48.5), body(-3, 50.5), body(3, 50.3), body(6, 48.8)),
                  shade, owner=owner)
    canvas.char(*head(13.2, 49.1), "-" if pose["blink"] else "o", palette["eye"], owner=owner)
    canvas.line(*head(14.2, 50.4), *head(15.4, 50.2), shade, owner=owner)
    for point in ((-7, 46), (-3, 44.8), (1.5, 46), (-4, 48), (3, 48.5)):
        canvas.char(*body(*point), ".", shade, owner=owner)


def _ankylosaurus_pose(pose, motion):
    response = pose["reaction"] * motion
    sleep = pose["sleep"]
    bob = abs(math.sin(pose["phase"])) * .1 * motion * pose["stride"]
    body = lambda x, y: (pose["x"] + x, y + .5 * sleep - bob)
    head = _pivot((6, 54.2), .08 * sleep + .2 * response, parent=body)
    tail = _pivot((-7, 54.3),
                  (.1 * math.sin(pose["phase"]*.35)*motion + .3*response) * (1-sleep),
                  parent=body)
    return body, head, tail


def _ankylosaurus(canvas, pose, motion, palette):
    canvas.depth = ANKYLOSAURUS_DEPTH
    owner = "ankylosaurus"
    color, shade = palette[owner], palette[owner + "_shade"]
    armor = palette["armor"]
    body, head, tail = _ankylosaurus_pose(pose, motion)
    # A narrow tail handle with a rigid rounded club, not a swinging body blob.
    canvas.polygon(_outline((
        (tail(-7, 53.9), tail(-10, 53.8), tail(-12, 54.2), tail(-14, 54.5)),
        (tail(-14, 54.5), tail(-12, 55), tail(-9, 55.2), tail(-7, 55)),
        (tail(-7, 55), tail(-7, 54.7), tail(-7, 54.3), tail(-7, 53.9)),
    )), shade, owner=owner, fill=" ")
    canvas.polygon([tail(-14.5 + 1.8*math.cos(n*math.tau/24),
                         54.6 + 1.0*math.sin(n*math.tau/24)) for n in range(24)],
                   armor, owner=owner, fill=":")
    for far in (True, False):
        for index, center in enumerate((-4.7, 3.8)):
            phase = pose["phase"] + index*math.pi + (math.pi if far else 0)
            step = math.sin(phase) * .45 * motion * pose["stride"]
            lift = max(0, math.cos(phase)) * .2 * motion * pose["stride"]
            hip = center + (.6 if far else 0)
            foot = pose["x"] + hip + step
            canvas.polygon((body(hip-.8, 54), body(hip+.9, 54),
                            (foot+.7, ANKYLOSAURUS_FOOT_Y-.5-lift),
                            (foot+1.1, ANKYLOSAURUS_FOOT_Y-lift),
                            (foot-1, ANKYLOSAURUS_FOOT_Y-lift)),
                           shade if far else color, owner=owner, fill=" ")
    canvas.polygon(_outline((
        (body(-8, 54), body(-8, 50.3), body(3, 49.8), body(6, 53)),
        (body(6, 53), head(8, 53.7), head(10.8, 53.1), head(12.6, 54)),
        (head(12.6, 54), head(15, 55.3), head(12.5, 56.6), head(9.5, 56)),
        (head(9.5, 56), head(7.3, 55.8), body(6, 56), body(3, 56.1)),
        (body(3, 56.1), body(-4, 56.7), body(-8, 56.4), body(-8, 54)),
    )), color, owner=owner, fill=" ")
    # Low mosaic scutes distinguish this armor from Stegosaurus's tall plates.
    for x, y, size in ((-5.8, 52.6, .85), (-2.9, 51.7, .95), (.4, 51.8, .95),
                        (3.4, 52.7, .8), (-5.5, 54.5, .7), (-2.3, 53.7, .85),
                        (1, 53.8, .85), (4, 54.3, .65)):
        canvas.path((body(x-size, y), body(x, y-.65*size),
                     body(x+size, y), body(x, y+.6*size)),
                    armor, owner=owner, closed=True)
    for x, y in ((-6.9, 53.8), (-4, 55.5), (-.5, 55.8), (3, 55.3)):
        canvas.path((body(x-.7, y), body(x, y+.6), body(x+.7, y)),
                    shade, owner=owner)
    eye_closed = pose["sleep"] > .6 or pose["blink"]
    canvas.char(*head(10.6, 54.6), "-" if eye_closed else "o", palette["eye"], owner=owner)
    canvas.line(*head(9.7, 54), *head(11, 54), armor, owner=owner)
    canvas.line(*head(12, 55.7), *head(13.3, 55.5), shade, owner=owner)
    if pose["state"] == "napping":
        canvas.char(*body(6, 50.5), "z", shade, owner=owner)

def _fern(canvas, x, y, height, palette, sway):
    color = palette["fern"]
    for side, reach in ((-1, .9), (1, 1), (-1, .54), (1, .55)):
        tip_x = x+side*height*reach+sway
        tip_y = y-height*(.72 if reach > .6 else 1)
        canvas.bezier(((x, y), (x+side*.7, y-height*.6),
                       (tip_x-side*.7, tip_y-.6), (tip_x, tip_y)), color)
        for n in range(2, 6):
            f = n/6
            bx = x+(tip_x-x)*f
            by = y+(tip_y-y)*f-height*.14*math.sin(f*math.pi)
            canvas.path(((bx-side*.5, by-.7), (bx, by),
                         (bx+side*.55, by-.1)), palette["fern_light"])
    canvas.line(x, y, x+sway*.5, y-height*1.05, color)


def _rock(canvas, rock, palette):
    if rock.kind == "boulder":
        def point(x, y):
            return rock.x + (x-10)*rock.scale, rock.y + (y-57.7)*rock.scale

        canvas.polygon(tuple(point(x, y) for x, y in (
            (4, 57), (5.5, 53.2), (9.5, 51.9), (13.7, 53.1),
            (16.2, 56.8), (12, 57.7), (7, 57.6))), palette["rock"], fill=" ")
        canvas.path(tuple(point(x, y) for x, y in (
            (5.5, 53.2), (9.6, 54), (12, 57.7))), palette["rock_shade"])
        canvas.line(*point(9.6, 54), *point(13.7, 53.1), palette["rock_shade"])
        canvas.char(*point(7.1, 55.3), ".", palette["rock_shade"])
        canvas.char(*point(13.6, 55.8), ":", palette["rock_shade"])
    else:
        canvas.ellipse(rock.x, rock.y-1.4*rock.scale,
                       3.7*rock.scale, 1.4*rock.scale,
                       palette["rock_shade"], fill=" ")



def _cycad(canvas, cycad, palette, sway):
    x, y, height = cycad.x, cycad.y, cycad.height
    crown_y = y - height * .42
    canvas.polygon(((x - .7, y), (x - .5, crown_y),
                    (x + .5, crown_y), (x + .7, y)),
                   palette["cycad_trunk"], fill=":")
    for side in (-1, 1):
        for reach, drop in ((1.0, .18), (.72, .48)):
            tip_x = x + side * height * reach + sway
            tip_y = y - height * (1 - drop)
            canvas.bezier(((x, crown_y),
                           (x + side * height * .45, crown_y - height * .45),
                           (tip_x - side * .4, tip_y - .3),
                           (tip_x, tip_y)), palette["fern_light"])


def _flower(canvas, flower, palette, sway):
    x, y, height = flower.x, flower.y, flower.height
    top_x = x + sway
    top_y = y - height
    canvas.line(x, y, top_x, top_y + .2, palette["fern"])
    bloom = palette["flower_warm"] if flower.tint == "warm" else palette["flower_cool"]
    canvas.char(top_x, top_y, "*", bloom)
    canvas.char(top_x - .6, top_y + .2, ".", bloom)
    canvas.char(top_x + .6, top_y + .2, ".", bloom)


def _egg(canvas, x, y, palette, wobble=0, crack=0, opening=0, sink=0):
    """The same stroke ellipse underlies whole eggs and both rigid shell halves."""
    c, s = math.cos(wobble), math.sin(wobble)
    transform = lambda px, py: (x + px*c - py*s, y + sink + px*s + py*c)
    arc = lambda start: [(.30 * math.cos(start + math.pi*n/24),
                          .57 * math.sin(start + math.pi*n/24))
                         for n in range(25)]
    bottom, top = arc(0), arc(math.pi)
    seam = ((-.30, 0), (-.19, -.09), (-.05, .07),
            (.08, -.08), (.20, .06), (.30, 0))
    if opening <= 0:
        canvas.polygon(tuple(transform(*p) for p in bottom + top), palette["egg"], fill=" ")
        if crack > 0:
            count = crack * (len(seam)-1)
            points = list(seam[:int(count)+1])
            if count < len(seam)-1:
                a, b = seam[int(count):int(count)+2]
                fraction = count % 1
                points.append((a[0]+(b[0]-a[0])*fraction,
                               a[1]+(b[1]-a[1])*fraction))
            canvas.path(tuple(transform(*p) for p in points), palette["trunk"])
        return
    cap = _pivot((0, 0), -.35*opening,
                 origin=(0, -.65*opening), parent=transform)
    canvas.polygon(tuple(transform(*p) for p in bottom + list(seam)), palette["egg"], fill=" ")
    canvas.polygon(tuple(cap(*p) for p in top + list(reversed(seam))),
                   palette["egg"], fill=" ")
    canvas.path(tuple(transform(*p) for p in seam), palette["trunk"])
    canvas.path(tuple(cap(*p) for p in seam), palette["trunk"])


def _nest(canvas, nest, palette, hatching=None, *, rim_only=False):
    if nest is None:
        return
    previous = canvas.depth, canvas.clip_bottom, canvas.default_owner
    try:
        canvas.depth, canvas.default_owner = NEST_DEPTH, "nest"
        x, y, radius = nest.x, nest.y, nest.radius
        if not rim_only:
            canvas.ellipse(x, y - .5, radius, .95, palette["nest"], fill=".")
            offsets = egg_offsets(nest)
            # Neighbouring intact eggs stay in front of any opening shell.
            order = sorted(range(len(offsets)),
                           key=lambda index: hatching is None or index != hatching["egg_index"])
            for index in order:
                dx = offsets[index]
                if hatching is None or index != hatching["egg_index"]:
                    _egg(canvas, x+dx, y-.8, palette)
                    continue
                reset = hatching["reset"]
                if reset >= 1:
                    _egg(canvas, x+dx, y-.8, palette)
                    continue
                clip = round(canvas.project(x, y-.1)[1])
                canvas.clip_bottom = clip if previous[1] is None else min(clip, previous[1])
                try:
                    if reset > .5:
                        rise = (reset-.5)*2
                        rise = rise*rise*(3-2*rise)
                        _egg(canvas, x+dx, y-.8, palette, sink=3.6*(1-rise))
                    else:
                        sink = min(1, reset*2)
                        sink = 3.6*sink*sink*(3-2*sink)
                        _egg(canvas, x+dx, y-.8, palette,
                             wobble=hatching["wobble"], crack=hatching["crack"],
                             opening=hatching["emerge"], sink=sink)
                finally:
                    canvas.clip_bottom = previous[1]
        canvas.bezier(((x - radius, y - .3), (x - radius * .4, y + .45),
                       (x + radius * .4, y + .45), (x + radius, y - .3)),
                      palette["trunk"])
    finally:
        canvas.depth, canvas.clip_bottom, canvas.default_owner = previous

def _ground_paths(canvas, palette):
    previous_depth = canvas.depth
    try:
        canvas.depth = .55
        for points in (((-8, 54.7), (1, 54.4), (9, 54.7)),
                       ((13, 55), (21, 54.7), (27, 54.9)),
                       ((42, 55), (50, 54.7), (57, 55)),
                       ((67, 55.4), (77, 55), (84, 55.2)),
                       ((99, 55), (107, 54.5), (119, 55))):
            canvas.path(points, palette["ground"])
    finally:
        canvas.depth = previous_depth


def _foreground(canvas, time, motion, layout, palette, hatching=None, *, nest_back_drawn=False):
    canvas.depth = .80
    # Low framing: neither boulder nor fronds hide the focal head/body.
    for rock in layout.rocks:
        _rock(canvas, rock, palette)
    for fern in layout.ferns:
        sway = math.sin(time*.48 + layout.wind_phase + fern.phase)*.22*motion
        _fern(canvas, fern.x, fern.y, fern.height, palette, sway)
    for cycad in layout.cycads:
        sway = math.sin(time*.41 + layout.wind_phase + cycad.phase)*.18*motion
        _cycad(canvas, cycad, palette, sway)
    _nest(canvas, layout.nest, palette, hatching, rim_only=nest_back_drawn)
    for flower in layout.flowers:
        sway = math.sin(time*.57 + layout.wind_phase + flower.phase)*.14*motion
        _flower(canvas, flower, palette, sway)
    for x, y in ((23, 57.6), (34, 56.8), (50, 58.7), (57, 57.2),
                 (69, 58.5), (79, 57.4), (98, 59)):
        canvas.char(x, y, ".", palette["ground"])


def visible_cast_members(canvas: Canvas, snapshot: SceneSnapshot, config: Settings) -> tuple[str, ...]:
    """Cull reserved occupants for painting without changing admission."""
    admitted = set(snapshot['admitted'])
    selected = ['brachiosaurus']
    remaining = config['population']['maxVisible'] - 1
    for group in cast_groups(snapshot, config, canvas.world_bounds):
        if not group['active'] or group['key'] == 'plesiosaurus' and not snapshot['plesiosaurus']['visible']:
            continue
        members = tuple(member for member in group['members'] if member['id'] in admitted)[:remaining]
        if len(members) < group['minimum']:
            continue
        remaining -= len(members)
        for member in members:
            left, top, right, bottom, depth = member['bounds']
            x0, y0 = canvas.unproject(-.5, -.5, depth)
            x1, y1 = canvas.unproject(canvas.width-.5, canvas.height-.5, depth)
            if left <= x1 and right >= x0 and top <= y1 and bottom >= y0:
                selected.append(member['id'])
    return tuple(selected)


def draw_scene(canvas, snapshot, settings):
    """Paint one snapshot; the caller owns time, camera, sizing and ANSI I/O."""
    # A full-monitor terminal needs luminous glyphs like Omarcharium's fish,
    # not the low-contrast colors of the discarded painted experiment.
    palette = {name: tuple(min(255, round(v*1.45+8)) for v in rgb)
               for name, rgb in _PALETTES[settings.get("preset", "morning")].items()}
    time = snapshot["time"]
    layout = snapshot["layout"]
    motion = .18 if settings.get("motion", {}).get("reducedMotion", False) else 1.0
    selected = visible_cast_members(canvas, snapshot, settings)
    _sky(canvas, snapshot, palette)
    _distance_and_lake(canvas, snapshot["water_jump"] if "water_jump" in selected else None,
                       snapshot["plesiosaurus"] if "plesiosaurus" in selected else None,
                       snapshot["diplodocus"] if "diplodocus" in selected else None,
                       time, motion, layout, palette)
    _pteranodons(canvas, snapshot["pteranodons"], selected, palette)
    flock = snapshot["pteranodon_flock"]
    if flock is not None:
        _pteranodons(canvas, flock["members"], selected, palette)
    _ground_paths(canvas, palette)
    for family in snapshot["parasaurolophus_families"]:
        for member in family["members"]:
            if member["id"] in selected:
                _parasaurolophus(canvas, member, motion, palette)
    hatching = snapshot["hatching"]
    young_selected = hatching is not None and hatching["id"] in selected
    if hatching is not None and (hatching["id"] not in snapshot["admitted"]
                                 or settings["population"]["maxVisible"] < 2):
        hatching = None
    _focal_tree(canvas, time, motion, layout.wind_phase, palette)
    _brachiosaurus(canvas, snapshot, motion, palette)
    if hatching is not None:
        # Keep the live shell independent of the baby's viewport culling.
        _nest(canvas, layout.nest, palette, hatching)
    if young_selected:
        _young_brachiosaurus(canvas, hatching, layout.nest, motion, palette)
    if "trex" in selected:
        _trex(canvas, snapshot, motion, palette)
    if "triceratops" in selected:
        _triceratops(canvas, snapshot["herbivores"]["triceratops"], motion, palette)
    if "triceratops:calf" in selected:
        _triceratops(canvas, snapshot["triceratops_calf"], motion, palette)
    if "stegosaurus" in selected:
        _stegosaurus(canvas, snapshot["herbivores"]["stegosaurus"], motion, palette)
    _foreground(canvas, time, motion, layout, palette, hatching, nest_back_drawn=hatching is not None)
    if "ankylosaurus" in selected:
        _ankylosaurus(canvas, snapshot["ankylosaurus"], motion, palette)
