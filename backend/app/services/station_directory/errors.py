"""Errors raised by the shared station directory layer."""

from __future__ import annotations


class StationDirectoryError(RuntimeError):
    """Base error for station directory resolution and provider failures."""


class StationDirectoryNotFound(StationDirectoryError):
    """Raised when a requested station cannot be resolved by a provider."""
