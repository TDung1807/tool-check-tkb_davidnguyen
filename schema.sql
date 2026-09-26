-- Supabase schema for TDTU Calendar Bot multi-user support.
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New Query).

-- ============================================================
-- Users table
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    telegram_id         BIGINT PRIMARY KEY,
    telegram_username   TEXT,
    mssv                TEXT NOT NULL,
    encrypted_pass      TEXT NOT NULL,       -- Fernet-encrypted TDTU password
    google_refresh_token TEXT,               -- Fernet-encrypted OAuth refresh token
    google_calendar_id  TEXT,                -- Google Calendar ID for this user
    is_active           BOOLEAN DEFAULT true,
    created_at          TIMESTAMPTZ DEFAULT now(),
    last_sync_at        TIMESTAMPTZ
);

-- ============================================================
-- Sync snapshots (for change detection)
-- ============================================================
CREATE TABLE IF NOT EXISTS sync_snapshots (
    telegram_id     BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
    schedule_hash   TEXT,                    -- SHA-256 hash of schedule+exam data
    schedule_data   TEXT,                    -- Full JSON snapshot (for diffing)
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- Sync logs
-- ============================================================
CREATE TABLE IF NOT EXISTS sync_logs (
    id              BIGSERIAL PRIMARY KEY,
    telegram_id     BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    sync_type       TEXT NOT NULL DEFAULT 'morning',  -- 'morning' | 'manual' | 'hourly'
    status          TEXT NOT NULL,                     -- 'success' | 'failed' | 'no_change'
    message         TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Index for fast log queries by user + time
CREATE INDEX IF NOT EXISTS idx_sync_logs_user_created
    ON sync_logs (telegram_id, created_at DESC);

-- ============================================================
-- Row Level Security (RLS)
-- ============================================================
-- Enable RLS on all tables.  The service-role key bypasses RLS,
-- so the bot server can access everything.  The anon key is
-- blocked from reading user secrets.

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_logs ENABLE ROW LEVEL SECURITY;

-- Allow service_role full access (bot server uses this key).
CREATE POLICY "service_role_full_access_users"
    ON users FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role_full_access_snapshots"
    ON sync_snapshots FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role_full_access_logs"
    ON sync_logs FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
