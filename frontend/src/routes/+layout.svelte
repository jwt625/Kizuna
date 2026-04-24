<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	type ThemeMode = 'light' | 'dark';

	const themeStorageKey = 'kizuna-theme';
	const sections = [
		{ href: '/people', label: 'People' },
		{ href: '/organizations', label: 'Organizations' },
		{ href: '/events', label: 'Events' },
		{ href: '/reminders', label: 'Reminders' },
		{ href: '/pipelines', label: 'Pipelines' },
		{ href: '/search', label: 'Search' },
		{ href: '/imports', label: 'Imports' },
		{ href: '/exports', label: 'Exports' }
	] as const;

	let { children } = $props();
	let theme = $state<ThemeMode>('light');

	function applyTheme(nextTheme: ThemeMode) {
		theme = nextTheme;
		globalThis.document.documentElement.dataset.theme = nextTheme;
	}

	function toggleTheme() {
		const nextTheme = theme === 'light' ? 'dark' : 'light';
		applyTheme(nextTheme);
		globalThis.localStorage.setItem(themeStorageKey, nextTheme);
	}

	onMount(() => {
		const media = globalThis.window.matchMedia('(prefers-color-scheme: dark)');
		const savedTheme = globalThis.localStorage.getItem(themeStorageKey);
		const initialTheme =
			savedTheme === 'light' || savedTheme === 'dark'
				? savedTheme
				: media.matches
					? 'dark'
					: 'light';

		applyTheme(initialTheme);

		const handleChange = (event: MediaQueryListEvent) => {
			if (globalThis.localStorage.getItem(themeStorageKey)) {
				return;
			}
			applyTheme(event.matches ? 'dark' : 'light');
		};

		media.addEventListener('change', handleChange);

		return () => media.removeEventListener('change', handleChange);
	});
</script>

<svelte:head>
	<link rel="icon" href={theme === 'dark' ? '/icons/kizuna-icon-white.svg' : '/icons/kizuna-icon.svg'} />
</svelte:head>

<div class="app-shell">
	<header class="statusbar">
		<div class="status-copy">
			<img class="logo logo-light" src="/icons/kizuna-icon.svg" alt="Kizuna logo" />
			<img class="logo logo-dark" src="/icons/kizuna-icon-white.svg" alt="Kizuna logo" />
			<div>
				<strong>Kizuna</strong>
				<span>Local-first relationship workspace</span>
			</div>
		</div>
		<nav class="sectionbar" aria-label="Primary">
			{#each sections as section (section.href)}
				<a
					href={resolve(section.href)}
					class:active={page.url.pathname === section.href}
					aria-current={page.url.pathname === section.href ? 'page' : undefined}
				>
					{section.label}
				</a>
			{/each}
		</nav>
		<button
			type="button"
			class="theme-toggle"
			onclick={toggleTheme}
			aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
			title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
		>
			<svg class="theme-icon sun" viewBox="0 0 24 24" aria-hidden="true">
				<circle cx="12" cy="12" r="4.5" />
				<line x1="12" y1="1.5" x2="12" y2="5" />
				<line x1="12" y1="19" x2="12" y2="22.5" />
				<line x1="1.5" y1="12" x2="5" y2="12" />
				<line x1="19" y1="12" x2="22.5" y2="12" />
				<line x1="4.2" y1="4.2" x2="6.8" y2="6.8" />
				<line x1="17.2" y1="17.2" x2="19.8" y2="19.8" />
				<line x1="17.2" y1="6.8" x2="19.8" y2="4.2" />
				<line x1="4.2" y1="19.8" x2="6.8" y2="17.2" />
			</svg>
			<svg class="theme-icon moon" viewBox="0 0 24 24" aria-hidden="true">
				<path d="M15.5 2.5a8.8 8.8 0 1 0 6 15.2A9.8 9.8 0 0 1 15.5 2.5Z" />
			</svg>
		</button>
	</header>

	<div class="app-body">
		{@render children()}
	</div>
</div>

<style>
	:global(:root) {
		--bg: #f3f3f1;
		--panel: #fbfbfa;
		--panel-strong: #ffffff;
		--line: #cbcbc5;
		--line-strong: #151515;
		--text: #111111;
		--muted: #626262;
		--muted-soft: #7c7c77;
		--accent: #111111;
		--selection-row-bg: #eceae1;
		--radius: 0;
		--shadow: 0 0 0 1px rgba(17, 17, 17, 0.06);
		font-family:
			'IBM Plex Sans', 'Aptos', 'Segoe UI', sans-serif;
		background: var(--bg);
		color: var(--text);
		color-scheme: light;
	}

	:global(:root[data-theme='dark']) {
		--bg: #111313;
		--panel: #171a1a;
		--panel-strong: #1c2020;
		--line: #353b3b;
		--line-strong: #f3f3f1;
		--text: #f5f5f0;
		--muted: #bbbbaf;
		--muted-soft: #949488;
		--accent: #f5f5f0;
		--selection-row-bg: #23292a;
		--shadow: 0 0 0 1px rgba(255, 255, 255, 0.04);
		color-scheme: dark;
	}

	:global(html) {
		background: var(--bg);
	}

	:global(body) {
		margin: 0;
		background:
			linear-gradient(to bottom, rgba(17, 17, 17, 0.03), rgba(17, 17, 17, 0.03)) 0 0 / 100% 1px
				no-repeat,
			var(--bg);
		color: var(--text);
		font-family: inherit;
	}

	:global(html[data-theme='dark'] body) {
		background:
			linear-gradient(to bottom, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.06)) 0 0 / 100%
				1px no-repeat,
			var(--bg);
	}

	:global(*) {
		box-sizing: border-box;
	}

	:global(a) {
		color: inherit;
	}

	:global(button),
	:global(input),
	:global(select),
	:global(textarea) {
		font: inherit;
	}
	
	:global(button),
	:global(input),
	:global(select),
	:global(textarea) {
		border-radius: 0;
	}

	.app-shell {
		min-height: 100vh;
	}

	.statusbar {
		position: sticky;
		top: 0;
		z-index: 20;
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.7rem 1.25rem;
		border-bottom: 1px solid var(--line-strong);
		background: color-mix(in srgb, var(--bg) 92%, transparent);
		backdrop-filter: blur(10px);
	}

	.sectionbar {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		flex: 1;
		align-items: center;
	}

	.sectionbar a {
		border: 1px solid var(--line);
		padding: 0.5rem 0.7rem;
		text-decoration: none;
		background: var(--panel);
	}

	.sectionbar a.active {
		border-color: var(--line-strong);
		background: var(--panel-strong);
		box-shadow: var(--shadow);
	}

	.status-copy {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex: 0 0 auto;
	}

	.status-copy div {
		display: grid;
		gap: 0.1rem;
	}

	.status-copy strong {
		font-size: 0.78rem;
		letter-spacing: 0.14em;
		text-transform: uppercase;
	}

	.status-copy span {
		color: var(--muted);
		font-size: 0.9rem;
	}

	.logo {
		width: 2.25rem;
		height: 2.25rem;
		display: block;
		flex: 0 0 auto;
	}

	.logo-dark {
		display: none;
	}

	:global(:root[data-theme='dark']) .logo-light {
		display: none;
	}

	:global(:root[data-theme='dark']) .logo-dark {
		display: block;
	}

	.theme-toggle {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2.75rem;
		height: 2.75rem;
		flex: 0 0 auto;
		padding: 0;
		border: 1px solid var(--line-strong);
		background: var(--panel-strong);
		color: var(--text);
		cursor: pointer;
	}

	.theme-icon {
		width: 1.2rem;
		height: 1.2rem;
		stroke: currentColor;
		fill: none;
		stroke-width: 1.8;
		stroke-linecap: round;
		stroke-linejoin: round;
	}

	.theme-icon.moon {
		display: none;
		fill: currentColor;
		stroke: none;
	}

	:global(:root[data-theme='dark']) .theme-icon.sun {
		display: none;
	}

	:global(:root[data-theme='dark']) .theme-icon.moon {
		display: block;
	}

	.app-body {
		min-height: calc(100vh - 61px);
	}

	@media (max-width: 760px) {
		.statusbar {
			padding: 0.75rem 1rem;
			align-items: flex-start;
			flex-wrap: wrap;
		}

		.theme-toggle {
			align-self: flex-end;
		}

		.sectionbar {
			order: 3;
			width: 100%;
		}
	}
</style>
