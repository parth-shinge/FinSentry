import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Dashboard", icon: "📊" },
  { to: "/investigations", label: "Investigations", icon: "🔍" },
  { to: "/reports", label: "Reports", icon: "📄" },
];

export default function Sidebar() {
  return (
    <aside className="hidden md:flex w-56 flex-col border-r border-gray-200 bg-gray-50 p-4">
      <nav className="flex flex-col gap-1 mt-2">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-blue-50 text-blue-700"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              }`
            }
          >
            <span className="text-base">{l.icon}</span>
            {l.label}
          </NavLink>
        ))}
      </nav>

      {/* Bottom info */}
      <div className="mt-auto pt-6 border-t border-gray-200">
        <p className="text-xs text-gray-400 leading-relaxed">
          FinSentry v1.0
          <br />
          Financial Crime Detection
        </p>
      </div>
    </aside>
  );
}
