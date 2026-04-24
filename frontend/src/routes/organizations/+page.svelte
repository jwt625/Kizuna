<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import PreviewLink from '$lib/components/PreviewLink.svelte';
	import {
		addOrganizationLocation,
		addOrganizationTag,
		createOrganization,
		getOrganization,
		listOrganizations,
		updateOrganization,
		type Organization,
		type OrganizationDetail
	} from '$lib/api';

	const organizationTypes = ['Company', 'Fund', 'Supplier', 'School', 'Community', 'Partner', 'Nonprofit', 'Government', 'Other'];
	type OrganizationSortField = 'name' | 'type' | 'industry' | 'location';
	type SortDirection = 'none' | 'asc' | 'desc';

	let loading = $state(true);
	let saving = $state(false);
	let savingSelection = $state(false);
	let editingSelected = $state(false);
	let error = $state('');
	let query = $state('');
	let industry = $state('');
	let sortField = $state<OrganizationSortField | null>(null);
	let sortDirection = $state<SortDirection>('none');
	let organizations = $state<Organization[]>([]);
	let selectedId = $state('');
	let selectedOrganizationDetail = $state<OrganizationDetail | null>(null);

	let selectedEditForm = $state({
		name: '',
		type: 'Other',
		industry: '',
		location: '',
		website: '',
		description: '',
		notes: ''
	});

	let createForm = $state({
		name: '',
		type: 'Other',
		industry: '',
		location: '',
		website: '',
		description: '',
		notes: ''
	});

	let tagForm = $state({ name: '' });
	let locationForm = $state({ city: '', region: '', country: '' });

	const sortedOrganizations = $derived(sortOrganizations(organizations, sortField, sortDirection));
	const selectedOrganization = $derived(
		sortedOrganizations.find((organization) => organization.id === selectedId) ?? sortedOrganizations[0] ?? null
	);

	$effect(() => {
		if (selectedId) {
			void loadSelectedOrganization(selectedId);
		}
	});

	onMount(loadOrganizations);

	function sortOrganizations(items: Organization[], field: OrganizationSortField | null, direction: SortDirection) {
		if (!field || direction === 'none') {
			return items;
		}
		const factor = direction === 'asc' ? 1 : -1;
		return [...items].sort((left, right) => ((left[field] || '').localeCompare(right[field] || '')) * factor);
	}

	function toggleSort(field: OrganizationSortField) {
		if (sortField !== field) {
			sortField = field;
			sortDirection = 'asc';
			return;
		}
		if (sortDirection === 'none') {
			sortDirection = 'asc';
			return;
		}
		if (sortDirection === 'asc') {
			sortDirection = 'desc';
			return;
		}
		sortField = null;
		sortDirection = 'none';
	}

	function sortIndicator(field: OrganizationSortField) {
		if (sortField !== field || sortDirection === 'none') return '';
		return sortDirection === 'asc' ? '↑' : '↓';
	}

	function syncSelectedEditForm(detail: OrganizationDetail) {
		selectedEditForm = {
			name: detail.name || '',
			type: detail.type || 'Other',
			industry: detail.industry || '',
			location: detail.location || '',
			website: detail.website || '',
			description: detail.description || '',
			notes: detail.notes || ''
		};
	}

	async function loadOrganizations() {
		loading = true;
		error = '';
		try {
			organizations = await listOrganizations({ q: query, limit: 100, industry: industry || undefined });
			const available = sortOrganizations(organizations, sortField, sortDirection);
			if (!selectedId && available[0]) {
				selectedId = available[0].id;
			}
			if (selectedId && !available.some((organization) => organization.id === selectedId) && available[0]) {
				selectedId = available[0].id;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load organizations.';
		} finally {
			loading = false;
		}
	}

	async function loadSelectedOrganization(organizationId: string) {
		try {
			selectedOrganizationDetail = await getOrganization(organizationId);
			if (selectedOrganizationDetail && !editingSelected) {
				syncSelectedEditForm(selectedOrganizationDetail);
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load organization detail.';
		}
	}

	function startEditingSelected() {
		if (!selectedOrganizationDetail) return;
		syncSelectedEditForm(selectedOrganizationDetail);
		editingSelected = true;
	}

	function cancelEditingSelected() {
		if (selectedOrganizationDetail) {
			syncSelectedEditForm(selectedOrganizationDetail);
		}
		editingSelected = false;
	}

	async function saveSelectedOrganization() {
		if (!selectedId) return;
		savingSelection = true;
		error = '';
		try {
			selectedOrganizationDetail = await updateOrganization(selectedId, {
				name: selectedEditForm.name,
				type: selectedEditForm.type,
				industry: selectedEditForm.industry || null,
				location: selectedEditForm.location || null,
				website: selectedEditForm.website || null,
				description: selectedEditForm.description || null,
				notes: selectedEditForm.notes || null
			});
			editingSelected = false;
			await loadOrganizations();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to update organization.';
		} finally {
			savingSelection = false;
		}
	}

	async function submitOrganization() {
		saving = true;
		error = '';
		try {
			const created = await createOrganization({
				name: createForm.name,
				type: createForm.type,
				industry: createForm.industry || undefined,
				location: createForm.location || undefined,
				website: createForm.website || undefined,
				description: createForm.description || undefined,
				notes: createForm.notes || undefined
			});
			createForm = {
				name: '',
				type: 'Other',
				industry: '',
				location: '',
				website: '',
				description: '',
				notes: ''
			};
			await loadOrganizations();
			selectedId = created.id;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to create organization.';
		} finally {
			saving = false;
		}
	}

	async function submitTag() {
		if (!selectedId || !tagForm.name) return;
		try {
			selectedOrganizationDetail = await addOrganizationTag(selectedId, { name: tagForm.name });
			tagForm = { name: '' };
			await loadOrganizations();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to add tag.';
		}
	}

	async function submitLocation() {
		if (!selectedId) return;
		try {
			selectedOrganizationDetail = await addOrganizationLocation(selectedId, {
				location: {
					label: null,
					city: locationForm.city || null,
					region: locationForm.region || null,
					country: locationForm.country || null,
					address_line: null,
					latitude: null,
					longitude: null,
					location_type: 'Work',
					notes: null
				},
				is_primary: true
			});
			locationForm = { city: '', region: '', country: '' };
			await loadOrganizations();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to add location.';
		}
	}
</script>

<svelte:head>
	<title>Organizations | Kizuna</title>
</svelte:head>

<main class="shell">
	<header class="topbar">
		<div>
			<a class="brand" href={resolve('/')}>Kizuna</a>
			<h1>Organizations</h1>
		</div>
		<p class="meta">{organizations.length} records</p>
	</header>

	<section class="toolbar">
		<label>
			<span>Search</span>
			<input bind:value={query} placeholder="Name, industry, location, notes" />
		</label>
		<label>
			<span>Industry</span>
			<input bind:value={industry} placeholder="Filter industry" />
		</label>
		<button type="button" onclick={loadOrganizations}>Refresh</button>
	</section>

	{#if error}
		<p class="notice">{error}</p>
	{/if}

	<section class="workspace">
		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>Directory</h2>
					<span>{loading ? 'Loading…' : 'Live'}</span>
				</div>
			</div>
			<div class="table">
				<div class="row head">
					<button class="sort-button" type="button" onclick={() => toggleSort('name')}>Name {sortIndicator('name')}</button>
					<button class="sort-button" type="button" onclick={() => toggleSort('type')}>Type {sortIndicator('type')}</button>
					<button class="sort-button" type="button" onclick={() => toggleSort('industry')}>Industry {sortIndicator('industry')}</button>
				</div>
				{#each sortedOrganizations as organization (organization.id)}
					<button
						class:selected={selectedOrganization?.id === organization.id}
						class="row item"
						onclick={() => {
							selectedId = organization.id;
							editingSelected = false;
						}}
					>
						<span>{organization.name}</span>
						<span>{organization.type}</span>
						<span>{organization.industry || '—'}</span>
					</button>
				{/each}
			</div>
		</section>

		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>Selected record</h2>
					<span>{selectedOrganization?.location || 'No location'}</span>
				</div>
				{#if selectedOrganizationDetail}
					<div class="inline-actions">
						{#if editingSelected}
							<button type="button" onclick={cancelEditingSelected}>Cancel</button>
							<button type="button" onclick={saveSelectedOrganization} disabled={savingSelection}>
								{savingSelection ? 'Saving…' : 'Save'}
							</button>
						{:else}
							<button type="button" onclick={startEditingSelected}>Edit</button>
						{/if}
					</div>
				{/if}
			</div>
			{#if selectedOrganizationDetail}
				<div class="detail-grid">
					{#if editingSelected}
						<label>
							<span>Name</span>
							<input bind:value={selectedEditForm.name} />
						</label>
						<label>
							<span>Type</span>
							<select bind:value={selectedEditForm.type}>
								{#each organizationTypes as type (type)}
									<option value={type}>{type}</option>
								{/each}
							</select>
						</label>
						<label>
							<span>Industry</span>
							<input bind:value={selectedEditForm.industry} />
						</label>
						<label>
							<span>Location</span>
							<input bind:value={selectedEditForm.location} />
						</label>
						<label class="wide">
							<span>Website</span>
							<input bind:value={selectedEditForm.website} />
						</label>
						<label class="wide">
							<span>Description</span>
							<textarea bind:value={selectedEditForm.description} rows="4"></textarea>
						</label>
						<label class="wide">
							<span>Notes</span>
							<textarea bind:value={selectedEditForm.notes} rows="6"></textarea>
						</label>
					{:else}
						<div class="field">
							<span>Name</span>
							<strong>{selectedOrganizationDetail.name}</strong>
						</div>
						<div class="field">
							<span>Type</span>
							<strong>{selectedOrganizationDetail.type}</strong>
						</div>
						<div class="field">
							<span>Industry</span>
							<strong>{selectedOrganizationDetail.industry || '—'}</strong>
						</div>
						<div class="field">
							<span>Location</span>
							<strong>{selectedOrganizationDetail.location || '—'}</strong>
						</div>
						<div class="field wide">
							<span>Website</span>
							<p>
								{#if selectedOrganizationDetail.website}
									<PreviewLink value={selectedOrganizationDetail.website} />
								{:else}
									No website recorded.
								{/if}
							</p>
						</div>
						<div class="field wide">
							<span>Description</span>
							<p>{selectedOrganizationDetail.description || 'No description recorded.'}</p>
						</div>
						<div class="field wide">
							<span>Tags</span>
							<p>{selectedOrganizationDetail.tags.map((item) => item.tag.name).join(', ') || 'No tags yet.'}</p>
						</div>
						<div class="field wide">
							<span>Locations</span>
							<ul>
								{#if selectedOrganizationDetail.locations.length}
									{#each selectedOrganizationDetail.locations as item (item.id)}
										<li>{item.location.city || item.location.label || '—'} {item.location.country || ''}</li>
									{/each}
								{:else}
									<li>No structured locations yet.</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>People</span>
							<ul>
								{#if selectedOrganizationDetail.people.length}
									{#each selectedOrganizationDetail.people as role (role.id)}
										<li>{role.title || role.role_type || 'Role'} · {role.organization_name}</li>
									{/each}
								{:else}
									<li>No linked people yet.</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>Pipeline items</span>
							<ul>
								{#if selectedOrganizationDetail.pipeline_items.length}
									{#each selectedOrganizationDetail.pipeline_items as item (item.id)}
										<li>{item.title}</li>
									{/each}
								{:else}
									<li>No pipeline items.</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>Notes</span>
							<p>{selectedOrganizationDetail.notes || 'No notes yet.'}</p>
						</div>
					{/if}
				</div>
			{:else}
				<p class="notice">No organization selected.</p>
			{/if}
		</section>

		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>Actions</h2>
					<span>Capture and structure</span>
				</div>
			</div>
			<div class="action-stack">
				<form onsubmit={(event) => {
					event.preventDefault();
					submitOrganization();
				}}>
					<h3>New organization</h3>
					<label>
						<span>Name</span>
						<input bind:value={createForm.name} required />
					</label>
					<label>
						<span>Type</span>
						<select bind:value={createForm.type}>
							{#each organizationTypes as type (type)}
								<option value={type}>{type}</option>
							{/each}
						</select>
					</label>
					<label>
						<span>Industry</span>
						<input bind:value={createForm.industry} />
					</label>
					<label>
						<span>Location</span>
						<input bind:value={createForm.location} />
					</label>
					<label class="wide">
						<span>Website</span>
						<input bind:value={createForm.website} />
					</label>
					<label class="wide">
						<span>Description</span>
						<textarea bind:value={createForm.description} rows="4"></textarea>
					</label>
					<label class="wide">
						<span>Notes</span>
						<textarea bind:value={createForm.notes} rows="5"></textarea>
					</label>
					<button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Create organization'}</button>
				</form>

				<form class="separator" onsubmit={(event) => {
					event.preventDefault();
					submitTag();
				}}>
					<h3>Add tag to selected organization</h3>
					<label class="wide">
						<span>Tag</span>
						<input bind:value={tagForm.name} placeholder="supplier, school, partner" />
					</label>
					<button type="submit">Add tag</button>
				</form>

				<form class="separator" onsubmit={(event) => {
					event.preventDefault();
					submitLocation();
				}}>
					<h3>Add location to selected organization</h3>
					<label>
						<span>City</span>
						<input bind:value={locationForm.city} />
					</label>
					<label>
						<span>Region</span>
						<input bind:value={locationForm.region} />
					</label>
					<label>
						<span>Country</span>
						<input bind:value={locationForm.country} />
					</label>
					<button type="submit">Add primary location</button>
				</form>
			</div>
		</section>
	</section>
</main>

<style>
	.shell {
		min-height: 100vh;
		padding: 1.25rem;
	}

	.topbar,
	.toolbar,
	.workspace,
	.action-stack {
		display: grid;
		gap: 1rem;
	}

	.topbar {
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: end;
		padding-bottom: 1rem;
		border-bottom: 1px solid var(--line-strong);
	}

	.toolbar {
		grid-template-columns: minmax(0, 1fr) 12rem auto;
		align-items: end;
		margin-top: 1rem;
	}

	.workspace {
		grid-template-columns: 1.1fr 1fr 0.9fr;
		margin-top: 1rem;
	}

	.brand,
	.meta,
	.panel-header span,
	label span,
	.row.head,
	.field span {
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		color: var(--muted);
		text-decoration: none;
	}

	h1 {
		margin: 0.35rem 0 0;
		font-size: clamp(2rem, 4vw, 3rem);
		letter-spacing: -0.05em;
	}

	h2,
	h3 {
		margin: 0;
		font-size: 0.9rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	h3 {
		font-size: 0.84rem;
	}

	.panel {
		border: 1px solid var(--line-strong);
		background: var(--panel-strong);
		box-shadow: var(--shadow);
	}

	.panel-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 0.75rem;
		padding: 0.75rem 0.85rem;
		border-bottom: 1px solid var(--line);
	}

	.inline-actions {
		display: flex;
		gap: 0.6rem;
	}

	.table {
		display: grid;
		padding: 0 0.85rem 0.85rem;
	}

	.row {
		display: grid;
		grid-template-columns: 1.3fr 0.7fr 1fr;
		gap: 0.75rem;
		padding: 0.7rem 0;
		border-bottom: 1px solid var(--line);
		background: transparent;
		text-align: left;
	}

	.item {
		border-left: 0;
		border-right: 0;
		border-top: 0;
		padding-left: 0;
		padding-right: 0;
	}

	.item.selected {
		background: var(--selection-row-bg);
	}

	.sort-button {
		border: 0;
		padding: 0;
		background: transparent;
		color: inherit;
		text-align: left;
		text-transform: inherit;
		letter-spacing: inherit;
	}

	.detail-grid,
	form {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.85rem;
		padding: 0.85rem;
	}

	.separator {
		border-top: 1px solid var(--line);
	}

	label {
		display: grid;
		gap: 0.35rem;
	}

	input,
	select,
	textarea,
	button {
		width: 100%;
		border: 1px solid var(--line);
		background: var(--panel);
		padding: 0.62rem 0.72rem;
		color: var(--text);
	}

	button {
		cursor: pointer;
	}

	.field {
		display: grid;
		gap: 0.3rem;
		padding-bottom: 0.8rem;
		border-bottom: 1px solid var(--line);
	}

	.field strong,
	.field p,
	.field ul {
		margin: 0;
	}

	.field ul {
		padding-left: 1rem;
	}

	.wide {
		grid-column: 1 / -1;
	}

	.notice {
		margin-top: 1rem;
		padding: 0.85rem;
		border: 1px solid var(--line-strong);
		background: var(--panel-strong);
	}

	@media (max-width: 1100px) {
		.toolbar,
		.workspace,
		.row,
		.detail-grid,
		form {
			grid-template-columns: 1fr;
		}

		.panel-header,
		.inline-actions {
			flex-direction: column;
			align-items: stretch;
		}
	}
</style>
