import React from "react";

import VolunteerEntryClient from "./VolunteerEntryClient";

export const dynamic = "force-dynamic";

export default function VolunteerEntryPage() {
  return <VolunteerEntryClient liffId={process.env.LIFF_ID ?? ""} />;
}
