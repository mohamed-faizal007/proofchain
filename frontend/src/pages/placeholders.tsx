import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import { IconTile } from "../components/Badges";

function Placeholder({ title }: { title: string }): ReactElement {
  return (
    <main className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <div className="card flex flex-col items-center px-6 py-14 text-center">
        <IconTile name="help" className="h-14 w-14" />
        <h1 className="page-title mt-5">{title}</h1>
        <p className="mt-2 max-w-sm text-sm text-gray-500 dark:text-gray-400">
          The page you are looking for does not exist or has moved.
        </p>
        <Link to="/" className="btn-primary mt-6">
          Back to the dashboard
        </Link>
      </div>
    </main>
  );
}

export const NotFound = () => <Placeholder title="Page not found" />;
