<script lang="ts">
	import { onMount } from 'svelte';
	import {
		createCanonicalFromNoteMention,
		extractNoteSource,
		getNoteReviewSummary,
		getNoteSource,
		importNotesJsonl,
		importPeopleCsv,
		listLocations,
		listOrganizations,
		listPeople,
		manuallyMatchNoteMention,
		reviewNoteEventDraft,
		reviewNoteMention,
		scanNoteSources,
		updateNoteEventDraft,
		updateNoteMention,
		type Location,
		type NoteEventDraft,
		type NoteMention,
		type NoteSourceDetail,
		type NoteSourceReviewSummary,
		type Organization,
		type Person
	} from '$lib/api';

	type EntityType = 'Person' | 'Organization' | 'Location';
	type EntityResult = { id: string; label: string; subtitle: string };
	const pendingStatuses = new Set(['Pending', 'Deferred']);
	const eventTypes = [
		'Meeting',
		'One-on-one',
		'Group meeting',
		'Call',
		'Email',
		'Message',
		'Intro',
		'Meal',
		'Conference',
		'Event attendance',
		'Work session',
		'Supplier discussion',
		'Personal milestone',
		'Note',
		'Other'
	];

	let summaries = $state<NoteSourceReviewSummary[]>([]);
	let selected = $state<NoteSourceDetail | null>(null);
	let loading = $state(true);
	let busyId = $state<string | null>(null);
	let message = $state('');
	let query = $state('');
	let statusFilter = $state('Needs review');
	let sourceFilter = $state('JSONL');
	let sort = $state('attention');
	let entityFilter = $state('All');
	let eventFilter = $state('Actionable');
	let eventSort = $state('status');
	let jsonlFile = $state<File | null>(null);
	let csvFile = $state<File | null>(null);
	let noteRoot = $state('');
	let searchMention = $state<NoteMention | null>(null);
	let entityQuery = $state('');
	let entityResults = $state<EntityResult[]>([]);
	let searching = $state(false);
	let editingEvent = $state<NoteEventDraft | null>(null);
	let eventForm = $state({
		title: '',
		event_type: 'Note',
		started_on: '',
		summary: '',
		evidence_text: '',
		participant_refs: '',
		organization_refs: '',
		location_refs: ''
	});

	let totals = $derived.by(() => {
		const rows = summaries.filter(
			(row) =>
				sourceFilter === 'All' ||
				(sourceFilter === 'JSONL'
					? isJsonlSource(row.source_type)
					: !isJsonlSource(row.source_type))
		);
		return {
			sources: rows.length,
			pending: rows.reduce((n, row) => n + row.pending_mentions, 0),
			blocked: rows.reduce((n, row) => n + row.needs_review_events, 0),
			ready: rows.reduce((n, row) => n + row.ready_events, 0),
			imported: rows.reduce((n, row) => n + row.imported_events, 0)
		};
	});

	let visibleSources = $derived.by(() => {
		const needle = query.trim().toLowerCase();
		const rows = summaries.filter((row) => {
			const sourceMatches =
				sourceFilter === 'All' ||
				(sourceFilter === 'JSONL'
					? isJsonlSource(row.source_type)
					: !isJsonlSource(row.source_type));
			const statusMatches =
				statusFilter === 'All' ||
				(statusFilter === 'Has ready events'
					? row.ready_events > 0
					: statusFilter === 'Has pending identities'
						? row.pending_mentions > 0
						: statusFilter === 'Has imported events'
							? row.imported_events > 0
							: row.review_status === statusFilter);
			return (
				sourceMatches &&
				statusMatches &&
				(!needle || `${row.heading} ${row.note_date ?? ''}`.toLowerCase().includes(needle))
			);
		});
		return rows.sort((a, b) => {
			if (sort === 'date-asc') return (a.note_date ?? '').localeCompare(b.note_date ?? '');
			if (sort === 'date-desc') return (b.note_date ?? '').localeCompare(a.note_date ?? '');
			if (sort === 'status') return a.review_status.localeCompare(b.review_status);
			const aWork = a.pending_mentions + a.needs_review_events * 5 + a.ready_events * 2;
			const bWork = b.pending_mentions + b.needs_review_events * 5 + b.ready_events * 2;
			return bWork - aWork || (a.note_date ?? '').localeCompare(b.note_date ?? '');
		});
	});

	let pendingMentions = $derived(
		(selected?.mentions ?? []).filter(
			(mention) =>
				pendingStatuses.has(mention.review_status) &&
				(entityFilter === 'All' || mention.entity_type === entityFilter)
		)
	);
	let reviewedMentions = $derived(
		(selected?.mentions ?? []).filter((mention) => !pendingStatuses.has(mention.review_status))
	);
	let visibleEvents = $derived.by(() => {
		const rows = (selected?.event_drafts ?? []).filter((draft) => {
			if (eventFilter === 'All') return true;
			if (eventFilter === 'Actionable')
				return !['Imported', 'Rejected'].includes(draft.review_status);
			return draft.review_status === eventFilter;
		});
		return rows.sort((a, b) => {
			if (eventSort === 'date') return (a.started_on ?? '').localeCompare(b.started_on ?? '');
			if (eventSort === 'confidence') return (a.confidence ?? -1) - (b.confidence ?? -1);
			const rank: Record<string, number> = {
				'Needs review': 0,
				Ready: 1,
				Imported: 2,
				Rejected: 3
			};
			return (rank[a.review_status] ?? 4) - (rank[b.review_status] ?? 4);
		});
	});

	function fail(error: unknown, fallback: string) {
		message = error instanceof Error ? error.message : fallback;
	}

	function isJsonlSource(sourceType: string) {
		return sourceType.toLowerCase().includes('jsonl');
	}

	async function refresh(preferredId?: string) {
		loading = true;
		try {
			summaries = (await getNoteReviewSummary(500)).items;
			const id = preferredId ?? selected?.id;
			if (id && summaries.some((row) => row.id === id)) selected = await getNoteSource(id);
			else {
				const first =
					summaries.find(
						(row) => isJsonlSource(row.source_type) && row.review_status === 'Needs review'
					) ??
					summaries.find((row) => isJsonlSource(row.source_type)) ??
					summaries[0];
				selected = first ? await getNoteSource(first.id) : null;
			}
		} catch (error) {
			fail(error, 'Could not load import status.');
		} finally {
			loading = false;
		}
	}

	async function chooseSource(id: string) {
		busyId = id;
		try {
			selected = await getNoteSource(id);
			message = '';
		} catch (error) {
			fail(error, 'Could not load source.');
		} finally {
			busyId = null;
		}
	}

	async function stageJsonl() {
		if (!jsonlFile) return;
		busyId = 'jsonl';
		message = '';
		try {
			const result = await importNotesJsonl(jsonlFile);
			message = `Staged ${result.staged}; unchanged ${result.skipped}; errors ${result.errors.length}.`;
			await refresh(result.source_ids[0]);
		} catch (error) {
			fail(error, 'JSONL staging failed.');
		} finally {
			busyId = null;
		}
	}

	async function importCsv() {
		if (!csvFile) return;
		busyId = 'csv';
		try {
			const result = await importPeopleCsv(csvFile);
			message = `Created ${result.created}; skipped ${result.skipped}.`;
		} catch (error) {
			fail(error, 'CSV import failed.');
		} finally {
			busyId = null;
		}
	}

	async function reviewMention(
		mention: NoteMention,
		action: 'accept_match' | 'reject' | 'defer',
		candidateId?: string
	) {
		busyId = mention.id;
		try {
			await reviewNoteMention(mention.id, { action, selected_candidate_id: candidateId ?? null });
			await refresh(selected?.id);
		} catch (error) {
			fail(error, 'Mention review failed.');
		} finally {
			busyId = null;
		}
	}

	async function createEntity(mention: NoteMention) {
		const kind = mention.entity_type as EntityType;
		if (!['Person', 'Organization', 'Location'].includes(kind)) return;
		if (
			!globalThis.confirm(`Create a new ${kind.toLowerCase()} named “${mention.normalized_text}”?`)
		)
			return;
		busyId = mention.id;
		try {
			await createCanonicalFromNoteMention(mention.id, {
				entity_type: kind,
				display_name: mention.normalized_text,
				location_label: mention.normalized_text,
				notes: mention.evidence_text
			});
			await refresh(selected?.id);
		} catch (error) {
			fail(error, 'Could not create entity.');
		} finally {
			busyId = null;
		}
	}

	async function editMention(mention: NoteMention) {
		const value = globalThis.prompt('Correct name or label', mention.normalized_text);
		if (!value?.trim()) return;
		busyId = mention.id;
		try {
			await updateNoteMention(mention.id, {
				entity_type: mention.entity_type as EntityType,
				raw_text: value.trim(),
				normalized_text: value.trim(),
				evidence_text: mention.evidence_text
			});
			await refresh(selected?.id);
		} catch (error) {
			fail(error, 'Could not edit mention.');
		} finally {
			busyId = null;
		}
	}

	function openEntitySearch(mention: NoteMention) {
		searchMention = mention;
		entityQuery = mention.normalized_text;
		entityResults = [];
		void searchEntities();
	}

	async function searchEntities() {
		if (!searchMention || !entityQuery.trim()) return;
		searching = true;
		try {
			if (searchMention.entity_type === 'Person') {
				entityResults = (await listPeople({ q: entityQuery, limit: 12 })).map((item: Person) => ({
					id: item.id,
					label: item.display_name,
					subtitle: item.primary_location ?? item.relationship_category
				}));
			} else if (searchMention.entity_type === 'Organization') {
				entityResults = (await listOrganizations({ q: entityQuery, limit: 12 })).map(
					(item: Organization) => ({
						id: item.id,
						label: item.name,
						subtitle: item.industry ?? item.type
					})
				);
			} else {
				entityResults = (await listLocations({ q: entityQuery, limit: 12 })).map(
					(item: Location) => ({
						id: item.id,
						label: item.label ?? item.city ?? 'Unnamed location',
						subtitle: [item.city, item.region, item.country].filter(Boolean).join(', ')
					})
				);
			}
		} catch (error) {
			fail(error, 'Search failed.');
		} finally {
			searching = false;
		}
	}

	async function applyManualMatch(result: EntityResult) {
		if (!searchMention) return;
		busyId = searchMention.id;
		try {
			await manuallyMatchNoteMention(searchMention.id, {
				entity_type: searchMention.entity_type as EntityType,
				entity_id: result.id
			});
			searchMention = null;
			await refresh(selected?.id);
		} catch (error) {
			fail(error, 'Could not apply match.');
		} finally {
			busyId = null;
		}
	}

	function openEventEdit(draft: NoteEventDraft) {
		editingEvent = draft;
		eventForm = {
			title: draft.title,
			event_type: draft.event_type,
			started_on: draft.started_on ?? '',
			summary: draft.summary ?? '',
			evidence_text: draft.evidence_text ?? '',
			participant_refs: draft.participant_refs.join(', '),
			organization_refs: draft.organization_refs.join(', '),
			location_refs: draft.location_refs.join(', ')
		};
	}

	function refs(value: string) {
		return value
			.split(',')
			.map((item) => item.trim())
			.filter(Boolean);
	}

	async function saveEvent() {
		if (!editingEvent) return;
		busyId = editingEvent.id;
		try {
			await updateNoteEventDraft(editingEvent.id, {
				title: eventForm.title,
				event_type: eventForm.event_type,
				started_on: eventForm.started_on || undefined,
				summary: eventForm.summary || null,
				evidence_text: eventForm.evidence_text || null,
				participant_refs: refs(eventForm.participant_refs),
				organization_refs: refs(eventForm.organization_refs),
				location_refs: refs(eventForm.location_refs)
			});
			editingEvent = null;
			await refresh(selected?.id);
		} catch (error) {
			fail(error, 'Could not save event.');
		} finally {
			busyId = null;
		}
	}

	async function reviewEvent(draft: NoteEventDraft, action: 'commit' | 'reject') {
		busyId = draft.id;
		try {
			await reviewNoteEventDraft(draft.id, action);
			await refresh(selected?.id);
		} catch (error) {
			fail(error, 'Event review failed.');
		} finally {
			busyId = null;
		}
	}

	async function runLegacyScan() {
		if (!noteRoot.trim()) return;
		busyId = 'scan';
		try {
			await scanNoteSources({ root_path: noteRoot.trim(), recursive: true, max_files: 500 });
			await refresh();
		} catch (error) {
			fail(error, 'Scan failed.');
		} finally {
			busyId = null;
		}
	}

	async function rerunExtraction() {
		if (!selected) return;
		busyId = 'extract';
		try {
			await extractNoteSource(selected.id);
			await refresh(selected.id);
		} catch (error) {
			fail(error, 'Extraction failed.');
		} finally {
			busyId = null;
		}
	}

	onMount(() => {
		void refresh();
	});
</script>

<svelte:head><title>Import review | Kizuna</title></svelte:head>

<main class="shell">
	<header class="page-head">
		<div>
			<p class="eyebrow">Database-backed queue</p>
			<h1>Import review</h1>
		</div>
		<div class="upload-row">
			<input
				aria-label="JSONL file"
				type="file"
				accept=".jsonl"
				onchange={(e) => (jsonlFile = e.currentTarget.files?.[0] ?? null)}
			/>
			<button disabled={!jsonlFile || busyId === 'jsonl'} onclick={stageJsonl}
				>{busyId === 'jsonl' ? 'Staging…' : 'Stage JSONL'}</button
			>
			<button class="quiet" onclick={() => refresh()} disabled={loading}>Refresh</button>
		</div>
	</header>

	{#if message}<p class="notice">{message}</p>{/if}

	<section class="metrics" aria-label="Import totals">
		<div><strong>{totals.sources}</strong><span>sources</span></div>
		<div class:warn={totals.pending > 0}>
			<strong>{totals.pending}</strong><span>identities pending</span>
		</div>
		<div class:warn={totals.blocked > 0}>
			<strong>{totals.blocked}</strong><span>events blocked</span>
		</div>
		<div><strong>{totals.ready}</strong><span>ready to import</span></div>
		<div class="good"><strong>{totals.imported}</strong><span>imported events</span></div>
	</section>

	<section class="workspace">
		<aside class="queue">
			<div class="filters">
				<input bind:value={query} placeholder="Filter date or title" aria-label="Filter sources" />
				<select bind:value={statusFilter} aria-label="Review status">
					<option>All</option><option>Needs review</option><option>Has ready events</option><option
						>Has pending identities</option
					><option>Has imported events</option><option>Ready</option><option>Imported</option
					><option>Partially imported</option><option>Staged</option><option>No events</option
					><option>Rejected</option>
				</select>
				<select bind:value={sourceFilter} aria-label="Source type"
					><option>JSONL</option><option>Legacy</option><option>All</option></select
				>
				<select bind:value={sort} aria-label="Sort sources"
					><option value="attention">Most attention</option><option value="date-asc">Date ↑</option
					><option value="date-desc">Date ↓</option><option value="status">Status</option></select
				>
			</div>
			<div class="queue-label">
				<span>{visibleSources.length} sources</span><span>identity / event</span>
			</div>
			<div class="source-list">
				{#each visibleSources as row (row.id)}
					<button class:selected={selected?.id === row.id} onclick={() => chooseSource(row.id)}>
						<span
							><strong>{row.note_date ?? row.heading}</strong><small>{row.source_type}</small></span
						>
						<span class="counts"
							><b class:hot={row.pending_mentions > 0}>{row.pending_mentions}</b><b
								class:hot={row.needs_review_events > 0}>{row.needs_review_events}</b
							><em>{row.review_status}{row.ready_events ? ` · ${row.ready_events} ready` : ''}</em
							></span
						>
					</button>
				{:else}<p class="empty">No sources match these filters.</p>{/each}
			</div>
		</aside>

		<section class="review">
			{#if selected}
				<header class="review-head">
					<div>
						<p class="eyebrow">{selected.source_type}</p>
						<h2>{selected.heading}</h2>
					</div>
					<details>
						<summary>Source evidence</summary>
						<pre>{selected.body_text}</pre>
					</details>
				</header>

				<section class="lane">
					<div class="lane-head">
						<div>
							<h3>1 · Resolve identities</h3>
							<p>Match an existing record, create one, correct the text, defer, or reject.</p>
						</div>
						<select bind:value={entityFilter} aria-label="Entity type"
							><option>All</option><option>Person</option><option>Organization</option><option
								>Location</option
							></select
						>
					</div>
					{#each pendingMentions as mention (mention.id)}
						<article class="card">
							<div class="card-head">
								<div>
									<strong>{mention.normalized_text}</strong><span
										>{mention.entity_type} · {mention.confidence === null
											? '—'
											: `${Math.round(mention.confidence * 100)}%`}</span
									>
								</div>
								<span class="pill warn">{mention.review_status}</span>
							</div>
							{#if mention.evidence_text}<p class="evidence">{mention.evidence_text}</p>{/if}
							{#if mention.candidates.length}<div class="candidates">
									{#each mention.candidates.slice(0, 3) as candidate (candidate.id)}<button
											disabled={busyId === mention.id}
											onclick={() => reviewMention(mention, 'accept_match', candidate.id)}
											><strong>{candidate.label}</strong><span
												>{Math.round(candidate.score * 100)}% match</span
											></button
										>{/each}
								</div>{/if}
							<div class="actions">
								<button onclick={() => openEntitySearch(mention)}>Find existing</button><button
									onclick={() => createEntity(mention)}>Create new</button
								><button class="quiet" onclick={() => editMention(mention)}>Correct</button><button
									class="quiet"
									onclick={() => reviewMention(mention, 'defer')}>Defer</button
								><button class="danger" onclick={() => reviewMention(mention, 'reject')}
									>Reject</button
								>
							</div>
						</article>
					{:else}<p class="empty success">No unresolved identities in this view.</p>{/each}
					{#if reviewedMentions.length}<details class="reviewed">
							<summary>{reviewedMentions.length} resolved or rejected identities</summary>
							<div class="resolved-list">
								{#each reviewedMentions as mention (mention.id)}<div>
										<span>{mention.normalized_text}<b>{mention.review_status}</b></span
										>{#if ['Person', 'Organization', 'Location'].includes(mention.entity_type)}<button
												onclick={() => openEntitySearch(mention)}>Re-match</button
											><button onclick={() => reviewMention(mention, 'defer')}>Reopen</button>{/if}
									</div>{/each}
							</div>
						</details>{/if}
				</section>

				<section class="lane">
					<div class="lane-head">
						<div>
							<h3>2 · Review events</h3>
							<p>Correct fields and links, then explicitly import each ready event.</p>
						</div>
						<div class="select-row">
							<select bind:value={eventFilter} aria-label="Event status"
								><option>Actionable</option><option>All</option><option>Needs review</option><option
									>Ready</option
								><option>Imported</option><option>Rejected</option></select
							><select bind:value={eventSort} aria-label="Sort events"
								><option value="status">Status</option><option value="date">Date</option><option
									value="confidence">Lowest confidence</option
								></select
							>
						</div>
					</div>
					{#each visibleEvents as draft (draft.id)}
						<article class="card event">
							<div class="card-head">
								<div>
									<strong>{draft.title}</strong><span
										>{draft.started_on ?? 'No date'} · {draft.event_type} · {draft.confidence ===
										null
											? '—'
											: `${Math.round(draft.confidence * 100)}%`}</span
									>
								</div>
								<span
									class:warn={draft.review_status === 'Needs review'}
									class:good={draft.review_status === 'Imported'}
									class="pill">{draft.review_status}</span
								>
							</div>
							<p>{draft.summary ?? draft.evidence_text ?? 'No summary'}</p>
							{#if draft.review_reasons.length}<p class="reason">
									Review: {draft.review_reasons.join('; ')}
								</p>{/if}
							{#if draft.unresolved_refs.length}<p class="reason">
									Unresolved: {draft.unresolved_refs.join(', ')}
								</p>{/if}
							<div class="refs">
								<span>People: {draft.participant_refs.join(', ') || '—'}</span><span
									>Orgs: {draft.organization_refs.join(', ') || '—'}</span
								><span>Locations: {draft.location_refs.join(', ') || '—'}</span>
							</div>
							{#if !['Imported', 'Rejected'].includes(draft.review_status)}<div class="actions">
									<button onclick={() => openEventEdit(draft)}>Edit event</button><button
										class="primary"
										disabled={busyId === draft.id || draft.unresolved_refs.length > 0}
										title={draft.unresolved_refs.length
											? 'Resolve referenced identities first'
											: ''}
										onclick={() => reviewEvent(draft, 'commit')}>Confirm & import</button
									><button class="danger" onclick={() => reviewEvent(draft, 'reject')}
										>Reject</button
									>
								</div>{/if}
						</article>
					{:else}<p class="empty success">No events match this filter.</p>{/each}
				</section>
			{:else}<p class="empty">{loading ? 'Loading database status…' : 'Select a source.'}</p>{/if}
		</section>
	</section>

	<details class="utilities">
		<summary>Other import tools</summary>
		<div class="utility-grid">
			<form
				onsubmit={(e) => {
					e.preventDefault();
					importCsv();
				}}
			>
				<strong>People CSV</strong><input
					type="file"
					accept=".csv"
					onchange={(e) => (csvFile = e.currentTarget.files?.[0] ?? null)}
				/><button disabled={!csvFile || busyId === 'csv'}>Import CSV</button>
			</form>
			<form
				onsubmit={(e) => {
					e.preventDefault();
					runLegacyScan();
				}}
			>
				<strong>Legacy note scanner</strong><input
					bind:value={noteRoot}
					placeholder="Absolute notes path"
				/><button disabled={!noteRoot || busyId === 'scan'}>Scan</button
				>{#if selected && !isJsonlSource(selected.source_type)}<button
						type="button"
						onclick={rerunExtraction}
						disabled={busyId === 'extract'}>Run extraction</button
					>{/if}
			</form>
		</div>
	</details>
</main>

{#if searchMention}
	<div class="backdrop">
		<section class="modal" role="dialog" aria-modal="true" tabindex="-1">
			<header>
				<div>
					<p class="eyebrow">Manual match</p>
					<h2>Find existing {searchMention.entity_type.toLowerCase()}</h2>
				</div>
				<button class="quiet" onclick={() => (searchMention = null)}>Close</button>
			</header>
			<form
				class="search-row"
				onsubmit={(e) => {
					e.preventDefault();
					searchEntities();
				}}
			>
				<input bind:value={entityQuery} /><button>{searching ? 'Searching…' : 'Search'}</button>
			</form>
			<div class="search-results">
				{#each entityResults as result (result.id)}<button onclick={() => applyManualMatch(result)}
						><strong>{result.label}</strong><span>{result.subtitle}</span></button
					>{:else}<p class="empty">No results. Adjust the query or create a new record.</p>{/each}
			</div>
		</section>
	</div>
{/if}

{#if editingEvent}
	<div class="backdrop">
		<section class="modal event-modal" role="dialog" aria-modal="true" tabindex="-1">
			<header>
				<div>
					<p class="eyebrow">Event correction</p>
					<h2>Edit staged event</h2>
				</div>
				<button class="quiet" onclick={() => (editingEvent = null)}>Close</button>
			</header>
			<form
				class="event-form"
				onsubmit={(e) => {
					e.preventDefault();
					saveEvent();
				}}
			>
				<label>Title<input bind:value={eventForm.title} required /></label>
				<div class="two">
					<label
						>Type<select bind:value={eventForm.event_type}
							>{#each eventTypes as type (type)}<option>{type}</option>{/each}</select
						></label
					><label>Date<input type="date" bind:value={eventForm.started_on} /></label>
				</div>
				<label>Summary<textarea rows="3" bind:value={eventForm.summary}></textarea></label><label
					>Evidence<textarea rows="3" bind:value={eventForm.evidence_text}></textarea></label
				>
				<p class="hint">
					Reference keys are comma-separated and must match the structured JSONL mention keys.
				</p>
				<label>People refs<input bind:value={eventForm.participant_refs} /></label><label
					>Organization refs<input bind:value={eventForm.organization_refs} /></label
				><label>Location refs<input bind:value={eventForm.location_refs} /></label><button
					class="primary"
					disabled={busyId === editingEvent.id}>Save and revalidate</button
				>
			</form>
		</section>
	</div>
{/if}

<style>
	.shell {
		max-width: 1500px;
		margin: 0 auto;
		padding: 1rem 1.25rem 3rem;
	}
	.page-head,
	.review-head,
	.lane-head,
	.modal header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
	}
	.page-head {
		margin-bottom: 0.75rem;
	}
	.eyebrow {
		margin: 0 0 0.15rem;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		font-size: 0.7rem;
		color: var(--muted);
	}
	h1,
	h2,
	h3,
	p {
		margin-top: 0;
	}
	h1 {
		font-size: 1.65rem;
		margin-bottom: 0;
	}
	h2 {
		font-size: 1.2rem;
		margin-bottom: 0;
	}
	h3 {
		font-size: 1rem;
		margin-bottom: 0.1rem;
	}
	.upload-row,
	.actions,
	.search-row {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-wrap: wrap;
	}
	.select-row {
		display: flex;
		gap: 0.35rem;
	}
	button,
	input,
	select,
	textarea {
		border: 1px solid var(--line);
		background: var(--panel-strong);
		color: var(--text);
		padding: 0.48rem 0.6rem;
	}
	button {
		cursor: pointer;
		font-weight: 650;
	}
	button:hover {
		border-color: var(--line-strong);
	}
	button:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	.quiet {
		background: transparent;
	}
	.primary {
		color: var(--panel);
		background: var(--text);
	}
	.danger {
		color: #9e2721;
	}
	.notice {
		border: 1px solid var(--line);
		padding: 0.55rem 0.7rem;
		background: var(--panel);
		margin: 0.5rem 0;
	}
	.metrics {
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		border: 1px solid var(--line);
		margin-bottom: 0.75rem;
	}
	.metrics div {
		padding: 0.65rem 0.8rem;
		border-right: 1px solid var(--line);
		display: flex;
		align-items: baseline;
		gap: 0.45rem;
	}
	.metrics div:last-child {
		border: 0;
	}
	.metrics strong {
		font-size: 1.25rem;
	}
	.metrics span {
		font-size: 0.75rem;
		color: var(--muted);
	}
	.warn {
		color: #a64e00 !important;
	}
	.good {
		color: #237345 !important;
	}
	.workspace {
		display: grid;
		grid-template-columns: 320px minmax(0, 1fr);
		border: 1px solid var(--line);
		min-height: 650px;
	}
	.queue {
		border-right: 1px solid var(--line);
		background: var(--panel);
	}
	.filters {
		padding: 0.6rem;
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.35rem;
		border-bottom: 1px solid var(--line);
	}
	.filters input {
		grid-column: 1/-1;
		min-width: 0;
	}
	.filters select {
		min-width: 0;
	}
	.queue-label {
		display: flex;
		justify-content: space-between;
		padding: 0.4rem 0.65rem;
		font-size: 0.7rem;
		color: var(--muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.source-list {
		max-height: 670px;
		overflow: auto;
	}
	.source-list > button {
		width: 100%;
		border: 0;
		border-top: 1px solid var(--line);
		padding: 0.55rem 0.65rem;
		display: flex;
		justify-content: space-between;
		text-align: left;
		background: transparent;
	}
	.source-list > button.selected {
		background: var(--selection-row-bg);
		box-shadow: inset 3px 0 var(--text);
	}
	.source-list small {
		display: block;
		color: var(--muted);
		font-weight: 400;
		margin-top: 0.1rem;
	}
	.counts {
		display: grid;
		grid-template-columns: 2rem 2rem;
		text-align: right;
	}
	.counts b {
		font-size: 0.8rem;
	}
	.counts em {
		grid-column: 1/-1;
		font-size: 0.66rem;
		color: var(--muted);
		font-style: normal;
		white-space: nowrap;
	}
	.hot {
		color: #a64e00;
	}
	.review {
		min-width: 0;
		padding: 0.75rem;
		background: var(--panel-strong);
	}
	.review-head {
		padding: 0.1rem 0.15rem 0.7rem;
		border-bottom: 1px solid var(--line);
	}
	.review-head details {
		max-width: 50%;
	}
	.review-head pre {
		white-space: pre-wrap;
		max-height: 250px;
		overflow: auto;
		font: inherit;
		font-size: 0.78rem;
		background: var(--panel);
		padding: 0.6rem;
	}
	.lane {
		padding: 0.75rem 0;
		border-bottom: 1px solid var(--line);
	}
	.lane-head p {
		font-size: 0.78rem;
		color: var(--muted);
		margin-bottom: 0;
	}
	.card {
		border: 1px solid var(--line);
		padding: 0.6rem 0.7rem;
		margin-top: 0.45rem;
	}
	.card-head {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
	}
	.card-head > div > span {
		display: block;
		color: var(--muted);
		font-size: 0.74rem;
		margin-top: 0.1rem;
	}
	.pill {
		border: 1px solid currentColor;
		padding: 0.15rem 0.35rem;
		height: max-content;
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.evidence,
	.event > p {
		font-size: 0.82rem;
		margin: 0.4rem 0;
		color: var(--muted);
	}
	.reason {
		color: #a64e00 !important;
	}
	.candidates {
		display: flex;
		gap: 0.35rem;
		margin: 0.45rem 0;
	}
	.candidates button {
		display: flex;
		gap: 0.5rem;
		font-size: 0.76rem;
	}
	.candidates span {
		color: var(--muted);
	}
	.actions {
		margin-top: 0.45rem;
	}
	.actions button {
		font-size: 0.72rem;
		padding: 0.3rem 0.45rem;
	}
	.refs {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		font-size: 0.7rem;
		color: var(--muted);
	}
	.empty {
		padding: 1rem;
		color: var(--muted);
		margin: 0;
	}
	.success {
		border: 1px dashed var(--line);
		margin-top: 0.45rem;
	}
	.reviewed {
		margin-top: 0.55rem;
		font-size: 0.78rem;
	}
	.resolved-list {
		display: flex;
		gap: 0.3rem;
		flex-wrap: wrap;
		margin-top: 0.4rem;
	}
	.resolved-list > div {
		border: 1px solid var(--line);
		display: flex;
		align-items: center;
		gap: 0.3rem;
		padding-left: 0.4rem;
	}
	.resolved-list b {
		margin-left: 0.4rem;
		color: var(--muted);
		font-weight: 400;
	}
	.resolved-list button {
		border-width: 0 0 0 1px;
		font-size: 0.68rem;
		padding: 0.25rem 0.35rem;
	}
	.utilities {
		margin-top: 0.75rem;
		border: 1px solid var(--line);
		padding: 0.65rem;
	}
	.utility-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1rem;
		margin-top: 0.6rem;
	}
	.utility-grid form {
		display: flex;
		gap: 0.4rem;
		align-items: center;
		flex-wrap: wrap;
	}
	.backdrop {
		position: fixed;
		inset: 0;
		background: #0009;
		z-index: 50;
		display: grid;
		place-items: center;
		padding: 1rem;
	}
	.modal {
		background: var(--panel-strong);
		border: 1px solid var(--line-strong);
		width: min(600px, 100%);
		max-height: 90vh;
		overflow: auto;
		padding: 1rem;
		box-shadow: 0 16px 50px #0005;
	}
	.modal header {
		border-bottom: 1px solid var(--line);
		padding-bottom: 0.65rem;
	}
	.search-row {
		margin: 0.75rem 0;
	}
	.search-row input {
		flex: 1;
	}
	.search-results {
		display: grid;
		gap: 0.35rem;
	}
	.search-results button {
		text-align: left;
		display: flex;
		justify-content: space-between;
	}
	.search-results span {
		color: var(--muted);
	}
	.event-form {
		display: grid;
		gap: 0.65rem;
		margin-top: 0.75rem;
	}
	.event-form label {
		display: grid;
		gap: 0.2rem;
		font-size: 0.78rem;
		font-weight: 650;
	}
	.event-form textarea {
		resize: vertical;
	}
	.two {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.65rem;
	}
	.hint {
		font-size: 0.75rem;
		color: var(--muted);
		margin: 0;
	}

	@media (max-width: 900px) {
		.metrics {
			grid-template-columns: repeat(2, 1fr);
		}
		.metrics div {
			border-bottom: 1px solid var(--line);
		}
		.workspace {
			grid-template-columns: 1fr;
		}
		.queue {
			border-right: 0;
			border-bottom: 1px solid var(--line);
		}
		.source-list {
			max-height: 300px;
		}
		.page-head {
			align-items: flex-start;
			flex-direction: column;
		}
		.upload-row {
			width: 100%;
		}
		.review-head details {
			max-width: 100%;
		}
		.utility-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
