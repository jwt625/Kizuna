<script lang="ts">
	const quickMinuteOptions = ['00', '15', '30', '45'];
	const hourOptions = Array.from({ length: 24 }, (_, index) => `${index}`.padStart(2, '0'));

	let { label, value = $bindable(''), required = false, id }: {
		label: string;
		value?: string;
		required?: boolean;
		id?: string;
	} = $props();

	let date = $state('');
	let hour = $state('09');
	let quickMinute = $state('00');
	let exactMinute = $state('0');
	let exactMode = $state(false);
	let syncingFromValue = false;

	function syncFromValue(nextValue: string) {
		if (!nextValue) {
			date = '';
			hour = '09';
			quickMinute = '00';
			exactMinute = '0';
			exactMode = false;
			return;
		}

		const [nextDate, nextTime = '09:00'] = nextValue.split('T');
		const [nextHour = '09', nextMinute = '00'] = nextTime.split(':');
		date = nextDate;
		hour = nextHour.padStart(2, '0');
		quickMinute = quickMinuteOptions.includes(nextMinute) ? nextMinute : '00';
		exactMinute = `${Number(nextMinute) || 0}`;
		exactMode = !quickMinuteOptions.includes(nextMinute);
	}

	function composeValue() {
		if (!date) {
			value = '';
			return;
		}

		const minuteNumber = exactMode ? Math.min(59, Math.max(0, Number(exactMinute) || 0)) : Number(quickMinute);
		const minute = `${minuteNumber}`.padStart(2, '0');
		value = `${date}T${hour}:${minute}`;
	}

	$effect(() => {
		syncingFromValue = true;
		syncFromValue(value);
		syncingFromValue = false;
	});

	$effect(() => {
		if (syncingFromValue) {
			return;
		}
		composeValue();
	});
</script>

<fieldset class="datetime-field">
	<legend>{label}</legend>
	<div class="datetime-grid">
		<label>
			<span>Date</span>
			<input bind:value={date} {id} {required} type="date" />
		</label>
		<label>
			<span>Hour</span>
			<select bind:value={hour}>
				{#each hourOptions as option (option)}
					<option value={option}>{option}</option>
				{/each}
			</select>
		</label>
		<label>
			<span>Quick minute</span>
			<select bind:value={quickMinute} disabled={exactMode}>
				{#each quickMinuteOptions as option (option)}
					<option value={option}>{option}</option>
				{/each}
			</select>
		</label>
		<label>
			<span>Exact minute</span>
			<input bind:value={exactMinute} disabled={!exactMode} max="59" min="0" type="number" />
		</label>
	</div>
	<label class="fine-toggle">
		<input bind:checked={exactMode} type="checkbox" />
		<span>Manual minute edit</span>
	</label>
</fieldset>

<style>
	.datetime-field {
		display: grid;
		gap: 0.6rem;
		padding: 0;
		margin: 0;
		border: 0;
		min-width: 0;
	}

	legend,
	span {
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
	}

	.datetime-grid {
		display: grid;
		grid-template-columns: minmax(0, 1.2fr) repeat(3, minmax(0, 0.7fr));
		gap: 0.75rem;
	}

	label {
		display: grid;
		gap: 0.35rem;
		min-width: 0;
	}

	input,
	select {
		width: 100%;
		border: 1px solid var(--line);
		background: var(--panel);
		padding: 0.62rem 0.72rem;
		color: var(--text);
	}

	.fine-toggle {
		grid-template-columns: auto 1fr;
		align-items: center;
		gap: 0.55rem;
	}

	.fine-toggle input {
		width: auto;
		margin: 0;
	}

	@media (max-width: 760px) {
		.datetime-grid {
			grid-template-columns: 1fr 1fr;
		}
	}
</style>
