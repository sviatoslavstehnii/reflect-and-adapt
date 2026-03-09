const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../.env'), override: false });

const { ChatGoogleGenerativeAI } = require('@langchain/google-genai');
const { z } = require('zod');
const { SystemMessage, HumanMessage } = require('@langchain/core/messages');
const { Client } = require('langsmith');

const db = require('./db');

const SYSTEM_MSG_PATTERN = /A new session was started via \/new or \/reset/;

const langsmithClient = process.env.LANGCHAIN_API_KEY &&
    process.env.LANGCHAIN_API_KEY !== 'your_langsmith_api_key_here'
    ? new Client()
    : null;

// ─── LLM Judge ───────────────────────────────────────────────────────────────

const judgeLlm = new ChatGoogleGenerativeAI({
    model: process.env.GOOGLE_MODEL_MINI || process.env.GOOGLE_MODEL || 'gemini-3-pro-preview',
    apiKey: process.env.GOOGLE_API_KEY,
    temperature: 0,
    maxOutputTokens: 400,
    tags: ['evaluator', 'llm-as-judge'],
    metadata: { component: 'reflect-and-adapt-evaluator' },
});

// ─── Evaluation Schema ────────────────────────────────────────────────────────

const EvaluationSchema = z.object({
    helpfulness: z.number().int().min(1).max(5)
        .describe('How well did the response address the user\'s need? 1=missed entirely, 5=excellent'),
    conciseness: z.number().int().min(1).max(5)
        .describe('Was the response appropriately sized? 1=severely over/under-explained, 5=perfectly calibrated'),
    correction_signal: z.boolean()
        .describe('True if the user corrected, retried, or redirected after this response'),
    frustration_signal: z.boolean()
        .describe('True if the user message shows frustration, impatience, or dissatisfaction'),
    task_completed: z.boolean()
        .describe('True if this exchange reached a satisfactory conclusion'),
    user_satisfaction: z.enum(['positive', 'neutral', 'negative'])
        .describe('Overall satisfaction inferred from tone, word choice, and follow-up intent'),
    response_accepted: z.boolean()
        .describe('True if the user accepted and acted on the response vs. ignoring or pushing back'),
    format_match: z.boolean()
        .describe('True if the response format matched what the user implicitly expected'),
    reasoning: z.string()
        .describe('One sentence explaining the scores, citing specific evidence from the messages'),
});

const judgeWithStructuredOutput = judgeLlm.withStructuredOutput(EvaluationSchema, {
    name: 'score_conversation_turn',
});

const JUDGE_SYSTEM = `You are an objective AI conversation quality evaluator.
You receive one user message and the AI assistant's response.
Score the exchange using the provided criteria.
Be strict and evidence-based — only score on what is explicitly present in the text.
Do not assume positive intent or satisfaction unless the user explicitly signals it.
For user_satisfaction: positive requires explicit approval or enthusiasm; negative requires explicit displeasure; default to neutral when ambiguous.
For format_match: infer expected format from the user's message style and intent.
For conciseness: penalise both over-explanation and under-explanation equally.`;

// ─── Run ID Capture ───────────────────────────────────────────────────────────

function makeRunCapture() {
    let capturedRunId = null;
    const callback = {
        handleChainEnd(_output, runId) { if (runId) capturedRunId = runId; },
        handleLLMEnd(_output, runId) { if (runId) capturedRunId = runId; },
        handleToolEnd(_output, runId) { if (runId) capturedRunId = runId; },
    };
    return { callback, getRunId: () => capturedRunId };
}

// ─── LangSmith Feedback ───────────────────────────────────────────────────────

async function submitFeedback(runId, scores) {
    if (!langsmithClient || !runId) return;
    try {
        const satisfactionScore = { positive: 1, neutral: 0.5, negative: 0 };
        await Promise.all([
            langsmithClient.createFeedback(runId, 'helpfulness', { score: scores.helpfulness / 5, comment: scores.reasoning }),
            langsmithClient.createFeedback(runId, 'conciseness', { score: scores.conciseness / 5 }),
            langsmithClient.createFeedback(runId, 'correction_signal', { score: scores.correction_signal ? 1 : 0 }),
            langsmithClient.createFeedback(runId, 'frustration_signal', { score: scores.frustration_signal ? 1 : 0 }),
            langsmithClient.createFeedback(runId, 'task_completed', { score: scores.task_completed ? 1 : 0 }),
            langsmithClient.createFeedback(runId, 'user_satisfaction', { score: satisfactionScore[scores.user_satisfaction] }),
            langsmithClient.createFeedback(runId, 'response_accepted', { score: scores.response_accepted ? 1 : 0 }),
            langsmithClient.createFeedback(runId, 'format_match', { score: scores.format_match ? 1 : 0 }),
        ]);
        console.log(`[evaluator] Feedback submitted to LangSmith (run: ${runId})`);
    } catch (err) {
        console.warn(`[evaluator] LangSmith feedback upload failed: ${err.message}`);
    }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function evaluateTurn({ userMessage, assistantResponse, sessionId, turnTimestamp }) {
    try {
        if (!userMessage?.trim() || !assistantResponse?.trim()) return;
        if (SYSTEM_MSG_PATTERN.test(userMessage)) return;

        const userSnippet = userMessage.substring(0, 600);
        const assistantSnippet = assistantResponse.substring(0, 600);
        const judgePrompt = `USER MESSAGE:\n${userSnippet}\n\nASSISTANT RESPONSE:\n${assistantSnippet}`;

        const { callback: runCapture, getRunId } = makeRunCapture();

        const scores = await judgeWithStructuredOutput.invoke(
            [new SystemMessage(JUDGE_SYSTEM), new HumanMessage(judgePrompt)],
            {
                runName: 'turn_evaluation',
                callbacks: [runCapture],
                metadata: { sessionId, turnTimestamp },
                tags: ['evaluator', 'turn-score'],
            }
        );

        const runId = getRunId();
        await submitFeedback(runId, scores);

        db.prepare(`
            INSERT INTO scores
              (session_id, turn_timestamp, langsmith_run_id, helpfulness, conciseness,
               correction_signal, frustration_signal, task_completed,
               user_satisfaction, response_accepted, format_match, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `).run(
            sessionId || 'unknown',
            turnTimestamp || new Date().toISOString(),
            runId || null,
            scores.helpfulness,
            scores.conciseness,
            scores.correction_signal ? 1 : 0,
            scores.frustration_signal ? 1 : 0,
            scores.task_completed ? 1 : 0,
            scores.user_satisfaction,
            scores.response_accepted ? 1 : 0,
            scores.format_match ? 1 : 0,
            scores.reasoning,
        );

        console.log(
            `[evaluator] Scored turn — helpfulness: ${scores.helpfulness}/5, ` +
            `correction: ${scores.correction_signal}, frustration: ${scores.frustration_signal}. ` +
            `Reason: ${scores.reasoning}`
        );

        return scores;
    } catch (err) {
        console.warn(`[evaluator] Scoring failed (non-fatal): ${err.message}`);
    }
}

module.exports = { evaluateTurn };
