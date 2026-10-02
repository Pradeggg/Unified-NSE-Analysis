# Encrypted Agent Adda database backup — 2 October 2026

This directory contains a complete portable `nse_market` PostgreSQL backup and its migration companion files, encrypted with GnuPG AES-256. The encrypted archive is stored through **Git LFS**.

The same snapshot is intended for the `database-backup-20261002` branch in:

- `agentadda/Unified-NSE-Analysis` (private)
- `Pradeggg/Unified-NSE-Analysis` (public, as explicitly requested)

Only the encrypted payload and non-sensitive restore metadata are published here. **The decryption passphrase is not in either repository.** Transfer it separately to the new machine using a secure method. A public copy of this ciphertext does not make the database readable without the passphrase.

## Download and decrypt

Install Git LFS, GnuPG, and PostgreSQL 16. Use a recent GnuPG release compatible with AES-256 symmetric encryption.

```bash
git clone --branch database-backup-20261002 https://github.com/Pradeggg/Unified-NSE-Analysis.git agentadda-db-backup
cd agentadda-db-backup
git lfs install --local
git lfs pull
cd backups/nse-market-20261002
LC_ALL=C shasum -a 256 -c SHA256SUMS
# Linux alternative: sha256sum -c SHA256SUMS
```

Using the private copy is equivalent: replace the clone URL with `https://github.com/agentadda/Unified-NSE-Analysis.git` and authenticate normally.

Place the separately transferred passphrase file somewhere private, outside any Git checkout, and restrict its permissions. Replace the example path below with that location:

```bash
chmod 600 /secure/path/nse-market-20261002.passphrase
gpg --batch --pinentry-mode loopback   --passphrase-file /secure/path/nse-market-20261002.passphrase   --output nse-market-20261002.tar --decrypt nse-market-20261002.tar.gpg
tar -xf nse-market-20261002.tar
cd nse-market-20261002
LC_ALL=C shasum -a 256 -c SHA256SUMS
```

Read the decrypted `RESTORE.md` for database provisioning, `pg_restore`, companion-file restoration, dependencies, and limitations. Restore into a new empty database; the guide does not drop or overwrite an existing database. The decrypted guide's private-Git staging section describes the original local package before this encrypted public-copy request; use **this outer README** for downloading the published package.

## Verification and contents

- Full logical backup of 19 schemas; 138 base tables/partitions verified against a consistent source snapshot after a successful isolated PostgreSQL 16 restore.
- Twelve materialized views rebuilt; three previously cached source summaries differed, and their rebuilt data was verified against the defining SQL.
- Encryption/decryption round-trip tested byte for byte; the decrypted database dump SHA-256 matches the original verified backup.
- Companion files include fund ledgers, recipient settings, and the pending 1 October trade-reconciliation audit. Those remain inside the encrypted archive.
- Equity, index, score, and stage data are through 1 October 2026; F&O data is through 30 September 2026.
- No `.env` files or PostgreSQL role passwords were intentionally included. API-key-shaped strings found in stored source documents were a further reason to encrypt the entire package rather than upload the raw dump.

This is a database-migration snapshot, not an application-source release. The backup branch starts from the public repository's existing code baseline. Install the intended application version separately; uncommitted source changes and external cached filings/PDFs/reports are not included in the backup.

Keep the passphrase safely: **Git cannot recover it.** Decrypted files are ignored in this directory to reduce the chance of committing them accidentally.
