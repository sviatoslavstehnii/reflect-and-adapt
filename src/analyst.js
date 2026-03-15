const path = require('path');
const { ChatOpenAI } = require('@langchain/openai');
const { SystemMessage, HumanMessage } = require('@langchain/core/messages');
const { z } = require('zod');
const db = require('./db');

require('dotenv').config({ path: path.resolve(__dirname, '../.env'), override: false });

const llm = new ChatOpenAI({
  model: process.env.QWEN_MODEL || 'qwen-plus',
  apiKey: process.env.QWEN_API_KEY,
  configuration: {
    baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  },
  temperature: 0,
  maxTokens: 2000,
  tags: ['cortex', 'analyst'],
  metadata: { component: 'cortex-analyst' },
});

// ─── Schema ───────────────────────────────────────────────────────────────────

const FindingSchema = z.object({
  type: z.enum([
    'correction',           // user corrected, retried, or redirected the assistant
    'user_fact',            // new verifiable fact about the user
    'missing_capability',   // user needed something the assistant couldn't do well
    'workflow_convention',  // recurring workflow the assistant handled incorrectly
    'persona_preference',   // user expressed preference about assistant's style
    'periodic_task',        // user asked for something to be checked/done regularly
    'frustration_pattern',  // user showed frustration repeatedly over the same issue
    'memory_entry',         // episodic fact/context too specific for static files — store in vector DB
  ]),
  summary: z.string().describe('One sentence describing the pattern'),
  evidence: z.array(z.string()).describe('2-4 direct quotes or close paraphrases from logs with timestamps'),
  count: z.number().int().describe('Number of times this pattern appears in the data'),
  confidence: z.enum(['low', 'medium', 'high']),
});

const AnalystOutputSchema = z.object({
  findings: z.array(FindingSchema),
  analysis_notes: z.string().describe('1-2 sentences on overall session quality or notable meta-observations'),
});

const analystWithOutput = llm.withStructuredOutput(AnalystOutputSchema, {
  name: 'extract_findings',
});

// ─── System Prompt ────────────────────────────────────────────────────────────

const SYSTEM = `You are a conversation analyst for an AI assistant adaptation system.
Extract patterns from conversation logs that indicate the assistant should update its behavior, learn new facts about the user, or acquire new capabilities.

Finding types:
- correction: user corrected, retried, or redirected the assistant
- user_fact: new verifiable fact about the user (location, profession, preferences, context)
- missing_capability: user needed something the assistant could not do well
- workflow_convention: a recurring workflow pattern the assistant handled incorrectly
- persona_preference: user expressed preference about the assistant's personality or style
- periodic_task: user asked for something to be checked or done regularly
- frustration_pattern: user showed frustration repeatedly over the same issue
- memory_entry: episodic detail too specific for static files (specific project context, ongoing work, situational detail, things USER.md shouldn't have)

Rules:
- Only report patterns with clear textual evidence from the logs
- user_fact: 1 occurrence is enough. All other types: require 2+ occurrences
- Quote or closely paraphrase actual log entries with timestamps as evidence
- Sessions with low helpfulness scores or high frustration spikes are higher priority
- Do not invent patterns not visible in the data
- Assign confidence=low when the pattern is ambiguous, medium when reasonably clear, high when unambiguous`;

// ─── Main ─────────────────────────────────────────────────────────────────────

async function runAnalyst({ numTurns = 40 } = {}) {
  const sessionHealth = db.prepare(`
    SELECT
      session_id,
      ROUND(AVG(helpfulness), 1)  AS avg_helpfulness,
      ROUND(AVG(conciseness), 1)  AS avg_conciseness,
      SUM(frustration_signal)     AS frustration_spikes,
      CASE
        WHEN AVG(helpfulness) >= 4 AND SUM(frustration_signal) = 0 THEN 'good'
        WHEN AVG(helpfulness) < 3  OR  SUM(frustration_signal) > 1 THEN 'struggling'
        ELSE 'neutral'
      END AS session_health
    FROM scores
    GROUP BY session_id
    ORDER BY avg_helpfulness ASC
    LIMIT 5
  `).all();

  const turns = db.prepare(`
    SELECT role, text, timestamp, session_id
    FROM conversations
    WHERE role IN ('user', 'assistant')
      AND text NOT LIKE '%Execute your Session Startup sequence%'
    ORDER BY id DESC
    LIMIT ?
  `).all(numTurns);

  if (turns.length < 5) {
    console.log('[Analyst] Insufficient data — fewer than 5 turns.');
    return { findings: [], analysis_notes: 'Insufficient data.' };
  }

  const healthBlock = sessionHealth.length > 0
    ? `Session health (worst first):\n${sessionHealth.map(s =>
        `  ${s.session_id}: ${s.session_health} | helpfulness=${s.avg_helpfulness} | frustration_spikes=${s.frustration_spikes}`
      ).join('\n')}`
    : 'No scored sessions yet.';

  const turnsBlock = turns.reverse().map(t => {
    const ts = new Date(t.timestamp).toISOString().slice(0, 16).replace('T', ' ');
    const text = (t.text || '')
      .replace(/```[\s\S]{0,500}?```/g, '[code block]')
      .replace(/`[^`]{40,}`/g, '[code]')
      .substring(0, 300);
    return `[${ts}][${t.session_id}] ${t.role.toUpperCase()}: ${text}`;
  }).join('\n');

  const result = await analystWithOutput.invoke(
    [new SystemMessage(SYSTEM), new HumanMessage(`${healthBlock}\n\n---\n\n${turnsBlock}`)],
    { runName: 'cortex_analyst', tags: ['cortex', 'analyst'] }
  );

  console.log(`[Analyst] ${result.findings.length} finding(s). Notes: ${result.analysis_notes}`);
  return result;
}

module.exports = { runAnalyst };
