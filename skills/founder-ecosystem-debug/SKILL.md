---
name: founder-ecosystem-debug
description: Use when debugging, extending, or running experiments for the AI Scientist founder ecosystem in this repo. Covers system goals, non-negotiable institutional invariants, environment setup, safe debugging boundaries, baseline definitions, experiment ladder from smoke to soak, and how to analyze outputs without drifting away from the intended research design.
---

# Founder Ecosystem Debug

Use this skill when working on the founder ecosystem system in this repository.

Read these first:
- [docs/current_system_architecture.md](../../docs/current_system_architecture.md)
- [docs/runtime_playbook.md](../../docs/runtime_playbook.md)
- [founder_design.md](../../founder_design.md)

## Project Goal

The research goal is not "make AI Scientist run."

The system studies this hypothesis:
- Under equal compute budgets, a research ecosystem produces a more diverse paper set than a non-ecosystem setup.

Primary evaluation focus:
- Diversity first
- Quantity and acceptance can be secondary diagnostics

Important mechanisms being tested:
- Fund screening filters weak ideas
- Budget gating stops high-cost low-value experiments
- Review feedback shapes founder profiles and future funding
- Internal literature network improves later work quality
- Founder skill evolves over time

## Baselines

Do not redefine these casually.

Baseline 1:
- No research network
- This is the highest-priority baseline after stabilizing the main system

Baseline 2:
- No reviewers and no funds
- Agents can see prior papers and generate papers

Preferred order:
1. Stabilize main ecosystem
2. Run Baseline 1
3. Run Baseline 2

## Non-Negotiable Invariants

These are design constraints, not tuning suggestions.

Do not change any of these unless the owner explicitly asks.

### Multi-agent execution

- Founders must prepare work concurrently
- Heavy tasks must not be serialized by a simple `for` loop
- Message passing is the coordination mechanism
- Orchestrator should schedule and route; it should not become a giant synchronous executor

### Upstream boundary

- Files under `ai_scientist/` are not the first place to tune behavior
- Prefer changing wrappers, prompts, parsing, budgeting, and orchestration in `ai_system/`
- If a change to `ai_scientist/` is truly necessary, sync with the project owner and explain exactly what changed and why
- Upstream changes are high-risk because they can silently change the scientific core rather than the ecosystem shell

### Investor round semantics

- Investor accumulates proposals in `application_queue`
- Investor opens one review round only after all previously funded active projects are finished or dead
- One funding round means one evaluation pass over the queued proposals
- Investor approves at most `k` proposals in that round
- All non-approved proposals are rejected for that round; they do not wait in a GPU queue

### GPU semantics

- GPUs are owned by investors
- GPU allocation is decided at approval time
- GPU cannot be overcommitted
- If there are 4 GPUs, the investor cannot allocate 5
- Once a founder receives GPUs, those GPUs remain assigned until the cycle fully ends or the founder dies
- There is no GPU preemption model
- There is no approved-but-waiting-for-GPU state

### Review semantics

- Peer review is real double-blind LLM review
- Reviewer assignment is currently random over the founder pool, excluding the author
- Review itself is not a placeholder
- Reviewer matching may later become similarity-based, but random matching is the current intended behavior

### Writeup semantics

- Writeup and review are separate institutional steps
- Founder writeup should use the full paper pipeline when possible
- Review belongs to peer review, not to the writeup phase

### Resume semantics

- Budget exhaustion should suspend and resume, not silently restart from scratch
- Checkpoint/resume is part of the model, not a convenience hack

## What Can Change Safely

Usually safe:
- Logging and tracing
- Better file outputs for analysis
- Bug fixes in wrappers and adapters
- Prompt robustness
- Review-result parsing hardening
- Better experiment summaries
- Better failure handling
- More stable environment setup
- Baseline runners added alongside the main system
- In `ai_system/`, prompts, proposal formatting, investor wording, review wording, skill-update wording, and budget numbers can be adjusted if the institutional semantics stay unchanged
- Budget knobs are expected experiment controls, not policy violations

Usually not safe without approval:
- Changing investor round rules
- Changing GPU ownership semantics
- Changing what counts as "project finished"
- Changing baseline definitions
- Changing founder initial budget semantics without explicitly noting the research consequence
- Replacing message-driven flow with direct sequential orchestration
- Editing `ai_scientist/` internals when the same objective can be achieved in `ai_system/`

## Environment Setup

Assume the next operator does **not** inherit the current machine state.

The setup should be reproducible from repository files.

Recommended bootstrap sequence:

1. Create or activate a Python environment.
2. Install Python dependencies from `requirements.txt`.
3. Install the PDF toolchain from `install.txt`.
4. Create a local `.env` with that operator's own API credentials and base URL.
5. Add pricing for the actual model they plan to use.

Recommended commands:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

If they prefer conda, that is also fine. The important point is:
- do not assume this repository comes with a reusable packaged environment
- always reinstall from `requirements.txt`

API config:
- The project expects keys and endpoints in `.env`
- Do not hardcode keys into code or scripts
- The next operator should fill in their own credentials

Minimum `.env` fields:
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL` if using an OpenAI-compatible endpoint
- `S2_API_KEY` optional but useful

Example:

```env
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=https://your-compatible-endpoint/v1
S2_API_KEY=optional_semantic_scholar_key
```

Model pricing:
- Keep `ai_scientist/utils/token_tracker.py` `MODEL_PRICES` aligned with the actual provider prices for the model being used
- Do not assume the next operator will use `qwen3.6-plus`
- If they switch models, they should explicitly add or update that model's:
  - prompt/input price
  - completion/output price
  - cached-input price if applicable
- If this is not updated, budget accounting can silently become wrong

The current `qwen3.6-plus` entry is only an example of the format, not a universal default for future runs

Budget defaults worth knowing:
- founder initial budget: `$1.0`
- investor initial approval tranche: `$10.0`
- investor extra funding tranche: `$15.0`
- investor total budget: `$100.0`
- global ecosystem budget cap: `$100.0`

These budget knobs are legitimate experiment controls:
- `DEFAULT_INITIAL_TOKEN_USD`
- `approval_amount_usd`
- `extra_amount_usd`
- `INVESTOR_TOTAL_BUDGET_USD`
- `GLOBAL_BUDGET_CAP_USD`

Use them to change:
- competition intensity
- survival pressure
- rejection / bankruptcy frequency
- how aggressively weak projects are filtered out

Do not change the institutional rules when you only mean to change competitive pressure.
Usually prefer changing tranche sizes first, before changing round semantics.

The intended behavior of the main system is:
- good projects should get funded, continue through extra funding if justified, and reach paper / literature impact
- weak projects should either fail to raise money, or burn budget and fail to secure continued funding
- this filtering pressure should come mainly from budget settings and outer-layer prompts, not from secretly weakening the institutional rules

PDF toolchain:
- Install the TeX/PDF dependencies from `install.txt`
- Current file:
  - [install.txt](../../install.txt)
- At the time of writing it contains:
  - `sudo apt-get update`
  - `sudo apt-get install -y texlive-latex-base texlive-latex-recommended texlive-latex-extra latexmk`
  - `export PATH=/usr/bin:$PATH`
  - `which pdflatex`
  - `kpsewhich pdflatex.fmt`
- Without this toolchain, full PDF writeup degrades or partially fails

Python packages that have mattered:
- `tiktoken`
- `backoff`
- `anthropic` if using Claude
- `scikit-learn`

## Current System Caveats

Know these before debugging:

- Token usage fields for the current OpenAI-compatible API are available and compatible
- Cost accounting now works for `qwen3.6-plus`, but if a model is missing from `MODEL_PRICES`, cost falls back incorrectly
- Full PDF generation depends on `pdflatex`
- Review parsing can fail if a reviewer returns malformed or null output; harden parsing instead of weakening review semantics
- Literature DB is in-memory unless you explicitly add snapshot persistence

## Required Output Files

Runs should preserve enough evidence for later analysis.

Expected run-level artifacts:
- `orchestrator.log`
- `outer_llm_io.jsonl`
- `outer_events.jsonl`
- `proposals/`
- `reviews/`
- `skill_store/`
- `profile_store/`
- `runtime_state/`

Expected per-founder artifacts when funded:
- `cycle_k/idea.json`
- `cycle_k/worker_input.json`
- `cycle_k/worker_output.json`
- BFTS logs and experiment outputs
- writeup artifacts

If a change drops any of these, treat that as a regression.

## How To Debug

Work from smallest scope to largest.

Before changing code, ask:
- Is this a bug in ecosystem logic, or only in upstream AI Scientist behavior?
- Can this be fixed inside `ai_system/` through prompts, parsing, wrappers, budget knobs, or output formatting?

Default rule:
- change `ai_system/` first
- change `ai_scientist/` only when the shell cannot realistically enforce the intended behavior without it

### Step 1: Static sanity

Run:

```bash
python -m py_compile ai_system/*.py ai_scientist/utils/token_tracker.py
python -m ai_system.test_founder_integration
```

Do this before expensive real runs.

### Step 2: Token/accounting sanity

Run:

```bash
PYTHONPATH=. python scripts/check_token_accounting.py
```

Confirm:
- raw API returns `usage`
- tracker records prompt/completion tokens
- delta cost is not falling back to `$0.005`

### Step 3: Small real smoke

Start with:
- `num_founders=2`
- `num_investors=1`
- `max_projects_per_round=1`
- small BFTS limits

Goal:
- verify ideation
- verify proposal creation
- verify funding decision
- verify experiment wrapper
- verify writeup/review entry

Do not treat "pipeline ran end to end" as success by itself.

The real goal is to see whether:
- promising projects can survive the institutional path
- weak projects are screened out by proposal quality, investor judgment, budget burn, extra funding rejection, or review feedback

### Step 4: Main-system small concurrent run

Then move to:
- `num_founders=4 or 5`
- `num_investors=1`
- `max_projects_per_round=1`
- then `2`

Do not start by scaling both founder count and funding cap aggressively.

### Step 5: Soak

Only after the above is stable:
- `num_founders=5`
- `num_investors=1`
- `max_projects_per_round=2`
- `physical_gpu_count=2`
- `initial_review_delay_sec=180`

When tuning for better behavior, prefer this order:
1. budget knobs
2. proposal / investor / extra-funding / review / skill-update prompts
3. rendering of internal literature in prompts
4. parser hardening and trace improvements
5. only then consider deeper logic changes

## Recommended Experiment Ladder

Use this progression unless there is a strong reason not to.

1. Main system, very small smoke
2. Main system, small concurrent run
3. Main system, soak
4. Baseline 1, small smoke
5. Baseline 1, larger run
6. Baseline 2, small smoke
7. Baseline 2, larger run

Keep investor count at `1` early.
Increase founder count first.
Increase per-round approvals second.
Only then consider multiple investors.

## What To Inspect In Logs

In `orchestrator.log`, check for:
- all founders entering ideation concurrently
- `opening funding round with N queued proposals`
- funded founders only up to the round cap
- no GPU over-allocation
- actual experiment workers launching on separate GPUs
- no second funding round opening while active projects are still running
- review tasks completing without parser crashes

Red flags:
- investor opens a round with only one proposal when many founders should have been preparing
- approved founders falling back to CPU because GPUs were already exhausted
- review crashes from malformed reviewer outputs
- writeup failing because `pdflatex` is missing
- token accounting falling back to flat `$0.005`

## How To Analyze Results

Primary question:
- Did the ecosystem produce more diverse papers than the baseline under comparable compute?

Minimum analysis bundle:
- funded vs rejected proposal comparison
- skill evolution per founder
- review outcomes and reasons
- investor reasons
- internal paper graph growth
- per-founder experiment summaries

Use these files first:
- `outer_llm_io.jsonl`
- `outer_events.jsonl`
- `skill_store/*.json`
- `profile_store/*.json`
- `proposals/**/*.json`
- `reviews/**/*.json`
- per-founder `worker_output.json`

Questions to answer:
- Which proposal styles get funded?
- Which review failures are common?
- How does skill drift after approval vs rejection?
- Are funded ideas less noisy than rejected ideas?
- Does the internal literature start to shape later proposals or papers?
- Does the ecosystem improve diversity, or just narrow toward one style?

Most important interpretation question:
- do the outer-layer LLM steps look like a toy workflow built to satisfy process, or do they contain real academic reasoning and filtering?

Use that question at every stage below.

Specific things to inspect:

- Internal literature retrieval
  - Did the founder actually receive system-internal literature?
  - Did that information plausibly affect ideation, proposal writing, or paper writing?
  - If not, is the issue the presentation format rather than the retrieval itself?
  - Consider whether internal papers should be shown as title only, abstract, structured summary, or fuller text.

- Idea -> proposal -> funding -> extra funding
  - Did the proposal sharpen the idea into something fundable?
  - Did the extra funding request summarize progress and remaining uncertainty credibly?
  - Did investor reasoning actually compare projects and allocate scarce resources?
  - Did this stage behave like a filter, or just like a ceremony?

- Skill evolution
  - Did the skill updates move the founder in a coherent direction?
  - Did approval, rejection, review, and budget pressure produce believable specialization or caution?
  - If not, tune the skill-update prompt and the feedback excerpts before changing the overall lifecycle.

- Outer-layer LLM I/O quality
  - Inspect `outer_llm_io.jsonl` directly
  - Check whether prompts and responses contain academic substance
  - Check whether investor reasoning is comparative rather than generic
  - Check whether reviews diagnose scientific issues rather than only format issues
  - Check whether skill updates say something learned, instead of repeating platitudes

## Reporting Discipline

When handing results back:
- distinguish wrapper bugs from research outcomes
- distinguish missing environment dependencies from system logic failures
- distinguish policy changes from bug fixes
- always state exact run directory
- always state exact founder/investor/cap/GPU configuration

Do not claim a research conclusion from a run contaminated by:
- missing `pdflatex`
- broken token pricing
- malformed review parsing
- incomplete tracing

## When In Doubt

- Preserve institutional semantics
- Add trace outputs instead of weakening the system
- Prefer bug fixes over rule simplification
- Prefer smaller controlled reruns over one giant expensive rerun
- If a possible fix changes the research definition, stop and ask the owner
