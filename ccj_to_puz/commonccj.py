"""A variety of helper classes useful to the CCJ parsing code"""

from collections import defaultdict
import re

def clue_number_string_to_duple(in_across, clue_number_string, grid):
    """A function that parses a clue number

    If an across clue is labelled something like "12,3 Down,5", then
    you can call this function (with in_across set to True) on each
    element of that comma separated list and it will return (12,True),
    (3,False) and (5,True) respectively."""

    m = re.search(r'(?ims)(\d+) *(A|D)?', clue_number_string)
    if m:
        n = int(m.group(1), 10)
        if m.group(2):
            # If across or down has been definitedly specified,
            # believe that:
            across = (m.group(2).lower() == 'a')
        else:
            directions = grid.clue_directions(n)
            if len(directions) == 0:
                raise Exception, "No clue directions found for clue number {0}!".format(n)
            elif len(directions) == 1:
                # It's unambiguously determined, so use that:
                across = (directions[0] == 'A')
            else:
                print "Warning: couldn't determine the direction of clue number {0}, so falling back on the clue group it was in"
                across = in_across
        return ( n, across )
    else:
        message = "Couldn't parse clue number string: '{0}'"
        raise Exception(message.format(clue_number_string))

class Cell:
    """A class to represent a particular cell in a crossword grid"""
    def __init__(self, row, column):
        self.letter = '+'
        self.row = row
        self.column = column
    def set_letter(self, l):
        """A setter method to update what's in the cell"""
        self.letter = l

class Grid:
    """A class to represent all the cells in a crossword grid"""
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.cells = []
        for _ in range(self.height):
            row = []
            for _ in range(self.width):
                row.append(None)
            self.cells.append(row)

    def to_grid_string(self, empty):
        """Output an ASCII-art representation of the grid"""
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

    def set_numbers(self):
        self.clue_numbers = defaultdict(dict)
        next_number_to_assign = 1
        for y in range(self.height):
            for x in range(self.width):
                cell = self.cells[y][x]
                if cell is None:
                    continue
                cell_left = None
                cell_right = None
                cell_above = None
                cell_below = None
                if x >= 1:
                    cell_left = self.cells[y][x - 1]
                if x < (self.width - 1):
                    cell_right = self.cells[y][x + 1]
                if y >= 1:
                    cell_above = self.cells[y - 1][x]
                if y < (self.height - 1):
                    cell_below = self.cells[y + 1][x]
                # This cell gets a number if:
                #   - there's no cell to the left, but there is one to the right
                #       (this is the start of an across entry)
                #   - or there's no cell above, but there is one below
                #       (this is the start of a down entry
                if cell_right and not cell_left:
                    self.clue_numbers[next_number_to_assign]['across'] = True
                if cell_below and not cell_above:
                    self.clue_numbers[next_number_to_assign]['down'] = True
                if next_number_to_assign in self.clue_numbers:
                    self.clue_numbers[next_number_to_assign]['x'] = x
                    self.clue_numbers[next_number_to_assign]['y'] = y
                    next_number_to_assign += 1

    def clue_directions(self, clue_number):
        if clue_number not in self.clue_numbers:
            return []
        result = []
        if 'across' in self.clue_numbers[clue_number]:
            result.append('A')
        if 'down' in self.clue_numbers[clue_number]:
            result.append('D')
        return result
