<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import DateTimeField from '$lib/components/DateTimeField.svelte';
	import { createEvent, getEvent, listEvents, listPeople, updateEvent, type Event, type Person } from '$lib/api';

	const eventTypes = [
		'Meeting',
		'One-on-one',
		'Group meeting',
		'Call',
		'Email',
		'Message',
		'Meal',
		'Event attendance',
		'Work session',
		'Intro',
		'Other'
	];
	type SortField = 'started_at' | 'title' | 'type' | 'duration_minutes';
	type SortDirection = 'none' | 'asc' | 'desc';
	type ViewMode = 'list' | 'calendar';
	type EventsByDay = Record<string, Event[]>;

	let loading = $state(true);
	let saving = $state(false);
	let savingSelection = $state(false);
	let editingSelected = $state(false);
	let error = $state('');
	let events = $state<Event[]>([]);
	let people = $state<Person[]>([]);
	let selectedId = $state('');
	let selectedEventDetail = $state<Event | null>(null);
	let sortField = $state<SortField | null>(null);
	let sortDirection = $state<SortDirection>('none');
	let viewMode = $state<ViewMode>('list');
	let monthCursor = $state(new Date().toISOString().slice(0, 7));

	let selectedEditForm = $state({
		title: '',
		type: 'Meeting',
		started_at: '',
		duration_minutes: 30,
		context: '',
		summary: '',
		selected_person_ids: [] as string[]
	});

	let form = $state({
		title: '',
		type: 'Meeting',
		started_at: '',
		duration_minutes: 30,
		context: '',
		summary: '',
		selected_person_ids: [] as string[]
	});

	const sortedEvents = $derived(sortEvents(events, sortField, sortDirection));
	const selectedEvent = $derived(sortedEvents.find((event) => event.id === selectedId) ?? sortedEvents[0] ?? null);
	const calendarDays = $derived(buildCalendarDays(monthCursor));
	const eventsByDay = $derived(groupEventsByDay(events));

	$effect(() => {
		if (selectedId) {
			void loadSelectedEvent(selectedId);
		}
	});

	onMount(async () => {
		await Promise.all([loadEvents(), loadPeople()]);
	});

	function toDayKey(value: string) {
		return new Date(value).toISOString().slice(0, 10);
	}

	function monthStartDate(monthKey: string) {
		return new Date(`${monthKey}-01T00:00:00`);
	}

	function sortEvents(items: Event[], field: SortField | null, direction: SortDirection) {
		if (!field || direction === 'none') {
			return items;
		}
		const factor = direction === 'asc' ? 1 : -1;
		return [...items].sort((left, right) => {
			if (field === 'started_at') {
				return (new Date(left.started_at).getTime() - new Date(right.started_at).getTime()) * factor;
			}
			if (field === 'duration_minutes') {
				return (((left.duration_minutes || 0) - (right.duration_minutes || 0)) * factor);
			}
			return ((left[field] || '').localeCompare(right[field] || '')) * factor;
		});
	}

	function toggleSort(field: SortField) {
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

	function sortIndicator(field: SortField) {
		if (sortField !== field || sortDirection === 'none') return '';
		return sortDirection === 'asc' ? '↑' : '↓';
	}

	function buildCalendarDays(monthKey: string) {
		const firstDay = monthStartDate(monthKey);
		const startDay = 1 - firstDay.getDay();
		return Array.from(
			{ length: 42 },
			(_, index) => new Date(firstDay.getFullYear(), firstDay.getMonth(), startDay + index)
		);
	}

	function groupEventsByDay(items: Event[]) {
		const grouped: EventsByDay = {};
		for (const event of items) {
			const key = toDayKey(event.started_at);
			grouped[key] = [...(grouped[key] || []), event].sort((left, right) => left.started_at.localeCompare(right.started_at));
		}
		return grouped;
	}

	function syncSelectedEditForm(event: Event) {
		selectedEditForm = {
			title: event.title,
			type: event.type,
			started_at: event.started_at.slice(0, 16),
			duration_minutes: event.duration_minutes || 30,
			context: event.context || '',
			summary: event.summary || '',
			selected_person_ids: [...event.person_ids]
		};
	}

	async function loadEvents() {
		loading = true;
		error = '';
		try {
			events = await listEvents({ limit: 100 });
			const available = sortEvents(events, sortField, sortDirection);
			if (!selectedId && available[0]) {
				selectedId = available[0].id;
			}
			if (selectedId && !available.some((event) => event.id === selectedId) && available[0]) {
				selectedId = available[0].id;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load events.';
		} finally {
			loading = false;
		}
	}

	async function loadPeople() {
		try {
			people = await listPeople({ limit: 100 });
			if (!form.selected_person_ids.length && people[0]) {
				form.selected_person_ids = [people[0].id];
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load people.';
		}
	}

	async function loadSelectedEvent(eventId: string) {
		try {
			selectedEventDetail = await getEvent(eventId);
			if (selectedEventDetail && !editingSelected) {
				syncSelectedEditForm(selectedEventDetail);
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load event.';
		}
	}

	function startEditingSelected() {
		if (!selectedEventDetail) return;
		syncSelectedEditForm(selectedEventDetail);
		editingSelected = true;
	}

	function cancelEditingSelected() {
		if (selectedEventDetail) {
			syncSelectedEditForm(selectedEventDetail);
		}
		editingSelected = false;
	}

	async function saveSelectedEvent() {
		if (!selectedId || !selectedEditForm.title || !selectedEditForm.started_at) return;
		savingSelection = true;
		error = '';
		try {
			selectedEventDetail = await updateEvent(selectedId, {
				title: selectedEditForm.title,
				type: selectedEditForm.type,
				started_at: new Date(selectedEditForm.started_at).toISOString(),
				duration_minutes: Number(selectedEditForm.duration_minutes) || null,
				context: selectedEditForm.context || null,
				summary: selectedEditForm.summary || null,
				person_ids: selectedEditForm.selected_person_ids
			});
			editingSelected = false;
			await loadEvents();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to update event.';
		} finally {
			savingSelection = false;
		}
	}

	async function submitEvent() {
		saving = true;
		error = '';
		try {
			await createEvent({
				title: form.title,
				type: form.type,
				started_at: new Date(form.started_at).toISOString(),
				duration_minutes: Number(form.duration_minutes) || undefined,
				context: form.context || undefined,
				summary: form.summary || undefined,
				person_ids: form.selected_person_ids
			});
			form = {
				title: '',
				type: 'Meeting',
				started_at: '',
				duration_minutes: 30,
				context: '',
				summary: '',
				selected_person_ids: people[0] ? [people[0].id] : []
			};
			await loadEvents();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to create event.';
		} finally {
			saving = false;
		}
	}

	function formatDateTime(value: string) {
		return new Date(value).toLocaleString([], {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function formatMonth(date: Date) {
		return date.toLocaleDateString([], { year: 'numeric', month: 'long' });
	}

	function previousMonth() {
		const current = monthStartDate(monthCursor);
		monthCursor = new Date(current.getFullYear(), current.getMonth() - 1, 1).toISOString().slice(0, 7);
	}

	function nextMonth() {
		const current = monthStartDate(monthCursor);
		monthCursor = new Date(current.getFullYear(), current.getMonth() + 1, 1).toISOString().slice(0, 7);
	}
</script>

<svelte:head>
	<title>Events | Kizuna</title>
</svelte:head>

<main class="shell">
	<header class="topbar">
		<div>
			<a class="brand" href={resolve('/')}>Kizuna</a>
			<h1>Events</h1>
		</div>
		<p class="meta">{events.length} logged</p>
	</header>

	{#if error}
		<p class="notice">{error}</p>
	{/if}

	<section class="workspace">
		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>{viewMode === 'list' ? 'Directory' : 'Calendar'}</h2>
					<span>{loading ? 'Loading…' : viewMode === 'list' ? 'Recent first' : formatMonth(monthStartDate(monthCursor))}</span>
				</div>
				<div class="header-controls">
					<label>
						<span>View</span>
						<select bind:value={viewMode}>
							<option value="list">List</option>
							<option value="calendar">Calendar</option>
						</select>
					</label>
				</div>
			</div>

			{#if viewMode === 'list'}
				<div class="table">
					<div class="row head">
						<button class="sort-button" type="button" onclick={() => toggleSort('title')}>Event {sortIndicator('title')}</button>
						<button class="sort-button" type="button" onclick={() => toggleSort('type')}>Type {sortIndicator('type')}</button>
						<button class="sort-button" type="button" onclick={() => toggleSort('started_at')}>When {sortIndicator('started_at')}</button>
					</div>
					{#each sortedEvents as event (event.id)}
						<button
							class:selected={selectedEvent?.id === event.id}
							class="row item"
							onclick={() => {
								selectedId = event.id;
								editingSelected = false;
							}}
						>
							<span>
								<strong>{event.title}</strong>
								<small>{event.summary || event.context || 'No summary'}</small>
							</span>
							<span>{event.type}</span>
							<span>{formatDateTime(event.started_at)}</span>
						</button>
					{/each}
				</div>
			{:else}
				<div class="calendar-toolbar">
					<button type="button" onclick={previousMonth}>Prev</button>
					<strong>{formatMonth(monthStartDate(monthCursor))}</strong>
					<button type="button" onclick={nextMonth}>Next</button>
				</div>
				<div class="calendar-grid">
					{#each ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as dayName (dayName)}
						<div class="calendar-head">{dayName}</div>
					{/each}
					{#each calendarDays as day (`${day.toISOString()}`)}
						<div class:outside-month={day.getMonth() !== monthStartDate(monthCursor).getMonth()} class="calendar-cell">
							<div class="calendar-day">{day.getDate()}</div>
							<div class="calendar-events">
								{#each eventsByDay[day.toISOString().slice(0, 10)] || [] as event (event.id)}
									<button class:selected={selectedEvent?.id === event.id} class="calendar-chip" type="button" onclick={() => (selectedId = event.id)}>
										{event.title}
									</button>
								{/each}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>

		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>Selected record</h2>
					<span>{selectedEventDetail ? formatDateTime(selectedEventDetail.started_at) : 'No selection'}</span>
				</div>
				{#if selectedEventDetail}
					<div class="inline-actions">
						{#if editingSelected}
							<button type="button" onclick={cancelEditingSelected}>Cancel</button>
							<button type="button" onclick={saveSelectedEvent} disabled={savingSelection}>
								{savingSelection ? 'Saving…' : 'Save'}
							</button>
						{:else}
							<button type="button" onclick={startEditingSelected}>Edit</button>
						{/if}
					</div>
				{/if}
			</div>
			{#if selectedEventDetail}
				<div class="detail-grid">
					{#if editingSelected}
						<label class="wide">
							<span>Title</span>
							<input bind:value={selectedEditForm.title} />
						</label>
						<label>
							<span>Type</span>
							<select bind:value={selectedEditForm.type}>
								{#each eventTypes as type (type)}
									<option value={type}>{type}</option>
								{/each}
							</select>
						</label>
						<label>
							<span>Duration (min)</span>
							<input bind:value={selectedEditForm.duration_minutes} min="0" type="number" />
						</label>
						<div class="wide">
							<DateTimeField bind:value={selectedEditForm.started_at} label="Started at" />
						</div>
						<label class="wide">
							<span>People</span>
							<select bind:value={selectedEditForm.selected_person_ids} multiple size="6">
								{#each people as person (person.id)}
									<option value={person.id}>{person.display_name}</option>
								{/each}
							</select>
						</label>
						<label class="wide">
							<span>Context</span>
							<input bind:value={selectedEditForm.context} />
						</label>
						<label class="wide">
							<span>Summary</span>
							<textarea bind:value={selectedEditForm.summary} rows="5"></textarea>
						</label>
					{:else}
						<div class="field">
							<span>Title</span>
							<strong>{selectedEventDetail.title}</strong>
						</div>
						<div class="field">
							<span>Type</span>
							<strong>{selectedEventDetail.type}</strong>
						</div>
						<div class="field">
							<span>Started</span>
							<strong>{formatDateTime(selectedEventDetail.started_at)}</strong>
						</div>
						<div class="field">
							<span>Duration</span>
							<strong>{selectedEventDetail.duration_minutes || '—'} min</strong>
						</div>
						<div class="field wide">
							<span>Context</span>
							<p>{selectedEventDetail.context || 'No context recorded.'}</p>
						</div>
						<div class="field wide">
							<span>Summary</span>
							<p>{selectedEventDetail.summary || 'No summary recorded.'}</p>
						</div>
						<div class="field wide">
							<span>People</span>
							<ul>
								{#if selectedEventDetail.person_ids.length}
									{#each selectedEventDetail.person_ids as personId (personId)}
										<li>{people.find((person) => person.id === personId)?.display_name || personId}</li>
									{/each}
								{:else}
									<li>No people linked yet.</li>
								{/if}
							</ul>
						</div>
					{/if}
				</div>
			{:else}
				<p class="notice">No event selected.</p>
			{/if}
		</section>

		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>Actions</h2>
					<span>Quick capture</span>
				</div>
			</div>
			<div class="action-stack">
				<form onsubmit={(event) => {
					event.preventDefault();
					submitEvent();
				}}>
					<h3>Log event</h3>
					<label class="wide">
						<span>Title</span>
						<input bind:value={form.title} required />
					</label>
					<label>
						<span>Type</span>
						<select bind:value={form.type}>
							{#each eventTypes as type (type)}
								<option value={type}>{type}</option>
							{/each}
						</select>
					</label>
					<label>
						<span>Duration (min)</span>
						<input bind:value={form.duration_minutes} min="0" type="number" />
					</label>
					<div class="wide">
						<DateTimeField bind:value={form.started_at} label="Started at" required />
					</div>
					<label class="wide">
						<span>People</span>
						<select bind:value={form.selected_person_ids} multiple size="6">
							{#each people as person (person.id)}
								<option value={person.id}>{person.display_name}</option>
							{/each}
						</select>
					</label>
					<label class="wide">
						<span>Context</span>
						<input bind:value={form.context} />
					</label>
					<label class="wide">
						<span>Summary</span>
						<textarea bind:value={form.summary} rows="5"></textarea>
					</label>
					<button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Create event'}</button>
				</form>

				<section class="separator note-card">
					<h3>Calendar direction</h3>
					<p>This adds a native calendar view now. Google Calendar embedding still feels better as a later integration than a hard dependency in the MVP.</p>
				</section>
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

	.workspace {
		grid-template-columns: 1.2fr 1fr 0.9fr;
		margin-top: 1rem;
	}

	.brand,
	.meta,
	.panel-header span,
	label span,
	.row.head,
	.field span,
	.calendar-head {
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

	.header-controls,
	.inline-actions,
	.calendar-toolbar {
		display: flex;
		gap: 0.6rem;
		align-items: end;
	}

	.table {
		display: grid;
		padding: 0 0.85rem 0.85rem;
	}

	.row {
		display: grid;
		grid-template-columns: 1.4fr 0.8fr 1fr;
		gap: 0.75rem;
		padding: 0.75rem 0;
		border-bottom: 1px solid var(--line);
		background: transparent;
		align-items: center;
		text-align: left;
	}

	.item,
	.calendar-chip {
		border-left: 0;
		border-right: 0;
		border-top: 0;
	}

	.item.selected,
	.calendar-chip.selected {
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

	.row strong,
	.row small {
		display: block;
	}

	.row small {
		margin-top: 0.2rem;
		color: var(--muted);
	}

	.calendar-toolbar {
		justify-content: space-between;
		padding: 0.85rem;
		border-bottom: 1px solid var(--line);
	}

	.calendar-grid {
		display: grid;
		grid-template-columns: repeat(7, minmax(0, 1fr));
	}

	.calendar-head,
	.calendar-cell {
		border-right: 1px solid var(--line);
		border-bottom: 1px solid var(--line);
		padding: 0.65rem;
		min-height: 7rem;
	}

	.calendar-head:nth-child(7),
	.calendar-cell:nth-child(7n) {
		border-right: 0;
	}

	.calendar-day {
		font-weight: 600;
		margin-bottom: 0.5rem;
	}

	.calendar-events {
		display: grid;
		gap: 0.35rem;
	}

	.calendar-chip {
		width: 100%;
		padding: 0.45rem 0.55rem;
		text-align: left;
		background: var(--panel);
		border: 1px solid var(--line);
		color: var(--text);
		cursor: pointer;
	}

	.outside-month {
		background: color-mix(in srgb, var(--panel) 55%, transparent);
	}

	.detail-grid,
	form {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.85rem;
		padding: 0.85rem;
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
	.field ul,
	.note-card p {
		margin: 0;
	}

	.field ul {
		padding-left: 1rem;
	}

	.separator {
		border-top: 1px solid var(--line);
	}

	.note-card {
		padding: 0.85rem;
		display: grid;
		gap: 0.5rem;
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
		.workspace,
		.row,
		.detail-grid,
		form,
		.calendar-grid {
			grid-template-columns: 1fr;
		}

		.panel-header,
		.header-controls,
		.inline-actions,
		.calendar-toolbar {
			flex-direction: column;
			align-items: stretch;
		}
	}
</style>
