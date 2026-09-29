#!/usr/bin/env node
// One-shot session-control relay. A desk runs this on the far side of its own SSH session, so it
// reads one bounded JSON frame from stdin, writes it to the session's socket, prints the reply
// frame, and exits. It needs no build step, no configuration of its own, and no credential:
// ownership of the socket file is the whole gate.
//
// The frame contract is `integrations/voice-agent/src/task-protocol.mjs` in the Open DeskOS
// repository, spoken here rather than forked.
import { createConnection } from 'node:net'
import { readdirSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { isAbsolute, join, resolve as resolvePath, sep } from 'node:path'
import { StringDecoder } from 'node:string_decoder'

const REQUEST_LIMIT = 64 * 1024
const RESPONSE_LIMIT = 256 * 1024
const REQUEST_TIMEOUT = 8000
const DEADLINE = REQUEST_TIMEOUT + 1000
const FAILURE = '会话控制通信失败，结果未知'
const USAGE = '用法: session-host-client.mjs <session-control socket path> | --find，stdin 上一个 JSON 请求帧'

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
  if (isAbsolute(override) && !override.endsWith('.sock')) return override
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
  return target === root || target.startsWith(`${root}${sep}`)
}

/**
 * Which of this machine's sessions answers this frame. Every session publishes its own
 * project and its own socket, so the choice follows what each one declares; a project no
 * session serves has no answer, which the desk reads as the host's own project refusal
 * rather than as some other session's reply.
 */
function findSession(request) {
  const project = typeof request?.project === 'string' ? request.project : ''
  let names
  try {
    names = readdirSync(sessionsDir()).filter((name) => name.endsWith('.json'))
  } catch {
    return undefined
  }
  for (const name of names) {
    let descriptor
    try {
      descriptor = JSON.parse(readFileSync(join(sessionsDir(), name), 'utf8'))
    } catch {
      continue
    }
    if (descriptor?.version !== 1) continue
    if (typeof descriptor.socketPath !== 'string' || !isAbsolute(descriptor.socketPath)) continue
    if (project.length > 0 && !admits(descriptor.project, project)) continue
    return descriptor.socketPath
  }
  return undefined
}

const deadline = setTimeout(() => {
  process.stderr.write(`${FAILURE}\n`)
  process.exit(1)
}, DEADLINE)
try {
  const request = await readFrame(process.stdin)
  process.stdin.pause()
  // A desk declares one executable and sends one frame, so finding the session is this
  // client's work: --find asks each session's own descriptor which one owns the requested
  // project and relays the frame to that session. A socket path named directly still
  // addresses exactly one session.
  const first = process.argv[2]
  const socketPath = first === '--find' ? findSession(request) : first
  if (typeof socketPath !== 'string' || !socketPath.length || !isAbsolute(socketPath) || /[\x00-\x1f\x7f]/.test(socketPath)) {
    process.stderr.write(`${USAGE}\n`)
    process.exitCode = 2
  } else {
    const response = await exchange(socketPath, request)
    // A frame that is not this request's answer is not an answer: printing it would let a desk
    // read someone else's reply as its own.
    if (response === '' || Buffer.byteLength(response) > RESPONSE_LIMIT) throw new Error(FAILURE)
    const answer = JSON.parse(response)
    if (answer?.version !== 1 || answer.requestId !== request?.requestId || typeof answer.ok !== 'boolean') throw new Error(FAILURE)
    process.stdout.write(`${response}\n`)
  }
} catch {
  process.stderr.write(`${FAILURE}\n`)
  process.exitCode = 1
} finally {
  clearTimeout(deadline)
  process.stdin.destroy()
}
