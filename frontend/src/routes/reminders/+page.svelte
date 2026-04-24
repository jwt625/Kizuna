<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import DateTimeField from '$lib/components/DateTimeField.svelte';
	import {
		completeReminder,
		createReminder,
		listReminders,
		snoozeReminder,
		updateReminder,
		type Reminder
	} from '$lib/api';

	const statusOptions = ['All', 'Open', 'Snoozed', 'Done'];
	const entityOptions = ['Person', 'Organization', 'Event', 'PipelineItem', 'General'];
	type SortField = 'due_at' | 'title' | 'status' | 'priority';
	type SortDirection = 'none' | 'asc' | 'desc';

	let loading = $state(true);
	let saving = $state(false);
	let savingSelection = $state(false);
	let editingSelected = $state(false);
	let error = $state('');
	let status = $state('All');
	let sortField = $state<SortField | null>(null);
	let sortDirection = $state<SortDirection>('none');
	let reminders = $state<Reminder[]>([]);
	let selectedId = $state('');

	let selectedEditForm = $state({
		title: '',
		due_at: '',
		priority: 'Normal',
		status: 'Open',
		entity_type: 'Person',
		notes: ''
	});

	let form = $state({
		title: '',
		due_at: '',
		priority: 'Normal',
		entity_type: 'Person',
		notes: ''
	});

	const sortedReminders = $derived(sortReminders(reminders, sortField, sortDirection));
	const selectedReminder = $derived(sortedReminders.find((item) => item.id === selectedId) ?? sortedReminders[0] ?? null);

	$effect(() => {
		if (selectedReminder && !editingSelected) {
			syncSelectedEditForm(selectedReminder);
		}
	});

	onMount(loadReminders);

	function sortReminders(items: Reminder[], field: SortField | null, direction: SortDirection) {
		if (!field || direction === 'none') {
			return items;
		}
		const factor = direction === 'asc' ? 1 : -1;
		return [...items].sort((left, right) => {
			if (field === 'due_at') {
				return (new Date(left.due_at).getTime() - new Date(right.due_at).getTime()) * factor;
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

	function syncSelectedEditForm(reminder: Reminder) {
		selectedEditForm = {
			title: reminder.title,
			due_at: reminder.due_at.slice(0, 16),
			priority: reminder.priority,
			status: reminder.status,
			entity_type: reminder.entity_type || 'General',
			notes: reminder.notes || ''
		};
	}

	async function loadReminders() {
		loading = true;
		error = '';
		try {
			reminders = await listReminders({
				status: status === 'All' ? undefined : status,
				limit: 100
			});
			const available = sortReminders(reminders, sortField, sortDirection);
			if (!selectedId && available[0]) {
				selectedId = available[0].id;
			}
			if (selectedId && !available.some((reminder) => reminder.id === selectedId) && available[0]) {
				selectedId = available[0].id;
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load reminders.';
		} finally {
			loading = false;
		}
	}

	function startEditingSelected() {
		if (!selectedReminder) return;
		syncSelectedEditForm(selectedReminder);
		editingSelected = true;
	}

	function cancelEditingSelected() {
		if (selectedReminder) {
			syncSelectedEditForm(selectedReminder);
		}
		editingSelected = false;
	}

	async function saveSelectedReminder() {
		if (!selectedReminder || !selectedEditForm.title || !selectedEditForm.due_at) return;
		savingSelection = true;
		error = '';
		try {
			await updateReminder(selectedReminder.id, {
				title: selectedEditForm.title,
				due_at: new Date(selectedEditForm.due_at).toISOString(),
				priority: selectedEditForm.priority,
				status: selectedEditForm.status,
				entity_type: selectedEditForm.entity_type,
				notes: selectedEditForm.notes || null
			});
			editingSelected = false;
			await loadReminders();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to update reminder.';
		} finally {
			savingSelection = false;
		}
	}

	async function submitReminder() {
		saving = true;
		error = '';
		try {
			await createReminder({
				title: form.title,
				due_at: new Date(form.due_at).toISOString(),
				notes: form.notes || undefined,
				priority: form.priority,
				entity_type: form.entity_type
			});
			form = {
				title: '',
				due_at: '',
				priority: 'Normal',
				entity_type: 'Person',
				notes: ''
			};
			await loadReminders();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to create reminder.';
		} finally {
			saving = false;
		}
	}

	async function markDone(reminder: Reminder) {
		try {
			await completeReminder(reminder.id);
			await loadReminders();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to update reminder.';
		}
	}

	async function snoozeOneDay(reminder: Reminder) {
		try {
			await snoozeReminder(reminder.id, new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString());
			await loadReminders();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to update reminder.';
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
</script>

<svelte:head>
	<title>Reminders | Kizuna</title>
</svelte:head>

<main class="shell">
	<header class="topbar">
		<div>
			<a class="brand" href={resolve('/')}>Kizuna</a>
			<h1>Reminders</h1>
		</div>
		<p class="meta">{reminders.filter((item) => item.status !== 'Done').length} open</p>
	</header>

	<section class="toolbar">
		<label>
			<span>Status</span>
			<select bind:value={status}>
				{#each statusOptions as option (option)}
					<option value={option}>{option}</option>
				{/each}
			</select>
		</label>
		<button type="button" onclick={loadReminders}>Refresh</button>
	</section>

	{#if error}
		<p class="notice">{error}</p>
	{/if}

	<section class="workspace">
		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>Directory</h2>
					<span>{loading ? 'Loading…' : 'Queue'}</span>
				</div>
			</div>
			<div class="table">
				<div class="row head">
					<button class="sort-button" type="button" onclick={() => toggleSort('title')}>Task {sortIndicator('title')}</button>
					<button class="sort-button" type="button" onclick={() => toggleSort('due_at')}>Due {sortIndicator('due_at')}</button>
					<button class="sort-button" type="button" onclick={() => toggleSort('status')}>Status {sortIndicator('status')}</button>
					<span>Action</span>
				</div>
				{#each sortedReminders as reminder (reminder.id)}
					<button class:selected={selectedReminder?.id === reminder.id} class="row item" onclick={() => {
						selectedId = reminder.id;
						editingSelected = false;
					}}>
						<span>
							<strong>{reminder.title}</strong>
							<small>{reminder.priority} · {reminder.entity_type || 'General'}</small>
						</span>
						<span>{formatDateTime(reminder.due_at)}</span>
						<span>{reminder.status}</span>
						<span>{reminder.status === 'Done' ? 'Closed' : 'Open'}</span>
					</button>
				{/each}
			</div>
		</section>

		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>Selected record</h2>
					<span>{selectedReminder ? selectedReminder.priority : 'No selection'}</span>
				</div>
				{#if selectedReminder}
					<div class="inline-actions">
						{#if selectedReminder.status !== 'Done'}
							<button type="button" onclick={() => markDone(selectedReminder)}>Done</button>
							<button type="button" onclick={() => snoozeOneDay(selectedReminder)}>+1d</button>
						{/if}
						{#if editingSelected}
							<button type="button" onclick={cancelEditingSelected}>Cancel</button>
							<button type="button" onclick={saveSelectedReminder} disabled={savingSelection}>
								{savingSelection ? 'Saving…' : 'Save'}
							</button>
						{:else}
							<button type="button" onclick={startEditingSelected}>Edit</button>
						{/if}
					</div>
				{/if}
			</div>
			{#if selectedReminder}
				<div class="detail-grid">
					{#if editingSelected}
						<label class="wide">
							<span>Title</span>
							<input bind:value={selectedEditForm.title} />
						</label>
						<div class="wide">
							<DateTimeField bind:value={selectedEditForm.due_at} label="Due at" required />
						</div>
						<label>
							<span>Priority</span>
							<select bind:value={selectedEditForm.priority}>
								<option>Low</option>
								<option>Normal</option>
								<option>High</option>
							</select>
						</label>
						<label>
							<span>Status</span>
							<select bind:value={selectedEditForm.status}>
								<option>Open</option>
								<option>Snoozed</option>
								<option>Done</option>
								<option>Canceled</option>
							</select>
						</label>
						<label class="wide">
							<span>Entity type</span>
							<select bind:value={selectedEditForm.entity_type}>
								{#each entityOptions as option (option)}
									<option value={option}>{option}</option>
								{/each}
							</select>
						</label>
						<label class="wide">
							<span>Notes</span>
							<textarea bind:value={selectedEditForm.notes} rows="6"></textarea>
						</label>
					{:else}
						<div class="field">
							<span>Title</span>
							<strong>{selectedReminder.title}</strong>
						</div>
						<div class="field">
							<span>Due</span>
							<strong>{formatDateTime(selectedReminder.due_at)}</strong>
						</div>
						<div class="field">
							<span>Status</span>
							<strong>{selectedReminder.status}</strong>
						</div>
						<div class="field">
							<span>Priority</span>
							<strong>{selectedReminder.priority}</strong>
						</div>
						<div class="field wide">
							<span>Entity</span>
							<p>{selectedReminder.entity_type || 'General'} {selectedReminder.entity_id || ''}</p>
						</div>
						<div class="field wide">
							<span>Notes</span>
							<p>{selectedReminder.notes || 'No notes yet.'}</p>
						</div>
					{/if}
				</div>
			{:else}
				<p class="notice">No reminder selected.</p>
			{/if}
		</section>

		<section class="panel">
			<div class="panel-header">
				<div>
					<h2>Actions</h2>
					<span>Quick add</span>
				</div>
			</div>
			<form onsubmit={(event) => {
				event.preventDefault();
				submitReminder();
			}}>
				<h3>New reminder</h3>
				<label class="wide">
					<span>Title</span>
					<input bind:value={form.title} required />
				</label>
				<div class="wide">
					<DateTimeField bind:value={form.due_at} label="Due at" required />
				</div>
				<label>
					<span>Priority</span>
					<select bind:value={form.priority}>
						<option>Low</option>
						<option>Normal</option>
						<option>High</option>
					</select>
				</label>
				<label>
					<span>Entity type</span>
					<select bind:value={form.entity_type}>
						{#each entityOptions as option (option)}
							<option value={option}>{option}</option>
						{/each}
					</select>
				</label>
				<label class="wide">
					<span>Notes</span>
					<textarea bind:value={form.notes} rows="6"></textarea>
				</label>
				<button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Create reminder'}</button>
			</form>
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
	.workspace {
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
		grid-template-columns: 14rem auto;
		align-items: end;
		margin-top: 1rem;
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
		grid-template-columns: 1.3fr 1fr 0.7fr auto;
		gap: 0.75rem;
		padding: 0.75rem 0;
		border-bottom: 1px solid var(--line);
		align-items: center;
		text-align: left;
		background: transparent;
	}

	.row strong,
	.row small {
		display: block;
	}

	.row small {
		margin-top: 0.2rem;
		color: var(--muted);
	}

	.item {
		border-left: 0;
		border-right: 0;
		border-top: 0;
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
	.field p {
		margin: 0;
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
