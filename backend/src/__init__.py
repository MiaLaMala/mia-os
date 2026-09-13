"""Mia OS: persoenliches Lebens-Dashboard."""

# Die Version steht in version.json und wird beim Bauen aus der
# Git-Historie erzeugt. Frueher stand sie an drei Stellen und die
# widersprachen sich bereits (0.1.0 hier, 0.2.0 zweimal woanders).
from src.ueber import version as _version

__version__ = _version()
