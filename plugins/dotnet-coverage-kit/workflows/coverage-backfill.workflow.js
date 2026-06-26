export const meta = {
  name: 'coverage-backfill',
  description: 'Fan out the characterization/spec test backfill across the manifest worklist at a user-chosen parallelism, verify each chunk, then assemble into the working tree',
  phases: [
    { title: 'Plan', detail: 'read the worklist manifest from disk and partition it into chunks' },
    { title: 'Generate', detail: 'one worktree-isolated agent per chunk' },
    { title: 'Verify', detail: 'adversarial check that tests are real, not vacuous' },
    { title: 'Assemble', detail: 'apply patches to the main tree, confirm suite green' },
  ],
}

// args = { concurrency: number, solution: string, worklistManifest: string }
// The CALLER (generate-tests skill) builds the worklist from the manifest, risk-orders it, writes
// it as a JSON array to `worklistManifest` (default coverage/backfill/worklist.json), and asks the
// user for `concurrency` BEFORE invoking. The worklist is NOT passed inline through args — a large
// risk-ordered worklist mis-parses in the tool call. Workflow scripts cannot read disk, so a Plan
// agent reads the manifest and returns the worklist into this script's memory; the script then
// partitions it and inlines each chunk's items into a worktree agent's prompt (worktrees do not see
// the untracked coverage/ manifest, so paths must travel in the prompt, not via a file read). This
// script does not prompt the user.
const concurrency = Math.max(1, Math.floor(Number(args && args.concurrency) || 3))
const solution = (args && args.solution) || ''
const worklistManifest = (args && args.worklistManifest) || 'coverage/backfill/worklist.json'

phase('Plan')
// The script holds no worklist; a Plan agent reads it off disk and returns it. Reading + validating
// happens in the agent (robust structured output), not by typing a big array into the tool call.
const WORKLIST = {
  type: 'object',
  required: ['items'],
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object',
        required: ['file'],
        properties: {
          file: { type: 'string' },
          methods: { type: 'array', items: { type: 'string' } },
          group: { type: 'string' },
          mode: { type: 'string' },
        },
      },
    },
  },
}

const planPrompt = [
  'You are the PLANNING step of a parallel .NET test backfill. You do not write any tests — you only load a worklist. Read-only.',
  `Read the JSON file at \`${worklistManifest}\`. It is a JSON array of worklist items, each shaped { file, methods?, group?, mode? }.`,
  'Return it verbatim as { items: [...] }, preserving order (the caller has already risk-ordered it). Do not add, drop, reorder, or invent items.',
  'If the manifest is missing, empty, or not a JSON array, return { items: [] }.',
].join('\n')

const plan = await agent(planPrompt, { label: 'plan', phase: 'Plan', schema: WORKLIST })
const worklist = (plan && Array.isArray(plan.items)) ? plan.items : []

if (!worklist.length) {
  log(`Empty worklist — \`${worklistManifest}\` is missing, empty, or not a JSON array. Run coverage-init and confirm the manifest has a target set.`)
  return { error: 'empty-worklist', worklistManifest }
}

// One agent per chunk = exactly the parallelism the user chose. Chunking (not one-agent-per-file)
// means one worktree build per agent instead of one per file, and lets a chunk reuse shared
// fixtures. The caller orders the worklist so contiguous items share a service/folder.
const chunkSize = Math.ceil(worklist.length / concurrency)
const chunks = []
for (let i = 0; i < worklist.length; i += chunkSize) chunks.push(worklist.slice(i, i + chunkSize))
log(`${worklist.length} worklist items -> ${chunks.length} chunk(s); ${concurrency} run concurrently`)

const CHUNK_RESULT = {
  type: 'object',
  required: ['chunkIndex', 'filesCovered', 'cannotTest', 'observations', 'patch', 'allGreen'],
  properties: {
    chunkIndex: { type: 'integer' },
    filesCovered: { type: 'array', items: { type: 'string' } },
    cannotTest: {
      type: 'array',
      items: {
        type: 'object',
        required: ['target', 'category', 'reason'],
        properties: {
          target: { type: 'string' },
          category: { type: 'string' },
          reason: { type: 'string' },
        },
      },
    },
    observations: {
      type: 'array',
      items: {
        type: 'object',
        required: ['target', 'whatLookedWrong'],
        properties: { target: { type: 'string' }, whatLookedWrong: { type: 'string' } },
      },
    },
    patch: { type: 'string', description: 'unified diff (git diff --cached) of the test files added in the worktree; empty if nothing was written' },
    allGreen: { type: 'boolean' },
  },
}

const VERDICT = {
  type: 'object',
  required: ['solid', 'problems'],
  properties: {
    solid: { type: 'boolean' },
    problems: {
      type: 'array',
      items: {
        type: 'object',
        required: ['test', 'issue'],
        properties: { test: { type: 'string' }, issue: { type: 'string' } },
      },
    },
  },
}

const conventions = [
  'Read first: .claude/coverage/refs/unit-testing.md (repo overlay), .claude/coverage/refs/coverage-manifest.yml',
  '(categories/exclusions/cannot_test), and the kit base rule on unit testing. Follow them exactly.',
].join(' ')

function generatePrompt(chunk, i) {
  const items = chunk.map((it, n) => `  ${n + 1}. ${it.file}${it.methods ? ' :: ' + it.methods.join(', ') : ''}${it.mode ? ' [' + it.mode + ']' : ''}`).join('\n')
  return [
    `You are backfilling unit tests for ONE chunk (#${i + 1}) of a .NET coverage backfill, working in an isolated git worktree.`,
    conventions,
    '',
    'Cover EVERY item in this chunk — a coverage % is never a stopping condition; the chunk ends only when each item has a test or a cannot_test entry:',
    items,
    '',
    'Rules:',
    '- Existing-at-baseline code -> CHARACTERIZATION via run-capture-fill: write the test with dependencies mocked through interfaces and a placeholder expected value, RUN it, read the ACTUAL value from the run, pin it into the assertion, re-run until green. Never write an expected value by reading the source.',
    '- BATCH the capture: write the whole test class for a file, build once, run that class once, capture all actual values from that single run, then fill. Do not build/run per method.',
    '- PRE-TRIAGE before the loop: if a unit shows a clear untestable signal (direct DateTime.Now/UtcNow, Guid.NewGuid, Random with no injected seam; or it only works against real infrastructure/IO), do NOT force a test — record it in cannotTest and move on.',
    '- New/changed-after-baseline code -> SPEC mode: expected values come from intended behavior, not from running the code.',
    '- PATTERN-REPLICATE: if several items are structurally identical, solve the mock/fixture setup once and replicate the shape across the siblings.',
    '- Do NOT modify production source. Do NOT edit the manifest (return cannot_test entries as data; the assemble step writes them once). Name tests Method_Scenario_Expected and mirror source folder structure.',
    '',
    'When your chunk is green, stage your additions and capture the diff so the assemble step can apply it to the main tree: run `git add -A` then `git diff --cached` and put that text in `patch`.',
    'Return the structured result: filesCovered, cannotTest, observations (suspected latent bugs — frozen, not fixed), patch, allGreen.',
  ].join('\n')
}

function verifyPrompt(gen) {
  return [
    'Adversarially review the generated tests in this chunk for a .NET characterization/spec backfill. Default to flagging when unsure.',
    'Flag any VACUOUS or wrong test: asserts a mock returns exactly what it was configured to return (tautology); asserts nothing meaningful; a characterization assertion that was clearly hand-written rather than captured from a real run; a test that cannot actually exercise the unit.',
    'Here is the chunk patch and what it claims to cover:',
    `filesCovered: ${JSON.stringify(gen.filesCovered)}`,
    'PATCH:',
    gen.patch || '(empty)',
    '',
    'Return { solid, problems[] }. solid=true only if the tests genuinely pin observable behavior.',
  ].join('\n')
}

const generated = await pipeline(
  chunks,
  (chunk, _orig, i) => agent(generatePrompt(chunk, i), {
    label: `gen:chunk-${i + 1}`, phase: 'Generate', isolation: 'worktree', schema: CHUNK_RESULT,
  }),
  (gen, _chunk, i) => {
    if (!gen) return null
    if (!gen.patch) return { ...gen, verify: { solid: true, problems: [] } }
    return agent(verifyPrompt(gen), { label: `verify:chunk-${i + 1}`, phase: 'Verify', schema: VERDICT })
      .then(v => ({ ...gen, verify: v || { solid: false, problems: [{ test: 'all', issue: 'verify agent failed' }] } }))
  }
)

const ok = generated.filter(Boolean)
const flagged = ok.filter(r => r.verify && r.verify.solid === false)
if (flagged.length) log(`${flagged.length} chunk(s) flagged by verify — surfaced in the result for human review.`)

phase('Assemble')
const allPatches = ok.filter(r => r.patch).map(r => r.patch)
const allCannotTest = ok.flatMap(r => r.cannotTest || [])
const assemblePrompt = [
  'You are assembling a parallel .NET test backfill in the MAIN working tree (not a worktree).',
  '1. Apply each chunk patch below with `git apply`. They touch distinct test files, so they should not conflict; report any patch that fails to apply instead of forcing it.',
  '2. Append these cannot_test entries to .claude/coverage/refs/coverage-manifest.yml (dedup by target):',
  JSON.stringify(allCannotTest, null, 2),
  `3. Run the full suite once (dotnet test ${solution || '<solution>'}) and confirm it is green.`,
  '4. Do NOT run coverage-report, do NOT set the baseline, do NOT commit — leave the tree dirty per the promotion gate.',
  '',
  'PATCHES (apply in order):',
  ...allPatches.map((p, n) => `----- patch ${n + 1} -----\n${p}`),
].join('\n')

const assembled = await agent(assemblePrompt, { label: 'assemble', phase: 'Assemble' })

return {
  concurrency,
  chunks: chunks.length,
  itemsPlanned: worklist.length,
  chunkResults: ok.map(r => ({ chunkIndex: r.chunkIndex, filesCovered: r.filesCovered, allGreen: r.allGreen, cannotTest: r.cannotTest, observations: r.observations, verify: r.verify })),
  flaggedChunks: flagged.length,
  cannotTestTotal: allCannotTest.length,
  assembleReport: assembled,
}
