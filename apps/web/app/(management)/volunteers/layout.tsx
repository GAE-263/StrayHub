export default function VolunteerManagementLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // The parent ManagementLayout verifies SHELTER_ADMIN/PLATFORM_ADMIN before
  // mounting this subtree, so child pages cannot issue management requests first.
  return children;
}
