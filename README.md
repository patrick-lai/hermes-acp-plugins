# hermes-acp

`hermes-acp` lets Hermes Agent v0.21.0 use native Agent Client Protocol (ACP)
agents as model backends. It exposes one Hermes provider, `acp`, with two model
choices:

- `grok` launches `grok agent stdio`.
- `codex` launches the pinned adapter
  `npx -y @agentclientprotocol/codex-acp@1.7.0`.

The Python bridge uses ACP protocol version 1 through
`agent-client-protocol==0.9.0`. Every intercepted completion starts a fresh ACP
process, creates a fresh session, sends one text transcript, waits for a stop
reason, and closes the connection and process.

Hermes v0.21 only admits dynamically registered providers into its early auth
registry when they use the API-key profile shape. The plugin therefore declares
`HERMES_ACP_ENABLED` as a local routing sentinel; it is not a credential and is
never sent anywhere. The plugin sets it to `1` inside the Hermes process, and
the middleware short-circuits the placeholder HTTP route.

## Requirements

- Python 3.11 or newer
- Hermes Agent v0.21.0
- For Grok: the `grok` CLI on `PATH`, already authenticated
- For Codex: Node.js with `npx` on `PATH`, plus the authentication expected by
  the Codex ACP adapter

## Install

Install the package into Hermes's own Python environment, then enable its
supported `hermes_agent.plugins` entry point:

```sh
uv pip install \
  --python "$HOME/.hermes/hermes-agent/venv/bin/python" \
  "git+https://github.com/patrick-lai/hermes-acp.git"
hermes plugins enable hermes-acp --no-allow-tool-override
```

The Python entry point is intentional. Hermes discovers model-provider plugins
before it loads general middleware plugins; this package participates in both
supported seams. Hermes's Git directory installer places a repository in only
the general-plugin directory, so it cannot install this dual-seam plugin by
itself. The command above changes only Hermes's virtual environment and normal
plugin configuration—not the Hermes repository or source files.

## Select a provider and model

Choose provider `acp` and model `grok` or `codex` in the Hermes model picker. A
one-session CLI selection is:

```sh
hermes --provider acp --model grok
hermes --provider acp --model codex
```

The equivalent persistent model selection in the normal Hermes configuration
is:

```yaml
model:
  provider: acp
  default: grok
```

Use `default: codex` for the Codex adapter. No Claude or Cursor backend is
registered by this plugin.

## Configuration

All plugin behavior is configured under the normal Hermes plugin entry. There
are no plugin-specific behavioral environment variables.

```yaml
plugins:
  enabled:
    - hermes-acp
  entries:
    hermes-acp:
      settings:
        permission_mode: reject
        timeout_seconds: 300
        cwd: /absolute/path/to/project
        # auth_method: exact-id-advertised-by-the-agent
        grok:
          command: grok
          args: [agent, stdio]
        codex:
          command: npx
          args: [-y, "@agentclientprotocol/codex-acp@1.7.0"]
```

The backend blocks are optional overrides. Omitting them preserves the exact
commands shown above. `cwd` is optional; the active request/project directory
is resolved to an absolute path when it is absent. `timeout_seconds` covers the
whole initialize/new-session/prompt lifecycle. For migration from an earlier
flat configuration, `grok_command`/`grok_args` and
`codex_command`/`codex_args` are also accepted; nested backend blocks take
precedence.

ACP agents can advertise authentication methods during initialization. The
bridge records and validates that advertisement but does not guess among
methods. Set `auth_method` only to an exact advertised ID when the agent expects
the client to invoke ACP `authenticate`; an unadvertised value fails the call.

### Grok authentication

Authenticate with the Grok CLI itself before using Hermes:

```sh
grok login
```

The plugin launches `grok agent stdio` with the CLI's existing authentication.
It does not read, copy, or store Grok credentials. If Grok advertises a distinct
ACP authentication method, configure its exact advertised ID as described
above instead of relying on method ordering.

### Codex adapter behavior

Codex does not currently provide the native command used here for Grok. The
plugin therefore starts the pinned npm adapter
`@agentclientprotocol/codex-acp@1.7.0` through `npx -y`. `npx` may download that
exact package version when it is not cached. Authentication, sandboxing, and
inner tool behavior remain the adapter/Codex CLI's responsibility. To avoid an
on-demand download, provision that pinned package in the execution environment
or override the `codex` command and arguments with an equivalent local launch.

## Permission and security model

The default `permission_mode` is `reject`. Every reverse
`session/request_permission` request is answered with ACP's cancelled outcome.
Reverse filesystem and terminal methods are not advertised and are rejected;
unknown extension requests receive method-not-found, while unknown extension
notifications are ignored.

Setting `permission_mode: allow_once` is an explicit security decision. It
selects an agent-advertised `allow_once` option for an individual permission
request. It never selects `allow_always`, and it still cancels when the agent
does not offer `allow_once`. There is no tool auto-approval default.

The subprocess inherits only the ACP SDK's trimmed standard environment. ACP
stdout is reserved for newline-delimited JSON-RPC framing. Stderr is drained to
avoid deadlock and included in failures. A nonzero exit, malformed or rejected
protocol response, or timeout fails the call. On timeout the bridge sends
`session/cancel`, closes stdin, then escalates cleanup from terminate to kill if
the process does not exit.

This boundary does not turn ACP tools into Hermes tools. The ACP agent owns its
inner reasoning and tool loop, including its own sandbox and credentials.
Hermes retains the outer UI, session, memory, gateway, and provider-routing
loop. The bridge returns only accumulated agent message/thought text as an
OpenAI-shaped completion with zero token usage because ACP usage is not mapped.

## Uninstall

```sh
hermes plugins disable hermes-acp
uv pip uninstall \
  --python "$HOME/.hermes/hermes-agent/venv/bin/python" \
  hermes-acp
```

Removing the plugin does not uninstall the Grok CLI, Node.js, cached npm
packages, or their credentials.

## Development

The tests use a deterministic local ACP subprocess; they do not call Grok,
Codex, npm, or the network.

```sh
python -m pip install -e '.[test]'
pytest
```

## License

MIT
