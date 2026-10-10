import type { ReactElement } from "react";

function Placeholder({ title }: { title: string }): ReactElement {
  return (
    <main className="p-6">
      <h1 className="page-title">{title}</h1>
      <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">Not implemented yet.</p>
    </main>
  );
}

export const NotFound = () => <Placeholder title="Page not found" />;
