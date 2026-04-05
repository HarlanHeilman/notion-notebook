"""Validation and configuration errors for the Notion notebook exporter."""


class NotionNotebookError(Exception):
    """Base class for exporter errors that are safe to show to notebook users."""


class ConfigurationError(NotionNotebookError):
    """Raised when token, page id, or configuration is invalid or missing."""


class NotebookPathError(NotionNotebookError):
    """Raised when the active notebook path cannot be resolved in this environment."""
