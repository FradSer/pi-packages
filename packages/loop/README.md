# @fradser/pi-loop

Repeat one message into the current Pi session on a schedule.

`/loop` delivers every repetition through the native user-input path
(`pi.sendUserMessage`), so each repetition is a real user turn. It appears in the
transcript, and it enters the model context, exactly like a prompt you typed.

## Commands

| Command | Effect |
| --- | --- |
| `/loop <request>` | Start a repeating injection |
| `/loop status` | Show the active loop, or report `loop: no loop is running.` |
| `/loop stop` | Release the timer and end the loop |

`/loop` with no argument prints the same status and the usage text.

One loop runs per session. A second `/loop <request>` is refused while a loop is
active, so run `/loop stop` first.

## Two input forms

### Explicit flags

State every parameter, and the extension calls no model.

```bash
/loop --every 5m --times 3 check the build
/loop --every 1h --until "the deploy is green" report deploy status
/loop --every 30s --message "run the smoke test"
/loop --times 3 Hi
/loop -e 2h -t 2 -m report
```

| Flag | Meaning |
| --- | --- |
| `--every`, `-e` | The interval. Defaults to five minutes when it is omitted. |
| `--times`, `-t` | The total count. Omit it to repeat until `/loop stop`. |
| `--until`, `-u` | A stopping condition in natural language. |
| `--message`, `-m` | The text. Equivalent to trailing text. |

A duration is `500ms`, `30s`, `5m`, `2h`, `1d`, a combination such as `1h30m`, or a
bare number of seconds. The shortest interval is one second and the longest is one
day. `--` ends the flags, so the text after it may contain `--`.

`--every` is optional. A request that states no cadence runs every five minutes:
`/loop --times 3 Hi` repeats three times, and `/loop 检查项目修改，总结` repeats
until you stop it. The start notice says the cadence was assumed. A repetition
that is still running when the next tick arrives is skipped and counted, so the
repetitions never queue.

The message may use these placeholders:

| Placeholder | Value |
| --- | --- |
| `{{index}}` | This repetition, counting from 1 |
| `{{total}}` | The total count, or `unbounded` |
| `{{remaining}}` | Repetitions left, or `unbounded` |
| `{{time}}` | The local time, as `HH:MM:SS` |
| `{{date}}` | The local date, as `YYYY-MM-DD` |

Every `{{…}}` token is a placeholder, and only the names above are known. A token
that names anything else is refused at start, so a typo such as `{{Index}}` never
reaches the model. A brace group that never closes stays literal text.

### A free request

Write the request in your own words. The extension then asks TypeSafe Jev to
choose among candidates that it builds:

- `interval`: which listed interval is closest to the requested cadence. The
  listed intervals are 30s, 1m, 5m, 15m, 30m, 1h and 1d. `unspecified` is always
  accepted: the plan takes the default cadence of five minutes, and the start
  notice says the cadence was assumed.
- `runs`: the total count, or `unbounded`. The listed values are 1, 3, 5, 10, 20
  and `unbounded`.
- `stop`: which candidate segment states a stopping condition, or `none`. A
  segment that only states how many repetitions to run is not offered: that count
  is the run limit, and it is stripped from the message.
- `message`: which candidate text to repeat. This question runs only when more
  than one distinct candidate exists.

```bash
/loop keep an eye on the deploy every ten minutes
/loop check the CI status every 15 minutes. stop when the build is green
```

The message is never written by a model. Code assembles the candidates from your
own words, and the model selects one. Code owns the interval arithmetic, the
placeholder expansion, the timers and the delivery.

A count is scheduling metadata wherever it appears, so it leaves the message:
`/loop 输入3次Hi` repeats `输入Hi` three times.

An unknown or low-confidence answer is refused with a report. It is never
guessed, because a wrong cadence floods the session.

## Stopping conditions

A stopping condition is judged after each repetition settles. One closed `noul`
question asks whether the assistant's most recent message establishes that the
condition is met, and the loop stops above the threshold. The default threshold
is 0.8. A failed judgment leaves the loop running: a service fault must not end
your work.

Only the loop's own repetition is judged. A turn you start yourself settles too,
and so does a turn that was already running when a repetition was queued behind
it; their answers are not this loop's result, so they ask no question and cost
nothing.

## The start line

Starting a loop prints one line:

```
[loop] started · every 5m · 3 times · check the build
```

The line is injected at the head of the turn a repetition reaches, so it arrives
with the repetition rather than before the input you typed. A start with no
cadence reaches it at its first repetition, because the default cadence is five
minutes and the first tick comes one interval after the start.

## Scheduling rules

- The first repetition happens one interval after the start, not immediately.
- A tick whose previous repetition has not settled is skipped and counted. Pi
  never queues a backlog of prompts.
- A bounded loop stops itself after its last repetition. `/loop stop` and session
  shutdown release the timer. A stopped loop cannot restart; start a new one.
- A delivery call that throws is reported, and the loop stops. Pi reports a turn
  that fails after it accepts the message itself, and it stops a loop through
  `session_shutdown` before it invalidates a captured extension API, so this
  report is defensive: no session replacement or reload reaches it.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | none | The decision credential. Without it, a free request and `--until` are refused. |
| `TYPESAFE_BASE_URL` | `https://api.typesafe.ai` | The decision endpoint. |
| `TYPESAFE_MODEL` | `jev-1.13.0` | A pinned version, because an alias silently changes tuned answers. |
| `LOOP_STOP_THRESHOLD` | `0.8` | The probability above which a met condition stops the loop. |
| `LOOP_MIN_CHOICE_CONFIDENCE` | `0.3` | The minimum confidence accepted for a plan selection. |

## Requirements

- Pi 1.2 or later.
- `@fradser/pi-kit`, which supplies the shared decision client and the lifecycle row.
- A TypeSafe credential for the free request form and for `--until`.

## Install

```bash
pi install npm:@fradser/pi-loop
```

## Measured

Recorded on 2026-10-15 against the live decision service (`jev-1.13.0`) with
twelve labelled requests, and in a real terminal. Reproduce with
`tests/real-jev-accuracy.ts` (paid), `tests/live_delivery_refusal.py` and
`tests/live_terminal_accessibility.py`.

- **Free-request accuracy**: of the twelve labelled requests, ten were resolved
  and two were refused. The interval was right 10 of 10, the stopping condition
  10 of 10 and the message 10 of 10. The run limit was right 4 of 4, because only
  four requests state a count. One refusal names no cadence and one was below the
  confidence threshold; the probe excludes the second from every denominator.
- **Cost**: a plan costs one or two decision requests and 1,058-1,611 input
  tokens, in about 0.8 seconds. One `met` judgment costs 394 input tokens. An
  eight-hour five-minute loop is 96 repetitions: 96 x 394 tokens plus one plan of
  at most 1,611 tokens, which is about **$0.0165** at the vendor's published rate
  of $0.42 per million input tokens ($0.0098 at the bulk rate; output tokens are
  not charged). Without a stopping condition, a loop costs nothing after its
  plan.
- **Delivery**: a repetition that cannot be delivered is reported and ends the
  loop. No session replacement reaches that report: `ctx.reload()`,
  `ctx.newSession()`, `ctx.fork()` and `ctx.switchSession()` each stop the loop
  through `session_shutdown` before an invalidated API can be called, so the
  report is defensive.
- **Terminal**: the start row and the below-editor status row render and stay
  readable in a real `Terminal.app` window at 120x40, 48x24 and 48x12, and the
  terminal's accessibility text carries both rows.

## Unverified

- Requests other than the twelve measured ones: they are self-selected, not a
  distribution, so your own requests can resolve differently.
- Currency cost, which follows the vendor's published rate rather than an
  invoice from this account.
- VoiceOver speech output, hardware terminals, and terminal emulators other than
  the one measured.
- Service behavior outside what the probes exercised, such as rate limits and
  outages.

Review the first repetitions of a loop, and keep the interval longer than a
typical turn.
