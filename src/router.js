const db = require('./db');

// Maps finding type → target file + proposal type + minimum occurrence count
// memory_entry findings are handled separately (auto-committed to vector DB, not proposals)
const ROUTING_RULES = [
  { type: 'correction',          minCount: 2, targetFile: 'SOUL.md',      proposalType: 'instruction_edit' },
  { type: 'frustration_pattern', minCount: 2, targetFile: 'SOUL.md',      proposalType: 'instruction_edit' },
  { type: 'user_fact',           minCount: 1, targetFile: 'USER.md',       proposalType: 'user_profile_update' },
  { type: 'missing_capability',  minCount: 2, targetFile: null,            proposalType: 'new_skill' },
  { type: 'workflow_convention', minCount: 2, targetFile: 'AGENTS.md',    proposalType: 'instruction_edit' },
  { type: 'persona_preference',  minCount: 1, targetFile: 'IDENTITY.md',  proposalType: 'instruction_edit' },
  { type: 'periodic_task',       minCount: 2, targetFile: 'HEARTBEAT.md', proposalType: 'instruction_edit' },
];

function routeFindings(findings) {
  const rejected = db.prepare(`
    SELECT target_file, proposal_type, proposed_change FROM proposals WHERE status='REJECTED'
  `).all();

  const routed = [];

  for (const finding of findings) {
    // memory_entry findings go directly to vector DB — skip proposal routing
    if (finding.type === 'memory_entry') {
      routed.push({ ...finding, targetFile: null, proposalType: 'memory_entry' });
      continue;
    }

    const rule = ROUTING_RULES.find(r => r.type === finding.type);
    if (!rule) continue;

    // Evidence threshold
    if (finding.count < rule.minCount) {
      console.log(`[Router] Skip — count ${finding.count} < ${rule.minCount}: ${finding.summary}`);
      continue;
    }

    // Low confidence findings are noise
    if (finding.confidence === 'low') {
      console.log(`[Router] Skip — low confidence: ${finding.summary}`);
      continue;
    }

    // Suppress if a similar rejected proposal already covers this
    const isRejected = rejected.some(r =>
      r.target_file === rule.targetFile &&
      r.proposal_type === rule.proposalType &&
      wordOverlap(r.proposed_change || '', finding.summary) > 0.35
    );
    if (isRejected) {
      console.log(`[Router] Skip — matches rejected proposal: ${finding.summary}`);
      continue;
    }

    // Suppress if a PENDING or PRESENTED proposal already covers this file+type (new_skill exempt)
    if (rule.targetFile) {
      const hasPending = db.prepare(`
        SELECT 1 FROM proposals WHERE status IN ('PENDING','PRESENTED') AND target_file=? AND proposal_type=?
      `).get(rule.targetFile, rule.proposalType);
      if (hasPending) {
        console.log(`[Router] Skip — pending proposal exists for ${rule.targetFile}: ${finding.summary}`);
        continue;
      }
    }

    routed.push({ ...finding, targetFile: rule.targetFile, proposalType: rule.proposalType });
  }

  console.log(`[Router] Routed ${routed.length}/${findings.length} findings.`);
  return routed;
}

// Jaccard-style word overlap for rejection matching (no dependencies)
function wordOverlap(a, b) {
  const sa = new Set(a.toLowerCase().split(/\W+/).filter(Boolean));
  const sb = new Set(b.toLowerCase().split(/\W+/).filter(Boolean));
  const intersection = [...sa].filter(w => sb.has(w)).length;
  return intersection / Math.max(sa.size, sb.size, 1);
}

module.exports = { routeFindings };
