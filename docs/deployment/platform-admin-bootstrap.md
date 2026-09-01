# Production Platform Administrator Bootstrap

Use this one-shot operator command only when production has no usable platform administrator. It
creates the tenantless account `platform-admin` with role `PLATFORM_ADMIN`, records a system audit
event, and uses the normal Argon2 password and login flow.

The command requires all of these controls:

- `APP_ENV=production`;
- `STRAYHUB_ALLOW_PLATFORM_ADMIN_BOOTSTRAP=true`;
- `--confirm-username platform-admin`; and
- `PLATFORM_ADMIN_BOOTSTRAP_PASSWORD_FILE` pointing to a regular mode `0600` file containing at
  least 20 characters.

Run it with the migration database role because the runtime role cannot provision platform
identities. Do not put the password in Git, an environment variable, a command argument, or logs.

```bash
APP_ENV=production \
DATABASE_URL="$DATABASE_MIGRATION_URL" \
STRAYHUB_ALLOW_PLATFORM_ADMIN_BOOTSTRAP=true \
PLATFORM_ADMIN_BOOTSTRAP_PASSWORD_FILE=/run/secrets/platform-admin-password \
uv run python -m scripts.bootstrap_platform_admin \
  --confirm-username platform-admin
```

Use `--dry-run` first to execute the same checks and roll the transaction back. A repeated run is
accepted only when the existing account is active, still tenantless, still has the platform role,
and the supplied password matches. It never silently promotes an existing user or resets a
password. After creation, manage additional administrators and replacements through the protected
platform-administrator UI/API; the policy permits one or two active platform administrators.
