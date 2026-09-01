"""Directory-install entry point for the Hermes ACP plugin."""

if __package__:
    from .hermes_acp import register
else:  # Loaded directly rather than as a directory package.
    from hermes_acp import register

__all__ = ["register"]
