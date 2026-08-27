import VolunteerEntryClient from "../../(volunteer)/volunteer-entry/VolunteerEntryClient";
import VolunteerApplicationClient from "./VolunteerApplicationClient";

type Props = {
  searchParams: Promise<{ entry?: string; shelter_entry_reference?: string }>;
};

export default async function VolunteerApplicationRoute({
  searchParams,
}: Props) {
  const params = await searchParams;
  const entry = params.entry?.trim() || params.shelter_entry_reference?.trim();
  if (entry) {
    return <VolunteerEntryClient liffId={process.env.LIFF_ID ?? ""} />;
  }
  return <VolunteerApplicationClient liffId={process.env.LIFF_ID ?? ""} />;
}
