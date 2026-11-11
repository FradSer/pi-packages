# @fradser/pi-loop

## 0.2.0

### Minor Changes

- e5110d8: Run a count-bounded request that names no cadence.
  
  `/loop 输入3次Hi` and `/loop --times 3 Hi` were refused with "The request names no
  cadence". A run count bounds the loop, so nothing about that plan is undetermined:
  the loop now defaults to a five-minute cadence, and a tick that arrives while a
  repetition is still running is skipped rather than queued. The start notice says
  the cadence was assumed, so a defaulted cadence is never silent.
  
  The count is scheduling metadata wherever it appears, so it leaves the message:
  `/loop 输入3次Hi` repeats `输入Hi`. A count-only segment already left it, and a
  count phrase inside a segment now leaves it too.
  
  An unnamed cadence is never a refusal, with or without a run count. `/loop
  检查项目修改，总结` repeats every five minutes until you run `/loop stop` or its
  stopping condition is met, and the start notice says the cadence was assumed.
  
  The start line moves to the turn a repetition reaches. Every `/loop ...` arrives
  as a user turn and the first repetition is queued behind that run, so a line sent
  from the command landed ahead of the input you typed. The line is now injected at
  the head of the next run, which is the run a repetition reaches. A start with no
  cadence reaches it at its first repetition, which now runs as soon as the loop
  starts.
  
  Code-matched metadata no longer becomes a message question. The request and its
  metadata-free text differ only by a phrase this code matched itself, so the choice
  belongs to the code: `/loop say hi * 3` now asks one question set and injects
  `say hi`. Against the live service the two-way choice came back at 0.22 confidence
  and refused the whole command, and every free request paid for a question whose
  answer was already known. The message question still runs where the service's own
  answer shaped the text, such as the segment it named as the stopping condition.
  
  A free request now reports itself before it reports a plan. One `[loop] request`
  row names it, the request text follows verbatim, and the below-editor row reads
  `Analyzing · <request>` while the decision request runs. The flag form shows none
  of that: it calls no model and starts directly.
- fb4370b: Add `/loop <request>`: repeat one message into a session as a real user turn.
  
  `--every`, `--times`, `--until` and `--message` state a schedule explicitly and
  call no model. `{{index}}`, `{{total}}`, `{{remaining}}`, `{{time}}` and
  `{{date}}` expand per repetition. A free request is resolved by TypeSafe Jev
  choices over candidates the extension builds: the listed interval, the run
  limit, the request segment that states the stopping condition, and the text to
  repeat. A segment that only states a repetition count is the run limit, never a
  stopping condition. A natural-language stopping condition is judged by one closed
  noul question after each settled turn, against an explicit threshold.
  
  A tick whose previous injection has not settled is skipped and counted, so a slow
  turn cannot queue prompts. A delivery the host refuses is reported and ends the
  loop. `/loop stop` and session shutdown release the only timer, and a stopped loop
  cannot restart.
  
  Verified with deterministic module checks, a loopback decision endpoint covering
  low confidence, unspecified cadence, unknown answers and rejected credentials,
  and a native `pi` TUI run that delivered two scheduled injections as
  `messageType: "user"` turns. Measured against the live service on twelve labelled
  requests, all four questions resolved correctly and an eight-hour five-minute loop
  with a stopping condition costs about $0.02; read the package README for the
  numbers and for what stays unverified.

### Patch Changes

- 97e9add: Document the workspace's bun-only commands instead of the earlier package manager. Contributor guides, README verification blocks, BDD wording and shipped command examples now use `bun run typecheck`, `bun run check:install`, `bun pm pack` and `bun test`. Test fixtures and opt-in Docker acceptance harnesses invoke bun directly. No runtime behavior changes.
- 6ec3a97: Judge only the loop's own repetition, and drop the unused abort seam.
  
  Every settled turn reaches the extension, so a turn the user started, or a turn
  that was already running when a repetition was queued behind it, could end the
  loop before its first repetition and spend a decision request on an answer that
  was not the loop's result. `agent_end` now compares the run's last user message
  with the pending injection, and `agent_settled` judges only a match. The behavior
  matches `features/loop.feature` and the package README.
  
  `src/decide.ts` no longer declares an abort signal, because none reaches it: Pi
  1.2.0 reports `ctx.signal` to a hook inside a turn, and `undefined` inside an
  extension command and at the settle boundary. The client's timeout bounds each
  request. Read `packages/loop/AGENTS.md`.
  
  The package guidance also records why the start notice uses `triggerTurn: false`
  instead of the root guidance's `deliverAs: "followUp"` and `triggerTurn: true`:
  a triggered turn at the start would inject a model turn the user did not ask for.
- ab7a1b2: Use the cadence a multi-hour request names, and keep a Chinese schedule phrase out
  of the message.
  
  `/loop 每 2 个小时，清理一次非必要的文档、代码。` planned **every 1h**. The interval
  question answers with the closest listed cadence, and the listed set held only 1h
  and 1d, so half the cadence the user asked for was the closest reachable answer.
  The set now lists 2h, 4h, 6h, 8h and 12h beside 1h and 1d, so a stated multi-hour
  cadence is reachable exactly. The same request also repeated its own schedule
  phrase: the Chinese pattern required the unit to follow the number, and the measure
  word (每 2 **个**小时) and the 隔 form (每**隔**2 个小时) put a character between
  them. Both forms are matched now, so the message is `清理非必要的文档、代码`.
  
  A count stated as its own segment no longer becomes a message question either. When
  the service named no stopping condition, dropping that segment left the raw request
  among the candidates, and the code-matched count came back as a paid judgment:
  `/loop watch the logs every minute, 10 times` was refused at 0.27 < 0.30 against the
  live service, then decided in the next run. The metadata-free text is the message
  whenever no answer of the service shaped the text, so that request needs one
  question set and always repeats `watch the logs`.
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [ff9b7ff]
- Updated dependencies [a3ee3e3]
- Updated dependencies [2bba220]
- Updated dependencies [a0923d8]
- Updated dependencies [426ef90]
- Updated dependencies [6603d43]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [6416992]
- Updated dependencies [fc0d801]
- Updated dependencies [53cb34f]
- Updated dependencies [ceb8e23]
- Updated dependencies [842b92e]
- Updated dependencies [2116b41]
- Updated dependencies [b3daa7f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [842b92e]
- Updated dependencies [e86a44f]
- Updated dependencies [53cb34f]
- Updated dependencies [53cb34f]
  - @fradser/pi-kit@0.6.0
