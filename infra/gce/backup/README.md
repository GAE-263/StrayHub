# Phase B3 backup staging

Only policy and helper documentation belong in this directory. Runtime artifacts are written under
the Git-ignored `generated/` directory with owner-only permissions.

The generated directory is a local correctness-verification target, not durable storage. It must not
be mounted into nginx, Web, or API, and operators must not place real production dumps here on a
developer workstation. Production backups can contain credentials, PII, and shelter-owned data even
though the manifest itself excludes secrets.

The stable layout is directly transferable to the future private GCS target:

```text
strayhub-backups/<environment>/<backup-id>/
├── manifest.json
├── postgres/
│   ├── metadata.json
│   └── postgres.dump
└── minio/
    ├── inventory.json
    └── objects/<original object keys>
```

Phase D will choose and verify transfer tooling, private-bucket IAM, retention enforcement, and a
restore initiated from GCS. No B3 script contacts GCS.
