import React from "react";
import type { HTMLAttributes, TableHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export function Table({
  className,
  ...props
}: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="ui-table-wrap" tabIndex={0}>
      <table className={cn("ui-table", className)} {...props} />
    </div>
  );
}
export function TableHeader(props: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead {...props} />;
}
export function TableBody(props: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody {...props} />;
}
export function TableRow({
  className,
  ...props
}: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("ui-table-row", className)} {...props} />;
}
export function TableHead({
  className,
  ...props
}: HTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn("ui-table-head", className)} {...props} />;
}
export function TableCell({
  className,
  ...props
}: HTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("ui-table-cell", className)} {...props} />;
}
