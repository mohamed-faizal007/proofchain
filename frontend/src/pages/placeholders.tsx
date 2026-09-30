import type { ReactElement } from "react";

function Placeholder({ title }: { title: string }): ReactElement {
  return (
    <main className="p-6">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">Not implemented yet.</p>
    </main>
  );
}

export const RevisionNew = () => <Placeholder title="New revision" />;
export const NotFound = () => <Placeholder title="Page not found" />;
