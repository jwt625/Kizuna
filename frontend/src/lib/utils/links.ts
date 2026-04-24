export function normalizeExternalHref(value: string): string | null {
	const trimmed = value.trim();
	if (!trimmed) return null;
	if (/^(https?:|mailto:|tel:)/i.test(trimmed)) return trimmed;
	if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) return `mailto:${trimmed}`;
	if (/^\+?[0-9()\-\s]+$/.test(trimmed)) return `tel:${trimmed.replace(/\s+/g, '')}`;
	return `https://${trimmed}`;
}

export function isPreviewableHref(href: string | null): boolean {
	return href ? /^https?:\/\//i.test(href) : false;
}
