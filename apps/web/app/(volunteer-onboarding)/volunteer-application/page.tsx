import { redirect } from "next/navigation";

type Props = {
  searchParams: Promise<{ entry?: string }>;
};

export default async function VolunteerApplicationRoute({
  searchParams,
}: Props) {
  const params = await searchParams;
  const entry = params.entry?.trim();
  redirect(
    entry
      ? `/volunteer-entry?entry=${encodeURIComponent(entry)}`
      : "/volunteer-entry",
  );
}
