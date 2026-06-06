type DateLike = Date | string | number | null | undefined;

type FormatDateTimeOptions = {
  fallback?: string;
  includeTime?: boolean;
};

const DATE_TIME_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;

function pad2(value: number) {
  return String(value).padStart(2, "0");
}

function formatDateParts(
  year: string,
  month: string,
  day: string,
  hour?: string,
  minute?: string,
  second?: string,
  includeTime = true,
) {
  const dateText = `${year}-${month}-${day}`;

  if (!includeTime || !hour || !minute || !second) {
    return dateText;
  }

  return `${dateText} ${hour}:${minute}:${second}`;
}

export function formatDateTime(
  value: DateLike,
  options: FormatDateTimeOptions = {},
) {
  const { fallback = "-", includeTime = true } = options;

  if (value === null || value === undefined || value === "") {
    return fallback;
  }

  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) {
      return fallback;
    }

    return formatDateParts(
      String(value.getFullYear()),
      pad2(value.getMonth() + 1),
      pad2(value.getDate()),
      pad2(value.getHours()),
      pad2(value.getMinutes()),
      pad2(value.getSeconds()),
      includeTime,
    );
  }

  const text = String(value).trim();
  if (!text) {
    return fallback;
  }

  const dateTimeMatch = text.match(DATE_TIME_PATTERN);
  if (dateTimeMatch) {
    const [, year, month, day, hour, minute, second] = dateTimeMatch;
    return formatDateParts(
      year,
      month,
      day,
      hour,
      minute,
      second,
      includeTime,
    );
  }

  const parsed = new Date(text);
  if (!Number.isNaN(parsed.getTime())) {
    return formatDateTime(parsed, options);
  }

  return text;
}
