# A script to hide files inside PNG image files

Steganography, [according to Wikiedia](https://en.wikipedia.org/wiki/Steganography), is "the practice of concealing a file, message, image, or video within another file, message, image, or video". The script `steganography.py` inside this repository can be used to encode a file within a PNG image. It does this by placing the bits from the file in the last two bits of each image byte. This has the effect of slightly changing the image pixel values (and hence adding some noise to the image) however as we only modify the last two bits we only affect the pixel value by at most 3/256.

The script supports most PNG images except for:
- Interlaced PNGs
- Ones with a bitdepth < 8

Attempting to use such images with raise an exception. PNG images which use indexed colours _are_ suppored, however as these only have a palette of 256 colours, changing the values of each pixel can drastically alter the image.

The script is written in pure python and therefore does not have any pre-requisites, however it will only work with Python 3 (tested with version 3.7.2).

## Usage
There are two modes. An _encode_ mode, which encodes a file into the image, and a decode mode that extracts the file. 

For the encode mode, the syntax is:
```
python steganography.py encode [input_PNG] [file_to_encode] [output_PNG]
```
This will encode `file_to_encode` into the `input_PNG`, outputting `output_PNG`, which contains the file. The name of `file_to_encode` is also written to the PNG. If the file to be encoded is too large to fit inside the PNG, the script will say this, and exit.

For the decode mode, the syntax is:
```
python steganograpny.py decode [PNG_image]
```
This will extract the hidden file and write it to disk with its original name. If there is no file hidden within the PNG, a `FileNotFoundError` will be raised.

## The Underlying classes
The script uses a ```PNG``` class to do all its operations. The class is initiated with the name of the PNG file that is used as input. The class initiation checks that the file exists, reads its "IHDR" chunk (which contains some basic metadata on the image), and computes the maximum size of file which can be encoded within the PNG. It _*DOES NOT*_ read the PNG file in.

The class contains the following (public) methods:
- `get_max_hidden_filesize()`: Returns the maximum size of a file in bytes that can be hidden within the image
- `read()`: Reads in the PNG image
- `encode(filename)`: Encodes the file `filename` into the PNG data. This does not write to a new file, just alter the image data held within the PNG object
- `decode()`: Extracts a hidden file from the PNG image data, and writes it to file
- `write(filename)`: Writes the PNG data held within the object to a new PNG file, `filename`.

A simple example for reading in a file `input.png`, encoding `secret.txt`, and writing this to `output.png` would be:
``` python
png = PNG('input.png')
if png.get_max_hidden_filesize() > os.path.get_size('secret.txt'):
    png.read()
    png.encode('secret.txt')
    png.write('output.png')
```
We could skip the step where we check whether `secret.txt` is too big to fit in the PNG image data, however this will result in `png.encode()` raising an exception.

Similarly, an example for extracting the encoded file from `output.png` would be:
```python
png = PNG('output.png')
png.read()
png.extract()
```


## TODOs/Wishlist
- Support interlaced PNGs
- Re-implement encoding, decoding, filtering and de-filtering with numpy arrays to speed things up. Possibly try to use numba juat-in-time compiling too
- Write a C version?
- Implement steganography in other filetypes such as JPEG