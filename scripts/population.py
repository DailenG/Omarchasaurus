"""Deterministic walker poses and conservative encounter bounds."""
import math

ANKYLOSAURUS_DEPTH = .9
ANKYLOSAURUS_FOOT_Y = 57.8
PARASAUROLOPHUS_DEPTH = .32
PARASAUROLOPHUS_FOOT_Y = 49.5
GROUND_EXTENTS = {
    'trex': (-18, 29, 23, 55, .55),
    'triceratops': (-15, 41, 15, 55, .55),
    'stegosaurus': (-18, 38, 16, 55, .55),
    'ankylosaurus': (-17, 49.5, 14, ANKYLOSAURUS_FOOT_Y, ANKYLOSAURUS_DEPTH),
    'parasaurolophus': (-80, 29.5, 16, PARASAUROLOPHUS_FOOT_Y, PARASAUROLOPHUS_DEPTH),
}


def _ease(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def walking_distance(time, phase):
    """Cumulative distance: eighteen eased walking seconds, six stopped seconds."""
    cycles, age = divmod(time + phase * 24 / math.tau, 24)
    speed = 21.6 / 17
    if age < 1:
        travel = speed * age * age / 2
    elif age < 17:
        travel = speed * (age - .5)
    elif age < 18:
        ramp = age - 17
        travel = speed * (16.5 + ramp - ramp * ramp / 2)
    else:
        travel = 21.6
    return cycles * 21.6 + travel


def walking_time(distance, phase):
    """First arrival at a distance, including the start of a stopped interval."""
    cycles, travel = divmod(distance, 21.6)
    speed = 21.6 / 17
    if cycles > 0 and travel < 1e-12:
        age = -6
    elif travel < speed / 2:
        age = math.sqrt(2 * travel / speed)
    elif travel < speed * 16.5:
        age = travel / speed + .5
    else:
        age = 18 - math.sqrt(max(0, 2 * (21.6 - travel) / speed))
    return cycles * 24 + age - phase * 24 / math.tau


def herbivore_pose(walk_time, phase, start_x, reaction, blink):
    # Phase offsets desynchronize stops without allowing walkers to overtake.
    travel = walking_distance(walk_time, phase) - walking_distance(0, phase)
    age = (walk_time + phase * 24 / math.tau) % 24
    return {
        'x': start_x + travel,
        'phase': travel * 2.1 / .9 + phase,
        'stride': max(0, min(1, age, 18 - age)),
        'graze': math.sin((age - 18) * math.pi / 6)**2 if age >= 18 else 0,
        'reaction': reaction,
        'blink': blink,
    }


def triceratops_extents(count):
    """Conservative adult or adult/calf prefix bounds, relative to the adult."""
    return (-35, 41, 15, 55, .55) if count >= 2 else GROUND_EXTENTS['triceratops']


def triceratops_poses(walk_time, phase, start_x, time, calf_phase,
                     reaction, calf_reaction):
    adult = herbivore_pose(walk_time, phase, start_x, reaction,
                           (time + phase) % 6.3 > 6.1)
    travel = walking_distance(walk_time, phase) - walking_distance(0, phase)
    cycle_age = (walk_time + phase * 24 / math.tau) % 24
    adult.update(id='triceratops', scale=1.0, foot_y=54.5, juvenile=False)
    calf = {
        # Fixed following distance leaves daylight behind the adult's tail.
        'id': 'triceratops:calf', 'x': adult['x'] - 26,
        'scale': .56, 'foot_y': 54.5, 'juvenile': True,
        'phase': travel * 2.1 / (.9 * .56) + calf_phase,
        'stride': adult['stride'], 'graze': 0.0,
        'reaction': calf_reaction, 'blink': (time + calf_phase) % 5.9 > 5.7,
        'state': 'following' if cycle_age < 18 else 'resting',
    }
    return adult, calf


def ankylosaurus_pose(walk_time, phase, start_x, reaction, blink, wake=None):
    """The front-bank walker naps on its normal stops; waking never retimes travel.

    wake is (nap cycle, age seconds, sleep at click, wake duration seconds).
    A clicked animal stays alert for that nap, then rejoins the unchanged route.
    """
    pose = herbivore_pose(walk_time, phase, start_x, reaction, blink)
    pose.pop('graze')
    cycle, age = divmod(walk_time + phase * 24 / math.tau, 24)
    sleep = _ease(age - 18) * _ease(24 - age)
    if age < 18:
        state = 'waddling'
    elif age < 19:
        state = 'settling'
    elif age < 23:
        state = 'napping'
    else:
        state = 'waking'
    if age >= 18 and wake is not None and wake[0] == int(cycle):
        _, wake_age, initial_sleep, duration = wake
        sleep = min(sleep, initial_sleep * (1 - _ease(wake_age / duration)))
        state = 'waking' if sleep > 0 else 'awake'
    pose.update(sleep=sleep, state=state, nap_cycle=int(cycle))
    return pose


def parasaurolophus_extents(family, count):
    """Bounds of a leader/follower prefix, relative to the leader's position."""
    last = family.members[count - 1]
    return (last.offset - 15 * last.scale - 1, 29.5, 16,
            PARASAUROLOPHUS_FOOT_Y, PARASAUROLOPHUS_DEPTH)


def parasaurolophus_family_pose(family, walk_time, phase, origin_x, time, reactions):
    travel = walking_distance(walk_time, phase) - walking_distance(0, phase)
    leader_x = origin_x + travel
    stop_age = (walk_time + phase * 24 / math.tau) % 24
    stride = max(0, min(1, stop_age, 18 - stop_age))
    members = []
    for index, member in enumerate(family.members):
        x = leader_x + member.offset
        # Feet stay on the front bank. Only bills over the lake may lower.
        at_water = -8 <= x + 14 * member.scale <= 119
        drink = (_ease(stop_age - 18 - index * .2) * _ease(24 - stop_age)
                 if at_water else 0.0)
        members.append({
            'id': member.id, 'x': x, 'scale': member.scale,
            'foot_y': PARASAUROLOPHUS_FOOT_Y,
            'phase': travel * 2.1 / (.9 * member.scale) + member.blink_phase,
            'stride': stride, 'drink': drink,
            'reaction': reactions.get(member.id, 0.0),
            'blink': (time + member.blink_phase) % 6.5 > 6.3,
            'state': 'following' if stride > 0 else 'drinking' if drink > 0 else 'resting',
        })
    return {'id': family.id, 'members': tuple(members)}



def plesiosaurus_pose(descriptor, walk_time, motion_time, reaction, water_depth):
    """Translate one rigid swimmer through a continuous thirty-second dive cycle."""
    age = (walk_time + descriptor.phase) % 30
    emergence = _ease(age / 4) * _ease((18 - age) / 4)
    body_y = descriptor.water_y + .5 + 17 * (1 - emergence)
    state = ('surfacing' if age < 4 else 'looking' if age < 14
             else 'diving' if age < 18 else 'submerged')
    return {
        'id': descriptor.id,
        'x': descriptor.x + 2 * math.sin(walk_time * .19 + descriptor.look_phase),
        'water_y': descriptor.water_y,
        'body_y': body_y,
        'emergence': emergence,
        'look': .15 * math.sin(motion_time * .31 + descriptor.look_phase),
        'reaction': reaction,
        'blink': (motion_time + descriptor.look_phase) % 6.7 > 6.5,
        'state': state,
        'cycle': int((walk_time + descriptor.phase) // 30),
        'visible': emergence > 0 and body_y - 14 <= descriptor.water_y,
        'depth': water_depth,
    }


