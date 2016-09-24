from randomtools.utils import read_multi, write_multi
from sys import argv
from shutil import copyfile


class CompressedBuffer:
    def __init__(self, bytestring):
        self.bytestring = bytestring
        self.result = ""
        self.buff = [chr(0)] * 0x800  # ff6 decomp alg initializes to 0
        self.buffaddr = 0x7DE

    def get_next_byte(self):
        byte, self.bytestring = self.bytestring[0], self.bytestring[1:]
        return byte

    def push_next_byte(self, byte):
        self.result += byte
        self.buff[self.buffaddr] = byte
        self.buffaddr = (self.buffaddr + 1) % 0x800

    def get_push(self):
        self.push_next_byte(self.get_next_byte())

    def get_seekaddr_length(self):
        low = ord(self.get_next_byte())
        high = ord(self.get_next_byte())
        length = ((high & 0xF8) >> 3) + 3
        seekaddr = low | ((high & 0x07) << 8)
        if self.buffaddr == seekaddr:
            raise Exception("buffaddr equals seekaddr")
        return seekaddr, length

    def get_buffered(self, seekaddr, length):
        loop_length = (self.buffaddr - seekaddr) % len(self.buff)
        subbuff = (self.buff+self.buff)[seekaddr:seekaddr+loop_length]
        assert None not in subbuff
        while len(subbuff) < length:
            subbuff = subbuff + subbuff
        subbuff = "".join(subbuff)
        copied = "".join(subbuff[:length])
        assert len(copied) == length
        return copied

    def decompress_segment(self):
        flags = ord(self.get_next_byte())
        for i in xrange(8):
            if not self.bytestring:
                print "WARNING: Ran out of compressed data."
                break

            if flags & (1 << i):
                self.get_push()
                continue

            seekaddr, length = self.get_seekaddr_length()
            copied = self.get_buffered(seekaddr, length)
            for byte in copied:
                self.push_next_byte(byte)

    def decompress(self):
        while self.bytestring:
            self.decompress_segment()
        return self.result


class RecompressBuffer:
    def __init__(self, bytestring):
        self.bytestring = bytestring
        self.result = ""
        self.buff = [chr(0)] * 0x800
        self.buffaddr = 0x7DE

    def push_next_byte(self):
        byte, self.bytestring = self.bytestring[0], self.bytestring[1:]
        self.buff[self.buffaddr] = byte
        self.buffaddr = (self.buffaddr + 1) % 0x800

    def push_data(self, data):
        assert self.bytestring.startswith(data)
        for byte in data:
            self.push_next_byte()

    def compress_segment(self):
        flags = 0x00
        segment = ""
        for i in xrange(8):
            if not self.bytestring:
                # TODO: verify whether these flags should be set
                # They don't appear to be set at the end of the original data
                # flags |= (1 << i)
                continue

            searchbuff = self.buff + self.buff
            location, length = None, None
            for j in xrange(34, 2, -1):
                if j > len(self.bytestring):
                    continue
                searchstr = self.bytestring[:j]
                for k in xrange(j, 0, -1):
                    lower = (self.buffaddr-k)%0x800
                    if lower > self.buffaddr:
                        upper = self.buffaddr + 0x800
                    else:
                        upper = self.buffaddr
                    loopstr = searchbuff[lower:upper]
                    loopstr2 = searchstr[:k]
                    if loopstr is None or None in loopstr:
                        continue
                    loopstr, loopstr2 = "".join(loopstr), "".join(loopstr2)
                    if loopstr == loopstr2:
                        loops = (len(searchstr) / len(loopstr)) + 1
                        if (loopstr * loops).startswith(searchstr):
                            location = (self.buffaddr-k) % 0x800
                            length = j
                            assert length >= (self.buffaddr-location) % 0x800
                            break
                else:
                    continue
                break

            substr = None
            for j in xrange(0x800):
                if location is not None and length is not None:
                    break
                if searchbuff[j] != self.bytestring[0]:
                    continue
                if j == self.buffaddr:
                    continue
                if j > self.buffaddr:
                    upper_bound = self.buffaddr
                else:
                    upper_bound = self.buffaddr
                for k in xrange(j+34, j+2, -1):
                    if k >= upper_bound:
                        continue
                    substr = searchbuff[j:k]
                    assert 3 <= len(substr) <= 34
                    if None in substr:
                        continue
                    substr = "".join(substr)
                    if self.bytestring.startswith(substr):
                        location = j
                        length = len(substr)
                        searchstr = substr
                        break

            if location is None and length is None:
                flags |= (1 << i)
                byte = self.bytestring[0]
                segment += byte
                self.push_data(byte)
            else:
                assert (length-3) == (length-3) & 0b11111
                assert location == location & 0x7FF
                value = location | ((length-3) << 11)
                high, low = (value >> 8), (value & 0xFF)
                segment += chr(low)
                segment += chr(high)
                self.push_data(searchstr)
        self.result += chr(flags) + segment

    def compress(self):
        while self.bytestring:
            self.compress_segment()
        return self.result


def decompress_at_location(filename, address):
    f = open(filename, 'r+b')
    f.seek(address)
    size = read_multi(f, length=2)
    print "Size is %s" % size
    bytestring = f.read(size-2)
    decompressed = CompressedBuffer(bytestring).decompress()
    return decompressed, bytestring


class Decompressor():
    def __init__(self, address, fakeaddress=None, maxaddress=None):
        self.address = address
        self.fakeaddress = fakeaddress
        self.maxaddress = maxaddress
        self.data = None

    def read_data(self, filename):
        self.data, self.source_data = decompress_at_location(filename, self.address)
        self.backup = str(self.data)
        #assert decompress(recompress(self.backup)) == self.backup

    def writeover(self, address, to_write):
        to_write = "".join([chr(c) if type(c) is int else c for c in to_write])
        if self.fakeaddress:
            address = address - self.fakeaddress
        self.data = (self.data[:address] + to_write +
                     self.data[address+len(to_write):])

    def get_bytestring(self, address, length):
        if self.fakeaddress:
            address = address - self.fakeaddress
        return map(ord, self.data[address:address+length])

    def compress_and_write(self, filename):
        compressed = RecompressBuffer(self.data).compress()
        size = len(compressed)
        #print "Recompressed is %s" % size
        f = open(filename, 'r+b')
        if self.maxaddress:
            length = self.maxaddress - self.address
            f.seek(self.address)
            f.write("".join([chr(0xFF)]*length))
        f.seek(self.address)
        write_multi(f, size+2, length=2)
        f.write(compressed)
        if self.maxaddress and f.tell() >= self.maxaddress:
            raise Exception("Recompressed data out of bounds.")
        f.close()

if __name__ == "__main__":
    sourcefile = argv[1]
    fakeaddr = 0x0
    #pointer = 0x2FE49B
    #maxaddr = 0x2FE8B3
    pointer = 0x2FE8B3
    maxaddr = 0x2FED26
    de = Decompressor(pointer, fakeaddress=fakeaddr, maxaddress=maxaddr)
    de.read_data(sourcefile)
    for i in xrange(64):
        print "{0:0>2}".format(i),
        for byte in de.data[i*32:(i+1)*32]:
            print "{0:0>2}".format("%x" % ord(byte)),
        print
    import pdb; pdb.set_trace()
    exit(0)

    outfile = argv[2]
    copyfile(sourcefile, outfile)
    d = Decompressor(pointer, fakeaddress=fakeaddr, maxaddress=maxaddr)
    d.read_data(sourcefile)
    hexify = lambda stuff: " ".join(["{0:0>2}".format("%x" % ord(c)) for c in stuff])
    world_map = []
    for i in xrange(256):
        world_map.append(d.data[(i*256):((i+1)*256)])
    #for row in world_map:
    #    print hexify(row[:48])
    compressed = RecompressBuffer(d.data).compress()
    redecompressed = CompressedBuffer(compressed).decompress()
    print redecompressed[:len(d.data)] == d.data
    print len(compressed)
    print len(compressed) - (maxaddr - pointer)
    for data in [d.source_data, compressed]:
        print len(data), hexify(data[:32])
    import pdb; pdb.set_trace()
