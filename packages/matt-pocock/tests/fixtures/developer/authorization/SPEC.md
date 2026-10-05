# authorization

canRead(actor,document) defaults to deny. Missing actor/document or inactive actor is denied. Tenant ids must match. A same-tenant admin may read any document. A same-tenant member may read only their own document (userId===ownerId). Unknown roles are denied; matching ownerId does not bypass tenant isolation. Return a boolean, do not mutate either object, and do not add roles or fallbacks.
Given a cross-tenant admin or owner, then deny. Given an active same-tenant member owning the document, then allow. Given missing or inactive credentials, then deny.
