---
"@fradser/pi-loop": patch
---

Use the cadence a multi-hour request names, and keep a Chinese schedule phrase out
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
