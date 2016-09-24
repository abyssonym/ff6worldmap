from decompress2 import Decompressor
from terrain_generator import generate_cellular_world
from subprocess import call
from sys import argv, stdout
from time import sleep, time
from collections import defaultdict
from itertools import product
from bisect import insort
from os import path
import random


try:
    from sys import _MEIPASS
    REFERENCE_FILENAME = path.join(_MEIPASS, "reference.txt")
except ImportError:
    REFERENCE_FILENAME = "reference.txt"


def weighted_choice(weighted, root=False):
    if root:
        weighted = [(c, w**0.5) for (c, w) in weighted]
    maximum = sum([w for (c, w) in weighted])
    index = random.random() * maximum
    total = 0
    for c, w in weighted:
        total += w
        if index <= total:
            return c


def create_map_image(data):
    for i in xrange(0x100):
        row = data[(i*0x100):((i+1)*0x100)]
        cmd = ["convert", "+append"]
        for tile in row:
            cmd += ["images/tile_{0:0>2}.png".format("%x" % ord(tile))]
        cmd += ["row%x.png" % i]
        call(cmd)

    cmd = ["convert", "-append"]
    for i in xrange(0x100):
        cmd += ["row%x.png" % i]
    cmd += ["world_map_final.png"]
    call(cmd)
    call("rm row*.png", shell=True)


def generate_markov(data):
    markov = {}
    for index in xrange(0x10000):
        if index % 256 == 0 or index - 256 < 0:
            continue
        top = ord(data[index-0x100])
        left = ord(data[index-1])
        me = ord(data[index])
        key = (top, left, me)
        if key not in markov:
            markov[key] = 0
        markov[key] += 1
    return markov


def get_5gram(index, data, default=None):
    top = data[index-0x100] if index >= 0x100 else default
    bottom = data[index+0x100] if index < len(data)-0x100 else default
    left = data[index-1] if index % 0x100 else default
    right = data[index+1] if index % 0x100 != 0xFF else default
    middle = data[index]
    return top, bottom, left, right, middle


validict = defaultdict(set)


def generate_validators(data, default=6, reference=None):
    for index in xrange(0x10000):
        top, bottom, left, right, middle = get_5gram(index, data,
                                                     default=default)
        top = ord(top) if not isinstance(top, int) else top
        bottom = ord(bottom) if not isinstance(bottom, int) else bottom
        left = ord(left) if not isinstance(left, int) else left
        right = ord(right) if not isinstance(right, int) else right
        middle = ord(middle) if not isinstance(middle, int) else middle
        validict["top-bottom"].add((top, middle))
        validict["left-right"].add((left, middle))
        validict["top-left"].add((top, left))
        validict["top-left"].add((bottom, right))
        validict["top-right"].add((top, right))
        validict["top-right"].add((bottom, left))
    if reference is not None:
        for key in validict:
            validict[key] = [(a, b) for (a, b) in validict[key]
                             if reference[a] >= 0 and reference[b] >= 0]
    return validict


shorthand_cats = {"tb": "top-bottom", "lr": "left-right"}
valicache = {}
def getvalb(category, agroup, bgroup=None, get_first=False):
    if not hasattr(agroup, "__getitem__"):
        agroup = frozenset([agroup])
    elif not isinstance(agroup, frozenset):
        agroup = frozenset(agroup)

    if bgroup is not None:
        if not hasattr(bgroup, "__getitem__"):
            bgroup = frozenset([bgroup])
        elif not isinstance(bgroup, frozenset):
            bgroup = frozenset(bgroup)

    key = (category, agroup, bgroup, get_first)
    try:
        result = valicache[key]
    except KeyError:
        try:
            category = shorthand_cats[category]
        except KeyError:
            pass
        if not get_first:
            result = sorted(set([d for (c, d) in validict[category]
                                 if c in agroup]))
        else:
            result = sorted(set([c for (c, d) in validict[category]
                                 if d in agroup]))
        if bgroup is not None:
            result = [a for a in result if a in bgroup]
        valicache[key] = result

    return result


def generate_map(suggestion, reference, weights, default=6):
    global NotImplementedError
    worldmap = [default] * 0x10000
    index = 0

    def next_row_default(cands, distance):
        if distance == 0:
            return [c for c in cands if c == default]
        defcands = getvalb("tb", default, cands, get_first=True)
        altcands = [b for b in getvalb("tb", cands) if b != default]
        altcands = next_row_default(sorted(set(altcands)), distance-1)
        altcands = getvalb("tb", altcands, cands, get_first=True)
        return [c for c in cands if c in defcands + altcands]

    assert next_row_default([0x22], 100)

    def assign_tile(i, redo=False):
        tx, _, lx, rx, mx = get_5gram(i, worldmap, default=default)
        cands = getvalb("tb", tx)
        cands = getvalb("lr", lx, cands)

        distance = 0xFF - (i >> 8)
        if 1 <= distance <= 4:
            bcands = getvalb("tb", cands)
            lbcands = getvalb("tb", lx)
            bcands = next_row_default(bcands, distance-1)
            lbcands = next_row_default(lbcands, distance-1)
            bcands = getvalb("lr", lbcands, bcands)
            temp = getvalb("tb", bcands, cands, get_first=True)
            if not temp:
                return 1
            cands = temp
        elif distance <= 0:
            cands = getvalb("tb", default, cands, get_first=True)

        if not cands:
            raise NotImplementedError

        if i % 0x100 < 0xFF:
            txx, _, _, _, _ = get_5gram(i+1, worldmap, default=default)
            rcands = getvalb("lr", cands)
            temp = getvalb("tb", txx, rcands)
            if not temp:
                assert i >= 0x100
                txx, _, lxx, rxx, mxx = get_5gram(i-0xFF, worldmap,
                                                default=default)
                necands = getvalb("tb", txx)
                necands = getvalb("lr", lxx, necands)
                necands = getvalb("lr", rxx, necands, get_first=True)
                necands = getvalb("tb", rcands, necands, get_first=True)
                necands = [m for m in necands if m != mxx]
                if not necands:
                    return 1
                txx = random.choice(necands)
                assert worldmap[i-0xFF] != txx
                worldmap[i-0xFF] = txx
                rcands = getvalb("tb", txx, rcands)
            else:
                rcands = temp
            assert rcands
            cands = getvalb("lr", rcands, cands, get_first=True)
            assert cands
        else:
            rcands = [default]
            cands = getvalb("lr", rcands, cands, get_first=True)
            if not cands:
                return 1

        cands = sorted(set(cands))
        weighted_options = []
        for c in cands:
            sugg = suggestion[i]
            weight = weights[c]
            if c != default:
                weight = weight ** 0.75
            assert sugg in reference
            if reference[c] == sugg:
                weight *= 1000
            if i % 0x100 != 0xFF:
                rsugg = suggestion[i+1]
                if any([reference[r] == rsugg for r in getvalb("lr", c)]):
                    weight *= 10
            if i >> 8 != 0xFF:
                bsugg = suggestion[i+0x100]
                if any([reference[b] == bsugg for b in getvalb("tb", c)]):
                    weight *= 10
            if i % 0x100 != 0xFF and i >> 8 != 0xFF:
                rbsugg = suggestion[i+0x101]
                rbcands = getvalb("lr", c)
                rbcands = getvalb("tb", rbcands)
                rbcands = getvalb("lr", getvalb("tb", c), rbcands)
                if any([reference[rb] == rbsugg for rb in rbcands]):
                    weight *= 10
            if c != default or sugg != 0:
                # reweight to compensate for commonly repeating tiles
                did_one = False
                check = i-0xFF
                if (check >= 0 and check >> 8 == (i >> 8)-1
                        and worldmap[check] == c):
                    did_one = True
                if not did_one:
                    counter = 0
                    while True:
                        counter += 1
                        check = i-counter
                        if (check >= 0 and check >> 8 == i >> 8
                                and worldmap[check] == c):
                            weight /= 1.5
                            did_one = True
                        else:
                            break
                if not did_one:
                    counter = 0
                    while True:
                        counter += 1
                        check = i-(counter*0x100)
                        if check >= 0 and worldmap[check] == c:
                            weight /= 2.0
                            did_one = True
                        else:
                            break
                if not did_one:
                    counter = 0
                    while True:
                        counter += 1
                        check = i-(counter*0x101)
                        if (check >= 0
                                and check >> 8 == (i >> 8)-1
                                and worldmap[check] == c):
                            weight /= 3.0
                            did_one = True
                        else:
                            break
                '''
                if i >= 0x100:
                    _, _, lxx, rxx, mxx = get_5gram(i-0x100, worldmap,
                                                    default=default)
                    if rxx == c:
                        weight *= 1.0
                    if mxx == c:
                        weight /= 20.0
                    if lxx == c:
                        weight /= 40.0
                if lx == c:
                    weight /= 10.0
                '''
            weight = max(weight, 1)
            assert weight > 0
            weighted_options.append((c, weight))
        chosen = weighted_choice(weighted_options)
        worldmap[i] = chosen
        return 0

    order_index = 0
    failcounter = 0
    prevfail = 0
    counter = 0
    blocksize = len(worldmap) / 100
    starttime = time()
    try:
        while True:
            #index = ordering[order_index]
            index = order_index
            i = index
            success = assign_tile(i)

            if success in [1, 2] and i % 0x100:
                width = i % 0x100
                assert width
                i = random.randint(i-width, i-1)
                if i >> 8 == prevfail:
                    failcounter += 1
                    if not failcounter % 50:
                        if random.randint(0, 49):
                            i -= 0x100
                        else:
                            i -= 0x200
                        assert i > 0
                else:
                    failcounter = 0
                prevfail = (i >> 8)
                order_index = i

            if success == 0:
                order_index += 1
            if order_index >= len(worldmap):
                break
            if order_index / blocksize > counter:
                counter = order_index / blocksize
                stdout.write("{0: >3}".format(100-counter))
                if not counter % 10:
                    stdout.write("\n")
                stdout.flush()
                if counter == 100:
                    difference = time() - starttime
                    print "Completed. Elapsed time: %ss" % int(
                        round(difference))
    except (KeyboardInterrupt, NotImplementedError):
        while order_index < len(worldmap):
            worldmap[order_index] = 0
            order_index += 1
        sleep(2)
    return worldmap


def deinterleave_4bpp(data):
    data = map(ord, data)
    tiles = []
    for i in xrange(1000):
        tile = data[i*32:(i+1)*32]
        if not tile:
            break
        tiles.append(tile)

    newtiles = []
    for tile in tiles:
        rows = []
        for i in xrange(8):
            interleaved = (tile[i*2], tile[(i*2)+1],
                           tile[(i*2)+16], tile[(i*2)+17])
            row = []
            for j in xrange(7, -1, -1):
                pixel = 0
                mask = 1 << j
                for k, v in enumerate(interleaved):
                    pixel |= bool(v & mask) << k
                row.append(pixel)
            rows.append(row)
        newtiles.append(rows)
    return newtiles


def reinterleave_4bpp(tiles):
    newtiles = []
    for tile in tiles:
        newtile = [0]*32
        for i, row in enumerate(tile):
            for j, pixel in enumerate(row):
                j = 7 - j
                a = int(bool(pixel & 1))
                b = int(bool(pixel & 2))
                c = int(bool(pixel & 4))
                d = int(bool(pixel & 8))
                newtile[(i*2)] |= (a << j)
                newtile[(i*2)+1] |= (b << j)
                newtile[(i*2)+16] |= (c << j)
                newtile[(i*2)+17] |= (d << j)
        newtiles.extend(newtile)
    return "".join(map(chr, newtiles))


def map_to_tiles(data):
    width, height = 64, 64
    assert width % 8 == height % 8 == 0
    tiles = []
    for y in xrange(height/8):
        for x in xrange(width/8):
            tile = []
            for j in xrange(8):
                row = []
                for i in xrange(8):
                    index = (((y*8)+j)*width) + (x*8) + i
                    row.append(data[index])
                tile.append(row)
            tiles.append(tile)
    return tiles


def rerow_tiles(tiles):
    rows = []
    for i in xrange(8):
        rows.append(tiles[(i*8):((i+1)*8)])
    tiles = []
    tiles.extend(rows[0])
    tiles.extend(rows[2])
    tiles.extend(rows[1])
    tiles.extend(rows[3])
    tiles.extend(rows[4])
    tiles.extend(rows[6])
    tiles.extend(rows[5])
    tiles.extend(rows[7])
    return tiles


def map_to_palette(data, reference, valuemap, scale=(1, 4)):
    lowval, highval = scale
    difference = highval - lowval
    lowsum = min(valuemap.values()) * 16
    highsum = max(valuemap.values()) * 16
    sumdiff = highsum - lowsum
    mapfunc = lambda s: int(
            round((s-lowsum)*difference/float(sumdiff) + lowval))
    palmap = []
    for y in xrange(64):
        y = 4 * y
        for x in xrange(64):
            x = 4 * x
            values = []
            for i, j in product(range(4), range(4)):
                index = ((y+j)*0x100)+x+j
                values.append(data[index])
            values = [valuemap[reference[v]] for v in values]
            palmap.append(mapfunc(sum(values)))
    return palmap


def generate_world_mini_map(filename, seed):
    pointer = 0x2ED434
    maxaddr = 0x2F114F
    d = Decompressor(pointer, fakeaddress=0, maxaddress=maxaddr)
    d.read_data(filename)
    markov = generate_markov(d.data)
    markov = markov.items()
    weights = defaultdict(int)
    for ((t, l, m), v) in markov:
        weights[m] += v

    reference = "".join([line.strip() for line in
                         open(REFERENCE_FILENAME).readlines()])
    reference = [int(c) if c != "x" else -1 for c in reference]
    generate_validators(d.data, reference=reference)
    validict["left-right"] = [(a, b) for (a, b) in validict["left-right"]
        if a not in [0x17, 0x68, 0x16, 0x26, 0xE0, 0xF0, 0xCE, 0xDE]
        or b not in [0x19, 0x6A, 0x17, 0x27, 0xE1, 0xF1, 0xCF, 0xDF]]
    for key in validict:
        validict[key] = [(a, b) for (a, b) in validict[key] if
                           reference[a] >= 0 and reference[b] >= 0]

    print "Generating map shapes."
    cellworld = generate_cellular_world(seed)
    print "Generating map data."
    worldmap = generate_map(suggestion=cellworld,
                            reference=reference, weights=weights)
    valuemap = {0: 0, 1: 1, 2: 0.5}
    palmap = map_to_palette(worldmap, reference, valuemap)
    tiles = map_to_tiles(palmap)
    tiles = rerow_tiles(tiles)
    minimap = reinterleave_4bpp(tiles)

    #import pdb; pdb.set_trace()
    #create_map_image(d.data)
    #create_map_image("".join(map(chr, worldmap)))

    return "".join(map(chr, worldmap)), minimap

if __name__ == "__main__":
    sourcefile = argv[1]
    if len(argv) > 2:
        seed = int(argv[2])
    else:
        seed = 696969

    generate_world_mini_map(sourcefile, seed)

    '''
    fakeaddr = 0x0
    #pointer = 0x2FE49B
    #maxaddr = 0x2FE8B3
    pointer = 0x2FE8B3
    maxaddr = 0x2FED26
    de = Decompressor(pointer, fakeaddress=fakeaddr, maxaddress=maxaddr)
    de.read_data(sourcefile)
    hexify = lambda data: " ".join(map(hex, map(ord, data)))
    newdata = reinterleave_4bpp(deinterleave_4bpp(de.data))
    assert de.data == newdata

    #pointer = 0x2F6A56
    #maxaddr = 0x2F9D17
    '''
