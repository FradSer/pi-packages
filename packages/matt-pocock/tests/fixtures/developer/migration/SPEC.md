# migration

migrate(record) upgrades a validated version-1 record to version 2 by renaming fullName to displayName and removing fullName; preserve unknown fields and nested identities. Do not mutate input. Version-2 records are already migrated and must return the same object unchanged. Unsupported versions throw Error('Unsupported version'). No database writes or dependencies; this is the migration transformation, not a deployed migration.
Given a v1 frozen record with extra fields, then rename only the specified field. Given the migrated record again, then return the same object. Given an unknown version, then refuse.
