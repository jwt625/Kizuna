<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import {
		createCanonicalFromNoteMention,
		extractNoteSource,
		getNoteProviderHealth,
		getNoteSource,
		importPeopleCsv,
		listNoteSources,
		reviewNoteMention,
		scanNoteSources,
		updateNoteMention,
		type NoteMention,
		type NoteProviderHealth,
		type NoteSource,
		type NoteSourceDetail
	} from '$lib/api';

	type MentionType = 'Person' | 'Organization' | 'Location' | 'Event';
	type ModalMode = 'create' | 'edit-type';
	type FoldState = Record<string, boolean>;

	const mentionTypes: MentionType[] = ['Person', 'Organization', 'Location', 'Event'];
	const pendingStatuses = new Set(['Pending', 'Deferred']);

	let file = $state<File | null>(null);
	let uploading = $state(false);
	let error = $state('');
	let result = $state<{ created: number; skipped: number; errors: string[] } | null>(null);

	let noteRootPath = $state('/Users/wentaojiang/Documents/GitHub/daily-notes');
	let providerHealth = $state<NoteProviderHealth | null>(null);
	let sources = $state<NoteSource[]>([]);
	let selectedSourceId = $state<string | null>(null);
	let selectedSource = $state<NoteSourceDetail | null>(null);
	let scanSummary = $state<{ files_seen: number; sections_seen: number; created: number; updated: number; unchanged: number } | null>(null);
	let scanning = $state(false);
	let loadingSources = $state(false);
	let extracting = $state(false);
	let reviewingMentionId = $state<string | null>(null);
	let notesError = $state('');
	let pendingFoldState = $state<FoldState>({});
	let reviewedFoldState = $state<FoldState>({});

	let modalOpen = $state(false);
	let modalMode = $state<ModalMode>('create');
	let activeMention = $state<NoteMention | null>(null);
	let mentionEditForm = $state({
		entity_type: 'Person' as MentionType,
		raw_text: '',
		normalized_text: '',
		evidence_text: ''
	});
	let createForm = $state({
		entity_type: 'Person' as MentionType,
		display_name: '',
		given_name: '',
		family_name: '',
		primary_location: '',
		relationship_summary: '',
		how_we_met: '',
		notes: '',
		organization_type: 'Other',
		industry: '',
		location_label: '',
		location_address_line: '',
		location_city: '',
		location_region: '',
		location_country: '',
		location_type: 'Other',
		event_title: '',
		event_type: 'Note',
		event_summary: '',
		event_started_at: '',
		event_ended_at: ''
	});

	async function submitImport() {
		if (!file) return;
		uploading = true;
		error = '';
		try {
			result = await importPeopleCsv(file);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Import failed.';
		} finally {
			uploading = false;
		}
	}

	async function loadProviderHealth() {
		try {
			providerHealth = await getNoteProviderHealth();
		} catch (err) {
			notesError = err instanceof Error ? err.message : 'Failed to load provider health.';
		}
	}

	async function refreshSources() {
		loadingSources = true;
		notesError = '';
		try {
			sources = (await listNoteSources({ limit: 100 })).items;
			if (selectedSourceId) {
				await loadSourceDetail(selectedSourceId);
			}
		} catch (err) {
			notesError = err instanceof Error ? err.message : 'Failed to load note sources.';
		} finally {
			loadingSources = false;
		}
	}

	async function loadSourceDetail(sourceId: string) {
		selectedSourceId = sourceId;
		notesError = '';
		try {
			selectedSource = await getNoteSource(sourceId);
		} catch (err) {
			notesError = err instanceof Error ? err.message : 'Failed to load note source.';
		}
	}

	async function runScan() {
		if (!noteRootPath.trim()) return;
		scanning = true;
		notesError = '';
		try {
			const response = await scanNoteSources({
				root_path: noteRootPath.trim(),
				recursive: true,
				max_files: 100,
				include_glob: '*.md'
			});
			scanSummary = {
				files_seen: response.files_seen,
				sections_seen: response.sections_seen,
				created: response.created,
				updated: response.updated,
				unchanged: response.unchanged
			};
			sources = response.sources;
			if (response.sources.length > 0) {
				await loadSourceDetail(response.sources[0].id);
			}
		} catch (err) {
			notesError = err instanceof Error ? err.message : 'Failed to scan notes.';
		} finally {
			scanning = false;
		}
	}

	async function runExtraction() {
		if (!selectedSourceId) return;
		extracting = true;
		notesError = '';
		try {
			await extractNoteSource(selectedSourceId);
			await loadSourceDetail(selectedSourceId);
			await refreshSources();
		} catch (err) {
			notesError = err instanceof Error ? err.message : 'Failed to extract note source.';
		} finally {
			extracting = false;
		}
	}

	async function reviewMention(
		mentionId: string,
		action: 'accept_match' | 'reject' | 'defer' | 'create_new',
		selectedCandidateId?: string
	) {
		reviewingMentionId = mentionId;
		notesError = '';
		try {
			await reviewNoteMention(mentionId, {
				action,
				selected_candidate_id: selectedCandidateId ?? null
			});
			if (selectedSourceId) {
				await loadSourceDetail(selectedSourceId);
			}
		} catch (err) {
			notesError = err instanceof Error ? err.message : 'Failed to review mention.';
		} finally {
			reviewingMentionId = null;
		}
	}

	async function submitMentionEdit() {
		if (!activeMention) return;
		reviewingMentionId = activeMention.id;
		notesError = '';
		try {
			await updateNoteMention(activeMention.id, {
				entity_type: mentionEditForm.entity_type,
				raw_text: mentionEditForm.raw_text,
				normalized_text: mentionEditForm.normalized_text || null,
				evidence_text: mentionEditForm.evidence_text || null
			});
			closeModal();
			if (selectedSourceId) {
				await loadSourceDetail(selectedSourceId);
			}
		} catch (err) {
			notesError = err instanceof Error ? err.message : 'Failed to update mention.';
		} finally {
			reviewingMentionId = null;
		}
	}

	async function submitCreateCanonical() {
		if (!activeMention) return;
		reviewingMentionId = activeMention.id;
		notesError = '';
		try {
			await createCanonicalFromNoteMention(activeMention.id, {
				entity_type: createForm.entity_type,
				display_name: createForm.display_name || null,
				given_name: createForm.given_name || null,
				family_name: createForm.family_name || null,
				primary_location: createForm.primary_location || null,
				relationship_summary: createForm.relationship_summary || null,
				how_we_met: createForm.how_we_met || null,
				notes: createForm.notes || null,
				organization_type: createForm.organization_type || null,
				industry: createForm.industry || null,
				location_label: createForm.location_label || null,
				location_address_line: createForm.location_address_line || null,
				location_city: createForm.location_city || null,
				location_region: createForm.location_region || null,
				location_country: createForm.location_country || null,
				location_type: createForm.location_type || null,
				event_title: createForm.event_title || null,
				event_type: createForm.event_type || null,
				event_summary: createForm.event_summary || null,
				event_started_at: createForm.event_started_at || null,
				event_ended_at: createForm.event_ended_at || null
			});
			closeModal();
			if (selectedSourceId) {
				await loadSourceDetail(selectedSourceId);
			}
		} catch (err) {
			notesError = err instanceof Error ? err.message : 'Failed to create canonical entity.';
		} finally {
			reviewingMentionId = null;
		}
	}

	function openTypeModal(mention: NoteMention) {
		activeMention = mention;
		modalMode = 'edit-type';
		modalOpen = true;
		mentionEditForm = {
			entity_type: mention.entity_type as MentionType,
			raw_text: mention.raw_text,
			normalized_text: mention.normalized_text,
			evidence_text: mention.evidence_text || ''
		};
	}

	function openCreateModal(mention: NoteMention) {
		activeMention = mention;
		modalMode = 'create';
		modalOpen = true;
		createForm = {
			entity_type: mention.entity_type as MentionType,
			display_name: mention.normalized_text,
			given_name: '',
			family_name: '',
			primary_location: '',
			relationship_summary: '',
			how_we_met: '',
			notes: mention.evidence_text || '',
			organization_type: 'Other',
			industry: '',
			location_label: mention.normalized_text,
			location_address_line: '',
			location_city: '',
			location_region: '',
			location_country: '',
			location_type: 'Other',
			event_title: mention.normalized_text,
			event_type: mention.entity_type === 'Event' ? 'Note' : 'Note',
			event_summary: mention.evidence_text || '',
			event_started_at: '',
			event_ended_at: ''
		};
	}

	function closeModal() {
		modalOpen = false;
		activeMention = null;
	}

	function toggleFold(state: FoldState, key: string) {
		state[key] = !(state[key] ?? true);
		if (state === pendingFoldState) pendingFoldState = { ...state };
		if (state === reviewedFoldState) reviewedFoldState = { ...state };
	}

	function mentionsForStatus(kind: 'pending' | 'reviewed') {
		const mentions = selectedSource?.mentions ?? [];
		const filtered = mentions.filter((mention) =>
			kind === 'pending' ? pendingStatuses.has(mention.review_status) : !pendingStatuses.has(mention.review_status)
		);
		return [...filtered].sort(
			(left, right) => new Date(left.created_at).getTime() - new Date(right.created_at).getTime()
		);
	}

	function groupedMentions(kind: 'pending' | 'reviewed') {
		const groups: Array<{ type: MentionType; items: NoteMention[] }> = [];
		for (const type of mentionTypes) {
			const items = mentionsForStatus(kind).filter((mention) => mention.entity_type === type);
			if (items.length) groups.push({ type, items });
		}
		return groups;
	}

	function groupKey(kind: 'pending' | 'reviewed', type: MentionType) {
		return `${kind}-${type}`;
	}

	onMount(async () => {
		await Promise.all([loadProviderHealth(), refreshSources()]);
	});
</script>

<svelte:head>
	<title>Imports | Kizuna</title>
</svelte:head>

<main class="shell">
	<header class="topbar">
		<div>
			<a class="brand" href={resolve('/')}>Kizuna</a>
			<h1>Imports</h1>
		</div>
		<p class="meta">CSV and notes ingestion</p>
	</header>

	<section class="grid">
		<section class="panel">
			<div class="panel-header">
				<h2>People CSV</h2>
				<span>Dedupes by display name and email</span>
			</div>
			<form onsubmit={(event) => { event.preventDefault(); submitImport(); }}>
				<label class="wide">
					<span>CSV file</span>
					<input accept=".csv,text/csv" onchange={(event) => (file = (event.currentTarget as HTMLInputElement).files?.[0] || null)} type="file" />
				</label>
				<button type="submit" disabled={!file || uploading}>{uploading ? 'Importing…' : 'Import people'}</button>
			</form>
			{#if error}
				<p class="notice">{error}</p>
			{/if}
			{#if result}
				<div class="summary">
					<p>Created: {result.created}</p>
					<p>Skipped: {result.skipped}</p>
				</div>
			{/if}
		</section>

		<section class="panel notes-panel">
			<div class="panel-header">
				<h2>Daily Notes</h2>
				<span>Scan, extract, review</span>
			</div>

			<div class="stack">
				<label>
					<span>Notes root path</span>
					<input bind:value={noteRootPath} />
				</label>

				<div class="actions">
					<button type="button" onclick={runScan} disabled={scanning}>{scanning ? 'Scanning…' : 'Scan notes'}</button>
					<button type="button" onclick={refreshSources} disabled={loadingSources}>{loadingSources ? 'Refreshing…' : 'Refresh list'}</button>
				</div>

				{#if providerHealth}
					<div class="status-grid">
						<div class="status-card">
							<strong>Primary</strong>
							<p>{providerHealth.primary.provider_name} · {providerHealth.primary.model_name || 'No model'}</p>
							<p>{providerHealth.primary.reachable ? 'Reachable' : providerHealth.primary.detail || 'Unavailable'}</p>
						</div>
						{#if providerHealth.fallback}
							<div class="status-card">
								<strong>Fallback</strong>
								<p>{providerHealth.fallback.provider_name} · {providerHealth.fallback.model_name || 'No model'}</p>
								<p>{providerHealth.fallback.reachable ? 'Reachable' : providerHealth.fallback.detail || 'Unavailable'}</p>
							</div>
						{/if}
					</div>
				{/if}

				{#if scanSummary}
					<div class="summary">
						<p>Files: {scanSummary.files_seen}</p>
						<p>Sections: {scanSummary.sections_seen}</p>
						<p>Created: {scanSummary.created}</p>
						<p>Updated: {scanSummary.updated}</p>
						<p>Unchanged: {scanSummary.unchanged}</p>
					</div>
				{/if}

				{#if notesError}
					<p class="notice">{notesError}</p>
				{/if}

				<div class="notes-grid">
					<section class="subpanel">
						<div class="subpanel-header">
							<h3>Sources</h3>
							<span>{sources.length}</span>
						</div>
						<ul class="source-list">
							{#if sources.length}
								{#each sources as source (source.id)}
									<li class:selected={selectedSourceId === source.id}>
										<button type="button" class="source-button" onclick={() => loadSourceDetail(source.id)}>
											<strong>{source.heading}</strong>
											<p>{source.note_date || 'No date'} · {source.extraction_status}</p>
										</button>
									</li>
								{/each}
							{:else}
								<li class="empty">No note sources yet.</li>
							{/if}
						</ul>
					</section>

					<section class="subpanel detail">
						<div class="subpanel-header">
							<h3>Review</h3>
							{#if selectedSource}
								<button type="button" onclick={runExtraction} disabled={extracting}>
									{extracting ? 'Extracting…' : 'Run extraction'}
								</button>
							{/if}
						</div>

						{#if selectedSource}
							<div class="detail-block">
								<strong>{selectedSource.heading}</strong>
								<p class="muted">{selectedSource.file_path}</p>
								<pre>{selectedSource.body_text}</pre>
							</div>

							<div class="detail-block">
								<h4>Pending Review</h4>
								{#if mentionsForStatus('pending').length}
									{#each groupedMentions('pending') as group (group.type)}
										<section class="group">
											<button type="button" class="group-toggle" onclick={() => toggleFold(pendingFoldState, groupKey('pending', group.type))}>
												<strong>{group.type}</strong>
												<span>{group.items.length} · {pendingFoldState[groupKey('pending', group.type)] === false ? 'collapsed' : 'open'}</span>
											</button>
											{#if pendingFoldState[groupKey('pending', group.type)] !== false}
												<ul class="mention-list">
													{#each group.items as mention (mention.id)}
														<li>
															<div class="mention-head">
																<strong>{mention.raw_text}</strong>
																<span>{mention.review_status}</span>
															</div>
															<div class="mention-meta">
																<label>
																	<span>Type</span>
																	<select bind:value={mention.entity_type}>
																		{#each mentionTypes as option (option)}
																			<option value={option}>{option}</option>
																		{/each}
																	</select>
																</label>
																<button type="button" onclick={() => openTypeModal(mention)}>Edit details</button>
															</div>
															<p>{mention.evidence_text || 'No evidence snippet'}</p>
															{#if mention.candidates.length}
																<div class="candidate-list">
																	{#each mention.candidates as candidate (candidate.id)}
																		<div class="candidate">
																			<div>
																				<strong>{candidate.label}</strong>
																				<p>{candidate.subtitle || candidate.rationale || 'Candidate match'}</p>
																			</div>
																			<button type="button" onclick={() => reviewMention(mention.id, 'accept_match', candidate.id)} disabled={reviewingMentionId === mention.id}>
																				Match
																			</button>
																		</div>
																	{/each}
																</div>
															{/if}
															<div class="actions compact">
																<button type="button" onclick={() => openCreateModal(mention)} disabled={reviewingMentionId === mention.id}>Create new</button>
																<button type="button" onclick={() => reviewMention(mention.id, 'defer')} disabled={reviewingMentionId === mention.id}>Defer</button>
																<button type="button" onclick={() => reviewMention(mention.id, 'reject')} disabled={reviewingMentionId === mention.id}>Reject</button>
															</div>
														</li>
													{/each}
												</ul>
											{/if}
										</section>
									{/each}
								{:else}
									<p class="empty">No pending mentions.</p>
								{/if}
							</div>

							<div class="detail-block">
								<h4>Reviewed</h4>
								{#if mentionsForStatus('reviewed').length}
									{#each groupedMentions('reviewed') as group (group.type)}
										<section class="group">
											<button type="button" class="group-toggle" onclick={() => toggleFold(reviewedFoldState, groupKey('reviewed', group.type))}>
												<strong>{group.type}</strong>
												<span>{group.items.length} · {reviewedFoldState[groupKey('reviewed', group.type)] === false ? 'collapsed' : 'open'}</span>
											</button>
											{#if reviewedFoldState[groupKey('reviewed', group.type)] !== false}
												<ul class="messages">
													{#each group.items as mention (mention.id)}
														<li>
															<strong>{mention.raw_text}</strong>
															<p>{mention.review_status}</p>
														</li>
													{/each}
												</ul>
											{/if}
										</section>
									{/each}
								{:else}
									<p class="empty">No reviewed mentions yet.</p>
								{/if}
							</div>

							<div class="detail-block">
								<h4>Event Drafts</h4>
								{#if selectedSource.event_drafts.length}
									<ul class="messages">
										{#each selectedSource.event_drafts as draft (draft.id)}
											<li>
												<strong>{draft.title}</strong>
												<p>{draft.summary || draft.evidence_text || 'No summary'}</p>
											</li>
										{/each}
									</ul>
								{:else}
									<p class="empty">No event drafts yet.</p>
								{/if}
							</div>
						{:else}
							<p class="empty">Select a source after scanning notes.</p>
						{/if}
					</section>
				</div>
			</div>
		</section>
	</section>

	{#if modalOpen && activeMention}
		<div
			class="modal-backdrop"
			role="button"
			aria-label="Close dialog"
			tabindex="0"
			onclick={closeModal}
			onkeydown={(event) => {
				if (event.key === 'Escape' || event.key === 'Enter' || event.key === ' ') closeModal();
			}}
		>
			<div
				class="modal"
				role="dialog"
				aria-modal="true"
				tabindex="-1"
				onclick={(event) => event.stopPropagation()}
				onkeydown={(event) => event.stopPropagation()}
			>
				<div class="panel-header">
					<h2>{modalMode === 'create' ? 'Create canonical entity' : 'Edit mention'}</h2>
					<button type="button" class="close-button" onclick={closeModal}>Close</button>
				</div>

				{#if modalMode === 'edit-type'}
					<form class="stack" onsubmit={(event) => { event.preventDefault(); submitMentionEdit(); }}>
						<label>
							<span>Type</span>
							<select bind:value={mentionEditForm.entity_type}>
								{#each mentionTypes as option (option)}
									<option value={option}>{option}</option>
								{/each}
							</select>
						</label>
						<label>
							<span>Raw text</span>
							<input bind:value={mentionEditForm.raw_text} />
						</label>
						<label>
							<span>Normalized text</span>
							<input bind:value={mentionEditForm.normalized_text} />
						</label>
						<label>
							<span>Evidence</span>
							<textarea bind:value={mentionEditForm.evidence_text} rows="4"></textarea>
						</label>
						<button type="submit" disabled={reviewingMentionId === activeMention.id}>Save mention</button>
					</form>
				{:else}
					<form class="stack" onsubmit={(event) => { event.preventDefault(); submitCreateCanonical(); }}>
						<label>
							<span>Entity type</span>
							<select bind:value={createForm.entity_type}>
								{#each mentionTypes as option (option)}
									<option value={option}>{option}</option>
								{/each}
							</select>
						</label>

						{#if createForm.entity_type === 'Person'}
							<label><span>Display name</span><input bind:value={createForm.display_name} /></label>
							<label><span>Given name</span><input bind:value={createForm.given_name} /></label>
							<label><span>Family name</span><input bind:value={createForm.family_name} /></label>
							<label><span>Primary location</span><input bind:value={createForm.primary_location} /></label>
							<label><span>Relationship summary</span><textarea bind:value={createForm.relationship_summary} rows="3"></textarea></label>
							<label><span>How we met</span><textarea bind:value={createForm.how_we_met} rows="3"></textarea></label>
							<label><span>Notes</span><textarea bind:value={createForm.notes} rows="4"></textarea></label>
						{:else if createForm.entity_type === 'Organization'}
							<label><span>Name</span><input bind:value={createForm.display_name} /></label>
							<label><span>Type</span><input bind:value={createForm.organization_type} /></label>
							<label><span>Industry</span><input bind:value={createForm.industry} /></label>
							<label><span>Location</span><input bind:value={createForm.primary_location} /></label>
							<label><span>Notes</span><textarea bind:value={createForm.notes} rows="4"></textarea></label>
						{:else if createForm.entity_type === 'Location'}
							<label><span>Label</span><input bind:value={createForm.location_label} /></label>
							<label><span>Street / address line</span><input bind:value={createForm.location_address_line} /></label>
							<label><span>City</span><input bind:value={createForm.location_city} /></label>
							<label><span>Region</span><input bind:value={createForm.location_region} /></label>
							<label><span>Country</span><input bind:value={createForm.location_country} /></label>
							<label><span>Location type</span><input bind:value={createForm.location_type} placeholder="Home, Work, Cafe" /></label>
							<label><span>Notes</span><textarea bind:value={createForm.notes} rows="4"></textarea></label>
						{:else}
							<label><span>Title</span><input bind:value={createForm.event_title} /></label>
							<label><span>Type</span><input bind:value={createForm.event_type} /></label>
							<label><span>Started at</span><input bind:value={createForm.event_started_at} type="datetime-local" /></label>
							<label><span>Ended at</span><input bind:value={createForm.event_ended_at} type="datetime-local" /></label>
							<label><span>Summary</span><textarea bind:value={createForm.event_summary} rows="4"></textarea></label>
							<label><span>Notes</span><textarea bind:value={createForm.notes} rows="4"></textarea></label>
						{/if}

						<button type="submit" disabled={reviewingMentionId === activeMention.id}>Create {createForm.entity_type}</button>
					</form>
				{/if}
			</div>
		</div>
	{/if}
</main>

<style>
	.shell { min-height: 100vh; padding: 1.25rem; }
	.topbar { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: 1rem; padding-bottom: 1rem; border-bottom: 1px solid var(--line-strong); }
	.grid { display: grid; grid-template-columns: minmax(18rem, 24rem) minmax(0, 1fr); gap: 1rem; margin-top: 1rem; }
	.brand, .meta, .panel-header span, .subpanel-header span, label span { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted); text-decoration: none; }
	h1 { margin: 0.35rem 0 0; font-size: clamp(2rem, 4vw, 3rem); letter-spacing: -0.05em; }
	h2, h3, h4 { margin: 0; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.08em; }
	h4 { font-size: 0.8rem; }
	.panel, .subpanel, .notice, .modal { border: 1px solid var(--line-strong); background: var(--panel-strong); box-shadow: var(--shadow); }
	.panel-header, .subpanel-header { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 0.85rem; border-bottom: 1px solid var(--line); }
	form, .stack, .detail-block { display: grid; gap: 1rem; padding: 0.85rem; }
	.notes-panel { min-width: 0; }
	.notes-grid { display: grid; grid-template-columns: minmax(16rem, 20rem) minmax(0, 1fr); gap: 1rem; }
	.source-list, .messages, .mention-list { list-style: none; margin: 0; padding: 0; }
	.source-list li, .messages li, .mention-list li { border-bottom: 1px solid var(--line); }
	.source-list li:last-child, .messages li:last-child, .mention-list li:last-child { border-bottom: 0; }
	.source-button { width: 100%; text-align: left; border: 0; background: transparent; padding: 0.85rem; color: var(--text); cursor: pointer; }
	.source-list li.selected { background: var(--selection-row-bg); }
	.source-button p, .candidate p, .mention-list p, .muted, .status-card p, .messages p { margin: 0.2rem 0 0; color: var(--muted); }
	label { display: grid; gap: 0.35rem; }
	input, button, select, textarea { width: 100%; border: 1px solid var(--line); background: var(--panel); padding: 0.62rem 0.72rem; color: var(--text); }
	button { cursor: pointer; }
	textarea { resize: vertical; }
	pre { margin: 0; white-space: pre-wrap; background: var(--panel); border: 1px solid var(--line); padding: 0.75rem; max-height: 18rem; overflow: auto; }
	.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); gap: 0.5rem; padding: 0.85rem; }
	.summary p { margin: 0; padding: 0.55rem 0.65rem; border: 1px solid var(--line); background: var(--panel); }
	.notice { margin: 0.85rem; padding: 0.85rem; }
	.actions { display: flex; gap: 0.75rem; flex-wrap: wrap; }
	.actions.compact { padding: 0; }
	.status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: 0.75rem; }
	.status-card { border: 1px solid var(--line); background: var(--panel); padding: 0.75rem; }
	.candidate-list { display: grid; gap: 0.5rem; }
	.candidate { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.75rem; align-items: start; border: 1px solid var(--line); background: var(--panel); padding: 0.65rem; }
	.mention-head { display: flex; justify-content: space-between; gap: 0.75rem; align-items: baseline; }
	.mention-meta { display: grid; grid-template-columns: minmax(12rem, 16rem) auto; gap: 0.75rem; align-items: end; }
	.empty { padding: 0.85rem; color: var(--muted); }
	.detail { min-width: 0; }
	.group { border: 1px solid var(--line); }
	.group-toggle { display: flex; justify-content: space-between; align-items: center; border: 0; border-bottom: 1px solid var(--line); background: var(--panel); padding: 0.7rem 0.85rem; }
	.modal-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.45); display: grid; place-items: center; padding: 1rem; }
	.modal { width: min(42rem, 100%); max-height: calc(100vh - 2rem); overflow: auto; }
	.close-button { width: auto; }
	@media (max-width: 1100px) {
		.grid, .notes-grid, .mention-meta { grid-template-columns: 1fr; }
	}
</style>
