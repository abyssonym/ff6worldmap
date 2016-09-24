import random
from itertools import product
from sys import argv


class Field:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.tiles = [list([0 for _ in xrange(width)])
                      for _2 in xrange(height)]

    def __repr__(self):
        chrdict = {0: " ",
                   1: "%",
                   2: "."}
        f = lambda i: chrdict[i] * 2
        #f = lambda i: str(i) if i > 0 else "."
        return "\n".join(["".join(map(f, row)) for row in self.tiles])

    def get_value(self, x, y, default=0):
        if x < 0 or y < 0:
            return default
        try:
            return self.tiles[y][x]
        except IndexError:
            return default

    def set_value(self, x, y, value):
        self.tiles[y][x] = value

    def copy_contiguous(self, x, y, newfield):
        value = self.get_value(x, y)
        newfield.set_value(x, y, value)
        todo = [(x, y)]
        while todo:
            (x, y) = todo.pop()
            for (i, j) in product(range(-1, 2), range(-1, 2)):
                if i == j == 0:
                    continue
                if i * j != 0:
                    continue
                i, j = x+i, y+j
                if i < 0 or i >= newfield.width:
                    continue
                if j < 0 or j >= newfield.height:
                    continue
                if not self.get_value(i, j) == value:
                    continue
                if newfield.get_value(i, j) == value:
                    continue
                newfield.set_value(i, j, value)
                todo.append((i, j))

    @property
    def line(self):
        line = []
        for row in self.tiles:
            line.extend(row)
        return line

    def recenter(self):
        for i in xrange(self.width):
            if not all(row[i] == 0 for row in self.tiles):
                break
        left = i
        for i in xrange(self.width-1, -1, -1):
            if not all(row[i] == 0 for row in self.tiles):
                break
        right = (self.width-1-i)
        for j in xrange(self.height):
            if not all(t == 0 for t in self.tiles[j]):
                break
        top = j
        for j in xrange(self.height-1, -1, -1):
            if not all(t == 0 for t in self.tiles[j]):
                break
        bottom = (self.height-1-j)

        shift_h = (left-right)/2
        self.tiles = [row[shift_h:] + row[:shift_h] for row in self.tiles]
        assert len(self.tiles[0]) == self.width

        shift_v = (top-bottom)/2
        self.tiles = self.tiles[shift_v:] + self.tiles[:shift_v]
        assert len(self.tiles) == self.height

    def get_bordered_line(self, width, height):
        assert width >= self.width
        assert height >= self.height
        newfield = Field(width, height)
        width_margin = (width - self.width) / 2
        height_margin = (height - self.height) / 2
        for x in xrange(self.width):
            for y in xrange(self.height):
                newfield.set_value(x+width_margin, y+height_margin,
                                   self.get_value(x, y))
        newfield.recenter()
        return newfield.line


def add_noise(field, valid_func=None, noiseval=1, rate=0.5):
    if valid_func is None:
        valid_func = lambda v: v == 0

    for i in xrange(field.width):
        for j in xrange(field.height):
            if valid_func(field.get_value(i, j)) and random.random() <= rate:
                field.set_value(i, j, noiseval)


def add_noise_center(field, noiseval=1):
    total = field.width * field.height
    hw, hh = field.width/3, field.height/3
    for _ in xrange(total):
        i = random.randint(0, hw) + random.randint(0, hw) + random.randint(0, hw)
        j = random.randint(0, hh) + random.randint(0, hh) + random.randint(0, hh)
        field.set_value(i, j, noiseval)


def evaluate_ruleset(field, ruleset, threshold, valid=None, livevalue=1, deadvalue=0, adjacents=None):
    newfield = Field(width=field.width, height=field.height)
    for x in xrange(field.width):
        for y in xrange(field.height):
            oldvalue = field.get_value(x, y)
            if valid is not None and oldvalue not in valid:
                newfield.set_value(x, y, field.get_value(x, y))
                continue
            if adjacents:
                for i, j in product(range(-1, 2), range(-1, 2)):
                    if field.get_value(x+i, y+j) in adjacents:
                        break
                else:
                    continue
            if evaluate_ruleset_tile(field, x, y, ruleset, threshold):
                newfield.set_value(x, y, livevalue)
            else:
                newfield.set_value(x, y, deadvalue)
    return newfield


def evaluate_ruleset_tile(field, x, y, ruleset, threshold):
    size = len(ruleset)
    assert size % 2
    margin = size / 2
    life_value = 0
    for j in xrange(-margin, margin+1):
        for i in xrange(-margin, margin+1):
            field_i, field_j = x+i, y+j
            value = field.get_value(field_i, field_j)
            score = ruleset[margin+j][margin+i](value)
            life_value += score
    return life_value >= threshold


def create_ruleset(scores, valids, negascores=None):
    if negascores is None:
        negascores = [list([0 for _ in xrange(len(scores[0]))])
                      for _2 in xrange(len(scores))]
    if not hasattr(valids, "__getitem__"):
        valids = [valids]
    if not hasattr(valids[0], "__getitem__"):
        valids = [list([valids for _ in xrange(len(scores[0]))])
                  for _2 in xrange(len(scores))]
    ruleset = []
    for y in xrange(len(scores)):
        ruleline = []
        for x in xrange(len(scores[0])):
            v = valids[y][x]
            s = scores[y][x]
            n = negascores[y][x]
            f = lambda a, v2=v, s2=s, n2=n: s2 if a in v2 else n2
            ruleline.append(f)
        ruleset.append(ruleline)
    return ruleset


def smooth_field(field, tilevalue=None, altvalue=None):
    assert (tilevalue is None and altvalue is None) or (
        tilevalue is not None and altvalue is not None)
    f = field
    for y in xrange(field.height):
        for x in xrange(field.width):
            left, middle, right = (f.get_value(x-1, y), f.get_value(x, y),
                                   f.get_value(x+1, y))
            top, middle, bottom = (f.get_value(x, y-1), f.get_value(x, y),
                                   f.get_value(x, y+1))
            topleft = f.get_value(x-1, y-1)

            if tilevalue:
                checkvalue = tilevalue
            else:
                checkvalue = middle

            if altvalue:
                setvalue = altvalue
            else:
                setvalue = left
            if middle != left and middle != right and middle == checkvalue:
                if tilevalue or left == right:
                    f.set_value(x, y, setvalue)

            if altvalue:
                setvalue = altvalue
            else:
                setvalue = top
            if middle != top and middle != bottom and middle == checkvalue:
                if tilevalue or top == bottom:
                    f.set_value(x, y, setvalue)

            continue
            if x == field.width or y == field.height or x == 0 or y == 0:
                continue
            if altvalue:
                setvalue = altvalue
            else:
                setvalue = f.get_value(x, y)
            middle = f.get_value(x, y)
            if (topleft == middle and top == left and top != middle):
                assert f.get_value(x-1, y-1) == f.get_value(x, y)
                assert f.get_value(x-1, y) == f.get_value(x, y-1)
                f.set_value(x, y-1, setvalue)
                f.set_value(x-1, y, setvalue)
                assert f.get_value(x-1, y-1) == f.get_value(x-1, y) == f.get_value(x, y-1) == f.get_value(x, y)



def select_bodies(field, num_bodies=15):
    newfield = Field(width=field.width, height=field.height)
    for _ in xrange(num_bodies):
        for _2 in xrange(1000):
            x = random.randint(0, field.width)
            y = random.randint(0, field.height)
            if newfield.get_value(x, y):
                continue
            value = field.get_value(x, y)
            if value:
                field.copy_contiguous(x, y, newfield)
                break
    return newfield


def fill_holes(field, valid=1, fillval=2, aggression=1000):
    for _ in xrange(aggression):
        for _2 in xrange(aggression):
            x = random.randint(0, field.width)
            y = random.randint(0, field.height)
            value = field.get_value(x, y)
            if value != valid:
                continue
            for _3 in xrange(aggression):
                x2 = x + random.randint(0, 10) + random.randint(-10, 0)
                y2 = y + random.randint(0, 10) + random.randint(-10, 0)
                value = field.get_value(x2, y2)
                if value != valid:
                    continue
                x1, x2 = min(x, x2), max(x, x2)
                y1, y2 = min(y, y2), max(y, y2)
                xh, yh = (x1+x2)/2, (y1+y2)/2
                value = field.get_value(xh, yh)
                if value in [valid, fillval]:
                    continue
                field.set_value(xh, yh, fillval)
                break
            break


def generate_cellular_world(seed=None):
    if seed is not None:
        random.seed(seed)
    f = Field(width=252, height=252)
    add_noise(f, rate=0.25)
    scores = [[2, 3, 0, 3, 2],
              [3, 5, 2, 5, 3],
              [0, 2, 7, 2, 0],
              [3, 5, 2, 5, 3],
              [2, 3, 0, 3, 2]]

    ruleset = create_ruleset(scores, 1)
    for _ in xrange(5):
        f = evaluate_ruleset(f, ruleset, 22)

    num_bodies = random.randint(random.randint(1, 10), 10) + random.randint(0, random.randint(0, 20))
    smooth_field(f)
    f = select_bodies(f, num_bodies=num_bodies)
    fill_holes(f, aggression=250)

    scores = [[1, 1, 1, 1, 1],
              [1, 1, 1, 1, 1],
              [1, 1, 1, 1, 1],
              [1, 1, 1, 1, 1],
              [1, 1, 1, 1, 1]]
    ruleset = create_ruleset(scores, valids=[1, 2])
    for _ in xrange(random.randint(10, 20)):
        f = evaluate_ruleset(f, ruleset, 12, valid=[0, 2], adjacents=[2], livevalue=2)

    smooth_field(f, tilevalue=2, altvalue=0)

    return f.get_bordered_line(256, 256)

if __name__ == "__main__":
    if len(argv) > 1:
        random.seed(int(argv[1]))
    #f = Field(width=16, height=16)
    #f = Field(width=128, height=128)
    f = Field(width=252, height=252)
    add_noise(f, rate=0.25)
    #add_noise_center(f)
    #ruleset = create_ruleset([[3, 2, 3],
    #                          [2, 3, 2],
    #                          [3, 2, 3]], 1)
    scores = [[0, 1, 0],
              [1, 5, 1],
              [0, 1, 0]]
    scores = [[5, 2, 5],
              [2, 7, 2],
              [5, 2, 5]]
    scores = [[1, 5, 3, 5, 1],
              [5, 1, 3, 1, 5],
              [3, 3, 5, 3, 3],
              [5, 1, 3, 1, 5],
              [1, 5, 3, 5, 1]]
    scores = [[2, 3, 0, 3, 2],
              [3, 5, 2, 5, 3],
              [0, 2, 7, 2, 0],
              [3, 5, 2, 5, 3],
              [2, 3, 0, 3, 2]]
    ruleset = create_ruleset(scores, 1)
    print f
    print
    for _ in xrange(5):
        f = evaluate_ruleset(f, ruleset, 22)
    print f
    print
    num_bodies = random.randint(random.randint(1, 10), 10) + random.randint(0, random.randint(0, 20))
    smooth_field(f)
    f = select_bodies(f, num_bodies=num_bodies)
    print f
    print
    fill_holes(f, aggression=250)
    print f
    print
    scores = [[1, 1, 1, 1, 1],
              [1, 1, 1, 1, 1],
              [1, 1, 1, 1, 1],
              [1, 1, 1, 1, 1],
              [1, 1, 1, 1, 1]]
    ruleset = create_ruleset(scores, valids=[1, 2])
    for _ in xrange(random.randint(10, 20)):
        f = evaluate_ruleset(f, ruleset, 12, valid=[0, 2], adjacents=[2], livevalue=2)
    smooth_field(f, tilevalue=2, altvalue=0)
    print f
    print
