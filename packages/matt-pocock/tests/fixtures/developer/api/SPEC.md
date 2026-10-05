# api

parseRequest(req) is a pure HTTP boundary with method,contentType,body fields. Return {status,body,headers} and content-type application/json for every response. POST only; other methods return 405 with {error:'method'}. JSON MIME case-insensitive and ignore parameters; other MIME returns 415 {error:'content-type'}. Malformed JSON, non-object/array/null payload, non-string or blank name returns 400 {error:'body'}. Success returns 201 with only {name: trimmedName}. Check method then MIME then body. Do not throw on malformed bodies, mutate req, create a server or use network.
Given malformed JSON, then return a structured 400. Given an unsupported method or MIME, then reject before parsing. Given a valid name, then preserve the normalized name only.
