import Link from "next/link";

export function Breadcrumbs({
  items,
}: {
  items: Array<{ label: string; href?: string }>;
}) {
  return (
    <nav aria-label="Breadcrumb" className="breadcrumbs">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`}>
          {index > 0 ? <span aria-hidden="true"> / </span> : null}
          {item.href ? (
            <Link className="text-link" href={item.href}>
              {item.label}
            </Link>
          ) : (
            item.label
          )}
        </span>
      ))}
    </nav>
  );
}
