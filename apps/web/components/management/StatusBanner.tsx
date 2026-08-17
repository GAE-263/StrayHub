type Props = {
  kind: "info" | "success" | "warning" | "error";
  children: React.ReactNode;
};

export function StatusBanner({ kind, children }: Props) {
  return (
    <div
      className={`status-banner status-${kind}`}
      role={kind === "error" ? "alert" : "status"}
      aria-live={kind === "error" ? "assertive" : "polite"}
    >
      {children}
    </div>
  );
}
