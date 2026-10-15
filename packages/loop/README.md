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
/loop -e 2h -t 2 -m report
```

| Flag | Meaning |
| --- | --- |
| `--every`, `-e` | The interval. Required when flags are used. |
| `--times`, `-t` | The total count. Omit it to repeat until `/loop stop`. |
| `--until`, `-u` | A stopping condition in natural language. |
| `--message`, `-m` | The text. Equivalent to trailing text. |

A duration is `500ms`, `30s`, `5m`, `2h`, `1d`, a combination such as `1h30m`, or a
bare number of seconds. The shortest interval is one second and the longest is one
day. `--` ends the flags, so the text after it may contain `--`.

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
  listed intervals are 30s, 1m, 5m, 15m, 30m, 1h and 1d. `unspecified` is
  rejected, and the command reports that the request names no cadence.
- `runs`: the total count, or `unbounded`. The listed values are 1, 3, 5, 10, 20
  and `unbounded`.
- `stop`: which candidate segment states a stopping condition, or `none`.
- `message`: which candidate text to repeat. This question runs only when more
  than one distinct candidate exists.

```bash
/loop keep an eye on the deploy every ten minutes
/loop check the CI status every 15 minutes. stop when the build is green
```

The message is never written by a model. Code assembles the candidates from your
own words, and the model selects one. Code owns the interval arithmetic, the
placeholder expansion, the timers and the delivery.

An unknown or low-confidence answer is refused with a report. It is never
guessed, because a wrong cadence floods the session.

## Stopping conditions

A stopping condition is judged after each repetition settles. One closed `noul`
question asks whether the assistant's most recent message establishes that the
condition is met, and the loop stops above the threshold. The default threshold
is 0.8. A failed judgment leaves the loop running: a service fault must not end
your work.

## Scheduling rules

- The first repetition happens one interval after the start, not immediately.
- A tick whose previous repetition has not settled is skipped and counted. Pi
  never queues a backlog of prompts.
- A bounded loop stops itself after its last repetition. `/loop stop` and session
  shutdown release the timer. A stopped loop cannot restart; start a new one.
- A repetition that cannot be delivered ends the loop, and the command reports
  the failure. A repetition that never arrived cannot be judged, so the loop
  never keeps claiming one.

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

## Unverified

TypeSafe Jev accuracy is not measured on your own requests. The listed intervals
and thresholds are starting points, not a measured result. Review the first
repetitions of a loop, and keep the interval longer than a typical turn.
