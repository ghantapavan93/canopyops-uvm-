import { Role } from './models';

export interface DemoUser {
  key: string;
  role: Role;
  label: string;
  email: string;
}

/** The synthetic sign-ins the demonstration switches between.
 *
 *  Lives in core rather than the shell because role-gated workspaces need to
 *  offer "switch to the role that can do this and continue" in place — a
 *  reviewer should never have to go hunting for the switcher to find out why a
 *  screen looks blank.
 */
export const DEMO_USERS: DemoUser[] = [
  { key: 'manager', role: 'program_manager', label: 'Manager', email: 'manager@synthetic.test' },
  { key: 'crew', role: 'field_crew', label: 'Field crew', email: 'crew@synthetic.test' },
  { key: 'reviewer', role: 'quality_reviewer', label: 'Reviewer', email: 'reviewer@synthetic.test' },
  { key: 'compliance', role: 'compliance_reviewer', label: 'Compliance', email: 'compliance@synthetic.test' },
  // A different program (tenant) — switching here proves isolation: the data changes.
  { key: 'northgrid', role: 'program_manager', label: 'NorthGrid ⧉', email: 'ng.manager@synthetic.test' },
];

/** The password every synthetic user shares. Not a secret — these accounts exist
 *  only in the seeded demo database. */
export const DEMO_PASSWORD = 'canopyops';

/** Human label for a role, for copy like "designed for Field crew". */
export const ROLE_LABEL: Record<Role, string> = {
  program_manager: 'Program Manager',
  field_crew: 'Field Crew',
  quality_reviewer: 'Quality Reviewer',
  compliance_reviewer: 'Compliance Reviewer',
};

/** The demo sign-in that can act as `role`, preferring the demo program. */
export function demoUserForRole(role: Role): DemoUser | undefined {
  return DEMO_USERS.find((u) => u.role === role && u.key !== 'northgrid');
}
