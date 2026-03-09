const Database = require('better-sqlite3');
const path = require('path');

const PLUGIN_DIR = path.resolve(__dirname, '..');
const db = new Database(path.join(PLUGIN_DIR, 'reflect.db'));

// WAL mode for better concurrent read performance
db.pragma('journal_mode = WAL');

db.exec(`
  CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    role       TEXT,
    text       TEXT,
    timestamp  TEXT,
    message_id TEXT UNIQUE
  );

  CREATE TABLE IF NOT EXISTS scores (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         TEXT,
    turn_timestamp     TEXT,
    langsmith_run_id   TEXT,
    helpfulness        INTEGER,
    conciseness        INTEGER,
    correction_signal  INTEGER,
    frustration_signal INTEGER,
    task_completed     INTEGER,
    user_satisfaction  TEXT,
    response_accepted  INTEGER,
    format_match       INTEGER,
    reasoning          TEXT
  );

  CREATE TABLE IF NOT EXISTS proposals (
    id              TEXT PRIMARY KEY,
    status          TEXT DEFAULT 'PENDING',
    proposal_type   TEXT,
    target_file     TEXT,
    proposed_change TEXT,
    rationale       TEXT,
    risk_level      TEXT,
    created_at      TEXT,
    superseded_at   TEXT,
    superseded_by   TEXT
  );

  CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT
  );
`);

// Migrations
try { db.exec(`ALTER TABLE proposals ADD COLUMN rejection_reason TEXT`); } catch { /* exists */ }
try { db.exec(`ALTER TABLE proposals ADD COLUMN presented_at TEXT`); } catch { /* exists */ }

module.exports = db;
