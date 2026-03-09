'use strict';
const path = require('path');

require('dotenv').config({ path: path.resolve(__dirname, '../.env'), override: false });

const PLUGIN_DIR = path.resolve(__dirname, '..');
const DB_PATH = path.join(PLUGIN_DIR, 'memory.lance');

// Lazy-initialized state
let _lancedb = null;
let _arrow = null;
let _db = null;
let _table = null;
let _embedder = null;
let _vectorDim = null;

const TABLE_NAME = 'memories';
const SIMILARITY_THRESHOLD = 0.82;
const SEARCH_LIMIT = 6;

function getLancedb()  { if (!_lancedb) _lancedb = require('@lancedb/lancedb'); return _lancedb; }
function getArrow()    { if (!_arrow)   _arrow   = require('apache-arrow');      return _arrow; }

function getEmbedder() {
  if (_embedder) return _embedder;
  const { GoogleGenerativeAIEmbeddings } = require('@langchain/google-genai');
  _embedder = new GoogleGenerativeAIEmbeddings({
    model: process.env.GOOGLE_EMBEDDING_MODEL || 'gemini-embedding-001',
    apiKey: process.env.GOOGLE_API_KEY,
  });
  return _embedder;
}

async function getDb() {
  if (!_db) _db = await getLancedb().connect(DB_PATH);
  return _db;
}

/**
 * Return the Arrow schema for the memories table.
 * Must be called after we know the embedding dimension.
 */
function buildSchema(dim) {
  const { Schema, Field, Utf8, FixedSizeList, Float32 } = getArrow();
  return new Schema([
    new Field('id',             new Utf8(),                                                              true),
    new Field('content',        new Utf8(),                                                              true),
    new Field('type',           new Utf8(),                                                              true),
    new Field('source_session', new Utf8(),                                                              true),
    new Field('created_at',     new Utf8(),                                                              true),
    new Field('vector', new FixedSizeList(dim, new Field('item', new Float32(), true)),                  false),
  ]);
}

/**
 * Get or create the LanceDB table.
 * Pass vectorDim only on first call (when creating the table).
 */
async function getOrCreateTable(vectorDim) {
  if (_table) return _table;
  const db = await getDb();
  const names = await db.tableNames();

  if (names.includes(TABLE_NAME)) {
    _table = await db.openTable(TABLE_NAME);
    return _table;
  }

  // Create empty table with explicit Arrow schema so vector column is FixedSizeList<Float32>
  const schema = buildSchema(vectorDim);
  _table = await db.createEmptyTable(TABLE_NAME, schema);
  return _table;
}

/**
 * Convert a JS array of numbers to a LanceDB-compatible Arrow record via makeArrowTable.
 * Using makeArrowTable with an explicit schema is the only reliable way to get
 * FixedSizeList<Float32> — passing Float32Array directly produces Struct<Float64>.
 */
function makeRecord(row, schema) {
  return getLancedb().makeArrowTable([
    {
      id:             row.id,
      content:        row.content,
      type:           row.type,
      source_session: row.source_session,
      created_at:     row.created_at,
      vector:         Array.from(row.vector), // plain JS array — schema forces Float32
    },
  ], { schema });
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Embed text and return a plain JS number array.
 */
async function embed(text) {
  const [vec] = await getEmbedder().embedDocuments([text]);
  if (!_vectorDim && vec?.length) _vectorDim = vec.length;
  return vec;
}

/**
 * Search memory for entries semantically similar to queryText.
 * Returns array of { id, content, type, source_session, created_at, similarity }.
 */
async function searchMemory(queryText, { limit = SEARCH_LIMIT, threshold = SIMILARITY_THRESHOLD } = {}) {
  try {
    const tbl = await (async () => {
      const db = await getDb();
      const names = await db.tableNames();
      if (!names.includes(TABLE_NAME)) return null;
      if (!_table) _table = await db.openTable(TABLE_NAME);
      return _table;
    })();
    if (!tbl) return [];

    const vec = await embed(queryText);
    const rows = await tbl
      .vectorSearch(Float32Array.from(vec))
      .distanceType('cosine')
      .limit(limit)
      .toArray();

    const maxDist = 1 - threshold;
    return rows
      .filter(r => r._distance <= maxDist)
      .map(r => ({
        id:             r.id,
        content:        r.content,
        type:           r.type,
        source_session: r.source_session,
        created_at:     r.created_at,
        similarity:     parseFloat((1 - r._distance).toFixed(4)),
      }));
  } catch (err) {
    console.warn(`[Memory] searchMemory failed: ${err.message}`);
    return [];
  }
}

/**
 * Insert a new memory entry. Returns the new entry id, or null on failure.
 */
async function insertMemory({ content, type, source_session }) {
  try {
    const vec = await embed(content);
    const schema = buildSchema(vec.length);
    const tbl = await getOrCreateTable(vec.length);
    const id = `mem-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`;
    await tbl.add(makeRecord({
      id,
      content,
      type:           type || 'fact',
      source_session: source_session || 'unknown',
      created_at:     new Date().toISOString(),
      vector:         vec,
    }, schema));
    return id;
  } catch (err) {
    console.warn(`[Memory] insertMemory failed: ${err.message}`);
    return null;
  }
}

module.exports = { searchMemory, insertMemory };
