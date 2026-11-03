# Native read-only mounts and listener qualification

The opt-in campaign runs the existing portable preview in a disposable Linux
container. It uses copied public source, invented identities and encrypted
fixture histories. No client document, runtime configuration, real credential,
provider request or production volume is selected.

Run `python scripts/qualify_native_operator_preview.py --base-image IMAGE
--output NEW_REPORT.json` with an already loaded public dependency image. The
output path must be new. The image is resolved to its immutable ID and checked
for runtime environment or volume declarations; no image or dependency is pulled.
The build context admits only bounded tracked code and public fixtures. Its
source hashes, package manifest pin and frozen case-plan hash bind the run.
The campaign's generated publisher pin is a fixture input, not genuine operator
approval or proof of an external transfer channel.

Preparation and runtime use fresh labelled volumes. The preparation process may
set ownership using limited capabilities. Runtime uses UID/GID10002, no added
capabilities, no privilege escalation, a read-only root filesystem, two CPUs,
1 GiB memory and64 PIDs. Host source and package volumes are kernel-read-only;
only the private fixture work volume and a bounded temporary directory are
writable. A non-secret volume marker and ownership/mode checks prevent Docker's
empty workdir copy-up from replacing the prepared private directory. Actual
Docker configuration is checked before starting either process.

The container has **no egress network, host mounts or host ports**. A separate
server process uses a pre-bound socket on its own127.0.0.1 interface. The client
process sends real HTTP requests with the fixture's `operator.invalid` virtual
Host and Origin; this does not resolve external DNS or qualify TLS/proxies. No
login or account-provisioning HTTP route is introduced. Credentials move only
through a private inherited IPC channel and memory; access logging is disabled.
The native image does not require pytest: it uses existing pure fixture builders
with the real authentication, role, receipt, binding and ASGI implementations.

The frozen22 cases check:

- Kernel `EROFS` writes on both protected volumes; wrong manifest pin, changed
  asset, extra file, symlink, hardlink, wrong ownership and writable stage/host
  rejection with the default read-only policy.
- Generic page, current-session CSRF bootstrap, exact preview, mismatching and
  matching independently supplied fixture checksums, missing CSRF, wrong Origin,
  wrong Host and forwarded-header denial over the actual socket.
- A partial request body timing out through the original two-second receive
  bound; controlled five-minute expiry; subsequent session revocation; clean
  shutdown and a refused connection after exit.

Each deliberate request uses a fresh connection. There is no POST retry after
the existing one-second keep-alive limit. The clock advance uses private test
IPC, not an HTTP mutation route, so this proves controlled-clock behavior rather
than elapsed five-minute wall-time accuracy. The four encrypted histories and
two input/candidate stores retain exact bytes and file metadata. The disposable
session database changes only for the explicit revocation test. Source and
package inventories remain exact. All generated containers, volumes and image
tags are removed with ownership checks; no global cleanup/prune is used.

The checked report records the successful22-case candidate and earlier incomplete
development attempts without assigning them qualification credit. Diagnostics
contain phase names, exception classes and source locations, never exception
values, request headers, credentials or raw runtime configuration. Offline CI
checks the report, source pins, case inventory and isolation policy; it does not
start the native campaign automatically.

This qualifies the disposable mount/listener subset. Genuine operator approval,
key custody, channel provenance, native inference, production deployment, TLS,
DNS, reverse proxies and legal review remain unqualified. The owner's private
focused-analysis-v3 review remains pending. Next: interrupted-listener restart
and fresh authorization, with no automatic replay or authority renewal.
