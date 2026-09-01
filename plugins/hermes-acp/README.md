# Hermes ACP

`hermes-acp` is a unified Hermes plugin that runs ACP coding agents as a
native `acp` model provider. It exposes four selectable models:

- `codex`, through `@agentclientprotocol/codex-acp`
- `claude`, through `@agentclientprotocol/claude-agent-acp`
- `cursor`, through Cursor Agent's native ACP server
- `grok`, through Grok CLI's native ACP server

Each Hermes chat, agent, and Bot Mode profile can select any of these models
independently. The provider remains `acp`; only the model name changes.

## Install

This repository is a multi-plugin workspace. Install this plugin member, not
the workspace root, then install its Python entry point into Hermes's virtual
environment. Hermes v0.21 installs the plugin files and Desktop extension but
does not install the Python distribution automatically:

```sh
hermes plugins install patrick-lai/hermes-acp/plugins/hermes-acp --enable
uv pip install \
  --python "$HOME/.hermes/hermes-agent/venv/bin/python" \
  "$HOME/.hermes/plugins/hermes-acp"
```

For a backend-only installation, skip the plugin-manager command and install
the Git subdirectory directly:

```sh
uv pip install \
  --python "$HOME/.hermes/hermes-agent/venv/bin/python" \
  "git+https://github.com/patrick-lai/hermes-acp.git#subdirectory=plugins/hermes-acp"
```

The plugin uses `HERMES_ACP_ENABLED` only as Hermes's required local
API-key-shaped registration sentinel. It is neither a credential nor sent to
any agent.

## Live selection in Hermes Desktop

1. In **Settings → Plugins**, enable **Hermes ACP**. Its Desktop half loads
   immediately and adds **ACP agents** to the sidebar and command palette.
2. The ACP agents page sets the profile default for new chats. Choosing a card
   writes the same live model configuration as Hermes's native picker.
3. To select a provider for one existing chat, click that chat's **model chip**.
   Choose provider **acp**, then choose `codex`, `claude`, `cursor`, or `grok`.
   The change is session-scoped and takes effect on the next turn.
4. To pin a Bot Mode persona/agent, open the bot's **Model** field and make the
   same provider/model selection. That override belongs to the bot profile and
   does not change the default or other agents.

After the first install or a backend update, restart Hermes Desktop once.
Hermes discovers the Python provider and its execution middleware when the
profile backend starts; the Desktop page itself hot-reloads independently.

The Desktop page and the native picker deliberately have different jobs:
the page controls the profile default, while Hermes owns the live per-session
and per-bot override lifecycle.

## Requirements and authentication

- Python 3.11 or newer and Hermes Agent v0.21.0 or newer
- Node.js with `npx` for Codex and Claude
- `cursor-agent` on `PATH` for Cursor
- `grok` on `PATH` for Grok

Authenticate each CLI through its normal interactive flow before selecting it:

```sh
codex login
claude auth login
cursor-agent login
grok login
```

The bridge never reads, copies, or stores provider credentials. ACP agents own
their own authentication, sandbox, tool loop, and permission UI.

## Advanced configuration

Use **Settings → Plugins** to inspect the plugin and use the ACP page for
normal selection. Advanced launch overrides live under the plugin's canonical
settings namespace and are read fresh for every completion, so changes are
live without a reinstall:

```yaml
plugins:
  enabled:
    - hermes-acp
  entries:
    hermes-acp:
      settings:
        default_model: codex
        permission_mode: reject  # or explicit allow_once
        timeout_seconds: 300
        # cwd: /absolute/path/to/project
        codex:
          command: npx
          args: [-y, "@agentclientprotocol/codex-acp@1.7.0"]
        claude:
          command: npx
          args: [-y, "@agentclientprotocol/claude-agent-acp"]
        cursor:
          command: cursor-agent
          args: [agent, acp]
        grok:
          command: grok
          args: [agent, stdio]
```

The older flat `*_command` and `*_args` settings remain supported for every
provider. Nested blocks take precedence. Set `auth_method` only when an agent
advertises that exact ACP authentication method.

The default `permission_mode` is `reject`: reverse permission requests are
cancelled, reverse filesystem and terminal methods are not advertised, and
unknown extension methods are rejected. `allow_once` is an explicit, one-request
exception and never selects an `allow_always` option.

## Prove the execution path

The bridge logs a credential-safe start and completion record for every ACP
turn. It includes `provider=acp`, the selected backend, the executable name,
and the result status, but never the prompt or command arguments.

Run a fresh one-shot through Hermes and inspect its machine-readable usage:

```sh
hermes -z 'Return exactly HERMES_ACP_OK.' \
  --provider acp \
  --model codex \
  --usage-file /tmp/hermes-acp-usage.json
cat /tmp/hermes-acp-usage.json
hermes logs --since 5m | grep 'Hermes ACP execution'
```

The response must be `HERMES_ACP_OK`, the usage file must report
`"provider": "acp"` with `"model": "codex"`, and the log must contain both
`execution started` and `execution completed` for `backend=codex`. A successful
response plus those two records proves Hermes intercepted the turn and drove
the ACP subprocess instead of falling through to the placeholder HTTP URL.

## Repository layout

This package is intentionally self-contained under `plugins/hermes-acp/`:

```text
plugins/hermes-acp/
├── plugin.yaml          # Hermes manifest and typed setting contract
├── hermes_acp/          # ACP provider registration and runtime bridge
├── desktop/plugin.js    # live Hermes Desktop UI half
├── tests/               # deterministic ACP and integration tests
└── pyproject.toml       # optional pip distribution
```

Add future Hermes plugins as sibling folders under `plugins/`. Each is
installed with its own repository subdirectory identifier, so it can evolve
and release without coupling to `hermes-acp`.

## Development

The tests use a deterministic local ACP subprocess. They never call vendor
CLIs, npm, or the network.

```sh
cd plugins/hermes-acp
uv sync --extra test
uv run pytest -q
```

From the workspace root, run `make verify` to run formatting, linting,
type-checking, the wheel build, and the deterministic tests for this package.

## License

MIT
