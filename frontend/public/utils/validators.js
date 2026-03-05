export function requiredText(value, min = 1) {
  return typeof value === 'string' && value.trim().length >= min;
}

export function isValidUrl(value) {
  if (!value || typeof value !== 'string') {
    return false;
  }

  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}
