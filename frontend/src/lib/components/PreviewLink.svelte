<script lang="ts">
	import { isPreviewableHref, normalizeExternalHref } from '$lib/utils/links';

	let { value, label = value, className = '' }: { value: string; label?: string; className?: string } = $props();

	const href = $derived(normalizeExternalHref(value));
	const previewable = $derived(isPreviewableHref(href));
</script>

{#if href}
	<span class={`preview-link ${className}`.trim()}>
		<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
		<a href={href} rel="noreferrer noopener" target="_blank">{label}</a>
		{#if previewable}
			<span class="preview-card">
				<span class="preview-meta">Preview</span>
				<iframe loading="lazy" referrerpolicy="no-referrer" sandbox="allow-same-origin allow-scripts" src={href} title={`Preview of ${label}`}></iframe>
				<small>Some sites block iframe previews. Open link if the preview stays blank.</small>
			</span>
		{/if}
	</span>
{:else}
	<span>{label}</span>
{/if}

<style>
	.preview-link {
		position: relative;
		display: inline-flex;
	}

	a {
		color: inherit;
		text-decoration: underline;
		text-decoration-thickness: 1px;
		text-underline-offset: 0.16em;
	}

	.preview-card {
		position: absolute;
		left: 0;
		top: calc(100% + 0.5rem);
		z-index: 30;
		display: none;
		width: min(32rem, 70vw);
		padding: 0.65rem;
		border: 1px solid var(--line-strong);
		background: var(--panel-strong);
		box-shadow: var(--shadow);
	}

	.preview-link:hover .preview-card,
	.preview-link:focus-within .preview-card {
		display: grid;
		gap: 0.45rem;
	}

	.preview-meta,
	small {
		font-size: 0.72rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--muted);
	}

	iframe {
		width: 100%;
		height: 18rem;
		border: 1px solid var(--line);
		background: var(--panel);
	}

	@media (max-width: 760px) {
		.preview-card {
			position: fixed;
			left: 1rem;
			right: 1rem;
			top: auto;
			bottom: 1rem;
			width: auto;
		}

		iframe {
			height: 14rem;
		}
	}
</style>
