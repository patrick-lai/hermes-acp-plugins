"""Hermes entry-point module.

Keeping this tiny module separate lets Hermes classify the package as a
general plugin for middleware loading. Importing the package also performs the
provider-side registration needed during Hermes' earlier provider discovery.
"""

from . import register

__all__ = ["register"]
