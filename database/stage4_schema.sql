
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS holiday_calendar (
    holiday_id TEXT PRIMARY KEY,
    holiday_date TEXT NOT NULL UNIQUE,
    holiday_name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_holiday_date
ON holiday_calendar(holiday_date);
