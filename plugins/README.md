# Workspace layout

Every folder directly below `plugins/` is a standalone Hermes plugin package.
It must be safe to install on its own with Hermes's Git installer using that
folder as the `subdir`.

```text
plugins/
  <plugin-id>/
    plugin.yaml          # Hermes native-plugin manifest
    __init__.py          # directory-plugin entry point
    pyproject.toml       # optional pip distribution
    <python-package>/    # runtime implementation
    desktop/plugin.js    # optional Hermes Desktop UI half
    tests/
```

Use a distinct plugin id, Python distribution name, and Python package for a
new sibling. Do not make one plugin import another unless the dependency is
declared in its `plugin.yaml` with `requires_plugins`.

Install a workspace member by its subdirectory, for example:

```sh
hermes plugins install patrick-lai/hermes-acp/plugins/hermes-acp --enable
```
