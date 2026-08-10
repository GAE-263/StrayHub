import { ManagementLayout } from "../../components/management/ManagementLayout";

export default function ManagementRouteLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return <ManagementLayout>{children}</ManagementLayout>;
}
