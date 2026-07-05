export const meta = {
  name: 'coverage-sweep',
  description: 'Classify every source file against the coverage classification rubric, in parallel chunks. Each chunk writes its full per-file evidence to disk and returns only counts + the rows needing attention, so the main agent can synthesize and critique without holding ~2k rows in context',
  phases: [
    { title: 'Plan', detail: 'read the files manifest from disk and partition it into per-chunk lists' },
    { title: 'Classify', detail: 'one agent per chunk: read its list, classify, write evidence to disk, return a summary' },
  ],
}

// args = { concurrency, filesManifest, rubric, evidenceDir? }
// The CALLER (coverage-init skill) enumerates files and writes them as a JSON array of paths to
// `filesManifest` (default coverage/sweep/files.json), asks the user for `concurrency`, and passes
// the rubric. The file list is NEVER passed inline through args or the script — on a large repo
// that array mis-parses in the tool call and, if inlined into the script, trips the control-char
// guard on the Workflow approval dialog (CRLF from a Windows heredoc). Workflow scripts cannot read
// disk, so a Plan agent reads the manifest and partitions it into on-disk per-chunk lists; each
// Classify agent reads its own list. Synthesis + the single cross-project critique run at the MAIN
// agent, NOT here.
const concurrency = Math.max(1, Math.floor(Number(args && args.concurrency) || 3))
const filesManifest = (args && args.filesManifest) || 'coverage/sweep/files.json'
const rubric = (args && args.rubric) || '(rubric not supplied — read it from the coverage-init skill conventions)'
const evidenceDir = (args && args.evidenceDir) || 'coverage/sweep'

phase('Plan')
// The script holds no file paths; a Plan agent reads the manifest off disk and splits it into
// `concurrency` contiguous per-chunk list files. It returns only the chunk-list paths + counts, so
// no large array ever crosses the args boundary or sits in this script's memory.
const PLAN_RESULT = {
  type: 'object',
  required: ['fileCount', 'chunkFiles'],
  properties: {
    fileCount: { type: 'integer', description: 'total number of paths read from the manifest' },
    chunkFiles: {
      type: 'array',
      description: 'one entry per non-empty chunk list written to disk',
      items: {
        type: 'object',
        required: ['index', 'path', 'count'],
        properties: {
          index: { type: 'integer', description: '1-based chunk number' },
          path: { type: 'string', description: 'relative path to the JSON array of this chunk\'s file paths' },
          count: { type: 'integer' },
        },
      },
    },
  },
}

const planPrompt = [
  'You are the PLANNING step of a parallel .NET coverage sweep. You do not classify anything — you only partition a file list. Read-only except for the per-chunk list files named below.',
  '',
  `Read the JSON file at \`${filesManifest}\`. It is a JSON array of source file paths to classify.`,
  `Split that array into ${concurrency} contiguous, roughly-equal chunks (keep neighbouring paths together so a chunk tends to share a folder/service). If there are fewer than ${concurrency} paths, produce one chunk per path; never emit an empty chunk.`,
  `For each chunk k (1-based), create the directory if needed and write that chunk's paths as a JSON array to \`${evidenceDir}/chunk-k.files.json\` (e.g. \`${evidenceDir}/chunk-1.files.json\`).`,
  '',
  `Return { fileCount: <total paths in the manifest>, chunkFiles: [ { index: k, path: "${evidenceDir}/chunk-k.files.json", count: <paths in that chunk> } ... ] }. The counts across chunkFiles MUST sum to fileCount.`,
  'If the manifest is missing, empty, or not a JSON array, return fileCount: 0 and chunkFiles: [].',
].join('\n')

const plan = await agent(planPrompt, { label: 'plan', phase: 'Plan', schema: PLAN_RESULT })

if (!plan || !plan.chunkFiles || !plan.chunkFiles.length) {
  log(`No files to classify — \`${filesManifest}\` is missing, empty, or not a JSON array. Nothing to sweep.`)
  return { error: 'empty-file-list', filesManifest }
}
log(`${plan.fileCount} files -> ${plan.chunkFiles.length} chunk(s); ${concurrency} run concurrently; lists in ${evidenceDir}/chunk-N.files.json; evidence -> ${evidenceDir}/chunk-N.json`)

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

function classifyPrompt(chunkFile) {
  const file = `${evidenceDir}/chunk-${chunkFile.index}.json`
  return [
    `You are one chunk (#${chunkFile.index}) of a parallel .NET coverage SWEEP. Classify EVERY file in your chunk against the rubric. Read-only on the production source — your ONLY write is the evidence file named below.`,
    '',
    `STEP 0 — get your file list: read the JSON array at \`${chunkFile.path}\` (${chunkFile.count} paths). Those paths ARE your chunk. Classify every one of them.`,
    '',
    'READ EVERY FILE IN FULL. Do not classify by name/folder alone, do not skip small files, do not sample — small files get misclassified too.',
    '',
    'Classification rubric — each classification is justified by an OBJECTIVE signal in the source, cited at file:line:',
    rubric,
    '',
    'TESTABILITY IS PER METHOD, NOT PER FILE. The classification is the file\'s DOMINANT signal for reporting; it is not a claim that the whole file is untestable. For every non-trivial file, also produce a `methodBreakdown`: for each method, { "method", "lines" (e.g. "40-58"), "testable" (bool), "reason" }. A method is testable when its body branches AND its dependencies are mockable/deterministic; untestable only when a specific signal holds (direct infra/IO with no seam, nondeterminism flowing into output). This is what lets a report say "lines 40-58 testable, lines 60-95 not testable because X" instead of a blanket file verdict.',
    '',
    'This applies to whole folders that LOOK untestable, not just god-classes. Controllers (`Controllers/`, `**/Api/**`, ControllerBase/[ApiController]) and Infrastructure projects get a blanket e2e/integration label, but controller actions validate and branch before delegating, and IO orchestrators have pure mapping/decision methods between their calls. READ them for their testable methods. For god-class files (large or dependency-heavy, e.g. >~300 lines or many injected collaborators): same rule, extreme case — classify by dominant signal AND list every deterministic branching method in carveOutMethods.',
    'HARD RULE: every method you mark `testable: true` in a file whose classification is NOT the unit-scope target MUST also appear in `carveOutMethods`. A file/folder-level exclusion may never silently swallow a testable method.',
    'HEURISTIC: a HIGH-COMPLEXITY method (many branches) named like Validate*/Map*/Build*/Calculate*/Convert*/Get*-that-computes is almost always a carve-out even inside an integration-scope class — the branch-heavy decision/mapping logic is exactly the pure part worth unit-testing. Do not exclude a complexity-100+ ValidateAndMap... method wholesale just because its class touches a DbContext; carve it out (or note precisely which lines touch infra vs which are pure).',
    'NONDETERMINISTIC IS DATAFLOW-AWARE, NOT TEXTUAL. Do NOT mark a file nondeterministic just because Guid.NewGuid()/new Stopwatch()/DateTime.Now appears in it. Trace where the value GOES: if its only consumer is a logging/telemetry call (Serilog.Log.*, LogContext.PushProperty, ILogger, a Stopwatch timing an elapsed-ms log line) it does NOT make the method untestable — classify by the real behavior instead (the event->command/document mapping is a target/carve-out; if the body is DbContext-bound it is integration-scope, NOT nondeterministic). A correlation-id/elapsed-ms logged on every handler is a house style. Only mark nondeterministic when the nondeterministic value flows into the returned/emitted/persisted output with no seam.',
    'A BARE (empty carveOutMethods) integration-scope/e2e-scope label on a LARGE file (>~400 lines OR >~10 methods) is NOT allowed without walking its methods first — that is exactly how a big service (e.g. a 2,400-line preset service) loses its pure validator/mapper cluster. Prove each method is genuinely IO-bound before leaving carveOutMethods empty on a large file.',
    '',
    'Mark a file `"trivial": true` when it is tiny (~15 lines or fewer) AND high-confidence excluded — e.g. a DTO/record of auto-properties only, an interface, or an enum with no behavior. Trivial requires ZERO deterministic branching methods; if it has any, it is not trivial. Trivial files will be collapsed into globs later, so they do NOT need to appear in your returned `attention` list or carry a methodBreakdown.',
    '',
    `STEP 1 — write the evidence: create the directory if needed and write ALL your per-file rows as a JSON array to \`${file}\`. Each row: { "path", "classification", "signal", "confidence", "trivial", "carveOutMethods", "methodBreakdown", "notes" }.`,
    `STEP 2 — return the compact summary ONLY (do NOT put every row in your reply): { chunkIndex: ${chunkFile.index}, evidenceFile: "${file}", fileCount, trivialCount, counts: [{classification,count}...], attention: [ the non-trivial rows that are low-confidence, god-classes, or surprising — with a \`why\` ] }.`,
  ].join('\n')
}

phase('Classify')
// Barrier: the main agent needs every chunk's evidence on disk before it can synthesize one
// coherent manifest and run the single cross-project critique.
const results = await parallel(plan.chunkFiles.map((chunkFile) => () =>
  agent(classifyPrompt(chunkFile), { label: `classify:chunk-${chunkFile.index}`, phase: 'Classify', schema: CHUNK_SUMMARY })
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

const missed = plan.fileCount - classified
const complete = missed === 0
if (!complete) log(`INCOMPLETE: ${classified} of ${plan.fileCount} files classified (${missed} unaccounted — a chunk likely failed). The coverage-init comprehensiveness gate must NOT proceed: re-sweep the gap before reporting.`)
log(`Evidence on disk in ${evidenceFiles.length} file(s); ${trivialTotal} trivial files collapsed; ${attention.length} rows flagged for attention.`)

return {
  // `complete` is the sweep's contribution to the coverage-init comprehensiveness gate: false
  // means files went unclassified (a chunk failed) and init must re-sweep the gap, not report
  // over the hole. filesPlanned/filesClassified let the caller assert 0 unaccounted.
  complete,
  unaccounted: missed,
  filesPlanned: plan.fileCount,
  filesClassified: classified,
  chunks: plan.chunkFiles.length,
  concurrency,
  evidenceDir,
  evidenceFiles,
  totals,
  trivialTotal,
  attention,
}
