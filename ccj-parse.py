#!/usr/bin/python3.1
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

(options, args) = parser.parse_args()

date_string = None
if options.date:
    if not re.search("^\d{4}-\d{2}-\d{2}",options.date):
        raise Exception("Unknown date format, must be YYYY-MM-DD")
    date_string = options.date

from commonccj import *

# Make sys.stdin binary:
d = sys.stdin.buffer.read()

import unicodedata
def contains_control_characters(s):
    for c in s:
        if unicodedata.category(c) == 'Cc':
            return True
    return False

# Not sure about character set issues here, but it seems that 0x03
# turns on italic and 0x01 turns it off. In addition, there may be
# several random 0x01 bytes before the enumeration.  We remove any
# 0x01 or 0x03 bytes first.  Then try UTF-8 decoding - if that doesn't
# succeed, try Windows 1252 and ISO-8859-1, giving up if there are
# control characters left after decoding..

def decode_bytes(b):
    b = bytes(filter(lambda c: (c != 0x01) and (c != 0x03), b))
    try:
        s = b.decode('utf_8')
        return s
    except UnicodeDecodeError:
        # Try ISO-8859-1 first, then Windows 1252 if
        # there are unprintable characters in the
        # decoded version.
        s = b.decode('latin_1')
        if not contains_control_characters(s):
            return s
        s = b.decode('cp1252')
        if not contains_control_characters(s):
            return s
        raise Exception("Couldn't guess the character set.")

def read_string(data,start_index):
    length = int(data[start_index])
    bytes_for_string = data[(start_index+1):(start_index+length+1)]
    s = decode_bytes(bytes_for_string)
    return (s,start_index+length+1)

# i is the index into the file for the rest of this script:
i = 2

# I think these must be the list of buttons on the left:
while d[i] != 0:
    s, i = read_string(d,i)
    if options.verbose:
        print("got button string: "+s)

# Then the congratulations message, I think:
i += 1
s, i = read_string(d,i)

if options.verbose:
    print("got congratulations message: "+s)

# Skip another byte; 0x02 in the Independent it seems, but 0x00 in the
# Herald puzzle I tried.
i += 1

# I think we get the grid dimensions in the next two:
width = d[i]
i += 1

height = d[i]
i += 1

grid = Grid(width,height)

# Now skip over everything until we think we see the grid, since I've
# no idea what it's meant to mean:
while d[i] != 0x3f and d[i] != 0x23:
    i += 1

for y in range(0,height):
    for x in range(0,width):
        # Lights seem to be indicated by: '?' (or 'M' very occasionally)
        if d[i] == 0x3f or d[i] == 0x4d:
            grid.cells[y][x] = Cell(y,x)
        # Blocked-out squares seem to be always '#'
        elif d[i] == 0x23:
            pass
        else:
            raise Exception("Unknown value: "+str(d[i])+" at ("+str(x)+","+str(y)+")")
        i += 1

if options.verbose:
    print("grid is:\n"+grid.to_grid_string(True))

# Next there's a grid structure the purpose of which I don't
# understand:
grid_unknown_purpose = Grid(width,height)

for y in range(0,height):
    for x in range(0,width):
        grid_unknown_purpose.cells[y][x] = Cell(y,x)
        if d[i] == 0:
            grid_unknown_purpose.cells[y][x].set_letter(' ')
        elif d[i] < 10:
            grid_unknown_purpose.cells[y][x].set_letter(str(d[i]))
        else:
            truncated = d[i] % 10
            if options.verbose:
                print("Warning, truncating "+str(d[i])+" to "+str(truncated)+" at ("+str(x)+","+str(y)+")")
            grid_unknown_purpose.cells[y][x].set_letter(str(truncated))
        i += 1

# Seem to need to skip over an extra byte (0x01) here before the
# answers.  Maybe it indicates whether there are answers next or not:
if d[i] != 1:
    raise Exception("So far we expect a 0x01 before the answers...")
i += 1

if options.verbose:
    print("grid_unknown_purpose is:\n"+grid_unknown_purpose.to_grid_string(False))

# Now there's the grid with the answers:
for y in range(0,height):
    for x in range(0,width):
        if grid.cells[y][x]:
            grid.cells[y][x].set_letter(chr(d[i]))
            i += 1

if options.verbose:
    print("grid with answers is:\n"+grid.to_grid_string(False))

# There sometimes seems to be a succession of bytes here in groups of
# repeated groups of four, next - this function tests for the patterns
# I've seen:

def skippable_block_of_four(data,start_index):
    if d[i] == 0x00 and d[i+1] == 0xff and d[i+2] == 0xff and d[i+3] == 0xff:
        return True
    elif d[i] == 0x00 and d[i+1] == 0x00 and d[i+2] == 0xff and d[i+3] == 0xff:
        return True
    elif d[i] == 0x00 and d[i+1] == 0x00 and d[i+2] == 0x00 and d[i+3] == 0x00:
        return True
    else:
        return False

skipped_blocks_of_four = 0
while skippable_block_of_four(d,i):
    i += 4
    skipped_blocks_of_four += 1

if skipped_blocks_of_four > 0:
    if options.verbose:
        print("Skipped over "+str(skipped_blocks_of_four)+" blocks of 0x00 0xff 0xff 0xff")

# I expect the next one to be 0x02:
if d[i] != 0x02:
    raise Exception("Expect the first of the block of 16 always to be 0x02, in fact: "+str(d[i]))

# Always just 16?
i += 16

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
    if data[start_index] >= 0x80:
        i = start_index
        while data[i] != 0:
            x = reduce_coordinate(data[i])
            y = reduce_coordinate(data[i+1])
            start_coordinates.append( (x,y) )
            i += 2
        return (start_coordinates,i+1)
    else:
        x = reduce_coordinate(data[start_index])
        y = reduce_coordinate(data[start_index+1])
        start_coordinates.append( (x,y) )
        return (start_coordinates,start_index+2)

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
    result.number_of_clues = data[i]
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
        if data[i] != 0:
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

across_clues, i = parse_list_of_clues(d,i)

if options.verbose:
    print("Now do down clues:")

down_clues, i = parse_list_of_clues(d,i)

setter = None
puzzle_number = None

m = re.search('^(.*)-([0-9]+)',across_clues.label)
if m:
    setter = m.group(1)
    puzzle_number = m.group(2)

if (not setter) and options.author:
    setter = options.author
if (not puzzle_number) and options.puzzle_number:
    puzzle_number = option.puzzle_number

title = "Crossword"
if options.title:
    title = options.title

if setter and puzzle_number:
    title += " "+puzzle_number+" / "+setter
elif setter:
    title += " / "+setter
elif puzzle_number:
    title += " "+puzzle_number

if date_string:
    title += " ("+date_string+")"

author = "Unknown Setter"
if options.author:
    author = options.author

copyright = "© Unknown"
if options.copyright:
    copyright = options.copyright

# In the AcrossLite .PUZ format we need to make sure that there's one
# "clue" for each clue number, even if it's just "See 6" for clues
# whose answers are split over different clue numbers in the grid.

# So, go through the clue dictionaries and make sure that there is
# something for every clue.  (So we don't miss the "See 6" type of
# clue.)

for across in (True,False):
    clue_dictionary = None
    if across:
        clue_dictionary = across_clues.clue_dictionary
    else:
        clue_dictionary = down_clues.clue_dictionary
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
                expected_dictionary = across_clues.clue_dictionary
            else:
                expected_dictionary = down_clues.clue_dictionary
            if a != across:
                clue_string += a and " across" or "down"
            ekeys = list(expected_dictionary.keys())
            if not n in ekeys:
                fake_clue = IndependentClue()
                fake_clue.across = a
                fake_clue.text_including_enumeration = clue_string
                fake_clue.set_number(str(n))
                expected_dictionary[n] = fake_clue
                if options.verbose:
                    print("**** Added missing clue with index "+str(n)+" "+fake_clue.tidied_text_including_enumeration())

# This function is for sorting clues before output, we want them to be
# in the order the number appear in the grid, with across before down
# if there's a choice:

def keyfunc_clues(x):
    across_for_sorting = 1
    if x.across:
        across_for_sorting = 0
    return ( x.all_clue_numbers[0][0], across_for_sorting )

# Output to something like the .PUZ format used by AcrossLite.  I only
# care about loading this into xword, so I'm not bothering to
# calculate all the checksums, etc.  If you wanted to do this, details
# can be found here: http://joshisanerd.com/puz/

if options.output_filename:
    f = io.FileIO(options.output_filename,'wb')
    f.write(bytearray(0x2C))
    dimensions_etc = bytearray(2)
    dimensions_etc[0] = width
    dimensions_etc[1] = height
    f.write(dimensions_etc)
    f.write(struct.pack("<h",across_clues.real_number_of_clues()+down_clues.real_number_of_clues()))
    f.write(bytearray(4))
    solutions = bytearray(width*height)
    empty_grid = bytearray(width*height)
    i = 0
    for y in range(0,height):
        for x in range(0,width):
            c = grid.cells[y][x]
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
    f.write(title.encode('UTF-8'))
    f.write(nul)
    f.write(author.encode('UTF-8'))
    f.write(nul)
    f.write(copyright.encode('UTF-8'))
    f.write(nul)
    all_clues = across_clues.ordered_list_of_clues() + down_clues.ordered_list_of_clues()
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