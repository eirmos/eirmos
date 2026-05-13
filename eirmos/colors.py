"""ANSI color codes used by the text formatters.

This module is purposely tiny — it is the only place that knows
about terminal escape sequences.  Other layers should depend on
``Colors`` rather than hard-coding escape codes so they can be
disabled centrally (e.g. when writing to a file or a non-TTY).
"""


class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

    @classmethod
    def disable(cls):
        """Replace all color codes with empty strings (irreversible)."""
        cls.HEADER = ''
        cls.BLUE = ''
        cls.CYAN = ''
        cls.GREEN = ''
        cls.YELLOW = ''
        cls.RED = ''
        cls.BOLD = ''
        cls.DIM = ''
        cls.RESET = ''
