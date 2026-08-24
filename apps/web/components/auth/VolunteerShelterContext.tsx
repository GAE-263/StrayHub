"use client";

import { createContext, useContext } from "react";

export type VolunteerShelterContextValue = {
  organizationId: string;
  organizationName?: string | null;
};

export const VolunteerShelterContext =
  createContext<VolunteerShelterContextValue | null>(null);

export function useVolunteerShelterContext(): VolunteerShelterContextValue | null {
  return useContext(VolunteerShelterContext);
}
