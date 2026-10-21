import type { ReactElement } from "react";
import { Link, matchPath, useLocation } from "react-router-dom";
import { useDocument } from "../api/hooks/documents";
import { Icon } from "./icons";

/** Shows the document's title once loaded (shares the page's own cached query). */
function DocumentTitle({ id }: { id: string }): ReactElement {
  const { data } = useDocument(id);
  return <>{data?.document.title ?? "Document"}</>;
}

type Spec = { label: ReactElement | string; to?: string };

function trail(pathname: string): Spec[] {
  const documents: Spec = { label: "Dashboard", to: "/" };
  if (pathname === "/") return [{ label: "Dashboard" }];
  if (matchPath("/verify", pathname)) return [{ label: "Verify a document" }];
  if (matchPath("/verifications", pathname)) return [{ label: "History" }];
  if (matchPath("/verifications/:id", pathname)) {
    return [{ label: "History", to: "/verifications" }, { label: "Report" }];
  }
  if (matchPath("/approvals", pathname)) return [{ label: "Approvals" }];
  if (matchPath("/documents/new", pathname)) return [documents, { label: "New document" }];
  const revision = matchPath("/documents/:id/revisions/new", pathname);
  if (revision?.params.id) {
    const id = revision.params.id;
    return [
      documents,
      { label: <DocumentTitle id={id} />, to: `/documents/${id}` },
      { label: "New revision" },
    ];
  }
  const doc = matchPath("/documents/:id", pathname);
  if (doc?.params.id) return [documents, { label: <DocumentTitle id={doc.params.id} /> }];
  return [{ label: "Page not found" }];
}

/** Top-bar trail; the last item is the page title. */
export function Breadcrumbs(): ReactElement {
  const { pathname } = useLocation();
  const items = trail(pathname);
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <li key={i} className="flex min-w-0 items-center gap-1.5">
              {i > 0 && (
                <Icon
                  name="chevronRight"
                  className="h-3.5 w-3.5 shrink-0 text-gray-400 dark:text-gray-600"
                />
              )}
              {last || !item.to ? (
                <span
                  aria-current={last ? "page" : undefined}
                  className="truncate font-display font-semibold text-gray-900 dark:text-white"
                >
                  {item.label}
                </span>
              ) : (
                <Link
                  to={item.to}
                  className="truncate text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
                >
                  {item.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
