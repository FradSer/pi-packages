#!/usr/bin/env node
// One-shot session-control relay. A desk runs this on the far side of its own SSH session, so it
// reads one bounded JSON frame from stdin, writes it to the session's socket, prints the reply
// frame, and exits. It needs no build step, no configuration of its own, and no credential:
// ownership of the socket file is the whole gate.
//
// The frame contract is `integrations/personal-bot/src/task-protocol.mjs` in the Open DeskOS
// repository, spoken here rather than forked.
import { createConnection } from 'node:net'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { realpath, stat } from 'node:fs/promises'
import { homedir } from 'node:os'
import { isAbsolute, join, resolve as resolvePath, sep } from 'node:path'
import { StringDecoder } from 'node:string_decoder'

const REQUEST_LIMIT = 64 * 1024
const RESPONSE_LIMIT = 256 * 1024
const REQUEST_TIMEOUT = 8000
const DEADLINE = REQUEST_TIMEOUT + 1000
const FAILURE = '会话控制通信失败，结果未知'
const USAGE = '用法: session-host-client.mjs <session-control socket path> | --find，stdin 上一个 JSON 请求帧'
// The protocol's own admission refusal, so a project no session serves is answered in
// the frame a desk already reads rather than as a client usage error.
const PROJECT_NOT_SERVED = '项目不在允许的开发目录内'
const TASK_NOT_FOUND = '未找到任务'
const NOT_A_SESSION_HOST = '此端点是当前 Pi 会话，不是 Hosted Pi 任务服务'
const ENDPOINT_LIMIT = 64
const ROOT_LIMIT = 16
const PROTOCOL_INVALID = '任务协议无效'
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Fixed operator arguments only; SSH_ORIGINAL_COMMAND is never an input. */
async function relayOptions(args) {
  const restricted = args.some(arg => arg.startsWith('--allow-root'))
  if (!restricted) return { restricted: false, endpoint: args[0] ?? '--find', roots: [] }
  const roots = []
  const remaining = [...args]
  const endpoint = remaining[0] === '--allow-root' ? '--find' : remaining.shift()
  try {
    while (remaining.length) {
      if (remaining.shift() !== '--allow-root' || roots.length >= ROOT_LIMIT) throw Error(PROTOCOL_INVALID)
      const root = remaining.shift()
      if (typeof root !== 'string' || !isAbsolute(root) || /[\x00-\x1f\x7f]/.test(root)) throw Error(PROTOCOL_INVALID)
      const canonical = await realpath(root)
      if (!(await stat(canonical)).isDirectory()) throw Error(PROTOCOL_INVALID)
      roots.push(canonical)
    }
    if (endpoint !== '--find' && (typeof endpoint !== 'string' || !isAbsolute(endpoint) || /[\x00-\x1f\x7f]/.test(endpoint))) throw Error(PROTOCOL_INVALID)
    return { restricted: true, endpoint, roots }
  } catch { return { restricted: true, endpoint, roots: [], invalid: true } }
}

/** Admit one protocol request before discovery or socket contact. */
async function restrictedRefusal(request, options) {
  if (options.invalid || !request || typeof request !== 'object' || Array.isArray(request)
    || request.version !== 1 || typeof request.requestId !== 'string' || !request.requestId.length || request.requestId.length > 128
    || !['list', 'status', 'prompt', 'cancel'].includes(request.command)) return PROTOCOL_INVALID
  const fields = ['version', 'requestId', 'command', 'project', ...(request.command === 'list' ? [] : ['taskId']),
    ...(['prompt', 'cancel'].includes(request.command) ? ['mutationId'] : []), ...(request.command === 'prompt' ? ['prompt', 'streamingBehavior'] : [])]
  if (Object.keys(request).some(key => !fields.includes(key))) return PROTOCOL_INVALID
  if (request.command !== 'list' && (typeof request.taskId !== 'string' || !UUID.test(request.taskId))) return PROTOCOL_INVALID
  if (request.mutationId !== undefined && (typeof request.mutationId !== 'string' || !UUID.test(request.mutationId))) return PROTOCOL_INVALID
  if (request.command === 'prompt' && (typeof request.prompt !== 'string' || !request.prompt.trim() || request.prompt.length > 16_384
    || Buffer.from(request.prompt).toString('utf8') !== request.prompt || (request.streamingBehavior !== undefined && !['steer', 'followUp'].includes(request.streamingBehavior)))) return PROTOCOL_INVALID
  if (typeof request.project !== 'string' || !isAbsolute(request.project) || /[\x00-\x1f\x7f]/.test(request.project)) return PROJECT_NOT_SERVED
  try {
    const project = await realpath(request.project)
    if (!(await stat(project)).isDirectory() || !options.roots.some(root => admits(root, project))) return PROJECT_NOT_SERVED
  } catch { return PROJECT_NOT_SERVED }
  return undefined
}

function refusal(request, error) {
  const requestId = typeof request?.requestId === 'string' && request.requestId.length <= 128 ? request.requestId : ''
  return { version: 1, requestId, ok: false, error }
}

/** Read exactly one bounded JSON line, as the protocol's own one-shot client does. */
function readFrame(stream) {
  return new Promise((resolve, reject) => {
    const decoder = new StringDecoder('utf8')
    let pending = ''
    const cleanup = () => { stream.off('data', onData); stream.off('end', onEnd); stream.off('close', onEnd); stream.off('error', onError) }
    const fail = () => { cleanup(); reject(new Error(FAILURE)) }
    const onEnd = () => fail()
    const onError = () => fail()
    const onData = chunk => {
      pending += decoder.write(chunk)
      if (Buffer.byteLength(pending) > REQUEST_LIMIT) return fail()
      const newline = pending.indexOf('\n')
      if (newline < 0) return
      if (pending.slice(newline + 1).trim()) return fail()
      const line = pending.slice(0, newline)
      let request
      try { request = JSON.parse(line) } catch { return fail() }
      cleanup()
      resolve(request)
    }
    stream.on('data', onData)
    stream.once('end', onEnd)
    stream.once('close', onEnd)
    stream.once('error', onError)
  })
}

/** Connect, write the one frame, and read the one frame back. */
function exchange(socketPath, request) {
  return new Promise((resolve, reject) => {
    const frame = `${JSON.stringify(request)}\n`
    const socket = createConnection(socketPath)
    const decoder = new StringDecoder('utf8')
    let pending = ''
    const cleanup = () => { clearTimeout(timer); socket.off('data', onData); socket.off('end', onEnd); socket.off('close', onEnd); socket.off('error', onError) }
    const fail = () => { cleanup(); socket.destroy(); reject(new Error(FAILURE)) }
    const onEnd = () => fail()
    const onError = () => fail()
    const onData = chunk => {
      pending += decoder.write(chunk)
      if (Buffer.byteLength(pending) > RESPONSE_LIMIT) return fail()
      const newline = pending.indexOf('\n')
      if (newline < 0) return
      cleanup()
      socket.destroy()
      resolve(pending.slice(0, newline))
    }
    const timer = setTimeout(fail, REQUEST_TIMEOUT)
    socket.on('data', onData)
    socket.once('end', onEnd)
    socket.once('close', onEnd)
    socket.once('error', onError)
    socket.once('connect', () => socket.write(frame))
  })
}

/** The directory this machine's sessions publish into, by the same rule the host binds with. */
function sessionsDir() {
  const override = process.env.ODK_SESSION_HOST_SOCKET ?? ''
  if (isAbsolute(override)) return override
  const runtimeDir = process.env.XDG_RUNTIME_DIR
  if (typeof runtimeDir === 'string' && runtimeDir.length > 0 && isAbsolute(runtimeDir)) return join(runtimeDir, 'open-deskos', 'sessions')
  return process.platform === 'win32'
    ? join(process.env.LOCALAPPDATA || join(homedir(), 'AppData', 'Local'), 'open-deskos', 'sessions')
    : join(homedir(), '.local', 'run', 'open-deskos', 'sessions')
}

/** True when a requested project is a session's own project or lies inside it. */
function admits(declared, requested) {
  if (typeof declared !== 'string' || declared.length === 0) return false
  if (typeof requested !== 'string' || requested.length === 0) return false
  const root = resolvePath(declared)
  const target = resolvePath(requested)
  return target === root || target.startsWith(root.endsWith(sep) ? root : `${root}${sep}`)
}

/**
 * Which of this machine's sessions answers this frame. Every session publishes its own
 * project and its own socket, so the choice follows what each one declares; a project no
 * session serves has no answer, which the desk reads as the host's own project refusal
 * rather than as some other session's reply.
 */
async function findSessions(request) {
  const project = typeof request?.project === 'string' ? request.project : ''
  if (!isAbsolute(project) || /[\x00-\x1f\x7f]/.test(project)) return []
  let scope
  try { scope = await realpath(project) } catch { return [] }
  let names
  try {
    names = readdirSync(sessionsDir()).filter((name) => name.endsWith('.json')).sort()
  } catch {
    return []
  }
  const sessions = []
  for (const name of names) {
    let descriptor
    try {
      const file = join(sessionsDir(), name)
      if (statSync(file).size > REQUEST_LIMIT) continue
      descriptor = JSON.parse(readFileSync(file, 'utf8'))
    } catch {
      continue
    }
    if (descriptor?.version !== 1) continue
    if (request.command !== 'list' && descriptor.sessionId !== request.taskId) continue
    if (typeof descriptor.socketPath !== 'string' || !isAbsolute(descriptor.socketPath)) continue
    if (request.command === 'list') {
      let declared
      try { declared = await realpath(descriptor.project) } catch { continue }
      if (!admits(scope, declared)) continue
    } else if (descriptor.project !== project) continue
    sessions.push(descriptor)
  }
  return sessions
}

async function discoveredResponse(request) {
  if (['start', 'launch', 'end', 'history'].includes(request.command)) {
    return { version: 1, requestId: request.requestId, ok: false, error: NOT_A_SESSION_HOST }
  }
  if (request.command !== 'list' && typeof request.taskId !== 'string') {
    return { version: 1, requestId: request.requestId, ok: false, error: TASK_NOT_FOUND }
  }
  const descriptors = await findSessions(request)
  if (!descriptors.length) return { version: 1, requestId: request.requestId, ok: false, error: request.command === 'list' ? PROJECT_NOT_SERVED : TASK_NOT_FOUND }
  if (request.command !== 'list') {
    if (descriptors.length !== 1) return { version: 1, requestId: request.requestId, ok: false, error: TASK_NOT_FOUND }
    return JSON.parse(await exchange(descriptors[0].socketPath, request))
  }
  const frames = await Promise.all(descriptors.slice(0, ENDPOINT_LIMIT).map(async descriptor => {
    try {
      const frame = JSON.parse(await exchange(descriptor.socketPath, { ...request, project: descriptor.project }))
      if (frame?.version !== 1 || frame.requestId !== request.requestId || frame.ok !== true || !Array.isArray(frame.tasks)) return { tasks: [], unavailable: true }
      const tasks = frame.tasks.filter(task => task?.taskId === descriptor.sessionId && task.project === descriptor.project)
      return { tasks, unavailable: tasks.length === 0, incomplete: frame.truncated === true || frame.incomplete === true }
    } catch { return { tasks: [], unavailable: true } }
  }))
  const tasks = []
  const unavailable = frames.filter(frame => frame.unavailable).length
  let truncated = descriptors.length > ENDPOINT_LIMIT
  for (const task of frames.flatMap(frame => frame.tasks)) {
    // false is one byte longer than true. Budget both longest metadata values,
    // including the newline, so a complete inventory also fits the wire bound.
    if (Buffer.byteLength(JSON.stringify({ version: 1, requestId: request.requestId, ok: true, tasks: [...tasks, task], truncated: false, unavailable, incomplete: false })) + 1 > RESPONSE_LIMIT) { truncated = true; break }
    tasks.push(task)
  }
  return { version: 1, requestId: request.requestId, ok: true, tasks, truncated, unavailable, incomplete: truncated || unavailable > 0 || frames.some(frame => frame.incomplete) }
}

let options = { restricted: process.argv.slice(2).some(arg => arg.startsWith('--allow-root')) }
let admitted = false
const deadline = setTimeout(() => {
  process.stderr.write(`${FAILURE}\n`)
  process.exit(1)
}, DEADLINE)
try {
  options = await relayOptions(process.argv.slice(2))
  const request = await readFrame(process.stdin)
  process.stdin.pause()
  const rejected = options.restricted ? await restrictedRefusal(request, options) : undefined
  if (rejected) {
    process.stdout.write(`${JSON.stringify(refusal(request, rejected))}\n`)
  } else {
  admitted = true
  // A desk declares one executable and sends one frame, so finding the session is this
  // client's work: --find asks each session's own descriptor which one owns the requested
  // project and relays the frame to that session. A socket path named directly still
  // addresses exactly one session.
  // A desk declares one executable and sends one frame, so with no socket named the
  // client finds the session that owns the frame's project by itself.
  const first = options.endpoint
  const finding = first === '--find'
  const socketPath = first
  if (!finding && (typeof socketPath !== 'string' || !socketPath.length || !isAbsolute(socketPath) || /[\x00-\x1f\x7f]/.test(socketPath))) {
    process.stderr.write(`${USAGE}\n`)
    process.exitCode = 2
  } else {
    const response = finding ? JSON.stringify(await discoveredResponse(request)) : await exchange(socketPath, request)
    // A frame that is not this request's answer is not an answer: printing it would let a desk
    // read someone else's reply as its own.
    if (response === '' || Buffer.byteLength(response) > RESPONSE_LIMIT) throw new Error(FAILURE)
    const answer = JSON.parse(response)
    if (answer?.version !== 1 || answer.requestId !== request?.requestId || typeof answer.ok !== 'boolean') throw new Error(FAILURE)
    process.stdout.write(`${response}\n`)
  }
  }
} catch {
  if (options.restricted && !admitted) process.stdout.write(`${JSON.stringify(refusal(undefined, PROTOCOL_INVALID))}\n`)
  else {
    process.stderr.write(`${FAILURE}\n`)
    process.exitCode = 1
  }
} finally {
  clearTimeout(deadline)
  process.stdin.destroy()
}
