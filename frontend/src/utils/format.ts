type DateLike = Date | string | number | null | undefined;

type FormatDateTimeOptions = {
  fallback?: string;
  includeTime?: boolean;
};

const DATE_TIME_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?$/;

const BEIJING_TIME_ZONE = "Asia/Shanghai";

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

function formatInBeijing(value: Date, includeTime: boolean) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    hour: includeTime ? "2-digit" : undefined,
    hour12: false,
    hourCycle: "h23",
    minute: includeTime ? "2-digit" : undefined,
    month: "2-digit",
    second: includeTime ? "2-digit" : undefined,
    timeZone: BEIJING_TIME_ZONE,
    year: "numeric",
  });
  const parts = Object.fromEntries(
    formatter
      .formatToParts(value)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );

  return formatDateParts(
    parts.year,
    parts.month,
    parts.day,
    parts.hour,
    parts.minute,
    parts.second,
    includeTime,
  );
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

    return formatInBeijing(value, includeTime);
  }

  if (typeof value === "number") {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
      ? fallback
      : formatInBeijing(parsed, includeTime);
  }

  const text = String(value).trim();
  if (!text) {
    return fallback;
  }

  const dateTimeMatch = text.match(DATE_TIME_PATTERN);
  if (dateTimeMatch) {
    const [, year, month, day, hour, minute, second, timeZone] = dateTimeMatch;
    if (timeZone) {
      const parsed = new Date(text);
      return Number.isNaN(parsed.getTime())
        ? fallback
        : formatInBeijing(parsed, includeTime);
    }
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
    return formatInBeijing(parsed, includeTime);
  }

  return text;
}
