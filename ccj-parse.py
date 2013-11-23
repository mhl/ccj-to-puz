#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This script takes a .ccj file on standard input and can output the
# crossword in something like the AcrossLite .puz binary format
# suitable for loading into xword. [1]  Use --help or -h for usage
# information.
#
#  [1] apt-get install xword
#
# You need the Debian version 1.04 of xword.
#
# Note that this script was written with guesswork based on looking at
# example CCJ files.

import sys
import re
from optparse import OptionParser
import io
import struct
import unicodedata

from commonccj import *

def contains_control_characters(s):
    return any(unicodedata.category(c) == 'Cc' for c in s)

# Not sure about character set issues here, but it seems that 0x03
# turns on italic and 0x01 turns it off. In addition, there may be
# several random 0x01 bytes before the enumeration.  We remove any
# 0x01 or 0x03 bytes first.  Then try UTF-8 decoding - if that doesn't
# succeed, try Windows 1252 and ISO-8859-1, giving up if there are
# control characters left after decoding and replacing newlines with
# spaces.
def decode_bytes(b):
    bytes_to_decode = bytearray(filter(lambda c: c not in (0x01, 0x03),
                                       bytearray(b)))
    for encoding in ('utf_8', 'latin_1', 'cp1252'):
        try:
            s = bytes_to_decode.decode(encoding)
        except UnicodeDecodeError:
            continue
        s = re.sub('\s+', ' ', s)
        if not contains_control_characters(s):
            return s
    raise Exception("Couldn't guess the character set.")

def byte_at(data, i):
    if isinstance(data, str):
        return ord(data[i])
    else:
        return int(data[i])

def read_string(data,start_index):
    length = byte_at(data, start_index)
    bytes_for_string = data[(start_index+1):(start_index+length+1)]
    s = decode_bytes(bytes_for_string)
    return (s,start_index+length+1)

# There sometimes seems to be a succession of bytes here in groups of
# repeated groups of four, next - this function tests for the patterns
# I've seen:

def skippable_block_of_four(data,start_index):
    block = bytearray(data[start_index:start_index + 4])
    skippable_blocks = [[0x00, 0xff, 0xff, 0xff],
                        [0x00, 0x00, 0xff, 0xff],
                        [0x00, 0x00, 0x00, 0x00]]
    return block in (bytearray(l) for l in skippable_blocks)

def reduce_coordinate(x):
    if x >= 0x80:
        return x - 0x80
    else:
        return x

def read_clue_start_coordinates(data,start_index):
    # My assumption is that if the first byte is >= 0x80 then it's a
    # list of coordinates terminated by a NUL, otherwise it's just two
    # bytes with the coordinate:
    start_coordinates = []
    if byte_at(data, start_index) >= 0x80:
        i = start_index
        while byte_at(data, i) != 0:
            x = reduce_coordinate(byte_at(data, i))
            y = reduce_coordinate(byte_at(data, i+1))
            start_coordinates.append( (x,y) )
            i += 2
        return (start_coordinates,i+1)
    else:
        x = reduce_coordinate(byte_at(data, start_index))
        y = reduce_coordinate(byte_at(data, start_index+1))
        start_coordinates.append( (x,y) )
        return (start_coordinates,start_index+2)

def parse_list_of_clues(data,start_index):
    result = ListOfClues()
    i = start_index
    # Read the label for this list of clues:
    result.label, i = read_string(data,i)
    if options.verbose:
        print("clue set label is: "+result.label)
    result.across = None
    if re.search("(?ims)across",result.label):
        result.across = True
    elif re.search("(?ims)down",result.label):
        result.across = False
    else:
        raise Exception("Couldn't find either /across/i or /down/i in label: '"+str(result.label)+"'")
    # Skip some bytes:
    result.unknown_bytes = data[i:i+3]
    i += 3
    if options.verbose:
        print("  Before list of clues, got these unknown bytes:")
        for b in result.unknown_bytes:
            print("    "+str(b))
    result.number_of_clues = byte_at(data, i)
    if options.verbose:
        print("number of clues is: "+str(result.number_of_clues))
    i += 1
    clues_found = 0
    while True:
        if options.verbose:
            print("--------------------------")
        clue = IndependentClue()
        clue.across = result.across
        clue.start_coordinates, i = read_clue_start_coordinates(data,i)
        if options.verbose:
            for c in clue.start_coordinates:
                print("A start at x: "+str(c[0])+", y: "+str(c[1]))
        s, i = read_string(data,i)
        clue.set_number(s)
        if options.verbose:
            print("clue number: "+clue.number_string)
            print("all clue numbers: "+(", ".join(map(lambda x: str(x[0])+(x[1] and "A" or "D"), clue.all_clue_numbers))))
        # Skip a NUL:
        if byte_at(data, i) != 0:
            raise Exception("After clue number we expect a NUL to skip over")
        i += 1
        clue.text_including_enumeration, i = read_string(data,i)
        if options.verbose:
            print("clue text: "+clue.text_including_enumeration)
        result.clue_dictionary[clue.all_clue_numbers[0][0]] = clue
        clues_found += 1
        if clues_found >= result.number_of_clues:
            break
    return result, i

# This function is for sorting clues before output, we want them to be
# in the order the number appear in the grid, with across before down
# if there's a choice:

def keyfunc_clues(x):
    across_for_sorting = 1
    if x.across:
        across_for_sorting = 0
    return ( x.all_clue_numbers[0][0], across_for_sorting )

# A convenience class - we have one object of this class for all the
# across clues and another object of this class for the down clues:

class ListOfClues:
    def __init__(self):
        self.number_of_clues = None
        self.label = None
        self.clue_dictionary = {}
        self.across = None
        self.unknown_bytes = None
    def ordered_list_of_clues(self):
        keys = sorted(self.clue_dictionary.keys())
        return list(map(lambda x: self.clue_dictionary[x], keys))
    def real_number_of_clues(self):
        return len(self.clue_dictionary)

# Just to store a single clue:

class IndependentClue:
    def __init__(self):
        self.number_string = None
        self.text_including_enumeration = None
        self.start_coordinates = None
        self.across = None
        self.all_clue_numbers = None
    def tidied_text_including_enumeration(self):
        t = re.sub('[\x00-\x1f]','',self.text_including_enumeration)
        t = re.sub(' *\(',' (',t)
        return t
    def set_number(self,clue_number_string):
        self.number_string = clue_number_string
        if self.across == None:
            raise Exception("Trying to call self.set_number() before self.across is set")
        self.all_clue_numbers = list(map( lambda x: clue_number_string_to_duple(self.across,x), re.split('[,/]',clue_number_string)))

class ParsedCCJ:

    def __init__(self):
        self.width = None
        self.height = None
        self.across_clues = None
        self.down_clues = None
        self.grid = None
        self.title = None
        self.author = None
        self.copyright = None
        self.setter = None
        self.puzzle_number = None

    def read_from_ccj(self, f, title, author, puzzle_number, copyright, verbose=False):

        d = f.read()

        # i is the index into the file for the rest of this script:
        i = 2

        # I think these must be the list of buttons on the left:
        while byte_at(d, i) != 0:
            s, i = read_string(d,i)
            if verbose:
                print("got button string: "+s)

        # Then the congratulations message, I think:
        i += 1
        s, i = read_string(d,i)

        if verbose:
            print("got congratulations message: "+s)

        # Skip another byte; 0x02 in the Independent it seems, but 0x00 in the
        # Herald puzzle I tried.
        i += 1

        # I think we get the grid dimensions in the next two:
        self.width = byte_at(d, i)
        i += 1

        self.height = byte_at(d, i)
        i += 1

        self.grid = Grid(self.width,self.height)

        # Now skip over everything until we think we see the grid, since I've
        # no idea what it's meant to mean:
        while byte_at(d, i) != 0x3f and byte_at(d, i) != 0x23:
            i += 1

        for y in range(0,self.height):
            for x in range(0,self.width):
                # Lights seem to be indicated by: '?' (or 'M' very occasionally)
                if byte_at(d, i) in (0x3f, 0x4d):
                    self.grid.cells[y][x] = Cell(y,x)
                # Blocked-out squares seem to be always '#'
                elif byte_at(d, i) == 0x23:
                    pass
                else:
                    raise Exception("Unknown value: "+str(byte_at(d, i))+" at ("+str(x)+","+str(y)+")")
                i += 1

        if verbose:
            print("grid is:\n"+self.grid.to_grid_string(True))

        # Next there's a grid structure the purpose of which I don't
        # understand:
        grid_unknown_purpose = Grid(self.width,self.height)

        for y in range(0,self.height):
            for x in range(0,self.width):
                grid_unknown_purpose.cells[y][x] = Cell(y,x)
                if byte_at(d, i) == 0:
                    grid_unknown_purpose.cells[y][x].set_letter(' ')
                elif byte_at(d, i) < 10:
                    grid_unknown_purpose.cells[y][x].set_letter(str(byte_at(d, i)))
                else:
                    truncated = byte_at(d, i) % 10
                    if verbose:
                        print("Warning, truncating "+str(byte_at(d, i))+" to "+str(truncated)+" at ("+str(x)+","+str(y)+")")
                    grid_unknown_purpose.cells[y][x].set_letter(str(truncated))
                i += 1

        # Seem to need to skip over an extra byte (0x01) here before the
        # answers.  Maybe it indicates whether there are answers next or not:
        if byte_at(d, i) != 1:
            raise Exception("So far we expect a 0x01 before the answers...")
        i += 1

        if verbose:
            print("grid_unknown_purpose is:\n"+grid_unknown_purpose.to_grid_string(False))

        # Now there's the grid with the answers:
        for y in range(0,self.height):
            for x in range(0,self.width):
                if self.grid.cells[y][x]:
                    self.grid.cells[y][x].set_letter(chr(byte_at(d, i)))
                    i += 1

        if verbose:
            print("grid with answers is:\n"+self.grid.to_grid_string(False))

        skipped_blocks_of_four = 0
        while skippable_block_of_four(d,i):
            i += 4
            skipped_blocks_of_four += 1

        if skipped_blocks_of_four > 0:
            if verbose:
                print("Skipped over "+str(skipped_blocks_of_four)+" blocks of 0x00 0xff 0xff 0xff")

        # I expect the next one to be 0x02:
        if byte_at(d, i) != 0x02:
            raise Exception("Expect the first of the block of 16 always to be 0x02, in fact: "+str(byte_at(d, i)))

        # Always just 16?
        i += 16

        self.across_clues, i = parse_list_of_clues(d,i)

        if verbose:
            print("Now do down clues:")

        self.down_clues, i = parse_list_of_clues(d,i)

        m = re.search('^(.*)-([0-9]+)',self.across_clues.label)
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
            self.title += " "+self.puzzle_number+" / "+self.setter
        elif self.setter:
            self.title += " / "+self.setter
        elif self.puzzle_number:
            self.title += " "+self.puzzle_number

        if date_string:
            self.title += " ("+date_string+")"

        self.author = "Unknown Setter"
        if author:
            self.author = author

        self.copyright = "© Unknown"
        if copyright:
            self.copyright = copyright

        # In the AcrossLite .PUZ format we need to make sure that there's one
        # "clue" for each clue number, even if it's just "See 6" for clues
        # whose answers are split over different clue numbers in the grid.

        # So, go through the clue dictionaries and make sure that there is
        # something for every clue.  (So we don't miss the "See 6" type of
        # clue.)

        for across in (True,False):
            clue_dictionary = None
            if across:
                clue_dictionary = self.across_clues.clue_dictionary
            else:
                clue_dictionary = self.down_clues.clue_dictionary
            values = list(clue_dictionary.values())
            for c in values:
                original_clue_duple = c.all_clue_numbers[0]
                for l in c.all_clue_numbers:
                    # l should be a duple of clue number and an "across"
                    # boolean:
                    n = l[0]
                    a = l[1]
                    expected_dictionary = None
                    clue_string = "See "+str(original_clue_duple[0])
                    if a:
                        expected_dictionary = self.across_clues.clue_dictionary
                    else:
                        expected_dictionary = self.down_clues.clue_dictionary
                    if a != across:
                        clue_string += a and " across" or " down"
                    ekeys = list(expected_dictionary.keys())
                    if not n in ekeys:
                        fake_clue = IndependentClue()
                        fake_clue.across = a
                        fake_clue.text_including_enumeration = clue_string
                        fake_clue.set_number(str(n))
                        expected_dictionary[n] = fake_clue
                        if verbose:
                            print("**** Added missing clue with index "+str(n)+" "+fake_clue.tidied_text_including_enumeration())

    def write_to_puz_file(self, output_filename):
        f = io.FileIO(output_filename,'wb')
        f.write(bytearray(0x2C))
        dimensions_etc = bytearray(2)
        dimensions_etc[0] = self.width
        dimensions_etc[1] = self.height
        f.write(dimensions_etc)
        f.write(struct.pack("<h",self.across_clues.real_number_of_clues()+self.down_clues.real_number_of_clues()))
        f.write(bytearray(4))
        solutions = bytearray(self.width*self.height)
        empty_grid = bytearray(self.width*self.height)
        i = 0
        for y in range(0,self.height):
            for x in range(0,self.width):
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
        f.write(self.copyright.encode('UTF-8'))
        f.write(nul)
        all_clues = self.across_clues.ordered_list_of_clues() + self.down_clues.ordered_list_of_clues()
        all_clues.sort(key=keyfunc_clues)
        for c in all_clues:
            number_string_tidied = re.sub('/',',',c.number_string)
            number_string_tidied = number_string_tidied.lower()
            clue_text = c.tidied_text_including_enumeration()
            # We have to stick the number string at the beginning
            # otherwise it won't be clear when the answers to clues cover
            # several entries in the grid.
            f.write(("["+number_string_tidied+"] ").encode('UTF-8'))
            # Encode the clue text as UTF-8, because it's not defined what
            # the character set should be anywhere that I've seen.  (xword
            # currently assumes ISO-8859-1, but that doesn't strike me as
            # a good enough reason in itself, since it's easily patched.)
            f.write(clue_text.encode('UTF-8'))
            f.write(nul)
        f.write(nul)
        f.close()


if __name__ == "__main__":

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
    parser.add_option('-c', '--copyright', dest='copyright',
                      help="specify the copyright message")

    if sys.version_info < (3, 0):
        for i, a in enumerate(sys.argv):
            sys.argv[i] = a.decode('UTF-8')

    (options, args) = parser.parse_args()

    if len(args) > 0:
        raise Exception("Unknown arguments: " + "\n".join(args))

    date_string = None
    if options.date:
        if not re.search("^\d{4}-\d{2}-\d{2}",options.date):
            raise Exception("Unknown date format, must be YYYY-MM-DD")
        date_string = options.date

    parsed = ParsedCCJ()

    # Make sys.stdin binary:
    parsed.read_from_ccj(io.open(sys.stdin.fileno(), 'rb'),
                         options.title,
                         options.author,
                         options.puzzle_number,
                         options.copyright,
                         options.verbose)

    # Output to something like the .PUZ format used by AcrossLite.  I only
    # care about loading this into xword, so I'm not bothering to
    # calculate all the checksums, etc.  If you wanted to do this, details
    # can be found here: http://joshisanerd.com/puz/

    if options.output_filename:
        parsed.write_to_puz_file(options.output_filename)
