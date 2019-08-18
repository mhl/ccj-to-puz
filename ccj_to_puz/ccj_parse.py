#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This module and script provides functionality for parsing CCJ crosswords

You can use the CCJParser class to parse CCJ files and write it out in
the AcrossLife .puz binary format.

Alternatively you can use this as a script, taking a .ccj file on
standard output, and it convert it to AcrossLite .puz format.

The output is only an approximation of that format, but it's good
enough for loading into xword. [1]

  [1] apt-get install xword

You need the Debian version 1.04 of xword.

Note that this script was written with guesswork based on looking at
example CCJ files."""

from __future__ import print_function

import copy
import sys
import re
from optparse import OptionParser
import io
import struct
import unicodedata

from commonccj import Cell, Grid, clue_number_string_to_duple

def contains_control_characters(string):
    """Returns True if any control character is in s, otherwise False"""
    return any(unicodedata.category(c) == 'Cc' for c in string)

def decode_bytes(bytes_to_decode):
    """Try to decode bytes (in an unknown encoding) into a string

    I'm not sure about character set issues here, but it seems that
    0x03 turns on italic and 0x01 turns it off. In addition, there may
    be several random 0x01 bytes before the enumeration.  So, we
    remove any 0x01 or 0x03 bytes first.  Then try UTF-8 decoding - if
    that doesn't succeed, try Windows 1252 and then ISO-8859-1, giving
    up if there are control characters left after decoding and
    replacing newlines with spaces.  0x02 might be bold, perhaps?
    e.g.  in Independent June 26th 2008 there's 'Unwise<b>r</b?'
    represented by

      55 6e 77 69 73 65 02 72 01 3f 01 01 20 28 39 29
      U  n  w  i  s  e     r     ?           (  9  )
    """
    bytes_to_decode = bytearray(c for c in bytearray(bytes_to_decode)
                                if c not in (0x01, 0x02, 0x03))
    if sys.version_info >= (3, 0):
        bytes_to_decode = bytes(bytes_to_decode)

    for encoding in ('utf_8', 'latin_1', 'cp1252'):
        try:
            s = bytes_to_decode.decode(encoding)
        except UnicodeDecodeError:
            continue
        s = re.sub(r'\s+', ' ', s)
        if not contains_control_characters(s):
            return s
    raise Exception("Couldn't guess the character set.")

def byte_at(data, i):
    """Return integer value of the byte at index i of data

    This is designed to work on a str (in Python 2) or a bytes (in
    Python 3)"""
    if isinstance(data, str):
        return ord(data[i])
    else:
        return int(data[i])

def read_string(data, start_index):
    """Decode a length-prefixed string from start_index in data"""
    length = byte_at(data, start_index)
    bytes_for_string = data[(start_index + 1):(start_index + length + 1)]
    s = decode_bytes(bytes_for_string)
    return (s, start_index + length + 1)


def skippable_block_of_four(data, start_index):
    """Detect if the 4 bytes at start_index in data are ignorable

    There sometimes seems to be a succession of bytes here in groups
    of repeated groups of four, next - this function tests for the
    patterns I've seen."""
    block = bytearray(data[start_index:start_index + 4])
    skippable_blocks = [[0x00, 0xff, 0xff, 0xff],
                        [0x00, 0x00, 0xff, 0xff],
                        [0x00, 0x00, 0x00, 0x00]]
    return block in (bytearray(l) for l in skippable_blocks)

def reduce_coordinate(x):
    """Coordinates sometimes seem to have 80 added to them"""
    if x >= 0x80:
        return x - 0x80
    else:
        return x

def read_clue_start_coordinates(data, start_index):
    """Extract the start coordinates for an answer"""
    # My assumption is that if the first byte is >= 0x80 then it's a
    # list of coordinates terminated by a NUL, otherwise it's just two
    # bytes with the coordinate:
    start_coordinates = []
    if byte_at(data, start_index) >= 0x80:
        i = start_index
        while byte_at(data, i) != 0:
            x = reduce_coordinate(byte_at(data, i))
            y = reduce_coordinate(byte_at(data, i + 1))
            start_coordinates.append((x, y))
            i += 2
        return (start_coordinates, i + 1)
    else:
        x = reduce_coordinate(byte_at(data, start_index))
        y = reduce_coordinate(byte_at(data, start_index + 1))
        start_coordinates.append((x, y))
        return (start_coordinates, start_index + 2)

def parse_list_of_clues(data, start_index, grid, verbose=False):
    result = ListOfClues()
    i = start_index
    # Read the label for this list of clues:
    result.label, i = read_string(data, i)
    if verbose:
        print("clue set label is:", result.label)
    result.across = None
    if re.search(r'(?ims)across', result.label):
        result.across = True
    elif re.search(r'(?ims)down', result.label):
        result.across = False
    else:
        message = "Couldn't find either 'across' or 'down' in label: '{0}'"
        raise Exception(message.format(result.label))

    # Skip some bytes:
    result.unknown_bytes = data[i:(i + 3)]
    i += 3
    if verbose:
        print("  Before list of clues, got these unknown bytes:")
        for b in result.unknown_bytes:
            print("    " + str(b))
    result.number_of_clues = byte_at(data, i)
    if verbose:
        print("number of clues is: " + str(result.number_of_clues))
    i += 1
    clues_found = 0
    while True:
        if verbose:
            print("--------------------------")
        clue = ParsedClue()
        clue.across = result.across
        clue.start_coordinates, i = read_clue_start_coordinates(data, i)
        if verbose:
            for c in clue.start_coordinates:
                print("A start at x: " + str(c[0]) + ", y: " + str(c[1]))
        s, i = read_string(data, i)
        clue.set_number(s, grid)
        if verbose:
            print("clue number: " + clue.number_string)
            print("all clue numbers:",
                  ", ".join(str(x[0]) + (x[1] and "A" or "D")
                            for x in clue.all_clue_numbers))
        # Skip a NUL:
        if byte_at(data, i) != 0:
            raise Exception("After clue number we expect a NUL to skip over")
        i += 1
        clue.text_including_enumeration, i = read_string(data, i)
        if verbose:
            print("clue text:", clue.text_including_enumeration)
        result.clue_dictionary[clue.all_clue_numbers[0][0]] = clue
        clues_found += 1
        if clues_found >= result.number_of_clues:
            break
    return result, i

def keyfunc_clues(x):
    """A key function for sorting clues before output"""
    # We want clues to be in the order the number appear in the grid,
    # with across before down if there's a choice:
    return (x.all_clue_numbers[0][0], 0 if x.across else 1)

def coord_str(x, y):
    """Return a string representation of x and y"""
    return "({0}, {1})".format(x, y)


class ListOfClues:
    """A class for grouping clues

    Typically there's one instance of this to hold the across clues,
    and one for the down clues."""

    def __init__(self):
        self.number_of_clues = None
        self.label = None
        self.clue_dictionary = {}
        self.across = None
        self.unknown_bytes = None

    def ordered_list_of_clues(self):
        keys = sorted(self.clue_dictionary.keys())
        return [self.clue_dictionary[x] for x in keys]

    def real_number_of_clues(self):
        return len(self.clue_dictionary)


class ParsedClue:
    """A class for storing data about a parsed clue"""
    def __init__(self):
        self.number_string = None
        self.text_including_enumeration = None
        self.start_coordinates = None
        self.across = None
        self.all_clue_numbers = None
    def tidied_text_including_enumeration(self):
        t = re.sub(r'[\x00-\x1f]', '', self.text_including_enumeration)
        t = re.sub(r' *\(', ' (', t)
        return t
    # Typically this looks like "5", "24", or for multiple entries
    # "4/12" - there can also be a disambiguating A or D afterwards,
    # e.g. in the Independent from 2012-06-04 there is "9/14D".  The A
    # or D only seems to be present where it is otherwise impossible
    # to infer the direction of one of the clues.  e.g. in the
    # Independent from 2013-12-05 there is in the down clues a "6/24",
    # to mean 6D/24A, but you should be able to tell because there's
    # only a 24A, and no 24D in the grid. (2013-11-14 also has a
    # difficult case: "33/16/12/2A/28D".
    def set_number(self, clue_number_string, grid):
        print("clue_number_string is:", clue_number_string)
        self.number_string = clue_number_string
        if self.across == None:
            msg = "Trying to call self.set_number() before self.across is set"
            raise Exception(msg)
        self.all_clue_numbers = [clue_number_string_to_duple(self.across, x, grid)
                                 for x in
                                 re.split(r'[,/]', clue_number_string)]


class ParsedCCJ:

    def __init__(self):
        self.width = None
        self.height = None
        self.across_clues = None
        self.down_clues = None
        self.grid = None
        self.title = None
        self.author = None
        self.copyright_message = None
        self.setter = None
        self.puzzle_number = None
        self.date_string = None

    def read_from_ccj(self,
                      f,
                      title,
                      author,
                      puzzle_number,
                      copyright_message,
                      date_string,
                      verbose=False):

        # Cope with puzzle number being passed in as a number rather
        # than a string:
        if puzzle_number is not None:
            puzzle_number = str(puzzle_number)

        d = f.read()

        # i is the index into the file for the rest of this script:
        i = 2

        # I think these must be the list of buttons on the left:
        while byte_at(d, i) != 0:
            s, i = read_string(d, i)
            if verbose:
                print("got button string:", s)

        # Then the congratulations message, I think:
        i += 1
        s, i = read_string(d, i)

        if verbose:
            print("got congratulations message:", s)

        # Skip another byte; 0x02 in the Independent it seems, but 0x00 in the
        # Herald puzzle I tried.
        i += 1

        # I think we get the grid dimensions in the next two:
        self.width = byte_at(d, i)
        i += 1

        self.height = byte_at(d, i)
        i += 1

        self.grid = Grid(self.width, self.height)

        # Now skip over everything until we think we see the grid, since I've
        # no idea what it's meant to mean:
        while byte_at(d, i) != 0x3f and byte_at(d, i) != 0x23:
            i += 1

        for y in range(0, self.height):
            for x in range(0, self.width):
                # Lights seem to be indicated by: '?' (or 'M' very occasionally)
                if byte_at(d, i) in (0x3f, 0x4d):
                    self.grid.cells[y][x] = Cell(y, x)
                # Blocked-out squares seem to be always '#'
                elif byte_at(d, i) == 0x23:
                    pass
                else:
                    message = "Unknown value {0} at {1}"
                    raise Exception(message.format(str(byte_at(d, i)),
                                                   coord_str(x, y)))
                i += 1

        if verbose:
            print("grid is:\n" + self.grid.to_grid_string(True))

        # Now tell the grid to work out where each clue number should
        # be:
        self.grid.set_numbers()

        # Next there's a grid structure the purpose of which I don't
        # understand:
        grid_unknown_purpose = Grid(self.width, self.height)

        for y in range(0, self.height):
            for x in range(0, self.width):
                grid_unknown_purpose.cells[y][x] = Cell(y, x)
                if byte_at(d, i) == 0:
                    grid_unknown_purpose.cells[y][x].set_letter(' ')
                elif byte_at(d, i) < 10:
                    letter = str(byte_at(d, i))
                    grid_unknown_purpose.cells[y][x].set_letter(letter)
                else:
                    truncated = str(byte_at(d, i) % 10)
                    if verbose:
                        message = "Warning, truncating {0} to {1} at {2}"
                        print(message.format(byte_at(d, i),
                                             truncated,
                                             coord_str(x, y)))
                    grid_unknown_purpose.cells[y][x].set_letter(truncated)
                i += 1

        # Seem to need to skip over an extra byte (0x01) here before the
        # answers.  Maybe it indicates whether there are answers next or not:
        if byte_at(d, i) != 1:
            raise Exception("So far we expect a 0x01 before the answers...")
        i += 1

        if verbose:
            print("grid_unknown_purpose is:\n" +
                  grid_unknown_purpose.to_grid_string(False))

        # Now there's the grid with the answers:
        for y in range(0, self.height):
            for x in range(0, self.width):
                if self.grid.cells[y][x]:
                    self.grid.cells[y][x].set_letter(chr(byte_at(d, i)))
                    i += 1

        if verbose:
            print("grid with answers is:\n" + self.grid.to_grid_string(False))

        skipped_blocks_of_four = 0
        while skippable_block_of_four(d, i):
            i += 4
            skipped_blocks_of_four += 1

        if skipped_blocks_of_four > 0:
            if verbose:
                print("Skipped over",
                      str(skipped_blocks_of_four),
                      "ignorable blocks")

        # I expect the next one to be 0x02:
        if byte_at(d, i) != 0x02:
            message = "Expect the first of the block of 16 always to be 0x02, "
            message += "in fact was: {0}"
            raise Exception(message.format(byte_at(d, i)))

        # Always just 16?
        i += 16

        self.across_clues, i = parse_list_of_clues(d, i, self.grid, verbose)

        if verbose:
            print("Now do down clues:")

        self.down_clues, i = parse_list_of_clues(d, i, self.grid, verbose)

        m = re.search(r'^(.*)-([0-9]+)', self.across_clues.label)
        if m:
            self.setter = m.group(1)
            self.puzzle_number = m.group(2)

        if (not self.setter) and author:
            self.setter = author
        if (not self.puzzle_number) and puzzle_number:
            self.puzzle_number = puzzle_number

        self.title = "Crossword"
        if title:
            self.title = title

        if self.setter and self.puzzle_number:
            self.title += " " + self.puzzle_number + " / " + self.setter
        elif self.setter:
            self.title += " / " + self.setter
        elif self.puzzle_number:
            self.title += " " + self.puzzle_number

        if date_string:
            self.title += " (" + date_string + ")"

        self.author = "Unknown Setter"
        if author:
            self.author = author

        self.copyright_message = "© Unknown"
        if copyright_message:
            self.copyright_message = copyright_message

    def write_to_puz_file(self, output_filename, verbose=False):
        """Write the crossword in AcrossLite .puz format to output_filename

        Note that the version for the file format that this outputs
        doesn't include checksums, so a strict loader will reject such
        a file - it's fine in xword, though."""

        # In the AcrossLite .PUZ format we need to make sure that there's one
        # "clue" for each clue number, even if it's just "See 6" for clues
        # whose answers are split over different clue numbers in the grid.

        # So, go through the clue dictionaries and make sure that there is
        # something for every clue.  (So we don't miss the "See 6" type of
        # clue.)

        # We take a deep copy of the across clues and down clues first
        # so that we don't add unnecessary fake clues to the
        # attributes of this instance.
        clue_groups = {
            True: copy.deepcopy(self.across_clues),
            False: copy.deepcopy(self.down_clues)}

        for group_across in (True, False):
            clue_dictionary = clue_groups[group_across].clue_dictionary
            for clue in clue_dictionary.values():
                first_clue_entry = str(clue.all_clue_numbers[0][0])
                for entry_n, entry_across in clue.all_clue_numbers:
                    clue_string = "See " + first_clue_entry
                    if entry_across != group_across:
                        clue_string += entry_across and " across" or " down"
                    expected_dictionary = {
                        True: clue_groups[True].clue_dictionary,
                        False: clue_groups[False].clue_dictionary
                    }[entry_across]
                    if entry_n not in expected_dictionary.keys():
                        fake_clue = ParsedClue()
                        fake_clue.across = entry_across
                        fake_clue.text_including_enumeration = clue_string
                        fake_clue.set_number(str(entry_n), self.grid)
                        expected_dictionary[entry_n] = fake_clue
                        if verbose:
                            print("**** Added missing clue with index ", str(entry_n),
                                  fake_clue.tidied_text_including_enumeration())

        # Now the file can be written out:

        with io.FileIO(output_filename, 'wb') as f:
            f.write(bytearray(0x2C))
            dimensions_etc = bytearray(2)
            dimensions_etc[0] = self.width
            dimensions_etc[1] = self.height
            f.write(dimensions_etc)
            f.write(struct.pack("<h",
                                clue_groups[True].real_number_of_clues() +
                                clue_groups[False].real_number_of_clues()))
            f.write(bytearray(4))
            solutions = bytearray(self.width*self.height)
            empty_grid = bytearray(self.width*self.height)
            i = 0
            for y in range(0, self.height):
                for x in range(0, self.width):
                    c = self.grid.cells[y][x]
                    if c:
                        solutions[i] = ord(c.letter)
                        empty_grid[i] = ord('-')
                    else:
                        solutions[i] = ord('.')
                        empty_grid[i] = ord('.')
                    i += 1
            f.write(solutions)
            f.write(empty_grid)
            nul = bytearray(1)
            f.write(self.title.encode('UTF-8'))
            f.write(nul)
            f.write(self.author.encode('UTF-8'))
            f.write(nul)
            f.write(self.copyright_message.encode('UTF-8'))
            f.write(nul)
            all_clues = clue_groups[True].ordered_list_of_clues()
            all_clues += clue_groups[False].ordered_list_of_clues()

            all_clues.sort(key=keyfunc_clues)
            for c in all_clues:
                number_string_tidied = re.sub(r'/', ',', c.number_string)
                number_string_tidied = number_string_tidied.lower()
                clue_text = c.tidied_text_including_enumeration()
                # We have to stick the number string at the beginning
                # otherwise it won't be clear when the answers to clues cover
                # several entries in the grid.
                f.write(("[" + number_string_tidied + "] ").encode('UTF-8'))
                # Encode the clue text as UTF-8, because it's not defined what
                # the character set should be anywhere that I've seen.  (xword
                # currently assumes ISO-8859-1, but that doesn't strike me as
                # a good enough reason in itself, since it's easily patched.)
                f.write(clue_text.encode('UTF-8'))
                f.write(nul)
            f.write(nul)

def ensure_sys_argv_is_decoded():
    """Ensure that elements of sys.argv are decoded to Unicodeon Python 2"""
    if sys.version_info < (3, 0):
        for i, a in enumerate(sys.argv):
            sys.argv[i] = a.decode('UTF-8')

def main():
    parser = OptionParser()
    parser.add_option('-o', "--output", dest="output_filename",
                      default=False, help="output in a broken .PUZ format")
    parser.add_option('-d', "--date", dest="date",
                      help="specify the date of this crossword")
    parser.add_option('-v', '--verbose', dest='verbose', action="store_true",
                      default=False, help='verbose output')
    parser.add_option('-t', '--title', dest='title',
                      help="specify the crossword title")
    parser.add_option('-a', '--author', dest='author',
                      help="specify the crossword author or setter")
    parser.add_option('-n', '--number', dest='puzzle_number',
                      help="specify the puzzle number")
    parser.add_option('-c', '--copyright', dest='copyright_message',
                      help="specify the copyright message")

    ensure_sys_argv_is_decoded()
    (options, args) = parser.parse_args()

    if len(args) > 0:
        raise Exception("Unknown arguments: " + "\n".join(args))

    date_string = None
    if options.date:
        if not re.search(r'^\d{4}-\d{2}-\d{2}', options.date):
            raise Exception("Unknown date format, must be YYYY-MM-DD")
        date_string = options.date

    parsed = ParsedCCJ()

    # Make sys.stdin binary:
    parsed.read_from_ccj(io.open(sys.stdin.fileno(), 'rb'),
                         options.title,
                         options.author,
                         options.puzzle_number,
                         options.copyright_message,
                         date_string,
                         options.verbose)

    # Output to something like the .PUZ format used by AcrossLite.  I only
    # care about loading this into xword, so I'm not bothering to
    # calculate all the checksums, etc.  If you wanted to do this, details
    # can be found here: http://joshisanerd.com/puz/

    if options.output_filename:
        parsed.write_to_puz_file(options.output_filename, options.verbose)

if __name__ == "__main__":
    main()
