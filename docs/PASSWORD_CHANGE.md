# Self-service password change

The signed-in user opens **Parolayı değiştir** (shield icon in the top bar), or
`#/account/password`. Enter the current password, a new password of 16–200
characters and its confirmation. Spaces and Turkish characters are preserved;
the new password must differ from the current password. Invalid attempts clear
the form, so re-enter all three fields to retry.

Success ends **every session for that account**, including the submitting
session. Sign in again with the new password. Other users remain signed in.
Passwords are never placed in URLs, browser storage, audit text or application
configuration. The screen uses password-manager-compatible secret inputs and a
same-origin, CSRF-protected, non-cached POST.

## Server contract

`POST /api/v1/auth/password` accepts only `current_password`, `new_password` and
`confirm_password`. It derives the account from the authenticated session;
there is no target username or account ID. Any active authenticated role can
change its own password without acquiring access to client or matter data.

Within the existing exclusive firm authorization guard, the server verifies
the current scrypt hash and atomically updates only that hash, deletes all of
the user's login sessions and appends a minimal `password_changed` audit event.
No replacement session is issued. An unsuccessful current-password verification
returns 400 and records `password_change_failed`; five failures in five minutes
block further attempts for that account for the remainder of the window. A
wrong password does not expire a legitimate session. Missing/expired access
returns 401; origin/CSRF violations return 403. Invalid fields and confirmation,
unchanged passwords, and failed database transactions cannot change credentials
or revoke sessions. Database failures return a fixed message without driver
details. Repeated failures are an abuse control, not an account recovery flow.

Login pins the verified hash and rechecks its exact identity after acquiring the
shared guard. A login admitted before a completed password change cannot mint
a session using the old hash after waiting behind the change. Already admitted
requests finish before the exclusive change commits; queued authenticated
requests revalidate their session when admitted. PostgreSQL uses the existing
cross-process advisory guard; demo SQLite retains the local test guard.

## Preservation and deployment

This operation does not write runtime secret files, `.env`, document encryption
keys, original files, provider credentials, account roles/grants, evidence
versions, drafts or review histories. Existing account identity is preserved.
Do not edit `LA_BOOTSTRAP_PASSWORD_FILE` to change an existing account password:
bootstrap configuration only creates an absent account. After self-service
change, the bootstrap password file no longer represents the user's login
password. Restarting the application does not reset the chosen password.

Account recovery, administrator password resets, MFA/SSO and provider/volume key
rotation are separate work. This feature does not qualify those capabilities.
The owner's private draft version 3 remains **Needs review** until the owner
records a legal review; engineering checks cannot supply that decision.

## Verification

Synthetic tests cover exact secret preservation, all-own-session revocation,
peer-session survival, unchanged encrypted originals and database records,
denied current-password/confirmation/weak inputs, CSRF/origin enforcement,
account-scoped throttling and expiry, transaction rollback, minimal audit,
restart preservation and guard/login/session admission races. Frontend tests
verify empty secret fields, the pre-submit warning, exact same-origin CSRF POST,
local validation and distinction between wrong password and expired access.
CI retains all existing jobs, workers, coverage, timeouts and reserve gates.

Hosted exact-head checks, guarded merge, local installation, preservation
comparison and owner acceptance remain separately recorded evidence states.
Do not change the real owner's password merely to demonstrate the feature.
