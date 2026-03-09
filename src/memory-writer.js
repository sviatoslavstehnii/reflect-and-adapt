'use strict';
const path = require('path');
const { ChatGoogleGenerativeAI } = require('@langchain/google-genai');
const { SystemMessage, HumanMessage } = require('@langchain/core/messages');
const { z } = require('zod');
const { searchMemory, insertMemory } = require('./memory');

require('dotenv').config({ path: path.resolve(__dirname, '../.env'), override: false });

const llm = new ChatGoogleGenerativeAI({
  model: process.env.GOOGLE_MODEL_MINI || 'gemini-3-flash-preview',
  apiKey: process.env.GOOGLE_API_KEY,
  temperature: 0,
  maxOutputTokens: 1000,
  tags: ['cortex', 'memory-writer'],
  metadata: { component: 'cortex-memory-writer' },
});

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

const memoryExtractor = llm.withStructuredOutput(MemoryEntrySchema, { name: 'extract_memory_entry' });
const dedupChecker = llm.withStructuredOutput(DedupSchema, { name: 'check_duplicate' });

// ─── Main ─────────────────────────────────────────────────────────────────────

async function writeMemoryEntries(memoryFindings, { sessionId } = {}) {
  let saved = 0;

  await Promise.all(memoryFindings.map(async (finding) => {
    try {
      const extracted = await memoryExtractor.invoke(
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
        const dedup = await dedupChecker.invoke(
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

module.exports = { writeMemoryEntries };
