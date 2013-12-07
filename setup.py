from setuptools import setup, find_packages
setup(
    name = "ccj-to-puz",
    version = "0.1",
    packages = find_packages(),
    author = "Mark Longair",
    author_email = "mark-python@longair.net",
    description = "Parse crosswords in .ccj format, and output in .puz format",
    license = "GPL",
    keywords = "crossword crosswords",
    url = "http://longair.net/blog/2009/07/24/avoiding-crossword-applets/",
    entry_points = {
        'console_scripts': [
            'ccj-to-puz = ccj_to_puz.ccj_parse:main'
        ]
    }
)
