import zlib
import os
import sys
import time
import math
import random


# Class for the PNG file. Supports reading and writing a PNG, as well as encoding and decoding stegonographically hidden data.
# When the class is initialised (with the filaname of the PNG) it reads the IHDR block of the PNG, but nothing else.
# "public" methods:
#  - read(): Reads the PNG file, returning the image data
#  - get_max_hidden_filesize(): Returns the maximum size in bytes of a file that can be hidden
#    in the PNG (so you can check if the file you want to hide can fit inside the image)
#  - write(filename): writes to a PNG file
#  - encode(filename): Encodes a file (filename) into the PNG using steganography
#  - decode(filename (optional)): extracts a stegonagraphically hidden file from the PNG.
#    If filename is given, this will be the name of the output file, else it defaults to the
#    filename of the file that was hidden
class PNG:
    # variables held in the object

    # the input image file
    inputfile = None
    # the input image file object
    inputfileobject = None
    
    #The output file
    outputfile = None
    #the output file object
    outputfileobject = None

    # list for all the chunks except for the IDAT chunks and IEND
    chunks = []
    # list for the IDAT chunks
    idats = []
    # the IEND chunk
    iend = None

    # properties from IHDR
    width = None
    height = None
    bitdepth = None
    colour = None
    compression = None
    filter = None
    interlace = None

    # number of rows and columns (in bytes) in image
    nrows = None
    ncols = None
    # number of bytes per pixel
    bytesperpixel = None
    # number of colour channels
    channels = None
    # size of the image in bytes
    imgsize = None

    # the uncompressed image data (int array)
    uncompressed = None
    # the compressed image data (before writing)
    compressed = None
    # the image itself (nrow x ncol int array)
    img = None

    # number of bits per byte for hiding the steganographic data
    bits = None
    # max size of a filename for a steganographic file
    filenamesize = 30
    # identifier for a PNG containing a steganographic file
    identifier = "SECRET".encode("ascii")
    # length of the header steganographically written into the image data (4 = # bytes for the count variable)
    headerlength = len(identifier) + 4 + filenamesize
    # maximum size of a file that can be hidden in the PNG
    maxsecretfilesize = None

    # Checks that the imgfile is a valid PNG file, reads in its IDAT chunk, and computes some
    def __init__(self, imgfile):
        # check the file exists
        if os.path.exists(imgfile):
            self.inputfile = imgfile
        else:
            raise FileNotFoundError("Cannot open '%s'. File does not exist" % imgfile)

        # open the file
        self.inputfileobject = open(self.inputfile, "rb")

        # read the file's magic number, and check that it matches that of a PNG file
        num = self.inputfileobject.read(8)
        if num != bytearray.fromhex("89504e470d0a1a0a"):
            raise Exception("'%s' does not appear to be a PNG file" % self.inputfile)

        # read the IHDR
        ihdr = next(self._read_chunk())

        # add ihdr to the list of chunks
        self.chunks.append(ihdr)

        # parse it
        self._parse_IHDR(ihdr)

    # reads a PNG file, returning the image data (as a 2d int array containing the image byte values)
    def read(self):
        if self.img is not None:
            raise Exception("'%s' has already been read in" % self.inputfile)

        # read in all the chunks
        self._read_chunks()

        # close the file
        self.inputfileobject.close()

        # extract and uncompress the IDAT blocks
        self._uncompress_data()

        # de-filter
        self._unfilter()

    # writes the png data (self.img) to a png file of name outputfile
    def write(self, outputfile):
        if self.img is None:
            raise Exception("'%s' has not been read in yet." % self.inputfile)
        self.outputfile = outputfile

        # filter self.img
        self._filter()

        # compress the data for writing
        self._compress()

        # create the idats
        self._create_idats()

        # write the file
        self._write_png()

    # encodes a file (filename) into the image
    def encode(self, filename):
        if self.img is None:
            raise Exception("'%s' has not been read in yet." % self.inputfile)
        print("\nEncoding")

        # get the name of the file (ignoring any path)
        # This name is encoded into the PNG along with the file's contents
        file = os.path.basename(filename)

        if len(file) > self.filenamesize:
            raise Exception(
                "The file to be compressed, '%s', must have a filename of less than %d characters"
                % (file, self.filenamesize)
            )

        filesize = os.path.getsize(filename)
        if filesize > self.maxsecretfilesize:
            raise Exception(
                "'%s' is too large to be placed into the PNG.The maximum filesize is %d"
                % (file, self.maxsecretfilesize)
            )

        # size of one encoded byte in image bytes
        onebyte = 8 // self.bits
        print("  One byte of encoded data = %d bytes of image data" % onebyte)

        # read the contents of the file to be encoded
        f = open(filename, "rb")
        secretdata = f.read()
        f.close()

        size = len(secretdata)

        # 4 byte header - describes this PNG as one containing hidden data
        HDR = self.identifier

        # 4 bytes giving the size of the encoded data
        sizeb = size.to_bytes(4, "big")

        # 20 bytes/chars giving the filename of the hidden file
        fileheader = " " * (self.filenamesize - len(file)) + file

        # The full "message", containing the above metadata and contants of the file (as a bytes object)
        message = HDR + sizeb + fileheader.encode("ascii") + secretdata

        # the total length of the message (file contents plus metadata) in bytes
        msgsize = len(message)
        # the length of the message in image bytes
        msgsizebytes = msgsize * onebyte

        counter = 0
        bar = progress_bar()

        # put the message into the last 'bits' bits of each byte in the image. After the end of the message, put in random bits
        for row in range(self.nrows):
            for col in range(self.ncols):

                # extract the byte from the array
                imgbyte = self.img[row][col]

                # clear out the leftmost bits we will fill with the new data
                imgbyte >>= self.bits
                imgbyte <<= self.bits

                if counter >= msgsizebytes:
                    # We are past the main file. Fill the remainder with random bits
                    msgbyte = random.randrange(256)
                else:
                    # extract the appropriate byte from the message
                    msgbyte = message[counter // onebyte]

                # Shift the message byte left until the bits we are interested in are at the left of the byte
                msgbyte >>= (onebyte - 1 - counter % onebyte) * self.bits

                # mask the byte so everything is zero but the bits we want
                msgbyte &= (2 ** self.bits) - 1

                # add the message bits into the image byte
                imgbyte += msgbyte

                self.img[row][col] = imgbyte

                counter += 1
            bar.update((row + 1) / self.nrows)
        print("  Done!")

    # extract a file hidden in the PNG image data
    def decode(self, outfile=None):
        if self.img is None:
            raise Exception("'%s' has not been read in yet." % self.inputfile)

        print("\nDecoding")

        # size of one encoded byte in image bytes
        onebyte = 8 // self.bits
        print("  One byte of encoded data = %d bytes of image data" % onebyte)

        bar = progress_bar()

        counter = 0
        data = []
        for row in range(self.nrows):
            for col in range(self.ncols):

                if counter % onebyte == 0:
                    # initialise the byte we're reading our data into
                    databyte = 0

                # create mask in left most bits that defines the shape we want to extract
                mask = 2 ** self.bits - 1
                # extract the next byte from the image data
                imgbyte = self.img[row][col]

                # mask this to just get the bits we're interested in
                imgbyte &= mask

                # shift the bits to the correct position
                imgbyte <<= (onebyte - 1 - counter % onebyte) * self.bits

                # add this to the databyte
                databyte += imgbyte

                if counter % onebyte == (onebyte - 1):
                    data.append(databyte)
                counter += 1

            bar.update((row + 1) / self.nrows)

        # convert the data (currently an array of ints) to bytes
        data = bytes(data)

        nident = len(self.identifier)

        header = data[0:nident]
        if header != self.identifier:
            raise FileNotFoundError("There is no hidden data in this PNG")
        else:
            print("  There is hidden data in this file!")

        datalength = int.from_bytes(data[nident : nident + 4], "big")
        print("  Length of hidden data: %s bytes" % formatInt(datalength))
        filename = (
            data[nident + 4 : nident + 4 + self.filenamesize].decode("ascii").strip()
        )

        # if we specified a filename for the hidden data, write it to this, otherwise use the
        # filename extracted from the image data
        if outfile != None:
            filename = outfile

        filecontents = data[self.headerlength : self.headerlength + datalength]
        print("  Writing to '%s'" % filename)

        f = open(filename, "wb")
        f.write(filecontents)
        f.close()

        print("  Done!")

    # reads a chunk and returns it
    # If at the end of the file, returns False
    def _read_chunk(self):
        while True:
            # the size in bytes of th next chunk
            sbytes = self.inputfileobject.read(4)

            # if thiz is zero bytes long, we have reached EOF
            if len(sbytes) == 0:
                break

            size = int.from_bytes(sbytes, "big")
            name = self.inputfileobject.read(4).decode("ascii")
            data = self.inputfileobject.read(size)
            crc = self.inputfileobject.read(4)

            chunk = Chunk(name, size, data, crc)

            yield chunk

    # reads all the remaining chunks in the file, placing them into self.chunks or self.idats as appropriate
    def _read_chunks(self):
        print("\nReading chunks")
        for chunk in self._read_chunk():
            if chunk.name == "IDAT":
                self.idats.append(chunk)
            else:
                self.chunks.append(chunk)

        # print out some info on the chunks in the file
        for chunk in self.chunks:
            print("  %s: %d bytes" % (chunk.name, chunk.size))

        nidat = len(self.idats)
        size = 0
        for idat in self.idats:
            size += idat.size

        print("  IDAT: %s bytes from %d chunks" % (formatInt(size), nidat))

    # parses the IHDR chunk, and prints out some stats
    def _parse_IHDR(self, ihdr):
        print("\nFile information")
        if ihdr.name != "IHDR":
            raise ValueError(
                "The first chunk in '%s' is not 'IHDR' Got '%s' instead."
                % (self.inputfile, ihdr.name)
            )
        if ihdr.size != 13:
            raise ValueError(
                "IHDR is the wrong size of bytes. Should be 13, but got %d" % ihdr.size
            )

        self.width = int.from_bytes(ihdr.data[0:4], "big")
        self.height = int.from_bytes(ihdr.data[4:8], "big")
        self.bitdepth = ihdr.data[8]
        self.colour = ihdr.data[9]
        self.compression = ihdr.data[10]
        self.filter = ihdr.data[11]
        self.interlace = ihdr.data[12]

        print("  Image dimensions: %d x %d" % (self.width, self.height))
        print("  Bitdepth: %d" % (self.bitdepth))

        # check the size of a pixel in bits, and identify the number of bits we want to use per byte for steganography
        if self.colour == 0:
            # greyscale
            print("  Pixel format: greyscale")
            self.channels = 1
            self.bits = 2
        elif self.colour == 2:
            # RGB
            print("  Pixel format: RGB")
            self.channels = 3
            self.bits = 2
        elif self.colour == 3:
            # indexed - not suitable for steganography
            print("  Pixel format: Indexed")
            self.channels = 1
            self.bits = 1
        elif self.colour == 4:
            # greyscale and alpha
            print("  Pixel format: Greyscale + Alpha")
            self.channels = 2
            self.bits = 2
        elif self.colour == 6:
            # RGB-alpha
            print("  Pixel format: RGB-Alpha")
            self.channels = 4
            self.bits = 2
        else:
            raise ValueError("Unknown Pixel format %d" % self.colour)

        if self.bitdepth < 8:
            raise NotImplementedError("PNGs with bitdepth < 8 not supported")

        if self.interlace != 0:
            raise NotImplementedError("Interlaced PNG files are not supported")

        self.bytesperpixel = self.channels * self.bitdepth // 8

        self.nrows = self.height
        self.ncols = self.width * self.bytesperpixel

        print("  Pixel size: %d bytes" % self.bytesperpixel)

        self.imgsize = self.nrows * self.ncols
        print("  Uncompressed image size: %s bytes" % formatInt(self.imgsize))

        self.maxsecretfilesize = self.imgsize * self.bits / 8 - self.headerlength

        print(
            "  Maximum size of file that can be hidden: %s bytes"
            % formatInt(self.maxsecretfilesize)
        )

    # returns the maximum size of file that can be hidden within the PNG
    def get_max_hidden_filesize(self):
        return self.maxsecretfilesize

    # uncompresses the data from the idats
    def _uncompress_data(self):
        print("\nUncompressing image data")
        decomp_obj = zlib.decompressobj()

        data = bytes()

        print("  Uncompressing from %d IDAT chunks" % (len(self.idats)))
        bar = progress_bar()
        i = 0
        for idat in self.idats:
            if idat.name != "IDAT":
                raise ValueError("Chunk is not an IDAT")
            data += decomp_obj.decompress(idat.data)
            i += 1
            bar.update(i / len(self.idats))
        print("  Uncompressed %s bytes of data" % formatInt(len(data)))

        expected_size = self.nrows * (self.ncols + 1)

        if len(data) != expected_size:
            raise Exception("Extracted data is not the expected size")

        # convert the data to ints
        data = list(data)

        self.uncompressed = []

        for row in range(self.nrows):
            self.uncompressed.append(
                data[row * (self.ncols + 1) : (row + 1) * (self.ncols + 1)]
            )

    # unfilters the data
    def _unfilter(self):
        print("\nUn-filtering image")

        # a list of the filtering methods for each row
        filters = []

        # the filtered image data in form [row][colbytes]. This does not have the preceeding filter byte on each row
        filtered = []

        # get filter type for each row, and convert imgbytes into a list of rows, each one containing ints corresponding to the bytes
        for row in self.uncompressed:
            # #index of the first byte in a row (which is the filter byte)
            # start = row*(self.ncols+1)
            # filters.append(self.uncompressed[start])
            f = row.pop(0)
            filters.append(f)

            # imgrow = self.uncompressed[start+1 : start + self.ncols+1]
            filtered.append(row)

        # list for the unfiltered image data
        img = []

        bar = progress_bar("")

        stride = self.bytesperpixel

        tstart = time.time()

        for row in range(self.nrows):
            img.append([])

            f = filters[row]

            if f == 0:
                for col in range(self.ncols):
                    img[row].append((filtered[row][col]))
            # filter value is the  corresponding byte to the left
            elif f == 1:
                for col in range(self.ncols):
                    if col < stride:
                        img[row].append(filtered[row][col])
                    else:
                        img[row].append(filtered[row][col] + img[row][col - stride])
                        img[row][col] %= 256
            # filter value is the  corresponding byte above
            elif f == 2:
                for col in range(self.ncols):
                    if row == 0:
                        img[row].append(filtered[row][col])
                    else:
                        img[row].append(filtered[row][col] + img[row - 1][col])
                        img[row][col] %= 256
            # filter value is the mean of left and above
            elif f == 3:
                for col in range(self.ncols):
                    if row == 0:
                        up = 0
                    else:
                        up = img[row - 1][col]

                    if col < stride:
                        left = 0
                    else:
                        left = img[row][col - stride]

                    img[row].append(filtered[row][col] + (left + up) // 2)
                    img[row][col] %= 256
            # paeth filter (defaults to left for row=0, and up for col=0)
            elif f == 4:
                for col in range(self.ncols):
                    #  C B
                    #  A X

                    if row == 0:
                        if col < stride:
                            img[row].append(filtered[row][col])
                        else:
                            img[row].append(filtered[row][col] + img[row][col - stride])
                    else:
                        if col < stride:
                            img[row].append(filtered[row][col] + img[row - 1][col])
                        else:
                            a = img[row][col - stride]
                            b = img[row - 1][col]
                            c = img[row - 1][col - stride]

                            p = a + b - c

                            pa = abs(p - a)
                            pb = abs(p - b)
                            pc = abs(p - c)

                            if (pa <= pb) and (pa <= pc):
                                pr = a
                            elif pb <= pc:
                                pr = b
                            else:
                                pr = c

                            img[row].append(filtered[row][col] + pr)
                    img[row][col] %= 256
            bar.update((row + 1) / self.nrows)

        tstop = time.time()

        print("  Un-filtered in %.2f seconds" % (tstop - tstart))

        self.img = img

    # Filters the image in preparaton for being written to file
    def _filter(self, filtertype=4):
        print("\nFiltering image data")

        # list for the filtered data
        filtered = []

        stride = self.bytesperpixel

        bar = progress_bar("")

        start = time.time()
        for row in range(self.nrows):
            filtered.append([])

            f = filtertype

            if f == 0:
                filtered[row].append(self.img[row])
            # filter value is the  corresponding byte to the left
            elif f == 1:
                for col in range(self.ncols):
                    if col < stride:
                        filtered[row].append(self.img[row][col])
                    else:
                        filtered[row].append(
                            self.img[row][col] - self.img[row][col - stride]
                        )
                        filtered[row][col] %= 256
            # filter value is the  corresponding byte above
            elif f == 2:
                for col in range(self.ncols):
                    if row == 0:
                        filtered[row].append(self.img[row][col])
                    else:
                        filtered[row].append(
                            self.img[row][col] - self.img[row - 1][col]
                        )
                        filtered[row][col] %= 256
            # filter value is the mean of left and above
            elif f == 3:
                for col in range(self.ncols):
                    if row == 0:
                        up = 0
                    else:
                        up = self.img[row - 1][col]

                    if col < stride:
                        left = 0
                    else:
                        left = self.img[row][col - stride]

                    filtered[row].append(self.img[row][col] - (left + up) // 2)
                    filtered[row][col] %= 256
            # paeth filter (defaults to left for row=0, and up for col=0)
            elif f == 4:
                for col in range(self.ncols):
                    #  C B
                    #  A X

                    if row == 0:
                        if col < stride:
                            filtered[row].append(self.img[row][col])
                        else:
                            filtered[row].append(
                                self.img[row][col] - self.img[row][col - stride]
                            )
                    else:
                        if col < stride:
                            filtered[row].append(
                                self.img[row][col] - self.img[row - 1][col]
                            )
                        else:
                            a = self.img[row][col - stride]
                            b = self.img[row - 1][col]
                            c = self.img[row - 1][col - stride]

                            p = a + b - c

                            pa = abs(p - a)
                            pb = abs(p - b)
                            pc = abs(p - c)

                            if (pa <= pb) and (pa <= pc):
                                pr = a
                            elif pb <= pc:
                                pr = b
                            else:
                                pr = c

                            filtered[row].append(self.img[row][col] - pr)
                    filtered[row][col] %= 256
            bar.update((row + 1) / self.nrows)
        stop = time.time()
        print("  Done! Took %.2f seconds." % (stop - start))

        for row in range(self.nrows):
            filtered[row].insert(0, filtertype)

        # print("  Size of filtered data: %d bytes"%(len(filtered)*len(filtered[0])))
        self.uncompressed = filtered

    # Compress the image data so it is ready to be written to file
    def _compress(self):
        print("\nCompressing the image data")

        compressor = zlib.compressobj()

        bytesout = bytes()

        bar = progress_bar()

        # compress the image line by line
        i = 0
        for row in self.uncompressed:
            rowb = bytes(row)
            bytesout += compressor.compress(rowb)
            i += 1
            bar.update((i) / self.nrows)
        bytesout += compressor.flush()

        nbytes = len(bytesout)
        print("  Compressed data is %s bytes" % formatInt(nbytes))

        self.compressed = bytesout

    # creates idats from self.compressed
    def _create_idats(self):
        print("\nGenerating new IDAT chunks")
        self.idats = []

        # max size of the chunks in bytes
        chunksize = 2 ** 14

        # determine the number of chunks we need
        nchunks = math.ceil(len(self.compressed) / chunksize)
        print("  Generating %d chunk(s)" % nchunks)
        bar = progress_bar()
        for n in range(nchunks):
            if n == nchunks - 1:
                chunkdata = self.compressed[n * chunksize :]
            else:
                chunkdata = self.compressed[n * chunksize : (n + 1) * chunksize]
            # print(n*chunksize, (n+1)*chunksize, (n+1)*chunksize - n*chunksize )
            # print(len(chunkdata))

            chunk = Chunk("IDAT", len(chunkdata), chunkdata)
            # print("IDAT", len(chunkdata))
            self.idats.append(chunk)
            bar.update((n + 1) / nchunks)

    # writes a png file
    def _write_png(self):
        print("\nWriting '%s'" % self.outputfile)
        self.outputfileobject = open(self.outputfile, "wb")

        # write the magic number speficying the file as a PNG
        self.outputfileobject.write(bytearray.fromhex("89504e470d0a1a0a"))

        nchunks = len(self.chunks) + len(self.idats)
        bar = progress_bar()
        n = 0
        for chunk in self.chunks:
            if chunk.name == "IEND":
                for idat in self.idats:
                    self._write_chunk(idat)
                    n += 1
                self._write_chunk(chunk)
            else:
                self._write_chunk(chunk)
            n += 1
            bar.update(n / nchunks)
        print("Done!")

    # writes a chunk to file
    def _write_chunk(self, chunk):
        size = chunk.size.to_bytes(4, "big")
        name = chunk.name.encode("ascii")
        data = chunk.data
        crc = chunk.crc

        self.outputfileobject.write(size)
        self.outputfileobject.write(name)
        self.outputfileobject.write(data)
        self.outputfileobject.write(crc)


# Class to hold chunk data
# The name, size and data (bytes) data are put as inputs.
# If the CRC is included, it is checked against the data. If not it is automatically generated
class Chunk:
    def __init__(self, name, size, data, crc=None):
        self.name = name
        self.size = size
        self.data = data
        self.crc = self._generate_crc()

        if crc is not None:
            # check that the provided crc matches the one provided
            if crc != self.crc:
                raise Exception(
                    "CRC for chunk '%s' does not match expected." % self.name
                )

    # returns the bytes for the whole chunk (for writing to file)
    def generate_bytes(self):
        name = self.name.encode("ascii")
        size = self.size.to_bytes(4, "big")
        data = self.data
        crc = self.crc
        return name + size + data + crc

    # generates the checksum for a block
    def _generate_crc(self):
        crc = zlib.crc32(self.name.encode("ascii"))
        crc = zlib.crc32(self.data, crc)
        return crc.to_bytes(4, "big")


# Class for a progress bar
# draws bar like this:
# message  [==========>        ] 55%
#
# - Initialise with bar=progress_bar(optional_message)
# - Update with bar.update( 0 <= float <= 1))
# - when the bar reaches 100% it automatically produces a new line in stdout so s
#   stdout is ready for the program to print other things
#
class progress_bar:
    def __init__(self, message="", start=0.0):

        self.fullwidth = 80  # maximum width of the bar and message
        self.percentwidth = 4  # the width the percent test takes up
        self.message = message

        self.width = len(message) + 2 + 1 + self.percentwidth + 1 + 2

        self.barwidth = self.fullwidth - self.width

        if self.width > self.fullwidth:
            raise Exception(
                "Progress bar width cannot be greater than %d" % fullwidth
                - self.percentwidth
            )

        self.update(0, clear=False)

    def update(self, progress, clear=True):
        if progress > 1 or progress < 0:
            raise Exception("Progress cannot be greater than 1")

        self.nbars = int(progress * self.barwidth)

        self.progress = int(progress * 100)

        if self.progress == 100:
            done = True
        else:
            done = False

        self._draw(clear, done)

    def _draw(self, clear=True, done=False):
        if clear:
            self._clear()
        if done:
            string = (
                self.message
                + "  "
                + "["
                + "=" * (self.nbars)
                + " " * (self.barwidth - self.nbars)
                + "]"
                + "%3d%%" % self.progress
                + " "
            )
        else:
            string = (
                self.message
                + "  "
                + "["
                + "=" * (self.nbars - 1)
                + ">"
                + " " * (self.barwidth - self.nbars)
                + "]"
                + "%3d%%" % self.progress
                + " "
            )

        sys.stdout.write(string)

        if done:
            sys.stdout.write("\n")

        sys.stdout.flush()

    def _clear(self):
        sys.stdout.write("\b" * self.fullwidth)


# formats an integer in a human readable way. E.g. 1234567 -> 1,234,567
def formatInt(i):
    # convert to a string
    s = "%d" % i

    # we want to go right to left and insert commas
    # n = Number of times we need to do this
    l = len(s)
    n = (l - 1) // 3
    for split in range(n):
        splitpoint = -(3 * (split + 1) + split)
        s = s[:splitpoint] + "," + s[splitpoint:]

    return s


helpstr = (
    "\nUsage: \n"
    "    steganography.py encode [input image] [file to hide] [output image]\n"
    "  or\n"
    "    steganography.py decode [input image]\n"
)


if __name__ == "__main__":

    if len(sys.argv) < 3 or len(sys.argv) == 4 or len(sys.argv) > 5:
        print(helpstr)
        sys.exit(1)

    if sys.argv[1] == "encode":
        if len(sys.argv) != 5:
            print(helpstr)
            sys.exit(1)

        imgfile = sys.argv[2]
        secretfile = sys.argv[3]
        outfile = sys.argv[4]

        png = PNG(imgfile)
        maxsize = png.get_max_hidden_filesize()

        if os.path.getsize(secretfile) > maxsize:
            print(
                "\n'%s' is too large to be put into '%s'. Aborting"
                % (secretfile, imgfile)
            )
            sys.exit(1)

        png.read()
        png.encode(secretfile)
        png.write(outfile)

    elif sys.argv[1] == "decode":
        if len(sys.argv) == 4:
            print(helpstr)
            sys.exit(1)

        imgfile = sys.argv[2]

        png = PNG(imgfile)
        png.read()
        png.decode()

    else:
        print(helpstr)
        sys.exit(1)
