from sys import argv
from time import time
from shutil import copyfile
from world_mapper import generate_world_mini_map
from decompress2 import Decompressor
from randomtools.utils import write_multi

def main():
    if len(argv) > 1:
        filename = argv[1]
    else:
        filename = raw_input("Filename? ")

    if len(argv) > 2:
        seed = argv[2]
    else:
        seed = raw_input("Seed? ")

    if seed == "":
        seed = int(time())
    else:
        seed = int(seed)

    if not filename.strip():
        raise IOError("Please provide a valid filename.")

    f = open(filename, 'r+b')
    f.close()

    outfile, extension = filename.rsplit(".", 1)
    outfile = ".".join([outfile, "%s" % seed, extension])
    copyfile(filename, outfile)

    world_map, mini_map = generate_world_mini_map(filename, seed)
    wm_ptr = 0x2F4A46
    mm_ptr = 0x2FE59B
    dec = Decompressor(wm_ptr, maxaddress=0x2FC624)
    dec.data = world_map
    print "Compressing world map data."
    dec.compress_and_write(outfile)
    dec = Decompressor(mm_ptr, maxaddress=0x2FED26)
    dec.data = mini_map
    dec.compress_and_write(outfile)

    f = open(outfile, 'r+b')
    f.seek(0x2EB20F)
    write_multi(f, 0xC00000 | wm_ptr, length=3)
    f.seek(0x2EB24B)
    write_multi(f, 0xC00000 | mm_ptr, length=3)

    f.seek(0xC9A4F)
    f.write("".join(map(chr, [
        0xB2, 0xE3, 0xF5, 0x00,     # start on airship
        0x41, 0x00,                 # show terra
        0xD2, 0xB9,                 # airship appears on world map
        0xFE,
        ])))
    f.seek(0xAF53A)
    f.write("".join(map(chr, [
        0xC0, 0x27, 0x01, 0x6E, 0xF5, 0x00,     # able to use airship
        ])))
    f.seek(0xA5E8E)
    f.write("".join(map(chr, [0xFD]*4)))        # remove intro
    f.seek(0x4E2D)
    f.write("".join(map(chr, [0x80, 0x00])))    # always sprinting
    f.close()
    raw_input("Finished successfully. Press enter to close this program. ")

if __name__ == "__main__":
    try:
        main()
    except Exception, e:
        print "ERROR: %s" % e.__repr__()
        raw_input("Press enter to close this program. ")
