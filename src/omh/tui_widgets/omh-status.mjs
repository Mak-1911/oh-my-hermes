import { execFile } from 'node:child_process'

export default function register(sdk) {
  const { Box, Text, defineWidgetApp, h, openWidget, updateWidget } = sdk
  const HOME = process.env.OMH_HOME || `${process.env.HOME}/.omh`
  const HERMES_HOME = process.env.HERMES_HOME || `${process.env.HOME}/.hermes`
  const READER = [
    'import json,os,sys',
    "sys.path.insert(0, os.path.join(os.environ['HERMES_HOME'], 'plugins'))",
    'from omh.runtime_reader import read_omh_hud',
    "print(json.dumps(read_omh_hud(os.environ.get('OMH_HOME'), os.environ.get('HERMES_HOME'))))",
  ].join(';')

  const safeText = value => String(value ?? '').replace(/[^\p{L}\p{N} .:/_·|+\-]/gu, '').slice(0, 96)

  const readHud = () => new Promise(resolve => {
    execFile(
      __OMH_PYTHON_EXECUTABLE__,
      ['-c', READER],
      {
        encoding: 'utf8',
        env: { ...process.env, HERMES_HOME, OMH_HOME: HOME },
        maxBuffer: 16384,
        timeout: 1500,
      },
      (error, stdout) => {
        if (error || !stdout || stdout.length > 16384) return resolve(null)
        try {
          resolve(JSON.parse(stdout))
        } catch {
          resolve(null)
        }
      }
    )
  })

  const compactTokens = value => {
    if (!Number.isInteger(value)) return ''
    if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
    return String(value)
  }

  const metricText = row => {
    const routed = [safeText(row.model), safeText(row.effort)].filter(Boolean).join(':')
    const tokens = compactTokens(row.tokens)
    return [routed, tokens ? `${tokens} tok` : ''].filter(Boolean).join(' · ')
  }

  function AgentRow({ row, t }) {
    const state = safeText(row.state)
    const color = state === 'blocked' ? t.color.error : t.color.ok
    return h(
      Box,
      { columnGap: 1, flexDirection: 'row' },
      h(Text, { color }, `${state === 'blocked' ? '▲' : '●'} ${state}`.padEnd(11)),
      h(Text, { bold: true, color: t.color.label }, safeText(row.role).padEnd(11)),
      h(Text, { color: t.color.text }, safeText(row.action)),
      metricText(row) ? h(Text, { color: t.color.muted }, ` ${metricText(row)}`) : null
    )
  }

  function Hud({ state, t }) {
    const payload = state.payload
    if (!payload || payload.error || payload.privacy !== 'metadata_only' || !payload.active) return null

    const runtime = payload.runtime || {}
    const agents = payload.subagents || {}
    const version = safeText(payload.plugin?.version || payload.version)
    const workflow = safeText(runtime.workflow)
    const phase = safeText(runtime.phase)
    const latest = safeText(agents.latest_action)
    const rows = Array.isArray(agents.rows) ? agents.rows.slice(0, 4) : []
    const maestro = payload.maestro || {}
    const maestroRows = Array.isArray(maestro.rows) ? maestro.rows.slice(0, 2) : []
    return h(
      Box,
      { flexDirection: 'column', width: '100%' },
      h(
        Box,
        { columnGap: 1, flexDirection: 'row' },
        h(Text, { bold: true, color: t.color.primary }, `[OMH] ${version}`),
        h(Text, { color: t.color.muted }, '|'),
        h(Text, { bold: true, color: t.color.label }, workflow),
        h(Text, { color: t.color.primary }, phase),
        h(
          Text,
          { color: t.color.muted },
          `agents ${agents.active || 0} · run ${agents.running || 0} · block ${agents.blocked || 0} · done ${agents.completed || 0}`
        )
      ),
      ...rows.map((row, index) => h(AgentRow, { key: `subagent-${index}`, row, t })),
      ...maestroRows.map((row, index) =>
        h(
          Box,
          { key: `maestro-${index}`, columnGap: 1, flexDirection: 'row' },
          h(Text, { bold: true, color: t.color.primary }, 'MAESTRO'),
          h(AgentRow, { row, t })
        )
      ),
      latest ? h(Text, { color: t.color.muted }, `latest ${latest}`) : null
    )
  }

  const app = defineWidgetApp({
    id: 'omh-status',
    help: 'OMH workflow and subagent status',
    mode: 'ambient',
    zone: 'dock-bottom',
    init: () => ({ payload: null }),
    reduce: (state, input) => input.kind === 'snapshot' ? { payload: input.payload } : state,
    render: ({ state, t }) => h(Hud, { state, t }),
  })

  openWidget(app, app.init(''))
  const timerKey = Symbol.for('omh.hermes-tui-widget.refresh')
  const generationKey = Symbol.for('omh.hermes-tui-widget.generation')
  const generation = (globalThis[generationKey] || 0) + 1
  globalThis[generationKey] = generation
  const schedule = () => {
    if (generation !== globalThis[generationKey]) return
    globalThis[timerKey] = setTimeout(async () => {
      const payload = await readHud()
      if (generation !== globalThis[generationKey]) return
      updateWidget(app, state => payload ? { payload } : state)
      schedule()
    }, 2000)
    globalThis[timerKey].unref?.()
  }
  clearTimeout(globalThis[timerKey])
  void readHud().then(payload => {
    if (generation !== globalThis[generationKey]) return
    updateWidget(app, state => payload ? { payload } : state)
  })
  schedule()
}
