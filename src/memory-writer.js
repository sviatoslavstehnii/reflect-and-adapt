'use strict';
const path = require('path');
const { ChatOpenAI } = require('@langchain/openai');
const { ChatGoogleGenerativeAI } = require('@langchain/google-genai');
const { SystemMessage, HumanMessage } = require('@langchain/core/messages');
const { z } = require('zod');
const { searchMemory, insertMemory } = require('./memory');

require('dotenv').config({ path: path.resolve(__dirname, '../.env'), override: false });

function createCortexLlms(maxTokens, tags, metadata) {
  const qwen = new ChatOpenAI({
    model: process.env.QWEN_MODEL || 'qwen-plus',
    apiKey: process.env.QWEN_API_KEY,
    configuration: { baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
    temperature: 0,
    maxTokens,
    tags,
    metadata,
  });
  const flash = new ChatGoogleGenerativeAI({
    model: process.env.GOOGLE_MODEL_FLASH || 'gemini-3-flash-preview',
    apiKey: process.env.GOOGLE_API_KEY,
    temperature: 0,
    maxOutputTokens: maxTokens,
    tags,
    metadata,
  });
  const geminiFirst = (process.env.CORTEX_PROVIDER || 'qwen') === 'gemini';
  return geminiFirst
    ? [{ llm: flash, name: 'Gemini Flash' }, { llm: qwen, name: 'Qwen' }]
    : [{ llm: qwen, name: 'Qwen' }, { llm: flash, name: 'Gemini Flash' }];
}

async function invokeStructured(schema, name, messages, options) {
  const providers = createCortexLlms(1000, ['cortex', 'memory-writer'], { component: 'cortex-memory-writer' });
  for (const [i, { llm, name: providerName }] of providers.entries()) {
    try {
      return await llm.withStructuredOutput(schema, { name }).invoke(messages, options);
    } catch (err) {
      if (i < providers.length - 1) {
        console.warn(`[MemoryWriter] ${providerName} failed (${err.message}), falling back to ${providers[i + 1].name}...`);
      } else {
        throw err;
      }
    }
  }
}

// ─── Schemas ──────────────────────────────────────────────────────────────────

const MemoryEntrySchema = z.object({
  content: z.string().describe('A self-contained, factual sentence about the user. Useful when retrieved out of context. Max 200 chars.'),
  type: z.enum(['user_fact', 'preference', 'example', 'context']).describe(
    'user_fact: verifiable fact about the user. ' +
    'preference: style or tool preferences. ' +
    'example: a specific past interaction showing how to handle something. ' +
    'context: ongoing project or situational context.'
  ),
  skip: z.boolean().describe('True if this finding does not produce useful episodic memory'),
  skip_reason: z.string().optional(),
});

const DedupSchema = z.object({
  is_duplicate: z.boolean().describe('True if the candidate is essentially the same fact as one of the existing entries'),
  reason: z.string().describe('One sentence explanation'),
});


// ─── Main ─────────────────────────────────────────────────────────────────────

async function writeMemoryEntries(memoryFindings, { sessionId } = {}) {
  let saved = 0;

  await Promise.all(memoryFindings.map(async (finding) => {
    try {
      const extracted = await invokeStructured(MemoryEntrySchema, 'extract_memory_entry',
        [
          new SystemMessage(
            'You convert analyst findings into concise, self-contained memory entries for an AI assistant.\n' +
            'Write as a factual statement that will be useful when retrieved months later, out of context.\n' +
            'Good: "User works as a software engineer and is writing a Bachelor\'s thesis on adaptive AI."\n' +
            'Bad: "User mentioned thesis" (too vague) or copying analyst jargon verbatim.'
          ),
          new HumanMessage(
            `Finding type: ${finding.type}\n` +
            `Summary: ${finding.summary}\n` +
            `Evidence:\n${(finding.evidence || []).map(e => `  - ${e.substring(0, 150)}`).join('\n')}\n\n` +
            'Create a self-contained memory entry from this finding.'
          ),
        ],
        { runName: 'cortex_memory_extract', tags: ['cortex', 'memory-writer'] }
      );

      if (extracted.skip) {
        console.log(`[MemoryWriter] Skipped: ${extracted.skip_reason}`);
        return;
      }

      const similar = await searchMemory(extracted.content, { threshold: 0.82 });

      if (similar.length > 0) {
        const existing = similar.map(m => `- ${m.content}`).join('\n');
        const dedup = await invokeStructured(DedupSchema, 'check_duplicate',
          [
            new SystemMessage(
              'Decide if a new memory entry is a duplicate of existing entries.\n' +
              'A duplicate means the same fact is already captured — even if worded differently.\n' +
              'New detail, higher specificity, or a correction counts as NEW (not a duplicate).'
            ),
            new HumanMessage(
              `New candidate:\n"${extracted.content}"\n\nExisting similar entries:\n${existing}\n\n` +
              'Is the candidate a duplicate of any existing entry?'
            ),
          ],
          { runName: 'cortex_memory_dedup', tags: ['cortex', 'memory-writer'] }
        );

        if (dedup.is_duplicate) {
          console.log(`[MemoryWriter] Duplicate — skipping: ${dedup.reason}`);
          return;
        }
        console.log(`[MemoryWriter] Similar but new: ${dedup.reason}`);
      }

      const id = await insertMemory({
        content: extracted.content,
        type: extracted.type,
        source_session: sessionId || 'unknown',
      });

      if (id) {
        console.log(`[MemoryWriter] Saved ${id}: ${extracted.content.substring(0, 80)}`);
        saved++;
      }
    } catch (err) {
      console.warn(`[MemoryWriter] Error processing finding: ${err.message}`);
    }
  }));

  return saved;
}

/**
 * Ingest a single raw observation directly into memory.
 * Runs the same reformulate → dedup → insert pipeline as writeMemoryEntries,
 * but accepts a plain string instead of an analyst finding object.
 *
 * Returns { id, content } on success, or { skipped: true, reason } if
 * the entry was filtered out as a duplicate or not useful.
 */
async function ingestMemory(rawContent, type = 'user_fact', sessionId = 'manual') {
  const extracted = await invokeStructured(MemoryEntrySchema, 'extract_memory_entry',
    [
      new SystemMessage(
        'You convert a raw observation into a concise, self-contained memory entry for an AI assistant.\n' +
        'Write as a factual statement that will be useful when retrieved months later, out of context.\n' +
        'Good: "User works as a software engineer and is writing a Bachelor\'s thesis on adaptive AI."\n' +
        'Bad: "User mentioned thesis" (too vague) or raw notes verbatim.'
      ),
      new HumanMessage(
        `Raw observation: ${rawContent}\n` +
        `Type hint: ${type}\n\n` +
        'Create a self-contained memory entry from this observation.'
      ),
    ],
    { runName: 'ingest_memory_extract', tags: ['memory-ingest'] }
  );

  if (extracted.skip) {
    return { skipped: true, reason: extracted.skip_reason || 'not useful' };
  }

  const similar = await searchMemory(extracted.content, { threshold: 0.82 });

  if (similar.length > 0) {
    const existing = similar.map(m => `- ${m.content}`).join('\n');
    const dedup = await invokeStructured(DedupSchema, 'check_duplicate',
      [
        new SystemMessage(
          'Decide if a new memory entry is a duplicate of existing entries.\n' +
          'A duplicate means the same fact is already captured — even if worded differently.\n' +
          'New detail, higher specificity, or a correction counts as NEW (not a duplicate).'
        ),
        new HumanMessage(
          `New candidate:\n"${extracted.content}"\n\nExisting similar entries:\n${existing}\n\n` +
          'Is the candidate a duplicate of any existing entry?'
        ),
      ],
      { runName: 'ingest_memory_dedup', tags: ['memory-ingest'] }
    );

    if (dedup.is_duplicate) {
      return { skipped: true, reason: dedup.reason };
    }
  }

  const id = await insertMemory({
    content: extracted.content,
    type: extracted.type,
    source_session: sessionId,
  });

  if (!id) throw new Error('insertMemory returned null');
  return { id, content: extracted.content };
}

module.exports = { writeMemoryEntries, ingestMemory };
