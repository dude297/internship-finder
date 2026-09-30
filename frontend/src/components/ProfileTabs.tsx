import { NavLink } from 'react-router'

const tabClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-t border-b-2 px-3 py-1 ${
    isActive ? 'border-slate-900 font-medium' : 'border-transparent hover:bg-slate-100'
  }`

/** Eligibility (may I apply?) and Match (how well does it fit?) stay separate (ADR-001). */
export function ProfileTabs() {
  return (
    <nav aria-label="Profile sections" className="flex gap-2 border-b border-slate-200">
      <NavLink to="/profile" end className={tabClass}>
        Eligibility Profile
      </NavLink>
      <NavLink to="/profile/match" className={tabClass}>
        Match Profile
      </NavLink>
      {/* Not "Sources": the main nav's Sources link (job boards) must stay unambiguous. */}
      <NavLink to="/profile/sources" className={tabClass}>
        Imported Profile
      </NavLink>
    </nav>
  )
}
