export function hasFirmAdministration(permissions: string[] | undefined) { return Boolean(permissions?.includes('firm.manage')); }
