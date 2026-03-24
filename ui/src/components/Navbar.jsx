import { NavLink } from 'react-router-dom'

export default function Navbar() {
  return (
    <nav className="navbar navbar-dark bg-dark px-4 py-2">
      <div className="d-flex align-items-center gap-3">
        <div>
          <div className="nav-brand text-white">🔍 Riverline — Prompt Autopsy</div>
          <div className="nav-sub">AI Voice Agent Evaluation</div>
        </div>
      </div>

      <div className="d-flex gap-1 align-items-center">
        <NavLink
          to="/part1"
          className={({ isActive }) => `nav-tab nav-link ${isActive ? 'active' : ''}`}
        >
          Part 1
          <span className="tab-badge">Detective</span>
        </NavLink>

        <NavLink
          to="/part2"
          className={({ isActive }) => `nav-tab nav-link ${isActive ? 'active' : ''}`}
        >
          Part 2
          <span className="tab-badge coming">Surgeon</span>
        </NavLink>

        <NavLink
          to="/part3"
          className={({ isActive }) => `nav-tab nav-link ${isActive ? 'active' : ''}`}
        >
          Part 3
          <span className="tab-badge coming">Architect</span>
        </NavLink>

        <NavLink
          to="/test"
          className={({ isActive }) => `nav-tab nav-link ${isActive ? 'active' : ''}`}
        >
          Test Lab
          <span className="tab-badge lab">Upload</span>
        </NavLink>
      </div>
    </nav>
  )
}
