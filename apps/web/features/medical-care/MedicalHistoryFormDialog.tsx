"use client";

import { Dialog } from "../../components/ui/dialog";
import { MedicalHistoryPanel } from "./MedicalHistoryPanel";

export function MedicalHistoryFormDialog({
  open,
  animalId,
  onClose,
}: {
  open: boolean;
  animalId: string;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} title="新增醫療紀錄" onClose={onClose}>
      <MedicalHistoryPanel animalId={animalId} />
    </Dialog>
  );
}
