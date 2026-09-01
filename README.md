# Hermes plugin workspace

This repository is a workspace for independently installable Hermes plugins.
Each plugin lives at `plugins/<plugin-id>/` and owns its manifest, Python
runtime, tests, Desktop extension, and release metadata.

| Plugin | Purpose |
| --- | --- |
| [`hermes-acp`](plugins/hermes-acp) | Runs ACP coding agents as Hermes model backends. |

See [the workspace guide](plugins/README.md) to add another plugin. Each
plugin is installed from its own Git subdirectory, so adding a sibling does not
change existing installs.
