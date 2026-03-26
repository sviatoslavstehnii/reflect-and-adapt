#!/usr/bin/env node
'use strict';

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../../.env') });

const VALID_TYPES = ['user_fact', 'preference', 'example', 'context'];

const rawContent = process.argv[2];
const type       = process.argv[3] || 'user_fact';

if (!rawContent) {
  console.error('Usage: node ingest-memory.js "<observation>" [type]');
  console.error(`Types: ${VALID_TYPES.join(' | ')}`);
  process.exit(1);
}

if (!VALID_TYPES.includes(type)) {
  console.error(`Invalid type "${type}". Must be one of: ${VALID_TYPES.join(', ')}`);
  process.exit(1);
}

const { ingestMemory } = require('../../src/memory-writer.js');

ingestMemory(rawContent, type, 'agent-direct')
  .then(result => {
    if (result.skipped) {
      console.log(`[remember] Skipped: ${result.reason}`);
    } else {
      console.log(`[remember] Saved ${result.id}`);
      console.log(`[remember] Stored as: "${result.content}"`);
    }
  })
  .catch(err => {
    console.error(`[remember] Failed: ${err.message}`);
    process.exit(1);
  });
