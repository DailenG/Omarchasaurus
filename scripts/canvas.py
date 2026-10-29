"""World-space character strokes, terminal projection and ANSI serialization."""
import math
from layout import HORIZON_Y
from scene_types import ViewportBounds

BACKGROUNDS = {'morning': (3, 15, 23), 'dusk': (16, 10, 24)}


class Canvas:
    """World-space ASCII strokes re-evaluated at actual terminal cell dimensions."""
    def __init__(self, width, height, camera=(0, 0), cell_aspect=2.0):
        self.width = max(1, min(500, width))
        self.height = max(1, min(200, height))
        self.aspect = max(1.2, min(3.0, cell_aspect))
        self.scale = min(self.height / 60, self.width / (self.aspect * 62))
        self.visible_width = self.width / (self.aspect * self.scale)
        # Blend focal framing instead of jumping 18 world units at one column.
        landscape = max(0, min(1, (self.visible_width - 100) / 10))
        self.center = 73 - 18*landscape
        self.origin_y = 60 - self.height / self.scale
        self.camera = camera
        self.depth = 0
        self.chars = [[' '] * self.width for _ in range(self.height)]
        self.colors = [[None] * self.width for _ in range(self.height)]
        skyline = self.project(0, HORIZON_Y)[1]
        self.owners = [[('sky' if y < skyline else None)] * self.width
                       for y in range(self.height)]
        self.default_owner = None
        self.clip_bottom = None

    @property
    def world_bounds(self) -> ViewportBounds:
        return (self.center - self.visible_width / 2, self.origin_y,
                self.center + self.visible_width / 2, 60)

    def project(self, x, y):
        return ((x - self.center - self.camera[0] * self.depth) * self.aspect * self.scale + self.width / 2,
                (y - self.origin_y - self.camera[1] * self.depth) * self.scale)

    def unproject(self, x, y, depth=0):
        return ((x-self.width/2)/(self.aspect*self.scale) + self.center + self.camera[0]*depth,
                y/self.scale + self.origin_y + self.camera[1]*depth)

    def put(self, x, y, glyph, color, owner=None):
        x, y = round(x), round(y)
        if (0 <= x < self.width and 0 <= y < self.height
                and (self.clip_bottom is None or y <= self.clip_bottom)):
            self.chars[y][x] = glyph
            self.colors[y][x] = color
            # Opaque blank interiors belong to the silhouette, too. Later
            # scenery passes owner=None and removes coverage it occludes.
            self.owners[y][x] = self.default_owner if owner is None else owner

    def char(self, x, y, glyph, color, owner=None):
        self.put(*self.project(x, y), glyph, color, owner)

    def text(self, x, y, text, color, owner=None):
        px, py = self.project(x, y)
        for offset, ch in enumerate(text):
            if ch != ' ':
                self.put(px + offset, py, ch, color, owner)

    def line(self, x1, y1, x2, y2, color, glyph=None, owner=None):
        a, b = self.project(x1, y1), self.project(x2, y2)
        dx, dy = b[0] - a[0], b[1] - a[1]
        if glyph is None:
            if abs(dy) < max(.3, abs(dx) * .18):
                glyph = '_'
            elif abs(dx) < max(.3, abs(dy) * .35):
                glyph = '|'
            else:
                glyph = '\\' if dx * dy > 0 else '/'
        count = max(1, math.ceil(max(abs(dx), abs(dy))))
        for n in range(count + 1):
            f = n / count
            self.put(a[0] + f * dx, a[1] + f * dy, glyph, color, owner)

    def path(self, points, color, owner=None, closed=False):
        points = list(points)
        for a, b in zip(points, points[1:] + ([points[0]] if closed else [])):
            self.line(*a, *b, color, owner=owner)

    def bezier(self, points, color, owner=None):
        p0, p1, p2, p3 = points
        samples = []
        for n in range(max(16, round(self.scale * 30)) + 1):
            t = n / max(16, round(self.scale * 30))
            samples.append(tuple((1-t)**3*p0[i]+3*(1-t)**2*t*p1[i]+3*(1-t)*t*t*p2[i]+t**3*p3[i] for i in (0, 1)))
        self.path(samples, color, owner)

    def polygon(self, points, color, owner=None, fill='.'):
        points = list(points)
        screen = [self.project(*p) for p in points]
        low = max(0, math.ceil(min(p[1] for p in screen)))
        high = min(self.height - 1, math.floor(max(p[1] for p in screen)))
        edges = tuple(zip(screen, screen[1:] + screen[:1]))
        for y in range(low, high + 1):
            crossings = []
            for a, b in edges:
                if (a[1] <= y < b[1]) or (b[1] <= y < a[1]):
                    crossings.append(a[0] + (y-a[1])*(b[0]-a[0])/(b[1]-a[1]))
            crossings.sort()
            for left, right in zip(crossings[::2], crossings[1::2]):
                for x in range(max(0, math.ceil(left)), min(self.width, math.ceil(right))):
                    ch = fill if fill and (x + y*2) % 7 == 0 else ' '
                    self.put(x, y, ch, color, owner)
        self.path(points, color, owner, closed=True)

    def ellipse(self, cx, cy, rx, ry, color, owner=None, fill=None):
        count = max(20, math.ceil(math.tau * max(rx * self.aspect, ry) * self.scale))
        points = [(cx + math.cos(n*math.tau/count)*rx, cy + math.sin(n*math.tau/count)*ry) for n in range(count)]
        if fill is not None:
            self.polygon(points, color, owner, fill)
        else:
            self.path(points, color, owner, closed=True)

    def plain(self):
        return '\n'.join(''.join(row).rstrip() for row in self.chars)

    def ansi(self, background, origin=(0, 0)):
        out = [f'\x1b[1m\x1b[48;2;{background[0]};{background[1]};{background[2]}m']
        current = None
        for y, row in enumerate(self.chars):
            out.append(f'\x1b[{y+1+origin[1]};{1+origin[0]}H')
            for x, ch in enumerate(row):
                color = self.colors[y][x]
                if ch != ' ' and color != current and color is not None:
                    out.append(f'\x1b[38;2;{color[0]};{color[1]};{color[2]}m')
                    current = color
                out.append(ch)
        out.append('\x1b[0m')
        return ''.join(out)

    def bounds(self, owner):
        cells = [(x, y) for y, row in enumerate(self.owners) for x, name in enumerate(row) if name == owner]
        if not cells:
            return None
        xs, ys = zip(*cells)
        return min(xs), min(ys), max(xs)-min(xs)+1, max(ys)-min(ys)+1
