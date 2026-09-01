import { host, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, Button, useValue } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const PROVIDERS = [
  {
    id: 'codex',
    title: 'Codex',
    detail: 'OpenAI Codex through the official ACP adapter.'
  },
  {
    id: 'claude',
    title: 'Claude Code',
    detail: 'Claude Agent SDK through the official ACP adapter.'
  },
  {
    id: 'cursor',
    title: 'Cursor',
    detail: 'Cursor Agent’s native ACP server.'
  },
  {
    id: 'grok',
    title: 'Grok',
    detail: 'Grok CLI’s native ACP server.'
  }
]

function ProviderCard({ active, provider, select }) {
  return jsxs('article', {
    className: 'flex min-h-40 flex-col justify-between rounded-xl border border-(--ui-stroke-secondary) p-4',
    children: [
      jsxs('div', {
        className: 'space-y-1.5',
        children: [
          jsx('h2', { className: 'text-sm font-semibold text-(--ui-text-primary)', children: provider.title }),
          jsx('p', {
            className: 'text-xs leading-5 text-(--ui-text-tertiary)',
            children: provider.detail
          })
        ]
      }),
      jsx(Button, {
        disabled: Boolean(active),
        onClick: () => void select(provider.id),
        size: 'sm',
        type: 'button',
        variant: active ? 'secondary' : 'primary',
        children: active ? 'Profile default' : 'Set profile default'
      })
    ]
  })
}

function ACPSettingsPage() {
  const selectedModel = useValue(host.state.model)
  const [updating, setUpdating] = useState('')
  const current = String(selectedModel || '').trim().toLowerCase()
  const selected = PROVIDERS.find(provider => provider.id === current)

  const select = async model => {
    setUpdating(model)
    try {
      // This is the same typed config command the native model picker uses
      // for a profile default. Per-session and per-bot choices stay scoped to
      // their own picker state, so this never overwrites a persona override.
      await host.request('config.set', {
        key: 'model',
        value: `${model} --provider acp --global`
      })
      host.notify({ kind: 'info', message: `${model} is now the ACP profile default.` })
    } catch (error) {
      host.notify({
        kind: 'error',
        message: error instanceof Error ? error.message : 'Could not update the ACP profile default.'
      })
    } finally {
      setUpdating('')
    }
  }

  return jsxs('main', {
    className: 'h-full overflow-auto p-5',
    children: [
      jsx('p', {
        className: 'text-xs font-medium uppercase tracking-[0.16em] text-(--ui-text-tertiary)',
        children: 'Hermes plugin'
      }),
      jsx('h1', {
        className: 'mt-1 text-2xl font-semibold tracking-tight text-(--ui-text-primary)',
        children: 'ACP agents'
      }),
      jsx('p', {
        className: 'mt-2 max-w-2xl text-sm leading-6 text-(--ui-text-secondary)',
        children:
          'Choose the default ACP coding agent for new chats. The native model picker keeps its own live choice for each open session and Bot Mode profile.'
      }),
      jsx('section', {
        className: 'mt-6 grid max-w-4xl gap-3 sm:grid-cols-2',
        children: PROVIDERS.map(provider =>
          jsx(ProviderCard, {
            active: !updating && current === provider.id,
            provider,
            select
          }, provider.id)
        )
      }),
      jsx('section', {
        className: 'mt-8 max-w-3xl rounded-xl border border-(--ui-stroke-tertiary) p-4',
        children: jsxs('div', {
          className: 'space-y-2 text-sm text-(--ui-text-secondary)',
          children: [
            jsx('h2', { className: 'font-semibold text-(--ui-text-primary)', children: 'Per persona or agent' }),
            jsx('p', {
              children:
                'Open the model chip in any chat, or the Model field in a Bot Mode profile. Select provider “acp”, then choose Codex, Claude, Cursor, or Grok. That override is live for only that session or bot profile.'
            })
          ]
        })
      }),
      jsx('section', {
        className: 'mt-3 max-w-3xl rounded-xl border border-(--ui-stroke-tertiary) p-4',
        children: jsxs('div', {
          className: 'space-y-3 text-sm text-(--ui-text-secondary)',
          children: [
            jsx('h2', { className: 'font-semibold text-(--ui-text-primary)', children: 'Runtime proof' }),
            jsx('p', {
              children: selected
                ? `Selected agent: ${selected.title}. In the native model picker it must appear under provider “ACP”.`
                : 'Select an agent under provider “ACP” in the native model picker for this chat.'
            }),
            jsx('p', {
              className: 'text-xs leading-5 text-(--ui-text-tertiary)',
              children:
                'Every intercepted turn records “provider=acp”, the backend name, and start/completion status in agent.log without recording the prompt.'
            }),
          ]
        })
      })
    ]
  })
}

export default {
  id: 'hermes-acp',
  name: 'Hermes ACP',
  defaultEnabled: false,
  register(ctx) {
    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/acp' },
        render: () => jsx(ACPSettingsPage, {})
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: '/acp', label: 'ACP agents', codicon: 'hubot' }
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'hermes-acp.open',
          label: 'Open ACP agents',
          keywords: ['acp', 'codex', 'claude', 'cursor', 'grok'],
          run: () => host.navigate('/acp')
        }
      }
    ])
  }
}
