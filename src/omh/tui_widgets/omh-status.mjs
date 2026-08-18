import { execFile } from 'node:child_process'

export default function register(sdk) {
  const { Box, Text, defineWidgetApp, h, openWidget, updateWidget, useShimmerPhase } = sdk
  const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
  const HOME = process.env.OMH_HOME || `${process.env.HOME}/.omh`
  const HERMES_HOME = process.env.HERMES_HOME || `${process.env.HOME}/.hermes`
  const READER_ENV = {
    HOME: process.env.HOME || '',
    HERMES_HOME,
    OMH_HOME: HOME,
  }
  for (const key of ['LANG', 'LC_ALL', 'LC_CTYPE', 'SYSTEMROOT', 'WINDIR']) {
    if (process.env[key]) READER_ENV[key] = process.env[key]
  }
  const READER = [
    'import json,os,sys',
    "sys.path.insert(0, os.path.join(os.environ['HERMES_HOME'], 'plugins'))",
    'from omh.runtime_reader import read_omh_hud',
    "print(json.dumps(read_omh_hud(os.environ.get('OMH_HOME'), os.environ.get('HERMES_HOME'))))",
  ].join(';')

  const safeText = value => String(value ?? '').replace(/[^\p{L}\p{N} .:/_·|+\-]/gu, '').slice(0, 96)

  // Text, not chrome. The owner's direction after living with the bordered
  // cards: the OMH surface should read like the host's own status line
  // (` ─ ready │ gpt 5.6 sol │ … `) and like oh-my-claudecode's HUD -- dense
  // text in the TUI's idiom, not a boxed widget that announces itself.
  // Colours still resolve only through the active theme, never literals.
  const SEPARATOR = ' │ '
  // The classic REPL frames the composer with horizontal rules; the modern
  // TUI draws none. These docks sit exactly above and below the composer, so
  // they carry the frame: a themed rule closes the top dock and opens the
  // bottom one, and the input reads like classic Hermes again.
  // Host cols include the dock's side margins, so a full-cols rule wraps by
  // two cells. The rules sit tight against the composer, exactly like the
  // classic REPL's frame -- padding was tried at one and two rows against
  // live renders and the owner removed it entirely.
  const Rule = ({ columns, t }) => h(Text, { color: t.color.border }, '─'.repeat(Math.max(1, columns - 2)))

  const plural = (count, noun) => `${count} ${noun}${count === 1 ? '' : 's'}`

  // Session metrics OMH can honestly source: cost sums observed per-agent
  // cost_usd across live bindings, ctx is the MAIN row's observed context
  // percentage. The host's own token gauge (36.4k/272k) is hermes session
  // state the reader cannot reach -- the host statusline above the composer
  // already shows it, so absent data renders as "--", never a fabricated
  // zero-of-total.
  function sessionMetrics(payload) {
    const rows = []
      .concat(Array.isArray(payload.maestro?.rows) ? payload.maestro.rows : [])
      .concat(Array.isArray(payload.subagents?.rows) ? payload.subagents.rows : [])
    const cost = rows.reduce((sum, row) => sum + (Number.isFinite(row.cost_usd) ? row.cost_usd : 0), 0)
    const main = Array.isArray(payload.maestro?.rows) ? payload.maestro.rows[0] : null
    const ctx = main && Number.isFinite(main.context_percentage)
      ? main.context_percentage
      : rows.map(row => row.context_percentage).filter(Number.isFinite)[0]
    return {
      cost: `$${cost.toFixed(3)}`,
      ctx: Number.isFinite(ctx) ? `ctx ${ctx}%` : 'ctx --',
    }
  }

  function hudStateLabel(active, agents) {
    // Idle says "ready" and nothing more. Claiming work that is not running is
    // what made the old fixed "Ultra Work Ready" header meaningless -- it read
    // identically whether four agents were running or none were.
    if (!active) return 'ready'
    const running = Number(agents.running) || 0
    const blocked = Number(agents.blocked) || 0
    const done = Number(agents.completed) || 0
    // Lingering just-finished subagents keep the block alive without live
    // work; "2 done" is the honest label there, not "0 agents".
    if (!running && !blocked && done) return `${done} done`
    const parts = [plural(Number(agents.active) || 0, 'agent')]
    if (running) parts.push(`${running} running`)
    if (blocked) parts.push(`${blocked} blocked`)
    if (done) parts.push(`${done} done`)
    return parts.join(' · ')
  }
  const readHud = () => new Promise(resolve => {
    execFile(
      __OMH_PYTHON_EXECUTABLE__,
      ['-I', '-c', READER],
      {
        encoding: 'utf8',
        env: READER_ENV,
        // Headroom over the payload's worst case (todo panel included) so an
        // oversized snapshot degrades to null instead of blanking the HUD.
        maxBuffer: 65536,
        timeout: 1500,
      },
      (error, stdout) => {
        if (error || !stdout || stdout.length > 65536) return resolve(null)
        try {
          resolve(JSON.parse(stdout))
        } catch {
          resolve(null)
        }
      }
    )
  })

  const cellWidth = value => Array.from(value).reduce((width, char) => {
    const code = char.codePointAt(0) || 0
    const wide = code >= 0x1100 && (
      code <= 0x115f ||
      code === 0x2329 ||
      code === 0x232a ||
      (code >= 0x2e80 && code <= 0xa4cf) ||
      (code >= 0xac00 && code <= 0xd7a3) ||
      (code >= 0xf900 && code <= 0xfaff) ||
      (code >= 0xfe10 && code <= 0xfe6f) ||
      (code >= 0xff00 && code <= 0xff60) ||
      (code >= 0xffe0 && code <= 0xffe6)
    )
    return width + (wide ? 2 : 1)
  }, 0)

  const truncateCells = (value, limit) => {
    const text = safeText(value)
    if (cellWidth(text) <= limit) return text
    let output = ''
    for (const char of Array.from(text)) {
      if (cellWidth(output + char) > Math.max(0, limit - 1)) break
      output += char
    }
    return `${output}…`
  }

  const elapsedText = value => {
    if (!Number.isFinite(value)) return ''
    const seconds = Math.max(0, Math.floor(value))
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
    return `${Math.floor(seconds / 3600)}h ${String(Math.floor(seconds / 60) % 60).padStart(2, '0')}m`
  }

  const metricSegment = (kind, text) => ({ kind, text })
  const observedPercent = (label, value) =>
    Number.isFinite(value) ? `${label} ${value}%` : `${label} uncollected`

  const activityLayout = (row, columns, main) => {
    const state = safeText(row.state) || 'running'
    const stateText = columns < 100 ? ({ running: 'run', blocked: 'block', failed: 'fail' })[state] || state : state
    const taskId = truncateCells(safeText(row.task_id) || safeText(row.role) || 'agent', 8).padEnd(8)
    const model = [safeText(row.model), safeText(row.effort)].filter(Boolean).join(':')
    const category = safeText(row.category)
    const route = category ? `category:${category}${model ? `(${model})` : ''}` : model
    const turn = Number.isFinite(row.turn_count) ? `turn ${row.turn_count}` : ''
    const tools = Number.isFinite(row.tool_count) ? `${row.tool_count} tools` : ''
    const turnTools = turn && tools ? `${turn} (${tools})` : turn || tools
    const optional = [
      metricSegment('route', route),
      metricSegment('fallback', Number.isFinite(row.fallback_count) && row.fallback_count > 0 ? `fallback:${row.fallback_count}` : ''),
      metricSegment('turn', turnTools),
      metricSegment('cost', Number.isFinite(row.cost_usd) ? `$${row.cost_usd.toFixed(4)}` : ''),
      metricSegment('rate', Number.isFinite(row.tokens_per_second) ? `${Math.round(row.tokens_per_second)} tok/s` : ''),
      metricSegment('cache', observedPercent('cache', row.cache_hit_percentage)),
      metricSegment('context', observedPercent('ctx', row.context_percentage)),
    ].filter(segment => segment.text)
    const required = [
      metricSegment('cache', observedPercent('cache', row.cache_hit_percentage)),
      metricSegment('context', observedPercent('ctx', row.context_percentage)),
      metricSegment('state', stateText),
      metricSegment('elapsed', elapsedText(row.elapsed_seconds)),
    ].filter(segment => segment.text)
    optional.splice(-2)
    const prefix = `${taskId} `
    const separator = '  ·  '
    const budget = Math.max(24, columns - 4)
    const minimumAction = columns >= 120 ? 26 : columns >= 90 ? 18 : 10
    const segments = [...optional, ...required]
    while (segments.length > required.length) {
      const metadata = segments.map(item => item.text).join(separator)
      if (cellWidth(prefix) + minimumAction + cellWidth(separator) + cellWidth(metadata) <= budget) break
      segments.splice(segments.length - required.length - 1, 1)
    }
    const metadata = segments.map(segment => segment.text).join(separator)
    const actionBudget = Math.max(
      8,
      budget - cellWidth(prefix) - cellWidth(metadata) - (metadata ? cellWidth(separator) : 0),
    )
    return {
      action: truncateCells(row.action, actionBudget),
      metadata,
      segments,
      taskId: main ? 'MAIN'.padEnd(8) : taskId,
    }
  }

  function ActivityRow({ columns, frame, main, row, t }) {
    const layout = activityLayout(row, columns, main)
    const blocked = row.state === 'blocked' || row.state === 'failed'
    const done = row.state === 'done'
    const marker = blocked ? '▲' : done ? '✓' : SPINNER_FRAMES[frame % SPINNER_FRAMES.length]
    const statusColor = blocked ? t.color.error : t.color.ok
    return h(
      Text,
      { wrap: 'truncate-end' },
      h(Text, { color: blocked ? t.color.error : done ? t.color.ok : t.color.warn }, `${marker} `),
      h(Text, { color: t.color.muted }, `${layout.taskId} `),
      h(Text, { color: t.color.text }, layout.action),
      layout.metadata ? h(Text, { color: t.color.muted }, '  ·  ') : null,
      ...layout.segments.map((segment, index) =>
        h(
          Text,
          {
            color: segment.kind === 'state'
              ? statusColor
              : segment.kind === 'route'
                ? t.color.label
                : t.color.muted,
            key: `${segment.kind}-${index}`,
          },
          `${index ? '  ·  ' : ''}${segment.text}`,
        )
      ),
    )
  }

  function ActivityRows({ columns, frame, mainRows, rows, t }) {
    return h(
      Box,
      { flexDirection: 'column', width: '100%' },
      ...mainRows.map((row, index) =>
        h(ActivityRow, {
          columns,
          frame,
          key: `main-${index}`,
          main: true,
          row,
          t,
        })
      ),
      ...rows.map((row, index) =>
        h(ActivityRow, {
          columns,
          frame,
          key: `${safeText(row.task_id)}-${index}`,
          row,
          t,
        })
      ),
    )
  }

  function AnimatedActivity({ columns, mainRows, rows, t, tick }) {
    // Mounted only while a RUNNING row needs the spinner. The SDK shimmer
    // clock is bounded — it stops advancing animateMs after MOUNT — so the
    // old top-level useShimmerPhase(30_000) froze thirty seconds into a
    // session and the spinner then jumped once per poll. A fresh mount per
    // activity burst restarts the window, and thirty minutes bounds the
    // render cost of one very long wave. Done/blocked-only states render the
    // static ActivityRows instead: no shimmer subscription, no repaints, so
    // a lingering finished wave stays drag-copyable.
    const frame = useShimmerPhase(1_800_000) + tick
    return h(ActivityRows, { columns, frame, mainRows, rows, t })
  }

  function Hud({ columns, state, t, viewportRows }) {
    const payload = state.payload
    if (!payload || payload.error || payload.privacy !== 'metadata_only') return null

    // The header stays visible whenever the plugin answers, so an installed
    // OMH is discoverable from an idle session; activity rows are the only
    // part gated on live work.
    const active = !!payload.active
    const agents = payload.subagents || {}
    const version = safeText(payload.version)
    const metrics = sessionMetrics(payload)
    const maestro = payload.maestro || {}
    const mainRows = active && Array.isArray(maestro.rows) ? maestro.rows.slice(0, 1) : []
    const activityLimit = Math.max(1, Math.min(3, viewportRows - 3))
    const rows = active && Array.isArray(agents.rows)
      ? agents.rows.slice(0, Math.max(0, activityLimit - mainRows.length))
      : []
    return h(
      Box,
      { flexDirection: 'column', width: '100%' },
      h(Rule, { columns, t }),
      h(
        Text,
        { wrap: 'truncate-end' },
        // Always visible: the owner kept the branded status row and asked for
        // live session metrics on it. Cost and ctx come from sessionMetrics
        // above -- observed values or "--", never fabricated totals.
        h(Text, { bold: true, color: t.color.primary }, '⚚ [OMH]'),
        version ? h(Text, { color: t.color.muted }, ` v${version}`) : null,
        h(Text, { color: t.color.border }, SEPARATOR),
        h(Text, { color: active ? t.color.warn : t.color.ok }, hudStateLabel(active, agents)),
        h(Text, { color: t.color.muted }, ` • ${metrics.cost} • ${metrics.ctx}`),
      ),
      mainRows.length || rows.length
        ? ([...mainRows, ...rows].some(row => !row.state || row.state === 'running')
            ? h(AnimatedActivity, { columns, mainRows, rows, t, tick: state.tick })
            : h(ActivityRows, { columns, frame: 0, mainRows, rows, t }))
        : null,
    )
  }

  function TodoPanel({ columns, state, t }) {
    const payload = state.payload
    if (!payload || payload.error || payload.privacy !== 'metadata_only') return null
    // Deliberately not gated on payload.active: a declared plan outlives
    // subagent activity, and the reader's 24h staleness rule bounds it. The
    // READER always projects the focused preset, which display_items encode.
    const todo = payload.todo || {}
    // The closing rule renders even with no plan: the frame around the
    // composer is constant chrome, the todo lines are the variable content.
    if (todo.status !== 'established' && todo.status !== 'all_done') {
      return h(Rule, { columns, t })
    }
    const counts = todo.counts || {}
    const title = safeText(todo.title)
    if (todo.status === 'all_done') {
      return h(
        Box,
        { flexDirection: 'column', width: '100%' },
        h(
          Text,
          { wrap: 'truncate-end' },
          // Same grammar as the status line below the prompt, so the two
          // surfaces read as one product.
          h(Text, { bold: true, color: t.color.primary }, '[Plan]'),
          title ? h(Text, { color: t.color.muted }, ` ${title}`) : null,
          h(Text, { color: t.color.border }, SEPARATOR),
          h(Text, { color: t.color.ok }, `✓ ${counts.done ?? 0}/${counts.total ?? 0}`),
        ),
        h(Rule, { columns, t }),
      )
    }
    const shown = Array.isArray(todo.display_items) ? todo.display_items : []
    const more = Number.isFinite(todo.more_count) ? todo.more_count : 0
    const markers = { active: '[•]', done: '[✓]', pending: '[ ]' }
    const budget = Math.max(16, columns - 10)
    // A phase-structured plan (todo init with phases) shows the current
    // phase's name above its checklist — the reader already narrowed
    // display_items to that phase, so the panel walks one phase at a time.
    const phase = safeText(todo.display_phase)
    const phaseCount = Number.isFinite(counts.phases) ? counts.phases : 0
    return h(
      Box,
      { flexDirection: 'column', width: '100%' },
      h(
        Text,
        { wrap: 'truncate-end' },
        h(Text, { bold: true, color: t.color.primary }, '[Plan]'),
        title ? h(Text, { color: t.color.muted }, ` ${title}`) : null,
        h(Text, { color: t.color.border }, SEPARATOR),
        h(Text, { color: t.color.warn }, `${counts.done ?? 0}/${counts.total ?? 0}`),
        phaseCount > 1 ? h(Text, { color: t.color.muted }, ` · ${phaseCount} phases`) : null,
      ),
      phase
        ? h(
            Text,
            { wrap: 'truncate-end' },
            h(Text, { bold: true, color: t.color.label }, truncateCells(phase, budget)),
          )
        : null,
      ...shown.map((item, index) => {
        const withMore = more > 0 && index === shown.length - 1
        // Reserve the "+N more" suffix width so truncation never eats it.
        const rowBudget = withMore ? Math.max(12, budget - 11) : budget
        return h(
          Text,
          { key: `todo-${index}`, wrap: 'truncate-end' },
          h(
            Text,
            {
              bold: item.state === 'active',
              color: item.state === 'active' ? t.color.ok : item.state === 'done' ? t.color.muted : t.color.text,
              strikethrough: item.state === 'done',
            },
            `${Object.hasOwn(markers, item.state) ? markers[item.state] : '[ ]'} ${truncateCells(item.text, rowBudget)}`,
          ),
          withMore ? h(Text, { color: t.color.muted }, `   +${more} more`) : null,
        )
      }),
      h(Rule, { columns, t }),
    )
  }

  const app = defineWidgetApp({
    id: 'omh-status',
    help: 'OMH workflow and subagent status',
    mode: 'ambient',
    zone: 'dock-bottom',
    init: () => ({ payload: null, tick: 0 }),
    reduce: (state, input) =>
      input.kind === 'snapshot'
        ? { ...state, payload: input.payload, tick: state.tick + 1 }
        : state,
    render: ({ cols, rows, state, t }) => h(Hud, {
      columns: Math.max(20, cols),
      state,
      t,
      viewportRows: Math.max(1, rows),
    }),
  })

  const todoApp = defineWidgetApp({
    id: 'omh-todo',
    help: 'OMH plan todo checklist above the prompt input',
    mode: 'ambient',
    zone: 'dock-top',
    init: () => ({ payload: null, tick: 0 }),
    reduce: (state, input) =>
      input.kind === 'snapshot'
        ? { ...state, payload: input.payload, tick: state.tick + 1 }
        : state,
    render: ({ cols, state, t }) => h(TodoPanel, { columns: Math.max(20, cols), state, t }),
  })

  openWidget(app, app.init(''))
  openWidget(todoApp, todoApp.init(''))
  // Render quiescence is what makes the docks drag-copyable: every repaint of
  // these lines clears an in-progress terminal selection over them, so an
  // unchanged snapshot must produce NO updateWidget call at all. The reader
  // freezes per-row elapsed for finished subagents precisely so a lingering
  // done state serializes identically poll after poll.
  let lastSnapshot = ''
  const applySnapshot = payload => {
    if (!payload) return
    const serialized = JSON.stringify(payload)
    if (serialized === lastSnapshot) return
    lastSnapshot = serialized
    for (const target of [app, todoApp]) {
      updateWidget(target, state => ({ ...state, payload, tick: state.tick + 1 }))
    }
  }
  const timerKey = Symbol.for('omh.hermes-tui-widget.refresh')
  const generationKey = Symbol.for('omh.hermes-tui-widget.generation')
  const generation = (globalThis[generationKey] || 0) + 1
  globalThis[generationKey] = generation
  const schedule = () => {
    if (generation !== globalThis[generationKey]) return
    globalThis[timerKey] = setTimeout(async () => {
      const payload = await readHud()
      if (generation !== globalThis[generationKey]) return
      applySnapshot(payload)
      schedule()
    }, 2000)
    globalThis[timerKey].unref?.()
  }
  clearTimeout(globalThis[timerKey])
  void readHud().then(payload => {
    if (generation !== globalThis[generationKey]) return
    applySnapshot(payload)
  })
  schedule()
}
