#!/usr/bin/env node
'use strict';

const path = require('path');
// Load env so db.js can find its path
require('dotenv').config({ path: path.resolve(__dirname, '../../.env'), override: false });
const db = require('../../src/db.js');

const [,, command, id, ...rest] = process.argv;

const COMMANDS = {

  list() {
    const rows = db.prepare(`
      SELECT id, status, risk_level, proposal_type, target_file, rationale, created_at, presented_at
      FROM proposals
      ORDER BY created_at DESC
    `).all();

    if (rows.length === 0) {
      console.log('No proposals found.');
      return;
    }

    const byStatus = { PENDING: [], PRESENTED: [], APPROVED: [], REJECTED: [], STALE: [] };
    for (const p of rows) (byStatus[p.status] ?? (byStatus.OTHER ??= [])).push(p);

    for (const [status, list] of Object.entries(byStatus)) {
      if (!list.length) continue;
      console.log(`\n── ${status} (${list.length}) ─────────────────────`);
      for (const p of list) {
        console.log(`  [${p.id}] ${p.risk_level ?? '?'} risk · ${p.proposal_type}`);
        console.log(`    File:     ${p.target_file}`);
        console.log(`    Rationale: ${p.rationale}`);
        console.log(`    Created:  ${p.created_at}${p.presented_at ? `  Presented: ${p.presented_at}` : ''}`);
      }
    }
  },

  show() {
    _requireId();
    const p = db.prepare('SELECT * FROM proposals WHERE id=?').get(id);
    if (!p) { console.error(`Proposal ${id} not found.`); process.exit(1); }
    console.log(JSON.stringify(p, null, 2));
    if (p.proposed_change) {
      console.log('\n── Proposed change ──────────────────────────────');
      console.log(p.proposed_change);
    }
  },

  approve() {
    _requireId();
    const result = db.prepare(`
      UPDATE proposals SET status='APPROVED'
      WHERE id=? AND status IN ('PENDING','PRESENTED')
    `).run(id);
    if (result.changes === 0) {
      console.error(`Proposal ${id} not found or already decided.`);
      process.exit(1);
    }
    const p = db.prepare('SELECT * FROM proposals WHERE id=?').get(id);
    console.log(`✓ APPROVED ${id}`);
    console.log(`\nApply to: ${p.target_file}`);
    console.log('──────────────────────────────────────────────────');
    console.log(p.proposed_change);
  },

  reject() {
    _requireId();
    const reason = rest.join(' ').trim() || null;
    const result = db.prepare(`
      UPDATE proposals SET status='REJECTED', rejection_reason=?
      WHERE id=? AND status IN ('PENDING','PRESENTED')
    `).run(reason, id);
    if (result.changes === 0) {
      console.error(`Proposal ${id} not found or already decided.`);
      process.exit(1);
    }
    console.log(`✗ REJECTED ${id}${reason ? ` — ${reason}` : ''}`);
  },

  pending() {
    _requireId();
    const result = db.prepare(`
      UPDATE proposals SET status='PENDING', presented_at=NULL WHERE id=?
    `).run(id);
    if (result.changes === 0) {
      console.error(`Proposal ${id} not found.`);
      process.exit(1);
    }
    console.log(`↩ Re-queued ${id} → PENDING`);
  },

};

function _requireId() {
  if (!id) {
    console.error(`Usage: manage-proposals.js ${command} <proposal-id>`);
    process.exit(1);
  }
}

if (!command || !COMMANDS[command]) {
  console.log('Usage: node manage-proposals.js <command> [args]\n');
  console.log('Commands:');
  console.log('  list                      — show all proposals grouped by status');
  console.log('  show    <id>              — show full proposal including proposed change');
  console.log('  approve <id>              — mark APPROVED and print the change to apply');
  console.log('  reject  <id> [reason]     — mark REJECTED with optional reason');
  console.log('  pending <id>              — re-queue as PENDING (show again next session)');
  process.exit(command ? 1 : 0);
}

COMMANDS[command]();
