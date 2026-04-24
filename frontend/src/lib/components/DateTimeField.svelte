<script lang="ts">
	let { label, value = $bindable(''), required = false, id }: {
		label: string;
		value?: string;
		required?: boolean;
		id?: string;
	} = $props();
</script>

<label class="datetime-field">
	<span>{label}</span>
	<input bind:value {id} {required} step={900} type="datetime-local" />
</label>

<style>
	.datetime-field {
		display: grid;
		gap: 0.35rem;
	}

	.datetime-field > span {
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
	}

	input {
		width: 100%;
		border: 1px solid var(--line);
		background: var(--panel);
		padding: 0.62rem 0.72rem;
		color: var(--text);
	}
</style>
