'use strict';
/**
 * Dumps all entries from memory.lance to stdout as JSON.
 * Used by the experiment harness to snapshot memory state after each session.
 *
 * Usage: node src/dump-memories.js [--session-prefix <prefix>]
 * Output: JSON array of { id, content, type, source_session, created_at }
 */
const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../.env'), override: false });

const PLUGIN_DIR = path.resolve(__dirname, '..');
const DB_PATH = path.join(PLUGIN_DIR, 'memory.lance');
const TABLE_NAME = 'memories';

async function main() {
  const args = process.argv.slice(2);
  const prefixIdx = args.indexOf('--session-prefix');
  const sessionPrefix = prefixIdx !== -1 ? args[prefixIdx + 1] : null;

  const lancedb = require('@lancedb/lancedb');
  const db = await lancedb.connect(DB_PATH);
  const names = await db.tableNames();

  if (!names.includes(TABLE_NAME)) {
    console.log(JSON.stringify([]));
    return;
  }

  const table = await db.openTable(TABLE_NAME);
  const rows = await table
    .query()
    .select(['id', 'content', 'type', 'source_session', 'created_at'])
    .toArray();

  let result = rows.map(r => ({
    id: r.id,
    content: r.content,
    type: r.type,
    source_session: r.source_session,
    created_at: r.created_at,
  }));

  if (sessionPrefix) {
    const filtered = result.filter(r => r.source_session && r.source_session.startsWith(sessionPrefix));
    // Fall back to all entries if prefix matches nothing (e.g. old entries stored as "unknown")
    result = filtered.length > 0 ? filtered : result;
  }

  // Sort by created_at ascending
  result.sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));

  console.log(JSON.stringify(result, null, 2));
}

main().catch(e => {
  console.error(e.message);
  process.exit(1);
});
