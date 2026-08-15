import { VolunteerApplicationPage } from "../../../features/volunteer-access/VolunteerApplicationPage";

type Props = {
  searchParams: Promise<{ entry?: string; id_token?: string }>;
};

export default async function VolunteerApplicationRoute({
  searchParams,
}: Props) {
  const params = await searchParams;
  return (
    <VolunteerApplicationPage
      idToken={params.id_token ?? ""}
      shelterEntryReference={params.entry ?? ""}
    />
  );
}
