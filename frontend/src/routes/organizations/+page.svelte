<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import PreviewLink from '$lib/components/PreviewLink.svelte';
	import {
		addOrganizationLocation,
		addOrganizationTag,
		createLocation,
		createOrganization,
		getOrganization,
		listLocations,
		listOrganizations,
		updateOrganization,
		type Location,
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
	let locations = $state<Location[]>([]);
	let selectedId = $state('');
	let selectedOrganizationDetail = $state<OrganizationDetail | null>(null);

	let selectedEditForm = $state({
		name: '',
		type: 'Other',
		industry: '',
		selected_location_id: '',
		location_search: '',
		website: '',
		description: '',
		notes: ''
	});

	let createForm = $state({
		name: '',
		type: 'Other',
		industry: '',
		selected_location_id: '',
		location_search: '',
		website: '',
		description: '',
		notes: ''
	});

	let tagForm = $state({ name: '' });
	let locationForm = $state({
		location_search: '',
		selected_location_id: '',
		link_notes: '',
		is_primary: true
	});
	let showCreateLocationModal = $state(false);
	let locationCreateForm = $state({
		label: '',
		address_line: '',
		city: '',
		region: '',
		country: '',
		location_type: 'Work',
		notes: ''
	});

	const requestedOrganizationId = $derived(page.url.searchParams.get('id') ?? '');
	const sortedOrganizations = $derived(sortOrganizations(organizations, sortField, sortDirection));
	const selectedOrganization = $derived(
		sortedOrganizations.find((organization) => organization.id === selectedId) ?? sortedOrganizations[0] ?? null
	);

	$effect(() => {
		const nextId = requestedOrganizationId;
		if (nextId && nextId !== selectedId) {
			selectedId = nextId;
			editingSelected = false;
		}
	});

	$effect(() => {
		if (selectedId) {
			void loadSelectedOrganization(selectedId);
		}
	});

	onMount(async () => {
		await Promise.all([loadOrganizations(), loadLocations()]);
	});

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
		const primaryStructuredLocation = detail.locations.find((item) => item.is_primary)?.location ?? detail.locations[0]?.location ?? null;
		selectedEditForm = {
			name: detail.name || '',
			type: detail.type || 'Other',
			industry: detail.industry || '',
			selected_location_id: primaryStructuredLocation?.id || '',
			location_search: primaryStructuredLocation ? locationOptionLabel(primaryStructuredLocation) : detail.location || '',
			website: detail.website || '',
			description: detail.description || '',
			notes: detail.notes || ''
		};
	}

	function locationSummary(location: Location | null | undefined) {
		if (!location) return '';
		return [location.city, location.region, location.country].filter(Boolean).join(', ') || location.label || location.address_line || '';
	}

	function selectedLocationById(locationId: string) {
		return locations.find((location) => location.id === locationId) ?? null;
	}

	async function syncSelectedOrganizationInUrl(organizationId: string) {
		const currentUrl = new URL(page.url);
		if (currentUrl.searchParams.get('id') === organizationId) {
			return;
		}
		currentUrl.searchParams.set('id', organizationId);
		await goto(currentUrl.pathname + currentUrl.search, {
			replaceState: true,
			noScroll: true,
			keepFocus: true,
			invalidateAll: false
		});
	}

	async function selectOrganization(organizationId: string) {
		selectedId = organizationId;
		editingSelected = false;
		await syncSelectedOrganizationInUrl(organizationId);
	}

	async function loadOrganizations() {
		loading = true;
		error = '';
		try {
			organizations = await listOrganizations({ q: query, limit: 100, industry: industry || undefined });
			const available = sortOrganizations(organizations, sortField, sortDirection);
			if (requestedOrganizationId && available.some((organization) => organization.id === requestedOrganizationId)) {
				selectedId = requestedOrganizationId;
			} else if (!selectedId && available[0]) {
				selectedId = available[0].id;
			} else if (selectedId && !available.some((organization) => organization.id === selectedId) && available[0]) {
				selectedId = available[0].id;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load organizations.';
		} finally {
			loading = false;
		}
	}

	async function loadLocations() {
		try {
			locations = await listLocations({ limit: 200 });
			if (!locationForm.selected_location_id && locations[0]) {
				locationForm.selected_location_id = locations[0].id;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load locations.';
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
			const selectedLocation = selectedLocationById(selectedEditForm.selected_location_id);
			selectedOrganizationDetail = await updateOrganization(selectedId, {
				name: selectedEditForm.name,
				type: selectedEditForm.type,
				industry: selectedEditForm.industry || null,
				location: locationSummary(selectedLocation) || null,
				website: selectedEditForm.website || null,
				description: selectedEditForm.description || null,
				notes: selectedEditForm.notes || null
			});
			if (selectedLocation) {
				selectedOrganizationDetail = await addOrganizationLocation(selectedId, {
					location_id: selectedLocation.id,
					is_primary: true
				});
			}
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
			const selectedLocation = selectedLocationById(createForm.selected_location_id);
			const created = await createOrganization({
				name: createForm.name,
				type: createForm.type,
				industry: createForm.industry || undefined,
				location: locationSummary(selectedLocation) || undefined,
				website: createForm.website || undefined,
				description: createForm.description || undefined,
				notes: createForm.notes || undefined
			});
			if (selectedLocation) {
				await addOrganizationLocation(created.id, {
					location_id: selectedLocation.id,
					is_primary: true
				});
			}
			createForm = {
				name: '',
				type: 'Other',
				industry: '',
				selected_location_id: '',
				location_search: '',
				website: '',
				description: '',
				notes: ''
			};
			await loadOrganizations();
			await selectOrganization(created.id);
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
		if (!selectedId || !locationForm.selected_location_id) return;
		try {
			selectedOrganizationDetail = await addOrganizationLocation(selectedId, {
				location_id: locationForm.selected_location_id,
				is_primary: locationForm.is_primary,
				notes: locationForm.link_notes || undefined
			});
			locationForm = {
				location_search: '',
				selected_location_id: locations[0]?.id || '',
				link_notes: '',
				is_primary: true
			};
			await loadOrganizations();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to add location.';
		}
	}

	function filteredLocations() {
		const search = locationForm.location_search.trim().toLowerCase();
		if (!search) return locations;
		return locations.filter((location) =>
			[
				location.label,
				location.address_line,
				location.city,
				location.region,
				location.country,
				location.location_type,
				location.notes
			]
				.filter(Boolean)
				.some((value) => value!.toLowerCase().includes(search))
		);
	}

	function locationOptionLabel(location: Location) {
		const title = location.label || location.address_line || location.city || 'Untitled location';
		const subtitle = [location.city, location.region, location.country].filter(Boolean).join(', ');
		return subtitle ? `${title} · ${subtitle}` : title;
	}

	async function submitNewLocation() {
		try {
			const created = await createLocation({
				label: locationCreateForm.label || null,
				address_line: locationCreateForm.address_line || null,
				city: locationCreateForm.city || null,
				region: locationCreateForm.region || null,
				country: locationCreateForm.country || null,
				location_type: locationCreateForm.location_type || 'Work',
				notes: locationCreateForm.notes || null,
				latitude: null,
				longitude: null
			});
			await loadLocations();
			locationForm.selected_location_id = created.id;
			locationForm.location_search = locationOptionLabel(created);
			locationCreateForm = {
				label: '',
				address_line: '',
				city: '',
				region: '',
				country: '',
				location_type: 'Work',
				notes: ''
			};
			showCreateLocationModal = false;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to create location.';
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
							void selectOrganization(organization.id);
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
						<label class="wide">
							<span>Primary location search</span>
							<input bind:value={selectedEditForm.location_search} placeholder="HQ, warehouse, branch, city" />
						</label>
						<label class="wide">
							<span>Primary location</span>
							<select bind:value={selectedEditForm.selected_location_id} size="5">
								<option value="">No primary location</option>
								{#each locations.filter((location) =>
									!selectedEditForm.location_search.trim()
										? true
										: [location.label, location.address_line, location.city, location.region, location.country, location.location_type, location.notes]
												.filter(Boolean)
												.some((value) => value!.toLowerCase().includes(selectedEditForm.location_search.trim().toLowerCase()))
								) as location (location.id)}
									<option value={location.id}>{locationOptionLabel(location)}</option>
								{/each}
							</select>
						</label>
						<div class="wide inline-actions">
							<button type="button" onclick={() => (showCreateLocationModal = true)}>Create new location</button>
						</div>
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
										<li><a href={resolve(`/locations?id=${item.location.id}`)}>{item.location.city || item.location.label || '—'} {item.location.country || ''}</a></li>
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
					<label class="wide">
						<span>Primary location search</span>
						<input bind:value={createForm.location_search} placeholder="HQ, warehouse, branch, city" />
					</label>
					<label class="wide">
						<span>Primary location</span>
						<select bind:value={createForm.selected_location_id} size="5">
							<option value="">No primary location</option>
							{#each locations.filter((location) =>
								!createForm.location_search.trim()
									? true
									: [location.label, location.address_line, location.city, location.region, location.country, location.location_type, location.notes]
											.filter(Boolean)
											.some((value) => value!.toLowerCase().includes(createForm.location_search.trim().toLowerCase()))
							) as location (location.id)}
								<option value={location.id}>{locationOptionLabel(location)}</option>
							{/each}
						</select>
					</label>
					<div class="wide inline-actions">
						<button type="button" onclick={() => (showCreateLocationModal = true)}>Create new location</button>
					</div>
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
					<label class="wide">
						<span>Search existing locations</span>
						<input bind:value={locationForm.location_search} placeholder="HQ, warehouse, branch, city" />
					</label>
					<label class="wide">
						<span>Choose location</span>
						<select bind:value={locationForm.selected_location_id} size="6">
							{#each filteredLocations() as location (location.id)}
								<option value={location.id}>{locationOptionLabel(location)}</option>
							{/each}
						</select>
					</label>
					<div class="wide inline-actions">
						<button type="button" onclick={() => (showCreateLocationModal = true)}>Create new location</button>
					</div>
					<label class="wide">
						<span>Link notes</span>
						<textarea bind:value={locationForm.link_notes} rows="2" placeholder="Why this location matters for this organization"></textarea>
					</label>
					<label class="checkbox">
						<input bind:checked={locationForm.is_primary} type="checkbox" />
						<span>Primary location</span>
					</label>
					<button type="submit" disabled={!locationForm.selected_location_id}>Add location</button>
				</form>
			</div>
		</section>
	</section>

	{#if showCreateLocationModal}
		<div
			class="modal-backdrop"
			role="button"
			tabindex="0"
			aria-label="Close create location modal"
			onclick={() => (showCreateLocationModal = false)}
			onkeydown={(event) => {
				if (event.key === 'Escape' || event.key === 'Enter' || event.key === ' ') {
					showCreateLocationModal = false;
				}
			}}
		>
			<div
				class="modal-card"
				role="dialog"
				tabindex="-1"
				aria-modal="true"
				aria-label="Create location"
				onclick={(event) => event.stopPropagation()}
				onkeydown={(event) => event.stopPropagation()}
			>
				<form onsubmit={(event) => {
					event.preventDefault();
					submitNewLocation();
				}}>
					<h3>Create location</h3>
					<label>
						<span>Label</span>
						<input bind:value={locationCreateForm.label} placeholder="HQ, warehouse, branch" />
					</label>
					<label class="wide">
						<span>Street / address line</span>
						<input bind:value={locationCreateForm.address_line} />
					</label>
					<label>
						<span>City</span>
						<input bind:value={locationCreateForm.city} />
					</label>
					<label>
						<span>Region</span>
						<input bind:value={locationCreateForm.region} />
					</label>
					<label>
						<span>Country</span>
						<input bind:value={locationCreateForm.country} />
					</label>
					<label>
						<span>Location type</span>
						<input bind:value={locationCreateForm.location_type} placeholder="Work, Warehouse, Office" />
					</label>
					<label class="wide">
						<span>Location notes</span>
						<textarea bind:value={locationCreateForm.notes} rows="3"></textarea>
					</label>
					<div class="wide modal-actions">
						<button type="button" onclick={() => (showCreateLocationModal = false)}>Cancel</button>
						<button type="submit">Create and select</button>
					</div>
				</form>
			</div>
		</div>
	{/if}
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

	.checkbox {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}

	.checkbox input {
		width: auto;
	}

	.checkbox span {
		font-size: 0.8rem;
		letter-spacing: normal;
		text-transform: none;
		color: var(--text);
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

	.modal-backdrop {
		position: fixed;
		inset: 0;
		display: grid;
		place-items: center;
		padding: 1.25rem;
		background: rgba(17, 17, 17, 0.38);
		z-index: 40;
	}

	.modal-card {
		width: min(42rem, 100%);
		border: 1px solid var(--line-strong);
		background: var(--panel-strong);
		box-shadow: var(--shadow);
	}

	.modal-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.75rem;
	}

	.modal-actions button,
	.inline-actions button {
		width: auto;
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
