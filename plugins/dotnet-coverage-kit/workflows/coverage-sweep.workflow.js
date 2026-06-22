export const meta = {
  name: 'coverage-sweep',
  description: 'Classify every source file against the coverage classification rubric, in parallel chunks. Each chunk writes its full per-file evidence to disk and returns only counts + the rows needing attention, so the main agent can synthesize and critique without holding ~2k rows in context',
  phases: [
    { title: 'Plan', detail: 'partition files into chunks' },
    { title: 'Classify', detail: 'one agent per chunk: classify, write evidence to disk, return a summary' },
  ],
}

// args = { concurrency, files: string[], rubric: string, evidenceDir?: string }
// The CALLER (coverage-init skill) enumerates files, asks the user for `concurrency`, passes the
// rubric, and reads the on-disk evidence afterward. Synthesis + the single cross-project critique
// run at the MAIN agent, NOT here.
const concurrency = Math.max(1, Math.floor(Number(args && args.concurrency) || 3))
const files = (args && Array.isArray(args.files)) ? args.files : []
const rubric = (args && args.rubric) || '(rubric not supplied — read it from the coverage-init skill conventions)'
const evidenceDir = (args && args.evidenceDir) || 'coverage/sweep'

if (!files.length) {
  log('No files to classify — nothing to sweep.')
  return { error: 'empty-file-list' }
}

phase('Plan')
const chunkSize = Math.ceil(files.length / concurrency)
const chunks = []
for (let i = 0; i < files.length; i += chunkSize) chunks.push(files.slice(i, i + chunkSize))
log(`${files.length} files -> ${chunks.length} chunk(s); ${concurrency} run concurrently; evidence -> ${evidenceDir}/chunk-N.json`)

// Each chunk returns ONLY a compact summary. The full per-file rows are written to disk by the
// agent (distinct file per chunk -> no write collision). Trivial files (tiny + obviously
// excluded) are counted, not surfaced — they are collapsed into globs at synthesis time.
const CHUNK_SUMMARY = {
  type: 'object',
  required: ['chunkIndex', 'evidenceFile', 'fileCount', 'trivialCount', 'counts', 'attention'],
  properties: {
    chunkIndex: { type: 'integer' },
    evidenceFile: { type: 'string', description: 'relative path to the JSON file this chunk wrote with ALL its per-file rows' },
    fileCount: { type: 'integer' },
    trivialCount: { type: 'integer', description: 'how many of this chunk\'s files were tiny + obviously-excluded (collapsed, not surfaced)' },
    counts: {
      type: 'array',
      description: 'classification -> count for this chunk',
      items: {
        type: 'object',
        required: ['classification', 'count'],
        properties: { classification: { type: 'string' }, count: { type: 'integer' } },
      },
    },
    attention: {
      type: 'array',
      description: 'ONLY the rows a human/critique should look at: non-trivial low-confidence, god-classes, or surprising calls. NOT every row.',
      items: {
        type: 'object',
        required: ['path', 'classification', 'signal', 'confidence', 'why'],
        properties: {
          path: { type: 'string' },
          classification: { type: 'string' },
          signal: { type: 'string', description: 'rubric signal cited at file:line' },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
          why: { type: 'string', description: 'why it needs a look: god-class | low-confidence | surprising | carve-out' },
          carveOutMethods: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

function classifyPrompt(chunk, i) {
  const file = `${evidenceDir}/chunk-${i + 1}.json`
  return [
    `You are one chunk (#${i + 1}) of a parallel .NET coverage SWEEP. Classify EVERY file in your chunk against the rubric. Read-only on the production source — your ONLY write is the evidence file named below.`,
    '',
    'READ EVERY FILE IN FULL. Do not classify by name/folder alone, do not skip small files, do not sample — small files get misclassified too.',
    '',
    'Classification rubric — each classification is justified by an OBJECTIVE signal in the source, cited at file:line:',
    rubric,
    '',
    'For god-class files (large or dependency-heavy, e.g. >~300 lines or many injected collaborators): classify by the dominant signal (usually integration-scope for IO orchestration) AND list the thin pure-logic methods in carveOutMethods.',
    '',
    'Mark a file `"trivial": true` when it is tiny (~15 lines or fewer) AND high-confidence excluded — e.g. a DTO/record of auto-properties only, an interface, or an enum with no behavior. These will be collapsed into globs later, so they do NOT need to appear in your returned `attention` list.',
    '',
    'Your files:',
    ...chunk.map((f, n) => `  ${n + 1}. ${f}`),
    '',
    `STEP 1 — write the evidence: create the directory if needed and write ALL your per-file rows as a JSON array to \`${file}\`. Each row: { "path", "classification", "signal", "confidence", "trivial", "carveOutMethods", "notes" }.`,
    `STEP 2 — return the compact summary ONLY (do NOT put every row in your reply): { chunkIndex: ${i + 1}, evidenceFile: "${file}", fileCount, trivialCount, counts: [{classification,count}...], attention: [ the non-trivial rows that are low-confidence, god-classes, or surprising — with a \`why\` ] }.`,
  ].join('\n')
}

phase('Classify')
// Barrier: the main agent needs every chunk's evidence on disk before it can synthesize one
// coherent manifest and run the single cross-project critique.
const results = await parallel(chunks.map((chunk, i) => () =>
  agent(classifyPrompt(chunk, i), { label: `classify:chunk-${i + 1}`, phase: 'Classify', schema: CHUNK_SUMMARY })
))

const ok = results.filter(Boolean)
const evidenceFiles = ok.map(r => r.evidenceFile)
const totals = {}
let trivialTotal = 0
let classified = 0
for (const r of ok) {
  classified += r.fileCount || 0
  trivialTotal += r.trivialCount || 0
  for (const c of (r.counts || [])) totals[c.classification] = (totals[c.classification] || 0) + c.count
}
const attention = ok.flatMap(r => r.attention || [])

const missed = files.length - classified
if (missed !== 0) log(`NOTE: ${classified} of ${files.length} files classified (${missed} unaccounted — a chunk may have failed; re-run or sweep the gap).`)
log(`Evidence on disk in ${evidenceFiles.length} file(s); ${trivialTotal} trivial files collapsed; ${attention.length} rows flagged for attention.`)

return {
  filesPlanned: files.length,
  filesClassified: classified,
  chunks: chunks.length,
  concurrency,
  evidenceDir,
  evidenceFiles,
  totals,
  trivialTotal,
  attention,
}
