# APEX UNIVERSAL TWO-ZIP AI AGENT PROMPTS

## Permanent Evidence-Handoff Standard for ChatGPT, Codex, Cursor, and All APEX Systems

**Purpose:** One Markdown file containing every reusable prompt required to enforce the same seamless two-ZIP evidence workflow across MLB, NCAA Football, NFL, MMA/UFC, and any future APEX system.

---

# HOW TO USE THIS FILE

For every material APEX execution wave:

1. Use **PROMPT A** with the lead ChatGPT/system agent.
2. Use **PROMPT B** with Codex after physical execution.
3. Use **PROMPT C** with Cursor for independent verification.
4. Use **PROMPT D** with any ChatGPT receiving the two ZIPs.
5. Use **PROMPT E** for the Windows PowerShell download/hash handoff.

Permanent workflow:

```text
EXECUTE
→ PROVE
→ BUILD PRIMARY ZIP
→ BUILD CURSOR_HANDOFF ZIP
→ VERIFY CRC
→ VERIFY INTERNAL SHA256
→ PRINT EXACT SCP COMMAND
→ DOWNLOAD TO WINDOWS DOWNLOADS
→ HASH LOCALLY
→ UPLOAD BOTH TO CHATGPT
→ INDEPENDENTLY ADJUDICATE
```

**Two ZIPs. Every material wave. Always.**

---

# PROMPT A — LEAD CHATGPT / SYSTEM-LEAD STANDARD

```text
APEX UNIVERSAL TWO-ZIP EVIDENCE HANDOFF STANDARD
SYSTEM: <SYSTEM>
MISSION: <MISSION>

You are the lead ChatGPT system agent responsible for this APEX execution wave.

Every material execution on the DigitalOcean droplet must finish with exactly TWO evidence packages:

1. PRIMARY EVIDENCE ZIP
2. CURSOR / INDEPENDENT HANDOFF ZIP

This applies to MLB, NCAA Football, NFL, MMA/UFC, every future APEX sport, and every future APEX system.

The purpose is to keep all AI agents informed by the ACTUAL PHYSICAL DROPLET STATE rather than summaries, screenshots, memory, or prose.

============================================================
PRIMARY ZIP
============================================================

The PRIMARY ZIP is the maximum-information adjudication package.

It must answer:

WHAT EXISTED BEFORE THE WORK?
WHAT EXACTLY WAS EXECUTED?
WHAT CHANGED?
WHAT DID NOT CHANGE?
WHAT PROVES THE CLAIMS?
WHAT FAILED?
WHAT REMAINS UNRESOLVED?

Include every relevant category:

mission README
final receipt
pre-state
post-state
canonical authorities
Testing authority
models
artifacts
feature contracts
input contracts
frozen matrices
folds
predictions
PMFs/distributions
proper scores
calibration
negative controls
multiplicity
uncertainty
regeneration
live/backtest parity
T-3
T-2
issuance
grader
Results
website
PDF
PNG
email
ops
systemd
Git
Vercel
Cloudflare
cross-sport isolation
cleanup
code/config
bounded logs
SHA256 manifests

Never rely on a bare PASS flag.

============================================================
CURSOR_HANDOFF ZIP
============================================================

The CURSOR_HANDOFF ZIP is a compact independent reproduction package.

It must answer:

CAN AN INDEPENDENT AI VERIFY OR REPRODUCE THE IMPORTANT CLAIMS WITHOUT TRUSTING MUTABLE LIVE PRODUCTION STATE?

Required structure:

README.md
MANIFEST/
CONTRACTS/
FROZEN_INPUTS/
CODE/
EXPECTED/
REPRODUCED/
RECEIPTS/
SHA256SUMS.txt

The reproducer must actually recompute material claims.

It must not merely read stored PASS flags.

Where applicable it must detect:

wrong engine
wrong artifact hash
wrong feature order
wrong folds
prediction mismatch
PMF mismatch
score mismatch
calibration mismatch
tier mismatch
grade mismatch
duplicate rows
unsupported claims
cross-sport contamination

============================================================
NAMING
============================================================

Use one UTC timestamp for both packages.

PRIMARY:

/tmp/APEX_<SYSTEM>_<MISSION>_<UTC_TIMESTAMP>.zip

CURSOR:

/tmp/APEX_<SYSTEM>_<MISSION>_CURSOR_HANDOFF_<UTC_TIMESTAMP>.zip

Never overwrite an earlier package.

============================================================
SECURITY
============================================================

No ZIP may contain secret values.

Exclude:

API keys
passwords
SSH private keys
OAuth tokens
SMTP credentials
Cloudflare tokens
GitHub tokens
Vercel tokens
DigitalOcean tokens
cookies
session secrets
.env secret values

Allowed:

secret names
presence checks
redacted configs
paths
hashes
status flags

Require:

SECRET_VALUE_INCLUDED_COUNT=0

============================================================
PRODUCTION MUTATION RECEIPT
============================================================

Always record:

PRODUCTION_MUTATION_COUNT=
PRODUCTION_MODEL_WRITE_COUNT=
PRODUCTION_DATABASE_WRITE_COUNT=
PRODUCTION_TIMER_CHANGE_COUNT=
PRODUCTION_SERVICE_CHANGE_COUNT=
PRODUCTION_PUBLICATION_COUNT=
CROSS_SPORT_WRITE_COUNT=

For TESTING-only missions these normally must be zero.

============================================================
CROSS-SPORT ISOLATION
============================================================

Always report:

OWNED_SPORT=
MLB_WRITE_COUNT=
NCAAF_WRITE_COUNT=
NFL_WRITE_COUNT=
MMA_WRITE_COUNT=
FOREIGN_GIT_PATH_STAGED_COUNT=
FOREIGN_GIT_PATH_COMMITTED_COUNT=
FOREIGN_FILE_DELETION_COUNT=

A sport-specific execution must not modify another sport's scientific/runtime state.

============================================================
DATABASE EVIDENCE
============================================================

For every canonical authority include:

ROLE=
PATH=
DATABASE_TYPE=
BYTES=
SHA256=
TABLE_COUNT=
ROW_COUNTS=
SCHEMA_FINGERPRINT=
LOGICAL_CONTENT_FINGERPRINT=
INTEGRITY=
ACTIVE_WRITER=
ACTIVE_READERS=
DATE_COVERAGE=
IDENTITY_COVERAGE=
UNRESOLVED_COUNT=
DUPLICATE_PRIMARY_KEY_COUNT=
ORPHAN_IDENTITY_COUNT=

For SQLite account for WAL/journal state and use a consistent snapshot/checkpoint/backup when required.

For DuckDB respect single-writer requirements and checkpoint before final physical sealing where appropriate.

============================================================
MODEL / EXPERIMENT EVIDENCE
============================================================

For each candidate/champion include:

EXPERIMENT_ID=
ENGINE=
CANDIDATE=
INCUMBENT=
BENCHMARK=
DATASET_ID=
ELIGIBLE_N=
FULL_INPUT_N=
COVERAGE_PCT=
OUTER_FOLDS=
CHRONOLOGY_PASS=
FEATURE_PARITY=
LIVE_BACKTEST_PARITY=
NEGATIVE_CONTROLS=
MULTIPLICITY=
INDEPENDENT_REGENERATION=

Include the correct proper scores.

For binary markets:

LogLoss
Brier
calibration intercept
calibration slope
ECE/reliability

For full distributions:

PMF LogScore
RPS/CRPS where appropriate
PIT/randomized PIT
CDF calibration
tail diagnostics
normalization/coherence

If a candidate loses, preserve the failed evidence.

============================================================
T-3 / T-2 / GRADER / ISSUANCE
============================================================

When relevant prove:

scheduled times
actual start/end
eligible universe
market universe
data hydration
engine identity
feature parity
outcome read count
legacy scorer call count
market snapshot hash
canonical issuance hash
no post-seal recomputation
publication receipt
email receipt
grader timer/service/implementation
as-issued population
official outcomes
grade rows
tier accumulation
Results publication
PDF/PNG generation
email provider receipt
idempotency
next trigger

============================================================
SHARED INFRASTRUCTURE
============================================================

Include when relevant:

Git status before/after
exact owned files staged
exact commit SHA
foreign dirty paths
Vercel deployment identity
public readback
Cloudflare operation/readback
shared publisher lock behavior
cross-sport write count

Never use git add -A across a shared sport worktree.

============================================================
ZIP INTEGRITY
============================================================

Both ZIPs must contain SHA256SUMS.txt.

Both must pass:

ZIP CRC
internal member hash verification
outer ZIP SHA256

Required terminal fields:

PRIMARY_FINAL_ZIP=
PRIMARY_FINAL_SHA256=
PRIMARY_CRC=PASS
PRIMARY_MEMBER_HASHES=PASS
PRIMARY_MEMBER_COUNT=
PRIMARY_BYTES=

CURSOR_FINAL_ZIP=
CURSOR_FINAL_SHA256=
CURSOR_CRC=PASS
CURSOR_MEMBER_HASHES=PASS
CURSOR_MEMBER_COUNT=
CURSOR_BYTES=

SECRET_VALUE_INCLUDED_COUNT=0
CROSS_SPORT_WRITE_COUNT=
HANDOFF_STATUS=PASS

============================================================
DOWNLOAD HANDOFF
============================================================

After both ZIPs exist, print ONE exact Windows PowerShell command downloading both files into:

$env:USERPROFILE\Downloads\

Use the actual droplet IP, exact paths, exact names, and exact UTC timestamp.

Then print Get-FileHash for both local files.

Never give placeholders after the files exist.

Permanent pipeline:

DROPLET
→ WINDOWS DOWNLOADS
→ CHATGPT UPLOAD
→ INDEPENDENT AI REVIEW

Do not end a material execution wave without this two-ZIP handoff.
```

---

# PROMPT B — CODEX TWO-ZIP EVIDENCE PACKAGING DIRECTIVE

```text
APEX — MANDATORY FINAL TWO-ZIP EVIDENCE PACKAGING
SYSTEM: <SYSTEM>
MISSION: <MISSION>

The physical execution is not complete until TWO evidence ZIPs exist, pass integrity checks, and are ready for direct SCP download to Windows.

Do not merely summarize the work.
Do not stop after printing PASS.

Use one UTC timestamp.

PRIMARY:
/tmp/APEX_<SYSTEM>_<MISSION>_<UTC_TIMESTAMP>.zip

CURSOR:
/tmp/APEX_<SYSTEM>_<MISSION>_CURSOR_HANDOFF_<UTC_TIMESTAMP>.zip

============================================================
PRIMARY PACKAGE
============================================================

Build a maximum-information PRIMARY stage containing all relevant evidence:

00_README/
01_FINAL_RECEIPT/
02_PRESTATE/
03_POSTSTATE/
04_AUTHORITIES/
05_TESTING/
06_MODELS/
07_DATA_INPUTS/
08_EXPERIMENTS/
09_SCORES/
10_CALIBRATION/
11_NEGATIVE_CONTROLS/
12_MULTIPLICITY/
13_REGENERATION/
14_LIVE_BACKTEST_PARITY/
15_T3/
16_T2/
17_GRADER/
18_ISSUANCE/
19_RESULTS/
20_WEBSITE/
21_EMAIL/
22_OPS/
23_SYSTEMD/
24_GIT_VERCEL_CLOUDFLARE/
25_CROSS_SPORT_ISOLATION/
26_CLEANUP/
27_CODE_CONFIG/
28_LOGS/
29_MANIFESTS/
30_SHA256/

Only omit genuinely irrelevant categories.

Create:

FINAL_RECEIPT.txt
FINAL_RECEIPT.json

Include exact paths, hashes, counts, timestamps, scores, grades, coverage, controls, multiplicity, regeneration, production mutation counts, cross-sport write counts, and unresolved blockers.

Never write only PASS.

============================================================
CURSOR PACKAGE
============================================================

Build:

README.md
MANIFEST/
CONTRACTS/
FROZEN_INPUTS/
CODE/
EXPECTED/
REPRODUCED/
RECEIPTS/
SHA256SUMS.txt

Include frozen inputs sufficient for independent reproduction.

Do not depend on mutable live Testing state for the final independent check.

Include a real reproducer, preferably:

code/reproduce.py

It must return nonzero on failure and actually recompute material claims.

Run it before packaging and save:

REPRODUCED/reproduce_stdout.txt
REPRODUCED/reproduce_stderr.txt
REPRODUCED/reproduce_receipt.json

============================================================
SECRET SAFETY
============================================================

Do not include secret values.

Require:

SECRET_VALUE_INCLUDED_COUNT=0

============================================================
SHA256 MANIFESTS
============================================================

Create SHA256SUMS.txt for both packages over every other staged file.

Independently verify every manifest entry before zipping.

============================================================
ZIP CREATION + VERIFICATION
============================================================

Build both ZIPs.

Then verify both ZIP CRCs.

Then open the final ZIPs and verify every archived member against SHA256SUMS.txt.

Then compute outer SHA256.

Required:

PRIMARY_CRC=PASS
PRIMARY_MEMBER_HASHES=PASS

CURSOR_CRC=PASS
CURSOR_MEMBER_HASHES=PASS

============================================================
FINAL TERMINAL RECEIPT
============================================================

Print:

============================================================
APEX TWO-ZIP EVIDENCE HANDOFF
============================================================

SYSTEM=<actual>
MISSION=<actual>
UTC_TIMESTAMP=<actual>

PRIMARY_FINAL_ZIP=<exact path>
PRIMARY_FINAL_SHA256=<exact sha256>
PRIMARY_CRC=PASS
PRIMARY_MEMBER_HASHES=PASS
PRIMARY_MEMBER_COUNT=<actual>
PRIMARY_BYTES=<actual>

CURSOR_FINAL_ZIP=<exact path>
CURSOR_FINAL_SHA256=<exact sha256>
CURSOR_CRC=PASS
CURSOR_MEMBER_HASHES=PASS
CURSOR_MEMBER_COUNT=<actual>
CURSOR_BYTES=<actual>

SECRET_VALUE_INCLUDED_COUNT=0
CROSS_SPORT_WRITE_COUNT=<actual>
PRODUCTION_MUTATION_COUNT=<actual>

HANDOFF_STATUS=PASS

============================================================
EXACT POWERSHELL COMMAND
============================================================

After the files exist, print one exact PowerShell command using the real droplet IP and exact generated filenames:

scp root@<ACTUAL_DROPLET_IP>:<PRIMARY_FINAL_ZIP> root@<ACTUAL_DROPLET_IP>:<CURSOR_FINAL_ZIP> "$env:USERPROFILE\Downloads\"; Get-FileHash "$env:USERPROFILE\Downloads\<PRIMARY_FILENAME>" -Algorithm SHA256; Get-FileHash "$env:USERPROFILE\Downloads\<CURSOR_FILENAME>" -Algorithm SHA256

Replace every placeholder.

Do not ask the human to construct the command.

Execution is not finished until both files are downloadable and verified.
```

---

# PROMPT C — CURSOR INDEPENDENT VERIFICATION

```text
APEX CURSOR — INDEPENDENT TWO-ZIP VERIFICATION
SYSTEM: <SYSTEM>
MISSION: <MISSION>

You are the independent verification agent.

Do not trust Codex PASS flags.

Use the sealed CURSOR_HANDOFF package as the primary verification court.

Do not depend on mutable live Testing state for final proof.

First verify:

ZIP CRC
SHA256SUMS.txt
all member hashes
manifest completeness

Then execute the included reproducer.

Prefer:

python3 code/reproduce.py

or the exact README command.

Do not modify expected values to obtain PASS.

Independently verify as applicable:

engine identity
artifact hash
feature contract
feature order
fold chronology
eligible population
full-input population
coverage
predictions
PMFs
proper scores
calibration
negative controls
multiplicity
uncertainty
exact regeneration
position identity
grades
tiers
cross-sport isolation

If a candidate was rejected, independently confirm the rejection numerically.

If a candidate was promoted, independently confirm every promotion gate.

Never conclude:

"receipt says PASS, therefore PASS."

Final receipt:

CURSOR_INDEPENDENT_VERIFICATION=
PACKAGE_CRC=
PACKAGE_MEMBER_HASHES=
REPRODUCER_STATUS=
ENGINE_IDENTITY=
ARTIFACT_HASH_PARITY=
FEATURE_PARITY=
FOLD_CHRONOLOGY=
PREDICTION_PARITY=
PMF_PARITY=
PROPER_SCORE_PARITY=
CALIBRATION_PARITY=
NEGATIVE_CONTROLS=
MULTIPLICITY=
UNCERTAINTY=
GRADE_PARITY=
TIER_PARITY=
CROSS_SPORT_ISOLATION=
UNSUPPORTED_CLAIM_COUNT=
FINAL_DISPOSITION=

List every discrepancy.

Do not rewrite production.
```

---

# PROMPT D — RECEIVING CHATGPT INDEPENDENT ADJUDICATION

```text
APEX CHATGPT — INDEPENDENT TWO-ZIP ADJUDICATION
SYSTEM: <SYSTEM>
MISSION: <MISSION>

You have received:

1. PRIMARY evidence ZIP
2. CURSOR / independent handoff ZIP

Adjudicate the actual work from the files.

Do not rely primarily on screenshots.
Do not rely on prior conversation memory.
Do not rely on Codex saying PASS.

First verify for BOTH ZIPs:

outer SHA256 if supplied
ZIP CRC
member count
SHA256SUMS
every internal member hash

If integrity fails, report it immediately.

Then inspect the PRIMARY evidence:

mission
pre-state
post-state
authorities
Testing
models
feature/input contracts
frozen matrices
folds
predictions
PMFs
proper scores
calibration
negative controls
multiplicity
uncertainty
regeneration
live/backtest parity
T-3
T-2
issuance
grader
Results
website
PDF
PNG
email
ops
systemd
Git/Vercel/Cloudflare
cross-sport isolation
cleanup
code/config
logs
final receipts

Then execute the CURSOR_HANDOFF reproducer where technically possible.

Do not merely inspect stored reproducer output.

For every material claim classify:

PROVED
PROVED_WITH_LIMITATION
NOT_PROVED
CONTRADICTED
NOT_APPLICABLE

Separate:

engine scientific quality
market-superiority evidence
production readiness
operational readiness
publication readiness
prospective/forward evidence

Verify production mutation and cross-sport counts.

For model experiments independently evaluate:

candidate vs incumbent
candidate vs benchmark
identical observations
same proposition
same line
same timestamp
chronology
coverage
proper scores
calibration
negative controls
multiplicity
uncertainty
independent regeneration
live/backtest parity

A candidate that regenerates exactly but loses scientifically is a clean rejection, not a promotion.

Final answer must state:

CURRENT PHYSICAL STATE
WHAT CHANGED
WHAT DID NOT CHANGE
SCIENTIFIC RESULT
OPERATIONAL RESULT
PRODUCTION RESULT
CROSS-SPORT RESULT
EXACT FAILURES
EXACT REMAINING WORK
PROMOTION JUSTIFIED=YES/NO
PRODUCTION SHOULD REMAIN FROZEN=YES/NO

Do not manufacture PASS.
Do not manufacture A.
```

---

# PROMPT E — WINDOWS POWERSHELL DOWNLOAD / HASH HANDOFF

## Multi-line template

```powershell
scp root@<DROPLET_IP>:/tmp/APEX_<SYSTEM>_<MISSION>_<UTC_TIMESTAMP>.zip `
    root@<DROPLET_IP>:/tmp/APEX_<SYSTEM>_<MISSION>_CURSOR_HANDOFF_<UTC_TIMESTAMP>.zip `
    "$env:USERPROFILE\Downloads\"

Get-FileHash "$env:USERPROFILE\Downloads\APEX_<SYSTEM>_<MISSION>_<UTC_TIMESTAMP>.zip" -Algorithm SHA256
Get-FileHash "$env:USERPROFILE\Downloads\APEX_<SYSTEM>_<MISSION>_CURSOR_HANDOFF_<UTC_TIMESTAMP>.zip" -Algorithm SHA256
```

## One-line template

```powershell
scp root@<DROPLET_IP>:/tmp/APEX_<SYSTEM>_<MISSION>_<UTC_TIMESTAMP>.zip root@<DROPLET_IP>:/tmp/APEX_<SYSTEM>_<MISSION>_CURSOR_HANDOFF_<UTC_TIMESTAMP>.zip "$env:USERPROFILE\Downloads\"; Get-FileHash "$env:USERPROFILE\Downloads\APEX_<SYSTEM>_<MISSION>_<UTC_TIMESTAMP>.zip" -Algorithm SHA256; Get-FileHash "$env:USERPROFILE\Downloads\APEX_<SYSTEM>_<MISSION>_CURSOR_HANDOFF_<UTC_TIMESTAMP>.zip" -Algorithm SHA256
```

Current known APEX droplet:

```text
104.131.171.210
```

The executing agent must replace every placeholder with the actual final values.

---

# QUICK HEADER FOR A NEW CHATGPT CONVERSATION

```text
These are an APEX PRIMARY evidence ZIP and matching CURSOR_HANDOFF independent-verification ZIP from the same DigitalOcean execution wave.

Do not trust the prior agent's PASS flags.

Independently verify both ZIP CRCs, outer hashes where supplied, all internal SHA256SUMS entries, inspect the full PRIMARY package, execute the CURSOR_HANDOFF reproducer where applicable, and adjudicate the actual work from the physical evidence.

PRIMARY = maximum-information physical/scientific/operational evidence.

CURSOR_HANDOFF = compact independent reproduction package.

Do not ask me to summarize the files before you inspect them.
```

---

# PERMANENT APEX RULE

```text
TWO ZIP FILES ARE REQUIRED FOR EVERY MATERIAL APEX WAVE.

PRIMARY = MAXIMUM INFORMATION.
CURSOR_HANDOFF = INDEPENDENT REPRODUCTION.

BOTH MUST BE:

HASHED
CRC-VERIFIED
MEMBER-HASH-VERIFIED
SECRET-SAFE
DIRECTLY SCP-DOWNLOADABLE
CHATGPT-UPLOADABLE

EVERY EXECUTING AGENT MUST PRINT THE EXACT WINDOWS POWERSHELL DOWNLOAD COMMAND.

EVERY RECEIVING AGENT MUST INDEPENDENTLY ADJUDICATE THE EVIDENCE.

TWO ZIPS.
EVERY MATERIAL WAVE.
ALWAYS.
```
