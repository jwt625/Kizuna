# DevLog 002: Notes Ingestion And Entity Extraction

Date: 2026-04-25
Author: Wentao & Codex

## Implementation Checklist

- [x] 1. Finalize the first implementation slice and execution order
- [x] 2. Add backend staging models for note sources, extraction runs, mentions, match candidates, and review state
- [x] 3. Add backend schemas and API routes for scanning notes, listing drafts, viewing matches, and review updates
- [x] 4. Add a provider abstraction for local LLM and remote OpenAI-compatible fallback
- [x] 5. Implement a local-first extraction service with conservative structured output handling
- [x] 6. Implement deterministic note parsing and normalization for markdown daily notes
- [x] 7. Implement candidate retrieval against existing Kizuna people, organizations, and locations
- [x] 8. Implement a first review-oriented import screen in the frontend
- [x] 9. Add automated backend tests for parsing, staging, retrieval, and review flows
- [x] 10. Run local end-to-end tests on real daily notes samples without disrupting existing services
- [x] 11. Evaluate local model quality and performance
- [x] 12. If local performance is unsatisfying, enable remote DeepSeek fallback through copied environment configuration
- [x] 13. Record implementation notes, remaining gaps, and next-step recommendations in this devlog

## Implementation Status

Last updated: 2026-04-25

Implemented in this round:

- Backend staging models and migration for note sources, extraction runs, entity mentions, event drafts, match candidates, and review decisions
- Backend note parsing, scanning, extraction, candidate retrieval, and review APIs
- Provider abstraction for local OpenAI-compatible inference plus remote OpenAI-compatible fallback
- Import screen updates for notes scanning and review
- Automated tests for note parsing and staged review flow

Validation completed in this round:

- Backend test suite passes
- Mypy passes
- Ruff passes
- Svelte check passes
- Real extraction was run against the `2026-04-01` entry from the daily notes repository

Local runtime evaluation:

- The local LM Studio endpoint was not running on `127.0.0.1:1234` during implementation
- No existing services were interrupted or restarted
- Because the local provider was unavailable, remote DeepSeek fallback was enabled in backend configuration

Observed fallback behavior:

- DeepSeek fallback is reachable and usable
- It required a looser JSON-mode parsing path instead of strict `response_format`
- After prompt tuning and payload normalization, it produced useful staged extraction results on real notes
- Quality is promising but still not canonical-write quality without review, which matches the staged workflow design

Current remaining gaps after this implementation round:

- No canonical commit action yet from staged note entities into final people, organizations, locations, and events
- No background scheduler yet
- No reminder generation yet
- Candidate ranking is still deterministic and lightweight rather than semantic
- Event drafting is usable but still fairly shallow

Recommendation for the next round:

- Add canonical apply/commit actions from staged review to final entities
- Improve event extraction prompts and event-to-entity linking
- Add source provenance links on committed entities
- Revisit local model setup once LM Studio is actively serving a model, then compare local quality against the remote fallback path

## Summary

DevLog 000 established Kizuna as a local-first private relationship intelligence system.

DevLog 001 narrowed that into an MVP centered on people, organizations, locations, events, reminders, and search.

DevLog 002 proposes the first major post-MVP core intelligence loop: turning daily notes into structured relationship memory.

The goal is not to auto-publish AI guesses directly into the canonical database. The goal is to build a local-first ingestion and review workflow that:

- Reads daily notes from local files
- Extracts people, organizations, locations, and event candidates
- Matches extracted mentions against the existing Kizuna database
- Surfaces unresolved or ambiguous candidates to the user
- Lets the user approve, edit, reject, or create new entities
- Commits approved results into the canonical Kizuna records

This should become a core product function because it closes the gap between unstructured memory capture and structured relationship continuity.

## Product Direction

### Why This Matters

Daily notes contain high-value relationship data that is often richer than a CRM entry:

- Who was met
- Where the interaction happened
- What the context was
- What organizations were involved
- What follow-up might be needed later
- How the user feels about the relationship or opportunity

In practice, many important relationship details never make it into a formal system because manual entry is too slow and too interruptive.

If Kizuna can reliably process daily notes and convert them into structured drafts, the system becomes much closer to a true memory layer instead of only a manual database.

### User Decisions Confirmed

The intended direction for this feature is:

- Fully local if possible
- Open-source friendly so others can run it themselves
- Focus first on capturing existing information, not generating reminders yet
- Use staging tables and draft entities for mid-flight results instead of writing directly into canonical records

This means the first version should optimize for portability, inspectability, and user control rather than automation at all costs.

## Local-First LLM Strategy

### Recommendation

The recommended first local setup is:

- Primary local runtime: LM Studio local server
- Primary local model: Qwen3 14B
- Secondary comparison / backup model: Gemma 3 12B
- Optional stronger adjudication model later: larger local model or explicitly configured remote fallback

### Why This Stack

The local machine already has LM Studio installed and is a strong Apple Silicon target.

This makes LM Studio the fastest path to a working local prototype without requiring custom inference infrastructure first.

Qwen3 14B is a strong first choice because:

- It is current and capable
- It is strong on multilingual instruction following
- It should handle English and Chinese names better than many smaller open models
- It is viable for structured extraction tasks on Apple Silicon hardware of this class

Gemma 3 12B is a strong backup because:

- It is designed as a strong single-accelerator open model
- It has a large context window
- It offers a useful second opinion path for extraction or matching prompts

### Remote Fallback

Remote fallback should exist, but it should not be the default path.

Remote use should be optional and explicit, for example:

- User enables remote fallback in settings
- Only low-confidence ambiguous cases use remote adjudication
- Remote mode is disabled by default

This is important both for privacy and for reproducibility by other open-source users.

## Core Workflow Proposal

### Design Principle

This should be a staged review pipeline, not a one-shot import.

The system should separate:

- Source ingestion
- Raw extraction
- Candidate retrieval
- Match resolution
- Human review
- Canonical commit

That separation will make the system easier to debug, safer to trust, and much easier to improve over time.

### End-To-End Flow

#### 1. Source Ingestion

The system scans one or more configured local note sources, beginning with the daily notes repository.

Each source unit should be tracked with:

- Source file path
- Note date
- Section heading or sub-entry identifier
- Raw text excerpt
- Checksum or hash
- Last processed timestamp
- Processing status

At this stage, the system should only detect new or changed note content and stage it for extraction.

#### 2. First LLM Pass: Raw Structured Extraction

The first LLM pass should extract structured draft data from the source text without trying too hard to resolve entities.

The output should include:

- People mentions
- Organization mentions
- Location mentions
- Event candidates
- Relationship hints
- Time expressions
- Confidence scores
- Source spans or quoted snippets

This pass should preserve ambiguity.

For example, if a note says "met Ming at Blue Bottle" or "talked with Stephen," the extractor should return the mention and surrounding evidence, not overconfidently decide which exact canonical entity it is.

#### 3. Deterministic Normalization

After raw extraction, a non-LLM normalization pass should standardize:

- Whitespace and punctuation
- Name casing
- Common abbreviations
- Date resolution using note headers
- Duplicate mentions within the same source unit
- Obvious entity type corrections

This layer should remain simple and inspectable.

#### 4. Candidate Retrieval Against Kizuna

For each extracted mention, the backend should retrieve likely existing entities from the canonical database.

Initial retrieval methods should be:

- Exact normalized match
- Prefix and token match
- Current full-text search
- Organization co-mention
- Location overlap
- Recent event overlap

This can start with existing search infrastructure and targeted SQL queries.

Embeddings or semantic retrieval may become useful later, but they should not be the initial dependency.

#### 5. Second LLM Pass: Match Resolution

The second LLM pass should compare the source evidence and retrieved candidates, then answer questions like:

- Is this likely an existing person in Kizuna?
- Which candidate is the most likely match?
- Is the evidence too weak to match confidently?
- Should this become a new person, organization, location, or event draft instead?

This pass should output structured reasoning fields such as:

- Match decision
- Candidate ranking
- Confidence
- Brief rationale
- Recommended create-new flag

#### 6. Human Review

The user reviews staged results before canonical commit.

Possible review actions:

- Accept proposed match
- Select a different existing candidate
- Create a new entity
- Edit extracted fields
- Reject a draft
- Merge duplicate drafts

This review step is essential. Daily notes are messy, names are ambiguous, and relationship memory is high-value enough that wrong auto-commits would erode trust quickly.

#### 7. Canonical Commit

Once approved, the system writes into the canonical tables:

- `Person`
- `Organization`
- `Location`
- `InteractionEvent`
- Related linking tables and source references

Approved commits should preserve provenance back to the note source so the user can always see where a structured record came from.

## Scope For Version 1

### In Scope

The first version should focus on capturing existing information:

- People
- Organizations
- Locations
- Events
- Basic relationship context
- Source provenance
- Review and approval workflow

### Explicitly Out Of Scope For The First Cut

The first cut should not yet attempt to:

- Auto-generate reminders by default
- Auto-create tasks or TODOs from every note
- Fully automate canonical writes without review
- Require embeddings infrastructure
- Require cloud APIs
- Solve every aliasing and entity resolution edge case

Reminder generation should come after the ingestion pipeline is trusted.

## Data Model Proposal

### Canonical Tables Stay Clean

The existing canonical CRM tables should remain the source of truth for approved entities.

The new notes pipeline should not overload those tables with low-confidence intermediate data.

### New Staging Tables

The first version should add staging tables for draft processing.

Recommended categories:

- `note_sources`
- `note_ingestion_runs`
- `note_extraction_drafts`
- `note_entity_mentions`
- `note_event_drafts`
- `note_match_candidates`
- `note_review_decisions`

The exact schema can still be refined, but the principle is:

- Raw source should be stored
- Draft extraction should be stored
- Candidate matching should be stored
- Human review state should be stored
- Final canonical commit should be traceable

### Why Staging Tables Matter

Staging tables provide:

- Auditability
- Reproducibility
- Safer iteration on prompts and ranking logic
- The ability to rerun extraction without damaging canonical data
- Better frontend review support

This is the right level of structure for an ingestion system that may need multiple passes and frequent prompt tuning.

## Frontend Proposal

### New Surface

This feature likely deserves a dedicated frontend area rather than being squeezed into the existing CSV import UI.

Recommended new surfaces:

- `Notes Import`
- `Extraction Review`
- `Commit Summary`

### Notes Import Screen

This screen should let the user:

- Select a configured local notes source
- Scan for new or changed notes
- Preview what will be processed
- Launch extraction manually
- See current model/runtime configuration

### Extraction Review Screen

This is the core user interface for trust and usability.

A likely layout:

- Left pane: note excerpt with highlighted mentions
- Right pane: people, organizations, locations, and event drafts
- Candidate existing matches with confidence and evidence
- Buttons to accept, edit, create new, reject, or defer

This should feel closer to triage than to a generic CRUD form.

### Commit Summary

After review, the user should see a concise commit summary:

- Existing people matched
- New people created
- Existing organizations matched
- New organizations created
- Events added
- Items skipped
- Items still unresolved

## Triggering And Scheduling

This area needs more discussion and should remain explicitly open for now.

### Option A: Manual Trigger In FE

The user manually starts a scan and extraction pass from the frontend.

Pros:

- Simple
- Predictable
- Easier to trust in the first version
- Easier to debug

Cons:

- Requires user discipline
- Less ambient and automatic

### Option B: Background Scheduled Scan

The backend periodically scans configured notes directories, for example twice per day.

Pros:

- More automatic
- Reduces forgotten imports
- Makes Kizuna feel more alive

Cons:

- Requires job scheduling and state management
- Risks surprising the user
- More complexity around local environments and deployment portability

### Recommended First Approach

The first version should be manual-first.

That means:

- User triggers scan and extraction in the frontend
- System only processes new or changed notes
- Scheduling can be added later as an optional feature

After the workflow is trusted, an optional background scan can be introduced, likely as:

- Disabled by default
- Configurable frequency
- Scan-only first, not auto-commit
- Review still required

## Architecture Notes

### Local Runtime Abstraction

The backend should not hardcode a single model provider.

Instead, it should define a small provider interface that can support:

- LM Studio local server
- Ollama local server later
- Remote OpenAI-compatible provider later

This keeps the pipeline portable and consistent with the local-first goal.

### Structured Output

All extraction and resolution calls should use strict JSON-schema-like structured outputs where possible.

This is especially important for:

- Repeatability
- Parsing reliability
- Testability
- Safer review UIs

### Prompt Versioning

Prompt templates should be versioned and associated with extraction runs.

That will make it possible to compare prompt quality over time and rerun old notes if needed.

## Risks And Failure Modes

### Ambiguous People

Daily notes often use only first names, nicknames, or partial references.

This means the system must avoid overconfident matching.

### Hallucinated Structure

Even good local models can invent details when pushed too hard.

This is why source spans, confidence, and review are essential.

### Over-Automation

If the system creates too many bad entities or noisy events, the user will stop trusting it.

The first version should optimize for precision and reviewability, not recall at any cost.

### Local Runtime Variability

Different users may run different local models and machines.

The pipeline should tolerate some model variability rather than depending on one exact provider behavior.

## Implementation Plan

### Phase 1: Local Extraction Spike

Build a local-only script or backend service that:

- Reads a sample of daily notes
- Calls a local LM Studio model
- Produces structured JSON extraction output
- Writes draft results to files or staging tables

Success criteria:

- Extracts obviously correct people, locations, organizations, and event candidates from real notes
- Produces parseable structured output consistently

### Phase 2: Staging Tables And Backend APIs

Add draft storage and API surfaces for:

- Source ingestion
- Draft listing
- Candidate retrieval
- Match review
- Approval and commit

Success criteria:

- Extraction results survive refresh and can be reviewed later
- Canonical data is not modified before explicit approval

### Phase 3: Review UI

Build the first frontend review flow.

Success criteria:

- User can inspect note excerpts
- User can approve or edit matches
- User can create new entities when needed

### Phase 4: Canonical Commit And Provenance

Write approved drafts into canonical Kizuna entities and preserve source links.

Success criteria:

- Approved results appear in people, organizations, locations, and events views
- Provenance back to source notes remains visible

### Phase 5: Optional Automation And Reminder Generation

Only after the pipeline is trusted:

- Add optional background scanning
- Add reminder and TODO suggestion generation
- Add stronger ranking and retrieval techniques if needed

## Current Recommendation

The next implementation step should be a narrow local-first spike:

- Use LM Studio as the local server
- Start with Qwen3 14B
- Process a real sample of daily notes
- Output strict structured drafts
- Evaluate extraction quality before finalizing schema and UI details

This will give the project concrete evidence about:

- Local model quality
- Extraction schema design
- Match-resolution pain points
- Review UI requirements

## Open Questions

The following questions remain active and should shape the next design discussion:

- Should the source unit be an entire day entry, or smaller sections within a day?
- Should event extraction create one event per paragraph, one event per interaction cluster, or one event only when confidence is high?
- How should the UI represent repeated mentions of the same person across many notes before canonical match is approved?
- Should background scan be a built-in backend scheduler, a CLI command, or both?
- When reminder generation is added later, should it be tied to note review completion or be a separate suggestion pipeline?

## Conclusion

Notes ingestion and entity extraction should become a core Kizuna function.

It fits the product's local-first philosophy, leverages the existing CRM structure, and addresses the most important missing bridge between unstructured lived experience and structured relationship memory.

The right first move is not full automation. The right first move is a trustworthy local-first staged pipeline with strong review surfaces and clean separation between draft intelligence and canonical data.
