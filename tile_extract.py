import sys
import png
import os
import itertools
import copy
import zlib
import struct
import math
from xml.dom import minidom


class TileExtractor:
    """
    A class with methods to output tile information from a large tile sheet.
    Tile list looks like this: two tiles, 2x2 pixels:
    [
        [[R, G, B, R, G, B], [R, G, B, R, G, B]], # tile 1
        [[R, G, B, R, G, B], [R, G, B, R, G, B]]  # tile 2
    ]
    It is a list of tiles, each containing a list of rows of pixels, with R G B for each pixel.
    """
    def __init__(self, file_name=None, tile_size=0):
        """
        An immediate initializer of the tile extractor class
        :param file_name: The name of the PNG to sub-divide into tiles
        :param tile_size: The size of tiles to extract from the PNG
        """
        self.tiles = None
        self.tile_indices = None
        self.tile_size = tile_size
        self.master_tile_file_name = file_name
        self.tiles_width = 0
        self.tiles_height = 0
        if file_name is not None and tile_size != 0:
            self.populate_extractor(file_name, tile_size)

    def has_validate_tiles(self):
        """
        Validates that there are valid tiles to work with
        :return: True on valid tiles
        """
        if not self.tiles or not self.tile_indices or self.tile_size <= 0:
            return False
        return True

    @staticmethod
    def print_tile_work_percentage(cur_y, max_y, percent_stack):
        """
        Prints the percentage for long tile work methods
        :param cur_y: The current Y in the tile parsing work
        :param max_y: The max Y in the tile parsing work
        :param percent_stack: A list of percentages already shown
        """
        percentage = int((float(cur_y) / max_y) * 100)
        if percentage != 0:
            sys.stdout.write('.')
        if percentage % 10 == 0 and percentage not in percent_stack:
            sys.stdout.write(' {0}% '.format(percentage))
            percent_stack.append(percentage)

    def populate_extractor(self, file_name, tile_size):
        """
        From a large PNG file, sub-divides the bitmap using tile_size as
        a boundary size.
        Improvements: Slowest part of code is reading from PNG and comparing a tile against all current tiles.
                      Tile comparisons become exponential.
                      Tile comparisons could be speed up with tile hashes. Comparisons could also be concurrent.
                      It is unclear if PNG reads could be speed up with concurrency however...
        :param file_name: The name of the PNG to sub-divide into tiles
        :param tile_size: The size of tiles to extract from the PNG
        """
        png_file = open(file_name)
        if not png_file:
            print('TileExtractor: No file at path {0}!'.format(file_name))
            return

        png_reader = png.Reader(file=png_file)
        image_data = png_reader.asRGB8()
        size = None
        iter_map = None

        # search the returned tuple for important information
        for elm in image_data:
            if isinstance(elm, itertools.imap):
                iter_map = elm
            elif isinstance(elm, dict) and elm.get('size'):
                size = elm['size']

        if size is None or size[0] % tile_size != 0 or size[1] % tile_size != 0:
            print('Invalid image size! {0}'.format(size))
            return

        print('Valid image size: {0} for tile size ({1}), extracting unique tiles...'.format(size, tile_size))

        # See comment at top of page to understand structure layout of tiles
        self.tiles = []

        # This is an index list of the used tiles in order so we can export a tile map file to use in tiled.
        # Note: Indices are 1 based so the +1s are intentional
        self.tile_indices = []

        self.tile_size = tile_size

        self.tiles_width = int(size[0] / tile_size)
        self.tiles_height = int(size[1] / tile_size)

        cur_slice_y = 0
        work_percentage_stack = []
        """
        We populate the tile list like this:
            1) grab tile_size rows in an iterator slice
            2) grab (width / tile_size) tiles in that slice
            3) compare new tiles vs current tiles and throw away duplicates
            4) grab next slice
        """
        while cur_slice_y < size[1]:
            # Initialize tile list
            new_tiles = [[] for _ in range(0, size[0] / self.tile_size)]

            # We go through each row of pixels grabbing tile_size iterator slices
            it_slice = itertools.islice(iter_map, 0, self.tile_size)

            # Run through every tile_size * tile_size tile
            for elm in it_slice:
                cur_new_tile = 0
                cur_slice_x = 0
                while cur_slice_x < size[0]:
                    # Get the row of pixels [R,G,B, R,G,B, R,G,B]
                    tile_row = list(elm[cur_slice_x * 3:cur_slice_x * 3 + self.tile_size * 3])

                    # Append the row to one of the new tiles
                    new_tiles[cur_new_tile].append(tile_row)

                    # Iterate to next section of row
                    cur_slice_x += self.tile_size
                    cur_new_tile += 1

            num_new_tiles = 0
            # Go through new tile list and see if any of the tiles are duplicates.
            # If there are duplicates, they are not added to the master list of tiles.
            for new_tile in new_tiles:
                found_tile = False
                for master_tile_index in range(0, len(self.tiles)):
                    if self.compare_tiles(self.tiles[master_tile_index], new_tile):
                        self.tile_indices.append(master_tile_index + 1)
                        found_tile = True
                        break

                if not found_tile:
                    self.tiles.append(copy.deepcopy(new_tile))
                    self.tile_indices.append(len(self.tiles))
                    num_new_tiles += 1

            # print('{0} tiles added for row {1}. Tile count = {2}'.format(num_new_tiles,
            #                                                            cur_slice_y / self.tile_size, len(self.tiles)))
            cur_slice_y += self.tile_size
            self.print_tile_work_percentage(cur_slice_y, size[1], work_percentage_stack)
        print('')  # new line after percentage indicator
        # Close the file, we have extracted what we need
        png_file.close()

    @staticmethod
    def compare_tiles(tile_row_list1, tile_row_list2):
        """
        Compares two tiles and returns True if they are the same
        :param tile_row_list1: tile row list 1
        :param tile_row_list2: tile row list 2
        :return: comparison result
        """
        for row in range(0, len(tile_row_list1)):
            for col in range(0, len(tile_row_list1[row])):
                if tile_row_list1[row][col] is not tile_row_list2[row][col]:
                    return False

        return True

    @staticmethod
    def output_tile_to_file(tile, tile_size, out_folder, group_name, file_index):
        """
        Outputs a tile row list to a PNG
        :param tile: The tile list to output
        :param tile_size: The length of the tile
        :param out_folder: The output folder to put the file
        :param group_name: The prefix for the file
        :param file_index: The postfix for the file
        """
        out_filename = '{0}{1}{2}_{3}.png'.format(out_folder, os.sep, group_name, file_index)
        tile_png = open(out_filename, 'wb')     # binary mode is important

        png_writer = png.Writer(tile_size, tile_size)
        png_writer.write(tile_png, tile)

    @staticmethod
    def output_tiles_to_sheet(tiles, square_width, out_folder, group_name, file_index):
        """
        Exports a tile map containing tiles in the tiles list.
        :param tiles: The tiles to output to the sheet
        :param square_width: The width of the texture to output, which will also be the height. Should be pow 2.
        :param out_folder: The output folder to put the tile maps.
        :param group_name: The prefix of the out file
        :param file_index: The postfix index
        """
        out_filename = '{0}{1}{2}_{3}.png'.format(out_folder, os.sep, group_name, file_index)
        tile_png = open(out_filename, 'wb')     # binary mode is important

        png_writer = png.Writer(square_width, square_width)

        # Get some information about the tiles we are injecting into the large sheet
        num_tiles = len(tiles)
        num_tile_rows = len(tiles[0])
        num_tiles_per_row = square_width / num_tile_rows

        # build rows
        output_rows = []
        for cur_row in range(0, square_width):
            row_out = []
            # row_debug = []

            for cur_tile_index in range(0, num_tiles_per_row):
                cur_tile_row = int(cur_row / num_tile_rows)
                tile_index = cur_tile_index + cur_tile_row * num_tiles_per_row
                if tile_index < num_tiles:
                    tile_row_index = cur_row % num_tile_rows
                    # row_debug.append((tile_index, tile_row_index))
                    row_out.extend(tiles[tile_index][tile_row_index])
                else:
                    # row_debug = list(itertools.repeat((99, 99), 8))
                    # create a row of white
                    row_out.extend(list(itertools.repeat(255, num_tile_rows * 3)))

            # print row_debug
            output_rows.append(row_out)

        png_writer.write(tile_png, output_rows)

    def output_tiles_to_sheets(self, out_folder, group_name):
        """
        Outputs the tiles created by the extractor.
        :param out_folder: The output folder to extract the sheet to
        :param group_name: The prefix name of the output file
        """
        if not self.has_validate_tiles():
            print('Unable to extract tiles, no tile information!')
            return

        self._check_output_dir(out_folder)

        # Now we need to create tile sheets with these unique tiles. Determine how many sheets we will need.
        sheet_info = self.get_tile_sheet_specs(len(self.tiles), self.tile_size)

        cur_out_tile = 0
        file_index = 0
        for square_width in sheet_info:
            num_tiles_in_sheet = int(math.pow(square_width / self.tile_size, 2))
            num_tiles_on_sheet = num_tiles_in_sheet
            num_tiles_left = len(self.tiles) - cur_out_tile

            if num_tiles_in_sheet > num_tiles_left:
                num_tiles_on_sheet = num_tiles_left

            tiles_out = self.tiles[cur_out_tile:cur_out_tile + num_tiles_on_sheet]

            out_msg = 'Creating ({0} x {0}) tile sheet containing {1} tiles. {2}% of sheet used...'
            print(out_msg.format(square_width, len(tiles_out), int((len(tiles_out) / float(num_tiles_in_sheet)) * 100)))

            self.output_tiles_to_sheet(tiles_out, square_width, out_folder, group_name, file_index)

            cur_out_tile += num_tiles_on_sheet
            file_index += 1

    @staticmethod
    def get_tile_sheet_specs(num_tiles, tile_size, min_sheet_width=64, max_sheet_width=512):
        """
        Determine how many sheets we need to make with this many tiles we want to output to optimal sizes
        :param num_tiles: number of tiles to put onto sheets
        :param tile_size: the size of tiles
        :param max_sheet_width: The max allowed sheet size, keep it Pow 2 or else!
        :return: list of square texture sheet widths
        """
        # Build sheet table
        # Table looks like : [(width, tiles), (width, tiles)] highest to lowest
        tiles_table = []
        cur_sheet_width = max_sheet_width
        while cur_sheet_width >= min_sheet_width:
            tiles_table.append((cur_sheet_width, int(math.pow(cur_sheet_width / tile_size, 2))))
            cur_sheet_width >>= 1

        output = []
        num_tiles_left = num_tiles
        while num_tiles_left > 0:
            if num_tiles_left > tiles_table[0][1]:
                chosen_sheet_size = tiles_table[0]
            else:
                # Search for a suitable table. Default to lowest table.
                chosen_sheet_size = tiles_table[len(tiles_table) - 1]
                for tile_table in tiles_table:
                    if tile_table[1] >= num_tiles_left:
                        chosen_sheet_size = tile_table

            num_tiles_left -= chosen_sheet_size[1]
            output.append(chosen_sheet_size[0])

        return output

    def output_single_tiles_to_folder(self, out_folder, group_name):
        """
        Extracts all tiles to a folder, one PNG per tile
        :param out_folder: The folder to output to
        :param group_name: The prefix of the output PNG files
        """
        if not self.has_validate_tiles():
            print('Unable to extract tiles, no tile information!')
            return

        self._check_output_dir(out_folder)

        print('Writing {0} unique tiles to output directory {1}...'.format(len(self.tiles), out_folder))
        # Write tiles out to the output directory
        file_index = 0
        for tile in self.tiles:
            self.output_tile_to_file(tile, self.tile_size, out_folder, group_name, file_index)
            file_index += 1

    @staticmethod
    def get_tile_indices(tmx_file):
        """
        Gets a list of tile indices
        :param tmx_file: the tmx file to read the indices from. Needs to be base64 with gzip compression.
        :return: the list of indices
        """
        xml_doc = minidom.parse(tmx_file)
        index_list = []

        layers = xml_doc.getElementsByTagName('layer')
        for layer in layers:
            data = layer.getElementsByTagName('data')
            encode_type = data[0].attributes['encoding'].value
            compress_type = data[0].attributes['compression'].value
            if (encode_type != u'base64') or (compress_type != u'gzip'):
                print('ERROR: Unsupported tiled format')
                quit()

            # Data is in Base64, decode to byte array
            data_base64 = data[0].firstChild.nodeValue.strip().encode('ascii', 'ignore')
            data_compressed = data_base64.decode('base64')

            # Decompress gzip. Zlib can do this. wbits is the window buffer for gzip, compression log
            decompressed_data = zlib.decompress(data_compressed, 16 + zlib.MAX_WBITS)

            # Now we have a byte string with unsigned ints every 4 bytes.
            num_ints = len(decompressed_data) / 4
            for i in range(0, num_ints):
                int_data = decompressed_data[i * 4:i * 4 + 4]
                # unpack to little endian, unsigned long
                tile_id = struct.unpack("<L", int_data)[0]
                index_list.append(tile_id)

        return index_list

    def get_base_64_index_string(self):
        """
        Returns a Base 64 index string of the input png tile map indices.
        Note: Indices are packed as 4 byte, little endian longs
        :return: the base 64 index string
        """
        packed_indices = ''
        for tile_index in self.tile_indices:
            packed_indices += struct.pack("<L", tile_index)

        return packed_indices.encode('base64')

    def output_tmx_for_tiles(self, out_folder, group_name):
        """
        Outputs a tmx file
        :param out_folder: The output folder for the tmx file
        :param group_name: The name of the tmx file to output, and the tile sheet names
        """
        if not self.has_validate_tiles():
            print('Unable to extract tiles, no tile information!')
            return

        self._check_output_dir(out_folder)

        # Create the initial document
        doc = minidom.Document()

        # Create map object
        world = doc.createElement('map')
        world.setAttribute('version', '1.0')
        world.setAttribute('orientation', 'orthogonal')
        world.setAttribute('renderorder', 'right-down')
        world.setAttribute('width', str(self.tiles_width))
        world.setAttribute('height', str(self.tiles_height))
        world.setAttribute('tilewidth', str(self.tile_size))
        world.setAttribute('tileheight', str(self.tile_size))
        world.setAttribute('nextobjectid', '1')
        doc.appendChild(world)

        # Now we need to create tile sheets with these unique tiles. Determine how many sheets we will need.
        sheet_info = self.get_tile_sheet_specs(len(self.tiles), self.tile_size)

        file_index = 0
        cur_first_tile_index = 0
        for square_width in sheet_info:
            num_tiles_in_sheet = int(math.pow(square_width / self.tile_size, 2))

            # Create a tile set description, describes the tile set sizes
            tile_set = doc.createElement('tileset')
            tile_set.setAttribute('firstgid', str(cur_first_tile_index + 1))  # 1 based indices
            tile_set.setAttribute('name', group_name + '_' + str(file_index))
            tile_set.setAttribute('tilewidth', str(self.tile_size))
            tile_set.setAttribute('tileheight', str(self.tile_size))
            world.appendChild(tile_set)

            # Create the image information
            image = doc.createElement('image')
            image.setAttribute('source', group_name + '_' + str(file_index) + '.png')
            image.setAttribute('width', str(square_width))
            image.setAttribute('height', str(square_width))
            tile_set.appendChild(image)

            file_index += 1
            cur_first_tile_index += num_tiles_in_sheet

        # Create a layer. TMX can have a number of layers which make up the map.
        layer = doc.createElement('layer')
        layer.setAttribute('name', group_name)
        layer.setAttribute('width', str(self.tiles_width))
        layer.setAttribute('height', str(self.tiles_height))
        world.appendChild(layer)

        # Create the data. The data describes how the tiles are laid.
        data = doc.createElement('data')
        data.setAttribute('encoding', 'base64')
        # data.setAttribute('compression', 'zlib')
        base_64_str = self.get_base_64_index_string()
        # print base_64_str
        # compressed_data = zlib.compress(base_64_str, 9)
        # out_test = open('out_compressed.txt', 'wb')
        # out_test.write(compressed_data)
        # out_test.close()
        map_layout = doc.createTextNode(base_64_str)
        data.appendChild(map_layout)
        layer.appendChild(data)

        # Four space tabbed pretty print output
        xml_out = doc.toprettyxml(indent="    ", encoding="utf-8")

        # Output utf-8 string to file
        out_file = os.path.join(out_folder, group_name) + '.tmx'
        print('Creating TMX XML of Base 64 Gzip indices describing input png to {0}...'.format(out_file))
        tmx_out_file = open(out_file, 'wb')
        tmx_out_file.write(xml_out)
        tmx_out_file.close()

    @staticmethod
    def _check_output_dir(out_folder):
        """
        Ensures the output directory exists
        :param out_folder: The folder to check and create if necessary
        """
        if not os.path.exists(out_folder):
            os.makedirs(out_folder)


def create_unique_tile_sheet_from_file(file_path, tile_size):
    """
    Output a unique tile sheet to a local folder named after the file path
    :param file_path: The path to the large PNG to split up
    :param tile_size: The size of the tiles to extract
    """
    extractor = TileExtractor(file_path, tile_size)

    # extract the base path and the file name
    file_path, file_name = os.path.split(file_path)

    # we will use the name of the file to name a folder
    group_name = os.path.splitext(file_name)[0]

    # Create output directory path
    out_folder = os.path.join(file_path, group_name)

    extractor.output_tiles_to_sheets(out_folder, group_name)
    extractor.output_tmx_for_tiles(out_folder, group_name)

    print('Done!')

# ----------------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    create_unique_tile_sheet_from_file('onett_full.png', 32)