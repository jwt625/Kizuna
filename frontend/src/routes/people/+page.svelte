<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import DateTimeField from '$lib/components/DateTimeField.svelte';
	import PreviewLink from '$lib/components/PreviewLink.svelte';
	import {
		addPersonLocation,
		addPersonOrganizationRole,
		addPersonTag,
		completeReminder,
		createEvent,
		createLocation,
		createPerson,
		createReminder,
		getPerson,
		listLocations,
		listOrganizations,
		listPeople,
		snoozeReminder,
		updatePerson,
		type Location,
		type Organization,
		type Person,
		type PersonDetail
	} from '$lib/api';
	import { normalizeExternalHref } from '$lib/utils/links';

	const categoryOptions = ['All', 'New', 'Active', 'Warm', 'Watch'];
	const contactTypeOptions = ['Email', 'Phone', 'WeChat', 'WhatsApp', 'Telegram', 'Website'];
	const peoplePageSize = 100;
	type PersonSortField = 'display_name' | 'relationship_category' | 'primary_location' | 'relationship_score';
	type SortDirection = 'none' | 'asc' | 'desc';
	type EditableContactMethod = {
		id: string;
		type: string;
		value: string;
		label: string;
		is_primary: boolean;
		notes: string | null;
	};

	let loading = $state(true);
	let loadingMorePeople = $state(false);
	let hasMorePeople = $state(true);
	let saving = $state(false);
	let savingSelection = $state(false);
	let editingSelected = $state(false);
	let error = $state('');
	let query = $state('');
	let category = $state('All');
	let city = $state('');
	let personSortField = $state<PersonSortField | null>(null);
	let personSortDirection = $state<SortDirection>('none');
	let people = $state<Person[]>([]);
	let peopleOffset = $state(0);
	let organizations = $state<Organization[]>([]);
	let locations = $state<Location[]>([]);
	let selectedId = $state('');
	let selectedPersonDetail = $state<PersonDetail | null>(null);
	let directoryViewport: HTMLDivElement | null = null;
	let hasLoadedInitialPeople = $state(false);
	let searchDebounceHandle: ReturnType<typeof setTimeout> | null = null;

	let selectedEditForm = $state({
		display_name: '',
		given_name: '',
		family_name: '',
		selected_location_id: '',
		location_search: '',
		first_met_date: '',
		relationship_summary: '',
		how_we_met: '',
		contact_methods: [] as EditableContactMethod[],
		profile_platform: 'LinkedIn',
		profile_url: '',
		notes: ''
	});

	let form = $state({
		display_name: '',
		given_name: '',
		family_name: '',
		nickname: '',
		pronouns: '',
		short_bio: '',
		first_met_date: '',
		selected_location_id: '',
		location_search: '',
		relationship_summary: '',
		how_we_met: '',
		contact_type: 'Email',
		contact_value: '',
		contact_label: '',
		contact_notes: '',
		profile_platform: 'LinkedIn',
		profile_url: '',
		profile_label: '',
		profile_notes: '',
		notes: ''
	});

	let eventForm = $state({
		title: '',
		type: 'One-on-one',
		started_at: '',
		ended_at: '',
		duration_minutes: 45,
		context: '',
		summary: '',
		notes: '',
		sentiment: ''
	});

	let reminderForm = $state({
		title: '',
		due_at: '',
		priority: 'Normal',
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
		location_type: 'Home',
		notes: ''
	});
	let roleForm = $state({
		organization_id: '',
		title: '',
		role_type: '',
		start_date: '',
		end_date: '',
		is_current: true,
		notes: ''
	});

	const requestedPersonId = $derived(page.url.searchParams.get('id') ?? '');
	const sortedPeople = $derived(sortPeople(people, personSortField, personSortDirection));
	const selectedPerson = $derived(sortedPeople.find((person) => person.id === selectedId) ?? sortedPeople[0] ?? null);

	$effect(() => {
		const nextId = requestedPersonId;
		if (nextId && nextId !== selectedId) {
			selectedId = nextId;
			editingSelected = false;
		}
	});

	$effect(() => {
		if (selectedId) {
			void loadSelectedPerson(selectedId);
		}
	});

	onMount(async () => {
		await Promise.all([loadPeople(), loadOrganizations(), loadLocations()]);
		hasLoadedInitialPeople = true;
	});

	$effect(() => {
		query;
		category;
		city;

			if (!hasLoadedInitialPeople) return;
			if (searchDebounceHandle) clearTimeout(searchDebounceHandle);
			searchDebounceHandle = setTimeout(() => {
				void loadPeople();
			}, 300);

		return () => {
			if (searchDebounceHandle) {
				clearTimeout(searchDebounceHandle);
				searchDebounceHandle = null;
			}
		};
	});

	function compareText(left: string | null | undefined, right: string | null | undefined, direction: Exclude<SortDirection, 'none'>) {
		const factor = direction === 'asc' ? 1 : -1;
		return (left || '').localeCompare(right || '') * factor;
	}

	function sortPeople(items: Person[], field: PersonSortField | null, direction: SortDirection) {
		if (!field || direction === 'none') {
			return items;
		}
		return [...items].sort((left, right) => {
			if (field === 'relationship_score') {
				const factor = direction === 'asc' ? 1 : -1;
				return ((left.relationship_score || 0) - (right.relationship_score || 0)) * factor;
			}
			return compareText(`${left[field] ?? ''}`, `${right[field] ?? ''}`, direction);
		});
	}

	function toggleSort(field: PersonSortField) {
		if (personSortField !== field) {
			personSortField = field;
			personSortDirection = 'asc';
			return;
		}
		if (personSortDirection === 'none') {
			personSortDirection = 'asc';
			return;
		}
		if (personSortDirection === 'asc') {
			personSortDirection = 'desc';
			return;
		}
		personSortField = null;
		personSortDirection = 'none';
	}

	function sortIndicator(field: PersonSortField) {
		if (personSortField !== field || personSortDirection === 'none') return '';
		return personSortDirection === 'asc' ? '↑' : '↓';
	}

	function syncSelectedEditForm(detail: PersonDetail) {
		const primaryProfile = detail.external_profiles[0] ?? null;
		const primaryStructuredLocation = detail.locations.find((item) => item.is_primary)?.location ?? detail.locations[0]?.location ?? null;
		selectedEditForm = {
			display_name: detail.display_name || '',
			given_name: detail.given_name || '',
			family_name: detail.family_name || '',
			selected_location_id: primaryStructuredLocation?.id || '',
			location_search: primaryStructuredLocation ? locationOptionLabel(primaryStructuredLocation) : detail.primary_location || '',
			first_met_date: detail.first_met_date || '',
			relationship_summary: detail.relationship_summary || '',
			how_we_met: detail.how_we_met || '',
			contact_methods: detail.contact_methods.length
				? detail.contact_methods.map((method) => ({
						id: method.id,
						type: method.type,
						value: method.value,
						label: method.label || '',
						is_primary: method.is_primary,
						notes: method.notes
					}))
				: [createEmptyContactMethod()],
			profile_platform: primaryProfile?.platform || 'LinkedIn',
			profile_url: primaryProfile?.url_or_handle || '',
			notes: detail.notes || ''
		};
	}

	function createEmptyContactMethod(): EditableContactMethod {
		return {
			id: crypto.randomUUID(),
			type: 'Email',
			value: '',
			label: '',
			is_primary: false,
			notes: null
		};
	}

	function locationSummary(location: Location | null | undefined) {
		if (!location) return '';
		return [location.city, location.region, location.country].filter(Boolean).join(', ') || location.label || location.address_line || '';
	}

	function selectedLocationById(locationId: string) {
		return locations.find((location) => location.id === locationId) ?? null;
	}

	async function syncSelectedPersonInUrl(personId: string) {
		const currentUrl = new URL(page.url);
		if (currentUrl.searchParams.get('id') === personId) {
			return;
		}
		currentUrl.searchParams.set('id', personId);
		await goto(currentUrl.pathname + currentUrl.search, {
			replaceState: true,
			noScroll: true,
			keepFocus: true,
			invalidateAll: false
		});
	}

	async function selectPerson(personId: string) {
		selectedId = personId;
		editingSelected = false;
		await syncSelectedPersonInUrl(personId);
	}

	function addEditableContactMethod() {
		selectedEditForm.contact_methods = [...selectedEditForm.contact_methods, createEmptyContactMethod()];
	}

	function removeEditableContactMethod(contactId: string) {
		const remaining = selectedEditForm.contact_methods.filter((method) => method.id !== contactId);
		if (!remaining.length) {
			selectedEditForm.contact_methods = [createEmptyContactMethod()];
			return;
		}
		const hasPrimary = remaining.some((method) => method.is_primary);
		selectedEditForm.contact_methods = remaining.map((method, index) => ({
			...method,
			is_primary: hasPrimary ? method.is_primary : index === 0
		}));
	}

	function setPrimaryContactMethod(contactId: string) {
		selectedEditForm.contact_methods = selectedEditForm.contact_methods.map((method) => ({
			...method,
			is_primary: method.id === contactId
		}));
	}

	function buildUpdatedContactMethods() {
		const populated = selectedEditForm.contact_methods.filter((method) => method.value.trim());
		if (!populated.length) return [];
		const hasPrimary = populated.some((method) => method.is_primary);
		return populated.map((method, index) => ({
			type: method.type,
			value: method.value.trim(),
			label: method.label.trim() || null,
			is_primary: hasPrimary ? method.is_primary : index === 0,
			notes: method.notes
		}));
	}

	function buildUpdatedExternalProfiles(detail: PersonDetail) {
		const existing = detail.external_profiles;
		const primaryProfile = selectedEditForm.profile_url
			? {
					platform: selectedEditForm.profile_platform,
					url_or_handle: selectedEditForm.profile_url,
					label: existing[0]?.label || null,
					notes: existing[0]?.notes || null,
					last_checked_at: existing[0]?.last_checked_at || null
				}
			: null;

		return existing.reduce<
			Array<{
				platform: string;
				url_or_handle: string;
				label: string | null;
				notes: string | null;
				last_checked_at: string | null;
			}>
		>((items, profile, index) => {
			if (index === 0) {
				if (primaryProfile) items.push(primaryProfile);
				return items;
			}
			items.push({
				platform: profile.platform,
				url_or_handle: profile.url_or_handle,
				label: profile.label,
				notes: profile.notes,
				last_checked_at: profile.last_checked_at
			});
			return items;
		}, existing.length ? [] : primaryProfile ? [primaryProfile] : []);
	}

	function syncSelectedPersonFromAvailable(available: Person[]) {
		if (requestedPersonId && available.some((person) => person.id === requestedPersonId)) {
			selectedId = requestedPersonId;
		} else if (!selectedId && available[0]) {
			selectedId = available[0].id;
		} else if (selectedId && !available.some((person) => person.id === selectedId) && available[0]) {
			selectedId = available[0].id;
		}
	}

	async function loadPeople(reset = true) {
		if (reset) {
			loading = true;
			peopleOffset = 0;
			hasMorePeople = true;
		} else {
			if (!hasMorePeople || loadingMorePeople) return;
			loadingMorePeople = true;
		}
		error = '';
		try {
			const nextPeople = await listPeople({
				q: query,
				relationship_category: category === 'All' ? undefined : category,
				city: city || undefined,
				limit: peoplePageSize,
				offset: reset ? 0 : peopleOffset
			});
			people = reset ? nextPeople : [...people, ...nextPeople];
			peopleOffset = people.length;
			hasMorePeople = nextPeople.length === peoplePageSize;
			syncSelectedPersonFromAvailable(sortPeople(people, personSortField, personSortDirection));
			if (reset && directoryViewport) {
				directoryViewport.scrollTop = 0;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load people.';
		} finally {
			if (reset) {
				loading = false;
			} else {
				loadingMorePeople = false;
			}
		}
	}

	async function maybeLoadMorePeople() {
		if (!directoryViewport || loading || loadingMorePeople || !hasMorePeople) return;
		const threshold = 120;
		const remaining =
			directoryViewport.scrollHeight - directoryViewport.scrollTop - directoryViewport.clientHeight;
		if (remaining <= threshold) {
			await loadPeople(false);
		}
	}

	function refreshPeopleNow() {
		if (searchDebounceHandle) {
			clearTimeout(searchDebounceHandle);
			searchDebounceHandle = null;
		}
		void loadPeople();
	}

	async function loadOrganizations() {
		try {
			organizations = await listOrganizations({ limit: 100 });
			if (!roleForm.organization_id && organizations[0]) {
				roleForm.organization_id = organizations[0].id;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load organizations.';
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

	async function loadSelectedPerson(personId: string) {
		try {
			selectedPersonDetail = await getPerson(personId);
			if (selectedPersonDetail && !editingSelected) {
				syncSelectedEditForm(selectedPersonDetail);
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load person detail.';
		}
	}

	function startEditingSelected() {
		if (!selectedPersonDetail) return;
		syncSelectedEditForm(selectedPersonDetail);
		editingSelected = true;
	}

	function cancelEditingSelected() {
		if (selectedPersonDetail) {
			syncSelectedEditForm(selectedPersonDetail);
		}
		editingSelected = false;
	}

	async function saveSelectedPerson() {
		if (!selectedId || !selectedPersonDetail) return;
		savingSelection = true;
		error = '';
		try {
			const selectedLocation = selectedLocationById(selectedEditForm.selected_location_id);
			selectedPersonDetail = await updatePerson(selectedId, {
				display_name: selectedEditForm.display_name,
				given_name: selectedEditForm.given_name || null,
				family_name: selectedEditForm.family_name || null,
				primary_location: locationSummary(selectedLocation) || null,
				first_met_date: selectedEditForm.first_met_date || null,
				relationship_summary: selectedEditForm.relationship_summary || null,
				how_we_met: selectedEditForm.how_we_met || null,
				contact_methods: buildUpdatedContactMethods(),
				external_profiles: buildUpdatedExternalProfiles(selectedPersonDetail),
				notes: selectedEditForm.notes || null
			});
			if (selectedLocation) {
				selectedPersonDetail = await addPersonLocation(selectedId, {
					location_id: selectedLocation.id,
					is_primary: true
				});
			}
			editingSelected = false;
			await loadPeople();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to update person.';
		} finally {
			savingSelection = false;
		}
	}

	async function submitPerson() {
		saving = true;
		error = '';
		try {
			const selectedLocation = selectedLocationById(form.selected_location_id);
			const created = await createPerson({
				display_name: form.display_name,
				given_name: form.given_name || undefined,
				family_name: form.family_name || undefined,
				nickname: form.nickname || undefined,
				pronouns: form.pronouns || undefined,
				short_bio: form.short_bio || undefined,
				first_met_date: form.first_met_date || undefined,
				primary_location: locationSummary(selectedLocation) || undefined,
				relationship_summary: form.relationship_summary || undefined,
				how_we_met: form.how_we_met || undefined,
				notes: form.notes || undefined,
				contact_methods: form.contact_value
					? [
							{
								type: form.contact_type,
								value: form.contact_value,
								label: form.contact_label || undefined,
								is_primary: true,
								notes: form.contact_notes || undefined
							}
						]
					: [],
				external_profiles: form.profile_url
					? [
							{
								platform: form.profile_platform,
								url_or_handle: form.profile_url,
								label: form.profile_label || undefined,
								notes: form.profile_notes || undefined
							}
						]
					: []
			});
			if (selectedLocation) {
				await addPersonLocation(created.id, {
					location_id: selectedLocation.id,
					is_primary: true
				});
			}
			form = {
				display_name: '',
				given_name: '',
				family_name: '',
				nickname: '',
				pronouns: '',
				short_bio: '',
				first_met_date: '',
				selected_location_id: '',
				location_search: '',
				relationship_summary: '',
				how_we_met: '',
				contact_type: 'Email',
				contact_value: '',
				contact_label: '',
				contact_notes: '',
				profile_platform: 'LinkedIn',
				profile_url: '',
				profile_label: '',
				profile_notes: '',
				notes: ''
			};
			await loadPeople();
			await selectPerson(created.id);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to create person.';
		} finally {
			saving = false;
		}
	}

	async function submitEvent() {
		if (!selectedId || !eventForm.started_at || !eventForm.title) return;
		try {
			await createEvent({
				title: eventForm.title,
				type: eventForm.type,
				started_at: new Date(eventForm.started_at).toISOString(),
				ended_at: eventForm.ended_at ? new Date(eventForm.ended_at).toISOString() : undefined,
				duration_minutes: Number(eventForm.duration_minutes) || undefined,
				context: eventForm.context || undefined,
				summary: eventForm.summary || undefined,
				notes: eventForm.notes || undefined,
				sentiment: eventForm.sentiment || undefined,
				person_ids: [selectedId]
			});
			eventForm = {
				title: '',
				type: 'One-on-one',
				started_at: '',
				ended_at: '',
				duration_minutes: 45,
				context: '',
				summary: '',
				notes: '',
				sentiment: ''
			};
			await Promise.all([loadPeople(), loadSelectedPerson(selectedId)]);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to create event.';
		}
	}

	async function submitReminder() {
		if (!selectedId || !reminderForm.title || !reminderForm.due_at) return;
		try {
			await createReminder({
				title: reminderForm.title,
				due_at: new Date(reminderForm.due_at).toISOString(),
				priority: reminderForm.priority,
				notes: reminderForm.notes || undefined,
				entity_type: 'Person',
				entity_id: selectedId
			});
			reminderForm = {
				title: '',
				due_at: '',
				priority: 'Normal',
				notes: ''
			};
			await Promise.all([loadPeople(), loadSelectedPerson(selectedId)]);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to create reminder.';
		}
	}

	async function completeSelectedReminder(reminderId: string) {
		try {
			await completeReminder(reminderId);
			if (selectedId) {
				await Promise.all([loadPeople(), loadSelectedPerson(selectedId)]);
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to complete reminder.';
		}
	}

	async function submitTag() {
		if (!selectedId || !tagForm.name) return;
		try {
			selectedPersonDetail = await addPersonTag(selectedId, { name: tagForm.name });
			tagForm = { name: '' };
			await loadPeople();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to add tag.';
		}
	}

	async function submitLocation() {
		if (!selectedId || !locationForm.selected_location_id) return;
		try {
			selectedPersonDetail = await addPersonLocation(selectedId, {
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
			await loadPeople();
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
				location_type: locationCreateForm.location_type || 'Home',
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
				location_type: 'Home',
				notes: ''
			};
			showCreateLocationModal = false;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to create location.';
		}
	}

	async function submitRole() {
		if (!selectedId || !roleForm.organization_id) return;
		try {
			selectedPersonDetail = await addPersonOrganizationRole(selectedId, {
				organization_id: roleForm.organization_id,
				title: roleForm.title || undefined,
				role_type: roleForm.role_type || undefined,
				start_date: roleForm.start_date || undefined,
				end_date: roleForm.end_date || undefined,
				is_current: roleForm.is_current,
				notes: roleForm.notes || undefined
			});
			roleForm = {
				organization_id: organizations[0]?.id || '',
				title: '',
				role_type: '',
				start_date: '',
				end_date: '',
				is_current: true,
				notes: ''
			};
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to add organization role.';
		}
	}

	async function snoozeSelectedReminder(reminderId: string) {
		try {
			const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
			await snoozeReminder(reminderId, tomorrow);
			if (selectedId) {
				await Promise.all([loadPeople(), loadSelectedPerson(selectedId)]);
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to snooze reminder.';
		}
	}

	function formatDate(value: string | null) {
		if (!value) return '—';
		return new Date(value).toLocaleDateString([], {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}

	function contactHref(type: string, value: string) {
		if (type === 'Email') return normalizeExternalHref(value);
		if (type === 'Phone' || type === 'WhatsApp' || type === 'Telegram') return normalizeExternalHref(value);
		if (['Website', 'LinkedIn', 'X', 'GitHub'].includes(type)) return normalizeExternalHref(value);
		return null;
	}
</script>

<svelte:head>
	<title>People | Kizuna</title>
</svelte:head>

<main class="shell">
	<header class="topbar">
		<div>
			<a class="brand" href={resolve('/')}>Kizuna</a>
			<h1>People</h1>
		</div>
		<p class="meta">{people.length} records</p>
	</header>

	<form class="toolbar" onsubmit={(event) => {
		event.preventDefault();
		refreshPeopleNow();
	}}>
		<label>
			<span>Search</span>
			<input bind:value={query} placeholder="Name, location, notes, how you met" />
		</label>
		<label>
			<span>Category</span>
			<select bind:value={category}>
				{#each categoryOptions as option (option)}
					<option value={option}>{option}</option>
				{/each}
			</select>
		</label>
		<label>
			<span>City</span>
			<input bind:value={city} placeholder="Filter city" />
		</label>
		<button type="submit">Refresh</button>
	</form>

	{#if error}
		<p class="notice error">{error}</p>
	{/if}

	<section class="workspace">
		<section class="panel list-panel">
			<div class="panel-header">
				<div>
					<h2>Directory</h2>
					<span>{loading ? 'Loading…' : hasMorePeople ? `${people.length}+ loaded` : `${people.length} loaded`}</span>
				</div>
			</div>
			<div bind:this={directoryViewport} class="table directory-scroll" onscroll={maybeLoadMorePeople}>
				<div class="row head">
					<button class="sort-button" type="button" onclick={() => toggleSort('display_name')}>Name {sortIndicator('display_name')}</button>
					<button class="sort-button" type="button" onclick={() => toggleSort('relationship_category')}>Category {sortIndicator('relationship_category')}</button>
					<button class="sort-button" type="button" onclick={() => toggleSort('primary_location')}>Location {sortIndicator('primary_location')}</button>
				</div>
				{#each sortedPeople as person (person.id)}
					<button
						class:selected={selectedPerson?.id === person.id}
						class="row item"
						onclick={() => {
							void selectPerson(person.id);
						}}
					>
						<span>{person.display_name}</span>
						<span>{person.relationship_category}</span>
						<span>{person.primary_location || '—'}</span>
					</button>
				{/each}
				{#if loadingMorePeople}
					<p class="list-status">Loading more people…</p>
				{:else if !hasMorePeople && people.length}
					<p class="list-status">End of directory.</p>
				{/if}
			</div>
		</section>

		<section class="panel detail-panel">
			<div class="panel-header">
				<div>
					<h2>Selected record</h2>
					<span>{selectedPerson ? `${selectedPerson.relationship_score} score` : 'No selection'}</span>
				</div>
				{#if selectedPersonDetail}
					<div class="inline-actions">
						{#if editingSelected}
							<button type="button" onclick={cancelEditingSelected}>Cancel</button>
							<button type="button" onclick={saveSelectedPerson} disabled={savingSelection}>
								{savingSelection ? 'Saving…' : 'Save'}
							</button>
						{:else}
							<button type="button" onclick={startEditingSelected}>Edit</button>
						{/if}
					</div>
				{/if}
			</div>
			{#if selectedPersonDetail}
				<div class="detail-grid">
					{#if editingSelected}
						<label>
							<span>Name</span>
							<input bind:value={selectedEditForm.display_name} required />
						</label>
						<label>
							<span>Given name</span>
							<input bind:value={selectedEditForm.given_name} />
						</label>
						<label>
							<span>Family name</span>
							<input bind:value={selectedEditForm.family_name} />
						</label>
						<label>
							<span>First met</span>
							<input bind:value={selectedEditForm.first_met_date} type="date" />
						</label>
						<label class="wide">
							<span>Primary location search</span>
							<input bind:value={selectedEditForm.location_search} placeholder="Cafe, street, city, country" />
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
						<div class="field">
							<span>Relationship score</span>
							<p>{selectedPersonDetail.relationship_score} · {selectedPersonDetail.relationship_category}</p>
						</div>
						<label class="wide">
							<span>Relationship summary</span>
							<textarea bind:value={selectedEditForm.relationship_summary} rows="3"></textarea>
						</label>
						<label class="wide">
							<span>How we met</span>
							<textarea bind:value={selectedEditForm.how_we_met} rows="3"></textarea>
						</label>
						<div class="field wide">
							<div class="section-heading">
								<span>Contact methods</span>
								<button type="button" onclick={addEditableContactMethod}>Add contact</button>
							</div>
							<div class="stacked-collection">
								{#each selectedEditForm.contact_methods as method, index (method.id)}
									<div class="collection-row">
										<label>
											<span>Type</span>
											<select bind:value={method.type}>
												{#each contactTypeOptions as option (option)}
													<option value={option}>{option}</option>
												{/each}
											</select>
										</label>
										<label>
											<span>Value</span>
											<input bind:value={method.value} />
										</label>
										<label>
											<span>Label</span>
											<input bind:value={method.label} placeholder="Personal, work, assistant" />
										</label>
										<label class="inline-toggle">
											<input
												checked={method.is_primary}
												name="primary-contact-method"
												onchange={() => setPrimaryContactMethod(method.id)}
												type="radio"
											/>
											<span>Primary</span>
										</label>
										<button
											type="button"
											onclick={() => removeEditableContactMethod(method.id)}
										>
											{selectedEditForm.contact_methods.length === 1 && index === 0 ? 'Clear' : 'Remove'}
										</button>
									</div>
								{/each}
							</div>
						</div>
						<label>
							<span>Profile platform</span>
							<select bind:value={selectedEditForm.profile_platform}>
								<option>LinkedIn</option>
								<option>Website</option>
								<option>X</option>
								<option>GitHub</option>
							</select>
						</label>
						<label class="wide">
							<span>Profile URL or handle</span>
							<input bind:value={selectedEditForm.profile_url} />
						</label>
						<label class="wide">
							<span>Notes</span>
							<textarea bind:value={selectedEditForm.notes} rows="6"></textarea>
						</label>
					{:else}
						<div class="field">
							<span>Name</span>
							<strong>{selectedPersonDetail.display_name}</strong>
						</div>
						<div class="field">
							<span>Location</span>
							<strong>{selectedPersonDetail.primary_location || '—'}</strong>
						</div>
						<div class="field">
							<span>Last interaction</span>
							<strong>{formatDate(selectedPersonDetail.last_interaction_date)}</strong>
						</div>
						<div class="field">
							<span>Next reminder</span>
							<strong>{formatDate(selectedPersonDetail.next_reminder_date)}</strong>
						</div>
						<div class="field wide">
							<span>Relationship summary</span>
							<p>{selectedPersonDetail.relationship_summary || 'No summary yet.'}</p>
						</div>
						<div class="field wide">
							<span>How we met</span>
							<p>{selectedPersonDetail.how_we_met || 'No origin recorded.'}</p>
						</div>
						<div class="field wide">
							<span>Relationship score</span>
							<p>{selectedPersonDetail.relationship_score} · {selectedPersonDetail.relationship_category}</p>
							<p>{selectedPersonDetail.relationship_score_reason || 'No explanation yet.'}</p>
						</div>
						<div class="field wide">
							<span>Contact methods</span>
							<ul>
								{#if selectedPersonDetail.contact_methods.length}
									{#each selectedPersonDetail.contact_methods as method (method.id)}
										<li>
											{method.type}:
											{#if contactHref(method.type, method.value)}
												<PreviewLink label={method.value} value={contactHref(method.type, method.value) || method.value} />
											{:else}
												{method.value}
											{/if}
										</li>
									{/each}
								{:else}
									<li>No contact methods</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>External profiles</span>
							<ul>
								{#if selectedPersonDetail.external_profiles.length}
									{#each selectedPersonDetail.external_profiles as profile (profile.id)}
										<li>{profile.platform}: <PreviewLink label={profile.url_or_handle} value={profile.url_or_handle} /></li>
									{/each}
								{:else}
									<li>No external profiles</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>Organizations</span>
							<ul>
								{#if selectedPersonDetail.organization_roles.length}
									{#each selectedPersonDetail.organization_roles as role (role.id)}
										<li>{role.organization_name || 'Organization'} · {role.title || role.role_type || 'Role'}</li>
									{/each}
								{:else}
									<li>No organization roles yet.</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>Tags</span>
							<p>{selectedPersonDetail.tags.map((item) => item.tag.name).join(', ') || 'No tags yet.'}</p>
						</div>
						<div class="field wide">
							<span>Locations</span>
							<ul>
								{#if selectedPersonDetail.locations.length}
									{#each selectedPersonDetail.locations as item (item.id)}
										<li><a href={resolve(`/locations?id=${item.location.id}`)}>{item.location.city || item.location.label || '—'} {item.location.country || ''}</a></li>
									{/each}
								{:else}
									<li>No structured locations yet.</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>Timeline</span>
							<ul>
								{#if selectedPersonDetail.recent_events.length}
									{#each selectedPersonDetail.recent_events as event (event.id)}
										<li>{formatDate(event.started_at)} · {event.type} · {event.title}</li>
									{/each}
								{:else}
									<li>No events yet.</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>Active reminders</span>
							<ul class="reminder-list">
								{#if selectedPersonDetail.active_reminders.length}
									{#each selectedPersonDetail.active_reminders as reminder (reminder.id)}
										<li>
											<div>
												<strong>{reminder.title}</strong>
												<p>{formatDate(reminder.due_at)}</p>
											</div>
											<div class="inline-actions">
												<button type="button" onclick={() => completeSelectedReminder(reminder.id)}>Done</button>
												<button type="button" onclick={() => snoozeSelectedReminder(reminder.id)}>+1d</button>
											</div>
										</li>
									{/each}
								{:else}
									<li>No active reminders.</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>Pipeline items</span>
							<ul>
								{#if selectedPersonDetail.pipeline_items.length}
									{#each selectedPersonDetail.pipeline_items as item (item.id)}
										<li>{item.title}</li>
									{/each}
								{:else}
									<li>No pipeline items.</li>
								{/if}
							</ul>
						</div>
						<div class="field wide">
							<span>Notes</span>
							<p>{selectedPersonDetail.notes || 'No notes yet.'}</p>
						</div>
					{/if}
				</div>
			{:else}
				<p class="notice">No person selected.</p>
			{/if}
		</section>

		<section class="panel form-panel">
			<div class="panel-header">
				<div>
					<h2>Actions</h2>
					<span>Capture and follow-up</span>
				</div>
			</div>
			<div class="action-stack">
				<form class="stacked" onsubmit={(event) => {
					event.preventDefault();
					submitPerson();
				}}>
					<h3>New person</h3>
					<label>
						<span>Display name</span>
						<input bind:value={form.display_name} required />
					</label>
					<label>
						<span>Given name</span>
						<input bind:value={form.given_name} />
					</label>
					<label>
						<span>Family name</span>
						<input bind:value={form.family_name} />
					</label>
					<label>
						<span>Nickname</span>
						<input bind:value={form.nickname} />
					</label>
					<label>
						<span>Pronouns</span>
						<input bind:value={form.pronouns} placeholder="she/her, he/him, they/them" />
					</label>
					<label class="wide">
						<span>Short bio</span>
						<textarea bind:value={form.short_bio} rows="2"></textarea>
					</label>
					<label>
						<span>First met date</span>
						<input bind:value={form.first_met_date} type="date" />
					</label>
					<label class="wide">
						<span>Primary location search</span>
						<input bind:value={form.location_search} placeholder="Cafe, street, city, country" />
					</label>
					<label class="wide">
						<span>Primary location</span>
						<select bind:value={form.selected_location_id} size="5">
							<option value="">No primary location</option>
							{#each locations.filter((location) =>
								!form.location_search.trim()
									? true
									: [location.label, location.address_line, location.city, location.region, location.country, location.location_type, location.notes]
											.filter(Boolean)
											.some((value) => value!.toLowerCase().includes(form.location_search.trim().toLowerCase()))
							) as location (location.id)}
								<option value={location.id}>{locationOptionLabel(location)}</option>
							{/each}
						</select>
					</label>
					<div class="wide inline-actions">
						<button type="button" onclick={() => (showCreateLocationModal = true)}>Create new location</button>
					</div>
					<label class="wide">
						<span>Relationship summary</span>
						<textarea bind:value={form.relationship_summary} rows="2"></textarea>
					</label>
					<label class="wide">
						<span>How we met</span>
						<textarea bind:value={form.how_we_met} rows="2"></textarea>
					</label>
					<label>
						<span>Contact type</span>
						<select bind:value={form.contact_type}>
							<option>Email</option>
							<option>Phone</option>
							<option>WeChat</option>
							<option>WhatsApp</option>
							<option>Telegram</option>
							<option>Website</option>
						</select>
					</label>
					<label>
						<span>Contact value</span>
						<input bind:value={form.contact_value} />
					</label>
					<label>
						<span>Contact label</span>
						<input bind:value={form.contact_label} placeholder="Personal, work, assistant" />
					</label>
					<label class="wide">
						<span>Contact notes</span>
						<input bind:value={form.contact_notes} placeholder="Preferred channel, assistant, time zone" />
					</label>
					<label>
						<span>Profile platform</span>
						<select bind:value={form.profile_platform}>
							<option>LinkedIn</option>
							<option>Website</option>
							<option>X</option>
							<option>GitHub</option>
						</select>
					</label>
					<label class="wide">
						<span>Profile URL or handle</span>
						<input bind:value={form.profile_url} />
					</label>
					<label>
						<span>Profile label</span>
						<input bind:value={form.profile_label} placeholder="Main, personal site, archive" />
					</label>
					<label class="wide">
						<span>Profile notes</span>
						<input bind:value={form.profile_notes} placeholder="What this profile is used for" />
					</label>
					<label class="wide">
						<span>Notes</span>
						<textarea bind:value={form.notes} rows="4"></textarea>
					</label>
					<button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Create person'}</button>
				</form>

				<form class="stacked separator" onsubmit={(event) => {
					event.preventDefault();
					submitEvent();
				}}>
					<h3>Log event for selected person</h3>
					<label class="wide">
						<span>Title</span>
						<input bind:value={eventForm.title} />
					</label>
					<label>
						<span>Type</span>
						<select bind:value={eventForm.type}>
							<option>One-on-one</option>
							<option>Meeting</option>
							<option>Call</option>
							<option>Email</option>
							<option>Message</option>
							<option>Meal</option>
							<option>Work session</option>
							<option>Intro</option>
						</select>
					</label>
					<label>
						<span>Duration</span>
						<input bind:value={eventForm.duration_minutes} min="0" type="number" />
					</label>
					<div class="wide">
						<DateTimeField bind:value={eventForm.started_at} label="Started at" />
					</div>
					<div class="wide">
						<DateTimeField bind:value={eventForm.ended_at} label="Ended at" />
					</div>
					<label class="wide">
						<span>Context</span>
						<input bind:value={eventForm.context} />
					</label>
					<label class="wide">
						<span>Summary</span>
						<textarea bind:value={eventForm.summary} rows="3"></textarea>
					</label>
					<label class="wide">
						<span>Notes</span>
						<textarea bind:value={eventForm.notes} rows="3"></textarea>
					</label>
					<label>
						<span>Sentiment</span>
						<input bind:value={eventForm.sentiment} placeholder="Positive, neutral, tense" />
					</label>
					<button type="submit">Log event</button>
				</form>

				<form class="stacked separator" onsubmit={(event) => {
					event.preventDefault();
					submitReminder();
				}}>
					<h3>Create reminder for selected person</h3>
					<label class="wide">
						<span>Title</span>
						<input bind:value={reminderForm.title} />
					</label>
					<div class="wide">
						<DateTimeField bind:value={reminderForm.due_at} label="Due at" />
					</div>
					<label>
						<span>Priority</span>
						<select bind:value={reminderForm.priority}>
							<option>Low</option>
							<option>Normal</option>
							<option>High</option>
						</select>
					</label>
					<label class="wide">
						<span>Notes</span>
						<textarea bind:value={reminderForm.notes} rows="3"></textarea>
					</label>
					<button type="submit">Create reminder</button>
				</form>

				<form class="stacked separator" onsubmit={(event) => {
					event.preventDefault();
					submitTag();
				}}>
					<h3>Add tag to selected person</h3>
					<label class="wide">
						<span>Tag</span>
						<input bind:value={tagForm.name} placeholder="friend, investor, supplier" />
					</label>
					<button type="submit">Add tag</button>
				</form>

				<form class="stacked separator" onsubmit={(event) => {
					event.preventDefault();
					submitLocation();
				}}>
					<h3>Add location to selected person</h3>
					<label class="wide">
						<span>Search existing locations</span>
						<input bind:value={locationForm.location_search} placeholder="Cafe, street, city, country" />
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
						<textarea bind:value={locationForm.link_notes} rows="2" placeholder="Why this place matters for this person"></textarea>
					</label>
					<label class="checkbox">
						<input bind:checked={locationForm.is_primary} type="checkbox" />
						<span>Primary location</span>
					</label>
					<button type="submit" disabled={!locationForm.selected_location_id}>Add location</button>
				</form>

				<form class="stacked separator" onsubmit={(event) => {
					event.preventDefault();
					submitRole();
				}}>
					<h3>Link selected person to organization</h3>
					<label class="wide">
						<span>Organization</span>
						<select bind:value={roleForm.organization_id}>
							{#each organizations as organization (organization.id)}
								<option value={organization.id}>{organization.name}</option>
							{/each}
						</select>
					</label>
					<label>
						<span>Title</span>
						<input bind:value={roleForm.title} />
					</label>
					<label>
						<span>Role type</span>
						<input bind:value={roleForm.role_type} />
					</label>
					<label>
						<span>Start date</span>
						<input bind:value={roleForm.start_date} type="date" />
					</label>
					<label>
						<span>End date</span>
						<input bind:value={roleForm.end_date} type="date" />
					</label>
					<label class="checkbox">
						<input bind:checked={roleForm.is_current} type="checkbox" />
						<span>Current role</span>
					</label>
					<label class="wide">
						<span>Notes</span>
						<textarea bind:value={roleForm.notes} rows="2"></textarea>
					</label>
					<button type="submit">Add role</button>
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
				<form class="stacked" onsubmit={(event) => {
					event.preventDefault();
					submitNewLocation();
				}}>
					<h3>Create location</h3>
					<label>
						<span>Label</span>
						<input bind:value={locationCreateForm.label} placeholder="Blue Bottle Mint Plaza" />
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
						<input bind:value={locationCreateForm.location_type} placeholder="Home, Work, Cafe" />
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

	.brand,
	.meta {
		font-size: 0.74rem;
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

	.toolbar {
		grid-template-columns: minmax(0, 1.4fr) 10rem 10rem auto;
		align-items: end;
		margin-top: 1rem;
	}

	.workspace {
		grid-template-columns: 1.2fr 1fr 0.95fr;
		margin-top: 1rem;
		align-items: start;
	}

	.panel {
		border: 1px solid var(--line-strong);
		background: var(--panel-strong);
		box-shadow: var(--shadow);
		min-height: 34rem;
	}

	.list-panel {
		display: flex;
		flex-direction: column;
		height: min(72vh, calc(100vh - 12rem));
		min-height: 34rem;
	}

	.panel-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 0.75rem;
		padding: 0.75rem 0.85rem;
		border-bottom: 1px solid var(--line);
	}

	.panel-header span,
	label span,
	.field span {
		display: block;
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
	}

	label {
		display: grid;
		gap: 0.35rem;
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

	.table {
		display: grid;
		padding: 0 0.85rem 0.85rem;
	}

	.directory-scroll {
		flex: 1;
		min-height: 0;
		height: 100%;
		overflow-y: auto;
		align-content: start;
	}

	.row {
		display: grid;
		grid-template-columns: 1.5fr 0.8fr 0.9fr;
		gap: 0.75rem;
		padding: 0.7rem 0;
		border-bottom: 1px solid var(--line);
		text-align: left;
		background: transparent;
	}

	.row.head {
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
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

	.list-status {
		margin: 0;
		padding: 0.9rem 0;
		font-size: 0.8rem;
		color: var(--muted);
		text-align: center;
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

	.section-heading {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.section-heading button,
	.collection-row button {
		width: auto;
	}

	.stacked-collection {
		display: grid;
		gap: 0.75rem;
	}

	.collection-row {
		display: grid;
		grid-template-columns: 0.9fr 1.4fr 1.1fr auto auto;
		gap: 0.75rem;
		padding: 0.75rem;
		border: 1px solid var(--line);
		background: var(--panel);
	}

	.inline-toggle {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		align-self: end;
	}

	.inline-toggle input {
		width: auto;
		margin: 0;
	}

	.inline-toggle span {
		margin: 0;
	}

	.field ul {
		padding-left: 1rem;
	}

	.reminder-list {
		list-style: none;
		padding-left: 0;
	}

	.reminder-list li {
		display: flex;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.55rem 0;
		border-bottom: 1px solid var(--line);
	}

	.inline-actions {
		display: flex;
		gap: 0.4rem;
		align-items: start;
	}

	.inline-actions button {
		width: auto;
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
		form,
		.collection-row {
			grid-template-columns: 1fr;
		}

		.panel-header {
			flex-direction: column;
			align-items: stretch;
		}
	}
</style>
