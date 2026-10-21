import type { MouseEvent, ReactElement } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Document } from "../../api/types";
import { formatDate, relativeTime } from "../../lib/format";
import { TypeChip, VersionBadge } from "../Badges";
import { Icon } from "../icons";

/** The list has no anchor field, so the badge says what the list does know: whether a version has
 * been approved. Anchor state is on the document page. */
function ApprovalBadge({ doc }: { doc: Document }): ReactElement {
  return doc.latest_approved_version_no != null ? (
    <span className="badge badge-green">
      <Icon name="checkCircle" className="h-3.5 w-3.5" strokeWidth={2.2} />
      Approved
    </span>
  ) : (
    <span className="badge badge-amber">
      <Icon name="clock" className="h-3.5 w-3.5" strokeWidth={2.2} />
      Awaiting approval
    </span>
  );
}

const TH = "eyebrow px-5 py-3.5 !text-[11px]";

export function DocumentsTable({ items }: { items: Document[] }): ReactElement {
  const navigate = useNavigate();

  // Whole-row click is a pointer convenience; the title link stays the keyboard/AT target.
  function openRow(e: MouseEvent<HTMLElement>, to: string): void {
    if ((e.target as HTMLElement).closest("a,button,input,select,textarea")) return;
    navigate(to);
  }

  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b bg-gray-50/80 dark:bg-gray-800/30">
          <th className={TH}>Title</th>
          <th className={TH}>Type</th>
          <th className={TH}>Latest version</th>
          <th className={TH}>Status</th>
          <th className={`${TH} hidden md:table-cell`}>Revisions</th>
          <th className={TH}>Updated</th>
        </tr>
      </thead>
      <tbody className="stagger">
        {items.map((doc) => (
          <tr
            key={doc.id}
            onClick={(e) => openRow(e, `/documents/${doc.id}`)}
            className="group cursor-pointer border-b border-gray-100 transition-colors last:border-b-0 hover:bg-blue-50/70 focus-within:bg-blue-50/70 dark:border-gray-800 dark:hover:bg-blue-500/[0.07] dark:focus-within:bg-blue-500/[0.07]"
          >
            <td className="px-5 py-3.5">
              <div className="flex items-center gap-3">
                <span
                  aria-hidden="true"
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-500/10 text-blue-600 ring-1 ring-inset ring-blue-500/20 transition-colors group-hover:bg-blue-500/20 dark:text-blue-300"
                >
                  <Icon name="document" className="h-5 w-5" />
                </span>
                <Link
                  to={`/documents/${doc.id}`}
                  className="font-semibold text-gray-900 hover:text-blue-600 dark:text-white dark:hover:text-blue-300"
                >
                  {doc.title}
                </Link>
              </div>
            </td>
            <td className="px-5 py-3.5">
              <TypeChip type={doc.doc_type} />
            </td>
            <td className="px-5 py-3.5">
              {doc.latest_approved_version_no != null ? (
                <VersionBadge>{`v${doc.latest_approved_version_no}`}</VersionBadge>
              ) : (
                <span className="text-gray-400">—</span>
              )}
            </td>
            <td className="px-5 py-3.5">
              <ApprovalBadge doc={doc} />
            </td>
            <td className="num hidden px-5 py-3.5 text-gray-600 md:table-cell dark:text-gray-300">
              {doc.revision_count}
            </td>
            <td className="px-5 py-3.5 text-gray-600 dark:text-gray-300">
              <time dateTime={doc.updated_at} title={formatDate(doc.updated_at)}>
                {relativeTime(doc.updated_at)}
              </time>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
