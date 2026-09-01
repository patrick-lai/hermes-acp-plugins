# Hermes ACP end-to-end QA

Result: **PASS**

Tested base revision: `c3e98670b12c2704b82614f8af65d6586c257217`

The verification was rerun after integrating the current `main` hotfix.

## Failure isolated

- The `lumine` Desktop profile previously sent `provider=acp` to the inert
  placeholder URL `http://127.0.0.1:1/v1`, ending in `APIConnectionError`.
- Once ACP middleware ran, the SDK's 64 KiB asyncio line limit failed on real
  Codex ACP frames with `Separator is not found, and chunk exceed the limit`.
- The repository also used a one-character provider sentinel that Hermes
  rejects as unusable and a manifest v2 label rejected by the v0.21 installer.

## Repair proved on the live Desktop backend

The verifier fetched the running profile backend's loopback token, connected
to its `/api/ws` JSON-RPC endpoint, and exercised the same protocol used by the
Desktop renderer.

- `gateway.ready`: received
- live `model.options`: selected `acp/codex`
- provider `ACP` models: `grok`, `codex`, `claude`, `cursor`
- session source: `desktop`
- session override: `provider=acp`, `model=codex`, `reasoning_effort=high`
- exact response: `DESKTOP_HERMES_ACP_E2E_OK`
- terminal status: `complete`
- ACP calls: `1`
- proof session closed cleanly

Machine-readable evidence: `desktop-e2e-proof.json`.

The active `lumine` agent log records the subprocess boundary for this exact
turn:

- line 2301: `Hermes ACP execution started provider=acp backend=codex executable=npx`
- line 2319: `Hermes ACP execution completed provider=acp backend=codex stop_reason=end_turn`

Together, the live picker response, Desktop-source session identity, exact
model response, one ACP call, and both middleware lifecycle records exclude a
hidden direct-provider fallback.

## Automated verification

- package tests: `34 passed`
- formatting: `18 files already formatted`
- lint: `All checks passed!`
- typing: `Success: no issues found in 7 source files`
- package build: `Successfully built hermes_acp-0.2.1`
- active plugin: `hermes-acp v0.2.1`, enabled, source `entrypoint`
- active profile: `lumine`, model `codex (acp)`

Accessibility scan: not applicable to this proof path. The exercised target is
the headless backend used by the native Electron Desktop renderer, not a
browser-served page; the backend explicitly reports that its web UI is
disabled. Static Desktop plugin assertions remain covered by the package tests.
