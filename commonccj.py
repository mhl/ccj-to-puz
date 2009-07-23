# A variety of helper classes useful to the CCJ parsing code in
# ccj-parse.py.

import re

# If an across clue is labelled something like "12,3 Down,5", then you
# can call this function (with in_across set to True) on each element
# of that comma separated list and it will return (12,True), (3,False)
# and (5,True) respectively.

def clue_number_string_to_duple(in_across,clue_number_string):
    m = re.search('(?ims)(\d+) *(A|D)?',clue_number_string)
    if m:
        across = in_across
        if m.group(2):
            across = (m.group(2).lower() == 'a')
        n = int(m.group(1),10)
        return ( n, across )
    else:
        raise Exception("Couldn't parse clue number string: '%s'" % (clue_number_string))

class Cell:
    def __init__(self,row,column):
        self.letter = '+'
        self.row = row
        self.column = column
    def set_letter(self,l):
        self.letter = l

class Grid:
    def __init__(self,width,height):
        self.width = width
        self.height = height
        self.cells = list()
        for r in range(self.height):
            row = list()
            for c in range(self.width):
                row.append(None)
            self.cells.append(row)
    def to_grid_string(self,empty):
        result = ""
        for r in self.cells:
            row_string = ""
            for c in r:
                if c:
                    letter = '+'
                    if not empty:
                        letter = c.letter
                    row_string = row_string + letter
                else:
                    row_string = row_string + ' '
            result = result + row_string + "\n"
        return result
