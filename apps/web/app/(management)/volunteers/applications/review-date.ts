export type ServiceDateAvailability = {
  service_date: string;
  pending_count: number;
};

export function selectInitialServiceDate(
  today: string,
  availableDates: ServiceDateAvailability[],
): string {
  const dates = availableDates
    .filter((item) => item.pending_count > 0)
    .map((item) => item.service_date)
    .sort();
  if (dates.includes(today)) return today;
  return dates.find((value) => value > today) ?? dates.at(-1) ?? today;
}
