'use strict';
const fs = require('fs');
const path = require('path');
const { ChatOpenAI } = require('@langchain/openai');
const { ChatGoogleGenerativeAI } = require('@langchain/google-genai');
const { SystemMessage, HumanMessage } = require('@langchain/core/messages');
const { z } = require('zod');

require('dotenv').config({ path: path.resolve(__dirname, '../.env'), override: false });

const PLUGIN_DIR = path.resolve(__dirname, '..');
const WORKSPACE_ROOT = path.resolve(PLUGIN_DIR, '../../../');

const SCHEMA = (() => {
  try {
    return fs.readFileSync(path.join(PLUGIN_DIR, 'CORTEX_SCHEMA.md'), 'utf-8');
  } catch {
    return '';
  }
})();

function createCortexLlms(maxTokens, tags, metadata) {
  const qwen = new ChatOpenAI({
    model: process.env.QWEN_MODEL || 'qwen-plus',
    apiKey: process.env.QWEN_API_KEY,
    configuration: { baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
    temperature: 0.1,
    maxTokens,
    tags,
    metadata,
  });
  const flash = new ChatGoogleGenerativeAI({
    model: process.env.GOOGLE_MODEL || 'gemini-3.1-pro-preview',
    apiKey: process.env.GOOGLE_API_KEY,
    temperature: 0.1,
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
  const providers = createCortexLlms(4000, ['cortex', 'writer'], { component: 'cortex-writer' });
  for (const [i, { llm, name: providerName }] of providers.entries()) {
    try {
      return await llm.withStructuredOutput(schema, { name }).invoke(messages, options);
    } catch (err) {
      if (i < providers.length - 1) {
        console.warn(`[Writer] ${providerName} failed (${err.message}), falling back to ${providers[i + 1].name}...`);
      } else {
        throw err;
      }
    }
  }
}

// ─── Output Schemas ───────────────────────────────────────────────────────────

const ProposalOutputSchema = z.object({
  proposed_change: z.string()
    .describe('The exact text to add to the file. Prefix with "## Add to <Section>:" if placement matters.'),
  rationale: z.string()
    .describe('1-2 sentence evidence-backed reason for this change'),
  skip: z.boolean()
    .describe('True if the finding does not warrant a change after reviewing the current file content'),
  skip_reason: z.string().optional(),
});

const SkillProposalOutputSchema = z.object({
  skill_name: z.string().describe('Short kebab-case name, e.g. "deploy-staging"'),
  proposed_change: z.string().describe('Full SKILL.md content'),
  rationale: z.string().describe('1-2 sentence evidence-backed reason'),
  skip: z.boolean(),
  skip_reason: z.string().optional(),
});


// ─── File-specific writer instructions ───────────────────────────────────────

const FILE_WRITER_PROMPTS = {
  'SOUL.md': `You write additions to SOUL.md, the assistant's behavioral guidelines.
SOUL.md has sections: Core Truths, Boundaries, Vibe, Continuity.

Rules:
- Write a single bullet or short sentence that fits naturally in the most relevant section
- Match the file's informal, direct tone — no corporate speak
- Format: "## Add to <Section Name>:\\n\\n- <your addition>"
- Set skip=true if the finding is already covered anywhere in the file`,

  'USER.md': `You add factual entries to USER.md, the user's profile.

Rules:
- Each fact as: \`- **Field:** Value\`
- Only facts — never behavioral rules or patterns
- If no section fits, add \`## <Section>\\n\\n\` before the fact
- Set skip=true if the fact is already present in the file`,

  'AGENTS.md': `You add workflow conventions to AGENTS.md.
AGENTS.md covers: memory discipline, group chat rules, tool usage, platform formatting.

Rules:
- Add a bullet or short paragraph to the most relevant existing section
- Match the file's style (headers + bullets, emoji where present)
- Set skip=true if the convention is already documented`,

  'HEARTBEAT.md': `You add periodic tasks to HEARTBEAT.md.

Rules:
- One line per task as a checklist item: \`- [ ] <task description>\`
- Only add if this is clearly a recurring task, not one-off
- Set skip=true if the task is already listed`,

  'IDENTITY.md': `You update IDENTITY.md, which defines the assistant's name, creature type, vibe, and avatar.

Rules:
- Only update if the user explicitly stated a persona preference — never infer
- Update the specific existing field: \`- **Field:** NewValue\`
- Never add new fields
- Set skip=true if this is inferred rather than explicitly requested by the user`,
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function readWorkspaceFile(filename) {
  try {
    const p = path.join(WORKSPACE_ROOT, filename);
    return fs.existsSync(p) ? fs.readFileSync(p, 'utf-8') : null;
  } catch { return null; }
}

function getRiskLevel(findingType, targetFile) {
  if (targetFile === 'IDENTITY.md') return 'HIGH';
  if (targetFile === 'SOUL.md') return 'MEDIUM';
  if (findingType === 'correction' || findingType === 'frustration_pattern') return 'MEDIUM';
  return 'LOW';
}

function sanitizeEvidence(text) {
  return text
    .replace(/```[\s\S]*?```/g, '[code block]')
    .replace(/`[^`]{20,}`/g, '[code]')
    .replace(/\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b/gi, '[email address]')
    .replace(/https?:\/\/\S+/gi, '[url]')
    .replace(/\b(password|token|api[_-]?key|secret|credential)s?\s*[:=]\s*\S+/gi, '[credential]')
    .replace(/\b(curl|wget|sudo|chmod|rm -rf|eval|exec|bash|sh -c)\s+\S+/gi, '[command]')
    .substring(0, 130)
    .trim();
}

function buildEvidenceBlock(evidence) {
  return evidence.map(e => `  - ${sanitizeEvidence(e)}`).join('\n');
}

// ─── Writers ──────────────────────────────────────────────────────────────────

async function writeFileProposal(routedFinding) {
  const { targetFile, proposalType, type, summary, evidence } = routedFinding;

  const fileContent = readWorkspaceFile(targetFile);
  const writerPrompt = FILE_WRITER_PROMPTS[targetFile];

  if (!writerPrompt) {
    console.warn(`[Writer] No writer prompt for ${targetFile} — skipping.`);
    return null;
  }

  const systemPrompt = `${writerPrompt}\n\n---\nMutation rules reference:\n${SCHEMA}`;

  const safeSummary = sanitizeEvidence(summary);
  const userMessage =
    `Finding type: ${type}\n` +
    `Summary: ${safeSummary}\n` +
    `Evidence:\n${buildEvidenceBlock(evidence)}\n\n` +
    `Current ${targetFile} content:\n\`\`\`\n${fileContent || '(empty)'}\n\`\`\`\n\n` +
    `Generate the exact change to make to ${targetFile}.`;

  const result = await invokeStructured(
    ProposalOutputSchema, 'write_proposal',
    [new SystemMessage(systemPrompt), new HumanMessage(userMessage)],
    { runName: `cortex_writer_${targetFile.replace(/[^a-z]/gi, '_')}`, tags: ['cortex', 'writer'] }
  );

  if (result.skip) {
    console.log(`[Writer] Skipped ${targetFile}: ${result.skip_reason}`);
    return null;
  }

  return {
    targetFile,
    proposalType,
    proposedChange: result.proposed_change,
    rationale: result.rationale,
    riskLevel: getRiskLevel(type, targetFile),
  };
}

async function writeSkillProposal(routedFinding) {
  const { type, summary, evidence } = routedFinding;

  const existingSkills = (() => {
    try {
      const skillsDir = path.join(WORKSPACE_ROOT, 'skills');
      if (!fs.existsSync(skillsDir)) return 'No skills directory yet.';
      const entries = fs.readdirSync(skillsDir, { withFileTypes: true });
      return entries.map(e => e.name).join(', ') || 'Empty skills directory.';
    } catch { return 'Could not read skills directory.'; }
  })();

  const systemPrompt =
    `You create new SKILL.md files for an AI assistant.\n` +
    `A skill teaches the assistant a reusable multi-step capability.\n\n` +
    `Existing skills: ${existingSkills}\n\n` +
    `SKILL.md format:\n\`\`\`\n# <Skill Name>\n\n## Trigger\n<When to use — keywords or request patterns>\n\n## Steps\n1. <step>\n...\n\n## Notes\n<Edge cases, caveats>\n\`\`\`\n\n` +
    `Rules:\n- skill_name in kebab-case\n- Steps must be specific and actionable\n- Set skip=true if this is already covered by an existing skill\n\n` +
    `Mutation rules reference:\n${SCHEMA}`;

  const safeSummary = sanitizeEvidence(summary);
  const userMessage =
    `Observed gap: ${safeSummary}\n` +
    `Pattern type: ${type}\n` +
    `Supporting observations:\n${buildEvidenceBlock(evidence)}\n\n` +
    `Write a SKILL.md that documents the procedure for handling this workflow.`;

  const result = await invokeStructured(
    SkillProposalOutputSchema, 'write_skill_proposal',
    [new SystemMessage(systemPrompt), new HumanMessage(userMessage)],
    { runName: 'cortex_writer_skill', tags: ['cortex', 'writer', 'skill'] }
  );

  if (result.skip) {
    console.log(`[Writer] Skipped skill: ${result.skip_reason}`);
    return null;
  }

  return {
    targetFile: `skills/${result.skill_name}/SKILL.md`,
    proposalType: 'new_skill',
    proposedChange: result.proposed_change,
    rationale: result.rationale,
    riskLevel: 'LOW',
  };
}

// ─── Main export ──────────────────────────────────────────────────────────────

async function writeProposals(routedFindings) {
  const results = await Promise.all(
    routedFindings.map(finding =>
      (finding.proposalType === 'new_skill' ? writeSkillProposal(finding) : writeFileProposal(finding))
        .catch(err => {
          console.warn(`[Writer] Failed for ${finding.targetFile || 'skill'}: ${err.message}`);
          return null;
        })
    )
  );
  return results.filter(Boolean);
}

module.exports = { writeProposals };
