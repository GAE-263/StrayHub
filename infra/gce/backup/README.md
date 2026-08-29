# Phase B3 backup staging

Only policy and helper documentation belong in this directory. Runtime artifacts are written under
the Git-ignored `generated/` directory with owner-only permissions.

The generated directory is a local correctness-verification target, not durable storage. It must not
be mounted into nginx, Web, or API, and operators must not place real production dumps here on a
developer workstation. Production backups can contain credentials, PII, and shelter-owned data even
though the manifest itself excludes secrets.

The stable layout is transferred to the private GCS backup target by the Phase D3 host-side scripts:

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

Phase D3 uses only `gcloud storage` with ADC, verifies the manifest before and after transfer, and
writes `_COMPLETE` last. The existing B3 capture/restore scripts still do not contact GCS. See
`docs/deployment/gcs-backup.md`; live bucket/IAM/lifecycle acceptance remains deferred.
