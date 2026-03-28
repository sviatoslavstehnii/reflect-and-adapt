// Load .env FIRST — before any LangChain modules are imported.
// LangChain reads LANGCHAIN_TRACING_V2 at require() time, so this must run
// before evaluator.js / cortex.js are loaded (they are lazy-loaded in register()).
const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });

let db;
try {
  db = require('./src/db.js');
} catch (err) {
  console.error(`[reflect-and-adapt] Failed to load src/db.js: ${err.message}`);
}

// Cooldown: run Cortex at most once per this interval (default 1h)
const CORTEX_COOLDOWN_MS = parseInt(process.env.CORTEX_COOLDOWN_HOURS || '1', 10) * 60 * 60 * 1000;

const SYSTEM_MSG_RE = /Execute your Session Startup sequence/;

function extractText(content) {
  if (!content) return '';
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content.filter(c => c.type === 'text').map(c => c.text).join('\n');
  }
  return '';
}

function getLastCortexRunMs() {
  try {
    const row = db.prepare('SELECT value FROM state WHERE key=?').get('lastCortexRun');
    return row ? new Date(row.value).getTime() : 0;
  } catch { return 0; }
}

function setLastCortexRun() {
  try {
    db.prepare('INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)').run('lastCortexRun', new Date().toISOString());
  } catch { /* non-fatal */ }
}

/**
 * Returns the last N real user+assistant conversation pairs from the database.
 * Skips system startup injections.
 */
function getLastNPairs(n) {
  try {
    const rows = db.prepare(`
      SELECT role, text, timestamp, session_id
      FROM conversations
      WHERE role IN ('user', 'assistant')
        AND text NOT LIKE '%Execute your Session Startup sequence%'
      ORDER BY id DESC
      LIMIT ?
    `).all(n * 4);

    const turns = rows.reverse();
    const pairs = [];
    let i = turns.length - 1;
    while (i >= 0 && pairs.length < n) {
      if (turns[i].role === 'assistant') {
        const assistantEntry = turns[i];
        let j = i - 1;
        while (j >= 0 && turns[j].role !== 'user') j--;
        if (j >= 0) {
          pairs.unshift({
            userMessage: turns[j].text || '',
            assistantResponse: assistantEntry.text || '',
            timestamp: assistantEntry.timestamp,
            sessionId: assistantEntry.session_id,
          });
          i = j - 1;
        } else {
          i--;
        }
      } else {
        i--;
      }
    }
    return pairs;
  } catch {
    return [];
  }
}

module.exports = {
  id: 'reflect-and-adapt',
  name: 'Reflect and Adapt',
  description: 'Logs session messages, evaluates interaction quality, and runs a Cortex meta-agent to propose workspace adaptations.',
  kind: 'lifecycle',

  register(api) {
    const log = api.logger ?? console;

    if (!db) {
      log.warn?.('[reflect-and-adapt] Database not available — plugin disabled.');
      return;
    }

    // ── Lazy-load LangChain-dependent modules ─────────────────────────────────
    // .env is loaded at the top of this file before these requires, so
    // LANGCHAIN_TRACING_V2 is already set when LangChain initializes.
    let runCortexCycle;
    try {
      const cortexModule = require('./src/cortex.js');
      runCortexCycle = cortexModule.runCortexCycle;
    } catch (err) {
      log.error?.(`[reflect-and-adapt] Failed to load src/cortex.js: ${err.message}`);
    }

    let searchMemory;
    try {
      const memoryModule = require('./src/memory.js');
      searchMemory = memoryModule.searchMemory;
    } catch (err) {
      log.warn?.(`[reflect-and-adapt] Memory module unavailable: ${err.message}`);
    }

    let evaluateTurn;
    try {
      const evaluatorModule = require('./src/evaluator.js');
      evaluateTurn = evaluatorModule.evaluateTurn;
    } catch (err) {
      log.error?.(`[reflect-and-adapt] Failed to load src/evaluator.js: ${err.message}`);
    }

    const insertConversation = db.prepare(`
      INSERT OR IGNORE INTO conversations (session_id, role, text, timestamp, message_id)
      VALUES (?, ?, ?, ?, ?)
    `);

    log.info?.('[reflect-and-adapt] Started.');

    const stmtResuface = db.prepare(`
      UPDATE proposals
      SET status='PENDING', presented_at=NULL
      WHERE status='PRESENTED'
        AND presented_at < datetime('now', '-48 hours')
    `);
    const stmtMarkPresented = db.prepare(`
      UPDATE proposals SET status='PRESENTED', presented_at=datetime('now') WHERE id=?
    `);

    // ── Hook: before_agent_start ──────────────────────────────────────────────
    api.on('before_agent_start', (event, ctx) => {
      try {
        // Re-surface proposals that were shown 48h+ ago but never acted on
        const resurfaced = stmtResuface.run();
        if (resurfaced.changes > 0) {
          log.info?.(`[reflect-and-adapt] Re-surfaced ${resurfaced.changes} stale PRESENTED proposal(s) → PENDING.`);
        }

        const pending = db.prepare(`SELECT * FROM proposals WHERE status='PENDING' ORDER BY created_at ASC`).all();
        if (pending.length === 0) return;

        const summaryLines = pending.map((p, i) =>
          `${i + 1}. [${p.id}] ${p.risk_level || 'UNKNOWN'} risk · ${p.proposal_type} → \`${p.target_file}\`\n` +
          `   Rationale: ${p.rationale}\n` +
          `   Proposed change:\n${(p.proposed_change || '').split('\n').map(l => `     ${l}`).join('\n')}`
        ).join('\n\n---\n\n');

        const contextBlock = `[REFLECT_AND_ADAPT: ${pending.length} PENDING PROPOSAL(S)]
Your background analysis agent has queued ${pending.length} workspace improvement suggestion(s) for review.

${summaryLines}

INSTRUCTIONS:
1. In your greeting, mention you have ${pending.length} suggestion(s) to review and ask if the user wants to go through them now.
2. For each proposal, present the rationale and proposed change, then ask the user to approve or reject.
3. After each user decision, immediately run the corresponding bash command before moving to the next proposal:
   - Approved: node skills/proposals/manage-proposals.js approve <id>
   - Rejected:  node skills/proposals/manage-proposals.js reject <id> [reason]
4. For each APPROVED proposal, apply the proposed change to the target file.
[/REFLECT_AND_ADAPT]`;

        // Mark as PRESENTED — won't re-inject next session unless 48h pass with no decision
        db.transaction(() => pending.forEach(p => stmtMarkPresented.run(p.id)))();
        log.info?.(`[reflect-and-adapt] Injected and marked ${pending.length} proposal(s) as PRESENTED.`);
        return { prependContext: contextBlock };
      } catch (err) {
        log.warn?.(`[reflect-and-adapt] Failed to inject proposals: ${String(err)}`);
      }
    });

    // ── Hook: before_prompt_build ─────────────────────────────────────────────
    api.on('before_prompt_build', async (event, ctx) => {
      const userPrompt = event?.prompt || '';

      // Intercept /adapt — run Cortex immediately, bypassing cooldown
      if (userPrompt.includes('/adapt') && userPrompt.replace(/\[.*?\]/g, '').trim() === '/adapt') {
        if (typeof runCortexCycle === 'function') {
          log.info?.('[reflect-and-adapt] /adapt — running Cortex cycle immediately.');
          runCortexCycle()
            .then(result => {
              log.info?.(`[reflect-and-adapt] /adapt cortex complete: ${result}`);
              setLastCortexRun();
            })
            .catch(err => log.warn?.(`[reflect-and-adapt] /adapt cortex failed: ${err.message}`));
        }
        return { prependContext: '[REFLECT_AND_ADAPT] Cortex adaptation cycle started in the background. Tell the user it\'s running and any proposals will appear at the next session start. [/REFLECT_AND_ADAPT]' };
      }

      if (!userPrompt || userPrompt.length < 10) return;
      if (typeof searchMemory !== 'function') return;

      try {
        const memories = await searchMemory(userPrompt, { limit: 5, threshold: 0.60 });
        if (memories.length === 0) return;

        const memBlock = memories
          .map(m => `- [${m.type}] ${m.content}`)
          .join('\n');

        const contextBlock =
          `[RELEVANT MEMORY]\n` +
          `The following facts about the user were retrieved from episodic memory:\n` +
          `${memBlock}\n` +
          `[/RELEVANT MEMORY]`;

        log.info?.(`[reflect-and-adapt] Injected ${memories.length} memory entry(ies) into context.`);
        return { prependContext: contextBlock };
      } catch (err) {
        log.warn?.(`[reflect-and-adapt] Memory retrieval failed: ${String(err)}`);
      }
    });


    // ── Hook: agent_end ───────────────────────────────────────────────────────
    api.on('agent_end', async (event, ctx) => {
      log.info?.(`[reflect-and-adapt] agent_end fired — success=${event?.success}, messages=${event?.messages?.length ?? 'none'}, sessionKey=${ctx?.sessionKey}`);
      if (!event?.success || !event?.messages?.length) return;

      const sessionId = ctx?.sessionKey || ctx?.sessionId || 'unknown-session';
      let newCount = 0;

      try {
        for (const msg of event.messages) {
          if (!msg || !msg.role) continue;
          if (!['user', 'assistant'].includes(msg.role)) continue;

          const textContent = extractText(msg.content);
          if (!textContent) continue;

          const messageId = msg.id || `fallback-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
          const rawTs = msg.timestamp;
          const timestamp = rawTs
            ? new Date(Number(rawTs) || rawTs).toISOString()
            : new Date().toISOString();

          const result = insertConversation.run(sessionId, msg.role, textContent, timestamp, messageId);
          if (result.changes > 0) newCount++;
        }

        if (newCount > 0) {
          log.info?.(`[reflect-and-adapt] Inserted ${newCount} new messages into conversations.`);
        }

        // ── Fire-and-forget evaluation of last 3 turns ────────────────────────
        if (typeof evaluateTurn === 'function' && newCount > 0) {
          const pairs = getLastNPairs(3);
          for (const pair of pairs) {
            evaluateTurn({
              userMessage: pair.userMessage,
              assistantResponse: pair.assistantResponse,
              sessionId: pair.sessionId || sessionId,
              turnTimestamp: pair.timestamp || new Date().toISOString(),
            }).catch(err => log.warn?.(`[evaluator] Background evaluation error: ${err.message}`));
          }
        }

        // ── Fire-and-forget Cortex cycle if cooldown has elapsed ──────────────
        if (typeof runCortexCycle === 'function' && newCount > 0) {
          const msSinceLastRun = Date.now() - getLastCortexRunMs();
          if (msSinceLastRun >= CORTEX_COOLDOWN_MS) {
            const hrsSince = (msSinceLastRun / 3_600_000).toFixed(1);
            log.info?.(`[reflect-and-adapt] Cooldown elapsed (${hrsSince}h). Running Cortex in background.`);
            runCortexCycle()
              .then(output => {
                const preview = typeof output === 'string' ? output.substring(0, 150) : 'complex output';
                log.info?.(`[reflect-and-adapt] Cortex cycle complete. Preview: ${preview}`);
              })
              .catch(err => log.warn?.(`[reflect-and-adapt] Cortex execution failed: ${err.message}`))
              .finally(() => setLastCortexRun());
          } else {
            log.info?.(`[reflect-and-adapt] Cortex cooldown active (${(msSinceLastRun / 3_600_000).toFixed(1)}h / ${process.env.CORTEX_COOLDOWN_HOURS || 2}h). Skipping.`);
          }
        }
      } catch (err) {
        log.warn?.(`[reflect-and-adapt] Failed to process messages: ${String(err)}`);
      }
    });
  }
};
