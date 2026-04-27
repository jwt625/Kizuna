<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import {
		createLocation,
		getLocation,
		listLocations,
		type Location,
		type LocationDetail,
		updateLocation
	} from '$lib/api';

	type LocationSortField = 'label' | 'city' | 'country' | 'location_type';
	type SortDirection = 'none' | 'asc' | 'desc';

	let loading = $state(true);
	let saving = $state(false);
	let savingSelection = $state(false);
	let editingSelected = $state(false);
	let error = $state('');
	let query = $state('');
	let city = $state('');
	let country = $state('');
	let locationType = $state('');
	let sortField = $state<LocationSortField | null>(null);
	let sortDirection = $state<SortDirection>('none');
	let locations = $state<Location[]>([]);
	let selectedId = $state('');
	let selectedLocationDetail = $state<LocationDetail | null>(null);

	let selectedEditForm = $state({
		label: '',
		address_line: '',
		city: '',
		region: '',
		country: '',
		location_type: 'Other',
		notes: ''
	});

	let createForm = $state({
		label: '',
		address_line: '',
		city: '',
		region: '',
		country: '',
		location_type: 'Other',
		notes: ''
	});

	const requestedLocationId = $derived(page.url.searchParams.get('id') ?? '');
	const sortedLocations = $derived(sortLocations(locations, sortField, sortDirection));
	const selectedLocation = $derived(sortedLocations.find((location) => location.id === selectedId) ?? sortedLocations[0] ?? null);

	$effect(() => {
		const nextId = requestedLocationId;
		if (nextId && nextId !== selectedId) {
			selectedId = nextId;
			editingSelected = false;
		}
	});

	$effect(() => {
		if (selectedId) {
			void loadSelectedLocation(selectedId);
		}
	});

	onMount(loadLocations);

	function sortLocations(items: Location[], field: LocationSortField | null, direction: SortDirection) {
		if (!field || direction === 'none') {
			return items;
		}
		const factor = direction === 'asc' ? 1 : -1;
		return [...items].sort((left, right) => ((left[field] || '').localeCompare(right[field] || '')) * factor);
	}

	function toggleSort(field: LocationSortField) {
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

	function sortIndicator(field: LocationSortField) {
		if (sortField !== field || sortDirection === 'none') return '';
		return sortDirection === 'asc' ? '↑' : '↓';
	}

	function syncSelectedEditForm(detail: LocationDetail) {
		selectedEditForm = {
			label: detail.label || '',
			address_line: detail.address_line || '',
			city: detail.city || '',
			region: detail.region || '',
			country: detail.country || '',
			location_type: detail.location_type || 'Other',
			notes: detail.notes || ''
		};
	}

	function locationTitle(location: Location | LocationDetail) {
		return location.label || location.address_line || location.city || 'Untitled location';
	}

	function locationSubtitle(location: Location | LocationDetail) {
		return [location.city, location.region, location.country].filter(Boolean).join(', ') || location.location_type || '—';
	}

	async function syncSelectedLocationInUrl(locationId: string) {
		const currentUrl = new URL(page.url);
		if (currentUrl.searchParams.get('id') === locationId) {
			return;
		}
		currentUrl.searchParams.set('id', locationId);
		await goto(currentUrl.pathname + currentUrl.search, {
			replaceState: true,
			noScroll: true,
			keepFocus: true,
			invalidateAll: false
		});
	}

	async function selectLocation(locationId: string) {
		selectedId = locationId;
		editingSelected = false;
		await syncSelectedLocationInUrl(locationId);
	}

	async function loadLocations() {
		loading = true;
		error = '';
		try {
			locations = await listLocations({
				q: query,
				city: city || undefined,
				country: country || undefined,
				location_type: locationType || undefined,
				limit: 150
			});
			const available = sortLocations(locations, sortField, sortDirection);
			if (requestedLocationId && available.some((location) => location.id === requestedLocationId)) {
				selectedId = requestedLocationId;
			} else if (!selectedId && available[0]) {
				selectedId = available[0].id;
			} else if (selectedId && !available.some((location) => location.id === selectedId) && available[0]) {
				selectedId = available[0].id;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load locations.';
		} finally {
			loading = false;
		}
	}

	async function loadSelectedLocation(locationId: string) {
		try {
			selectedLocationDetail = await getLocation(locationId);
			if (selectedLocationDetail && !editingSelected) {
				syncSelectedEditForm(selectedLocationDetail);
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load location detail.';
		}
	}

	function startEditingSelected() {
		if (!selectedLocationDetail) return;
		syncSelectedEditForm(selectedLocationDetail);
		editingSelected = true;
	}

	function cancelEditingSelected() {
		if (selectedLocationDetail) {
			syncSelectedEditForm(selectedLocationDetail);
		}
		editingSelected = false;
	}

	async function saveSelectedLocation() {
		if (!selectedId) return;
		savingSelection = true;
		error = '';
		try {
			selectedLocationDetail = await updateLocation(selectedId, {
				label: selectedEditForm.label || null,
				address_line: selectedEditForm.address_line || null,
				city: selectedEditForm.city || null,
				region: selectedEditForm.region || null,
				country: selectedEditForm.country || null,
				location_type: selectedEditForm.location_type || null,
				notes: selectedEditForm.notes || null
			});
			editingSelected = false;
			await loadLocations();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to update location.';
		} finally {
			savingSelection = false;
		}
	}

	async function submitLocation() {
		saving = true;
		error = '';
		try {
			const created = await createLocation({
				label: createForm.label || null,
				address_line: createForm.address_line || null,
				city: createForm.city || null,
				region: createForm.region || null,
				country: createForm.country || null,
				location_type: createForm.location_type || 'Other',
				notes: createForm.notes || null,
				latitude: null,
				longitude: null
			});
			createForm = {
				label: '',
				address_line: '',
				city: '',
				region: '',
				country: '',
				location_type: 'Other',
				notes: ''
			};
			await loadLocations();
			await selectLocation(created.id);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to create location.';
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head>
	<title>Locations | Kizuna</title>
</svelte:head>

<main class="shell">
	<header class="topbar">
		<div>
			<a class="brand" href={resolve('/')}>Kizuna</a>
			<h1>Locations</h1>
		</div>
		<p class="meta">{locations.length} records</p>
	</header>

	<section class="toolbar">
		<label>
			<span>Search</span>
			<input bind:value={query} placeholder="Label, street, city, country, notes" />
		</label>
		<label>
			<span>City</span>
			<input bind:value={city} placeholder="Filter city" />
		</label>
		<label>
			<span>Country</span>
			<input bind:value={country} placeholder="Filter country" />
		</label>
		<label>
			<span>Type</span>
			<input bind:value={locationType} placeholder="Cafe, Office, Venue" />
		</label>
		<button type="button" onclick={loadLocations}>Refresh</button>
	</section>

	{#if error}
		<p class="notice">{error}</p>
	{/if}

	<section class="workspace">
		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>Directory</h2>
					<span>{loading ? 'Loading…' : 'Structured places'}</span>
				</div>
			</div>
			<div class="table">
				<div class="row head">
					<button class="sort-button" type="button" onclick={() => toggleSort('label')}>Label {sortIndicator('label')}</button>
					<button class="sort-button" type="button" onclick={() => toggleSort('city')}>City {sortIndicator('city')}</button>
					<button class="sort-button" type="button" onclick={() => toggleSort('country')}>Country {sortIndicator('country')}</button>
				</div>
				{#each sortedLocations as location (location.id)}
					<button
						class:selected={selectedLocation?.id === location.id}
						class="row item"
						onclick={() => {
							void selectLocation(location.id);
						}}
					>
						<span>
							<strong>{locationTitle(location)}</strong>
							<small>{location.address_line || location.location_type}</small>
						</span>
						<span>{location.city || '—'}</span>
						<span>{location.country || '—'}</span>
					</button>
				{/each}
			</div>
		</section>

		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>Selected record</h2>
					<span>{selectedLocationDetail ? locationSubtitle(selectedLocationDetail) : 'No selection'}</span>
				</div>
				{#if selectedLocationDetail}
					<div class="inline-actions">
						{#if editingSelected}
							<button type="button" onclick={cancelEditingSelected}>Cancel</button>
							<button type="button" onclick={saveSelectedLocation} disabled={savingSelection}>
								{savingSelection ? 'Saving…' : 'Save'}
							</button>
						{:else}
							<button type="button" onclick={startEditingSelected}>Edit</button>
						{/if}
					</div>
				{/if}
			</div>
			{#if selectedLocationDetail}
				<div class="detail-grid">
					{#if editingSelected}
						<label>
							<span>Label</span>
							<input bind:value={selectedEditForm.label} />
						</label>
						<label>
							<span>Location type</span>
							<input bind:value={selectedEditForm.location_type} />
						</label>
						<label class="wide">
							<span>Street / address line</span>
							<input bind:value={selectedEditForm.address_line} />
						</label>
						<label>
							<span>City</span>
							<input bind:value={selectedEditForm.city} />
						</label>
						<label>
							<span>Region</span>
							<input bind:value={selectedEditForm.region} />
						</label>
						<label>
							<span>Country</span>
							<input bind:value={selectedEditForm.country} />
						</label>
						<label class="wide">
							<span>Notes</span>
							<textarea bind:value={selectedEditForm.notes} rows="5"></textarea>
						</label>
					{:else}
						<div class="field">
							<span>Label</span>
							<strong>{locationTitle(selectedLocationDetail)}</strong>
						</div>
						<div class="field">
							<span>Type</span>
							<strong>{selectedLocationDetail.location_type || '—'}</strong>
						</div>
						<div class="field wide">
							<span>Address</span>
							<p>{selectedLocationDetail.address_line || 'No street recorded.'}</p>
						</div>
						<div class="field">
							<span>City</span>
							<strong>{selectedLocationDetail.city || '—'}</strong>
						</div>
						<div class="field">
							<span>Region</span>
							<strong>{selectedLocationDetail.region || '—'}</strong>
						</div>
						<div class="field">
							<span>Country</span>
							<strong>{selectedLocationDetail.country || '—'}</strong>
						</div>
						<div class="field wide">
							<span>Linked people</span>
							<ul>
								{#if selectedLocationDetail.linked_people.length}
									{#each selectedLocationDetail.linked_people as person (person.id)}
										<li>
											<a href={resolve(`/people?id=${person.entity_id}`)}>{person.title}</a>
											{#if person.is_primary}<em> · primary</em>{/if}
										</li>
									{/each}
								{:else}
									<li>No people linked yet.</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>Linked organizations</span>
							<ul>
								{#if selectedLocationDetail.linked_organizations.length}
									{#each selectedLocationDetail.linked_organizations as organization (organization.id)}
										<li>
											<a href={resolve(`/organizations?id=${organization.entity_id}`)}>{organization.title}</a>
											{#if organization.is_primary}<em> · primary</em>{/if}
										</li>
									{/each}
								{:else}
									<li>No organizations linked yet.</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>Recent events</span>
							<ul>
								{#if selectedLocationDetail.recent_events.length}
									{#each selectedLocationDetail.recent_events as event (event.id)}
										<li><a href={resolve(`/events?id=${event.id}`)}>{event.title}</a> · {new Date(event.started_at).toLocaleString()}</li>
									{/each}
								{:else}
									<li>No events linked yet.</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>Notes</span>
							<p>{selectedLocationDetail.notes || 'No notes yet.'}</p>
						</div>
					{/if}
				</div>
			{:else}
				<p class="notice">No location selected.</p>
			{/if}
		</section>

		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>Actions</h2>
					<span>Capture reusable places</span>
				</div>
			</div>
			<div class="action-stack">
				<form onsubmit={(event) => {
					event.preventDefault();
					submitLocation();
				}}>
					<h3>New location</h3>
					<label>
						<span>Label</span>
						<input bind:value={createForm.label} placeholder="Blue Bottle Mint Plaza" />
					</label>
					<label>
						<span>Location type</span>
						<input bind:value={createForm.location_type} placeholder="Cafe, Office, Venue" />
					</label>
					<label class="wide">
						<span>Street / address line</span>
						<input bind:value={createForm.address_line} />
					</label>
					<label>
						<span>City</span>
						<input bind:value={createForm.city} />
					</label>
					<label>
						<span>Region</span>
						<input bind:value={createForm.region} />
					</label>
					<label>
						<span>Country</span>
						<input bind:value={createForm.country} />
					</label>
					<label class="wide">
						<span>Notes</span>
						<textarea bind:value={createForm.notes} rows="4"></textarea>
					</label>
					<button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Create location'}</button>
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
		grid-template-columns: minmax(0, 1.4fr) repeat(3, minmax(0, 0.7fr)) auto;
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

	h2 {
		margin: 0;
		font-size: 0.9rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	label {
		display: grid;
		gap: 0.35rem;
	}

	input,
	button,
	textarea {
		width: 100%;
		border: 1px solid var(--line);
		background: var(--panel);
		padding: 0.62rem 0.72rem;
		color: var(--text);
	}

	.panel,
	.notice {
		border: 1px solid var(--line-strong);
		background: var(--panel-strong);
		box-shadow: var(--shadow);
	}

	.panel {
		min-height: 24rem;
	}

	.panel-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.75rem 0.85rem;
		border-bottom: 1px solid var(--line);
	}

	.inline-actions {
		display: flex;
		gap: 0.5rem;
	}

	.table {
		display: grid;
	}

	.row {
		display: grid;
		grid-template-columns: minmax(0, 1.3fr) 0.8fr 0.7fr;
		gap: 0.75rem;
		align-items: start;
		padding: 0.75rem 0.85rem;
		border-bottom: 1px solid var(--line);
		text-align: left;
		background: transparent;
	}

	.row.item {
		cursor: pointer;
		border: 0;
		border-bottom: 1px solid var(--line);
	}

	.row.item.selected {
		background: var(--selection-row-bg);
	}

	.row span {
		display: grid;
		gap: 0.2rem;
	}

	.row small {
		color: var(--muted);
	}

	.sort-button {
		border: 0;
		padding: 0;
		background: transparent;
		text-align: left;
		color: inherit;
		cursor: pointer;
		font: inherit;
	}

	.detail-grid,
	form {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.85rem;
		padding: 0.85rem;
	}

	.field,
	label,
	.wide {
		min-width: 0;
	}

	.field strong,
	.field p,
	.field ul {
		margin: 0.2rem 0 0;
	}

	.field p,
	.field li {
		color: var(--text);
	}

	.wide {
		grid-column: 1 / -1;
	}

	ul {
		padding-left: 1rem;
	}

	.action-stack {
		padding: 0.85rem;
	}

	form {
		padding: 0;
	}

	h3 {
		grid-column: 1 / -1;
		margin: 0 0 0.35rem;
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.notice {
		margin-top: 1rem;
		padding: 0.85rem;
	}

	@media (max-width: 1100px) {
		.toolbar,
		.workspace {
			grid-template-columns: 1fr;
		}

		.row,
		.detail-grid,
		form {
			grid-template-columns: 1fr;
		}
	}
</style>
