const fs = require('fs');
const path = require('path');
const db = require('./db');
const { runAnalyst } = require('./analyst');
const { routeFindings } = require('./router');
const { writeProposals } = require('./writers');
const { writeMemoryEntries } = require('./memory-writer');

const PLUGIN_DIR = path.resolve(__dirname, '..');
const CORTEX_RUNS_DIR = path.join(PLUGIN_DIR, 'cortex_runs');

if (!fs.existsSync(CORTEX_RUNS_DIR)) {
  fs.mkdirSync(CORTEX_RUNS_DIR, { recursive: true });
}

// ─── Proposal persistence ─────────────────────────────────────────────────────

const insertProposal = db.prepare(`
  INSERT INTO proposals
    (id, status, proposal_type, target_file, proposed_change, rationale, risk_level, created_at)
  VALUES (?, 'PENDING', ?, ?, ?, ?, ?, ?)
`);

const supersede = db.prepare(`
  UPDATE proposals
  SET status='STALE', superseded_at=?, superseded_by=?
  WHERE status='PENDING' AND target_file=? AND proposal_type=?
`);

function saveProposal(proposal) {
  const id = `prop-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`;
  const createdAt = new Date().toISOString();
  db.transaction(() => {
    supersede.run(createdAt, id, proposal.targetFile, proposal.proposalType);
    insertProposal.run(id, proposal.proposalType, proposal.targetFile, proposal.proposedChange, proposal.rationale, proposal.riskLevel, createdAt);
  })();
  console.log(`[Cortex] Saved proposal ${id} → ${proposal.targetFile} [${proposal.proposalType}]`);
  return id;
}

// ─── Pipeline ─────────────────────────────────────────────────────────────────

async function runCortexCycle() {
  console.log('[Cortex] Starting pipeline...');
  const pipelineLog = { timestamp: new Date().toISOString(), stages: {} };

  // Stage 1 — Analyst: extract structured findings from conversations + scores
  const { findings, analysis_notes } = await runAnalyst();
  pipelineLog.stages.analyst = { finding_count: findings.length, findings, analysis_notes };

  if (findings.length === 0) {
    console.log('[Cortex] No findings — cycle complete.');
    savePipelineLog(pipelineLog);
    return 'No findings from analyst.';
  }

  // Stage 2 — Router: filter by thresholds, suppress rejected/pending duplicates
  const routed = routeFindings(findings);
  pipelineLog.stages.router = { routed_count: routed.length, routed };

  if (routed.length === 0) {
    console.log('[Cortex] No findings passed routing — cycle complete.');
    savePipelineLog(pipelineLog);
    return 'Findings detected but none passed routing thresholds.';
  }

  // Split: memory_entry findings → vector DB; everything else → file proposals
  const memoryFindings = routed.filter(f => f.proposalType === 'memory_entry');
  const proposalFindings = routed.filter(f => f.proposalType !== 'memory_entry');

  // Stage 3 — Run file writers and memory writer in parallel
  const [proposals, memoriesSaved] = await Promise.all([
    proposalFindings.length > 0
      ? writeProposals(proposalFindings)
      : Promise.resolve([]),
    memoryFindings.length > 0
      ? writeMemoryEntries(memoryFindings).catch(err => {
          console.warn(`[Cortex] Memory writer failed: ${err.message}`);
          return 0;
        })
      : Promise.resolve(0),
  ]);

  pipelineLog.stages.writers = {
    proposal_count: proposals.length,
    proposals,
    memories_saved: memoriesSaved,
  };

  // Stage 4 — Persist proposals (memory entries already saved by memory-writer)
  const savedIds = proposals.map(saveProposal);
  pipelineLog.stages.saved = savedIds;

  savePipelineLog(pipelineLog);

  const summary =
    `Analyst: ${findings.length} finding(s) → ` +
    `Router: ${routed.length} routed (${memoryFindings.length} memory, ${proposalFindings.length} proposals) → ` +
    `Writers: ${proposals.length} proposal(s) saved, ${memoriesSaved} memory entry(ies) committed.`;

  console.log(`[Cortex] Cycle complete. ${summary}`);
  return summary;
}

function savePipelineLog(log) {
  try {
    const ts = new Date().toISOString().replace(/\.\d{3}Z$/, '').replace('T', '_').replace(/:/g, '-');
    fs.writeFileSync(path.join(CORTEX_RUNS_DIR, `run_${ts}.json`), JSON.stringify(log, null, 2));
  } catch (err) {
    console.warn(`[Cortex] Could not save pipeline log: ${err.message}`);
  }
}

if (require.main === module) {
  runCortexCycle().catch(console.error);
}

module.exports = { runCortexCycle };
