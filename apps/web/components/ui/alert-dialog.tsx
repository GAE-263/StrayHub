import React, { type ComponentProps } from "react";
import { Dialog } from "./dialog";

export function AlertDialog(props: ComponentProps<typeof Dialog>) {
  return <Dialog {...props} role="alertdialog" />;
}
