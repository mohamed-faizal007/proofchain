import type { ReactElement } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { RoleGate } from "../auth/RoleGate";
import { Icon, type IconName } from "./icons";

function Item({
  to,
  icon,
  end,
  children,
}: {
  to: string;
  icon: IconName;
  end?: boolean;
  children: string;
}): ReactElement {
  return (
    <NavLink to={to} end={end} className="nav-item">
      <Icon name={icon} className="h-[18px] w-[18px] shrink-0" />
      {children}
    </NavLink>
  );
}

/** One nav for both layouts: a fixed sidebar from `lg`, a slide-in drawer below it. */
export function SidebarNav(): ReactElement {
  const { user } = useAuth();
  return (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {user && (
        <Item to="/" icon="dashboard" end>
          Dashboard
        </Item>
      )}
      <Item to="/verify" icon="shield">
        Verify a document
      </Item>
      {user && (
        <Item to="/verifications" icon="history">
          History
        </Item>
      )}
      <RoleGate roles={["APPROVER"]}>
        <Item to="/approvals" icon="inbox">
          Approvals
        </Item>
      </RoleGate>
    </nav>
  );
}
