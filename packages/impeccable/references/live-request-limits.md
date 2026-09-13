# Live request limits

The live server accepts JSON bodies up to 1 MiB on `/events`, `/poll`,
`/manual-edit-stash`, and `/manual-edit-repair-decision`. It counts received
UTF-8 bytes for both fixed-length and chunked requests. An oversized request
returns HTTP 413 with `Payload too large` and `maxBytes`, closes its connection,
and applies no event. Split a large batch into smaller requests before retrying.

PNG uploads to `/annotation` retain their separate 10 MiB limit. Interrupted
JSON uploads are discarded. Accepted JSON is decoded after collection so a
multibyte character split between network chunks remains intact.
