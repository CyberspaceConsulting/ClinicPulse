"""Command line backup tool (run inside the API container).

On the NEW instance, create a key pair first; it prints the public key and writes a protected key file:
    docker compose exec backend python -m app.backup_cli keygen /backups/recovery-key.cpkey

On the OLD instance, create a backup readable only with that key (or use the stored recipients):
    docker compose exec backend python -m app.backup_cli export /backups/manual.cpbak --recipient CPPUB1:...

On the NEW instance, restore it:
    docker compose exec backend python -m app.backup_cli import /backups/manual.cpbak --key /backups/recovery-key.cpkey --yes

The key-file password is read from CLINICPULSE_KEY_PASSPHRASE or prompted for.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

from .backup_core import BackupError, create_backup, generate_recovery_key, load_recovery_key, restore_backup


def _passphrase(confirm: bool) -> str:
    value = os.environ.get("CLINICPULSE_KEY_PASSPHRASE")
    if value:
        return value
    value = getpass.getpass("Passwort der Schlüsseldatei: ")
    if confirm and getpass.getpass("Passwort wiederholen: ") != value:
        raise BackupError("Die Passwörter stimmen nicht überein")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.backup_cli", description="ClinicPulse backup tool")
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser("keygen", help="Create a recovery key pair (prints the public key)")
    keygen.add_argument("file", type=Path)
    export = commands.add_parser("export", help="Create a backup encrypted for the given public keys")
    export.add_argument("file", type=Path)
    export.add_argument("--recipient", action="append", default=[], help="Public key (CPPUB1:…); default: all stored recipients")
    restore = commands.add_parser("import", help="Replace ALL data with the contents of a backup file")
    restore.add_argument("file", type=Path)
    restore.add_argument("--key", type=Path, required=True, help="Recovery key file (.cpkey)")
    restore.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args(argv)

    try:
        if args.command == "keygen":
            public_key, key_file = generate_recovery_key(_passphrase(confirm=True))
            args.file.write_bytes(key_file)
            args.file.chmod(0o600)
            print(f"Schlüsseldatei geschrieben: {args.file}\nÖffentlicher Schlüssel (für die alte Instanz):\n{public_key}")
            return 0

        from .database import Base, SessionLocal, engine

        Base.metadata.create_all(bind=engine)
        if args.command == "export":
            with SessionLocal() as db:
                recipients = args.recipient
                if not recipients:
                    from sqlalchemy import select

                    from . import models

                    recipients = list(db.scalars(select(models.BackupRecipient.public_key)))
                data = create_backup(db, recipients)
            args.file.write_bytes(data)
            args.file.chmod(0o600)
            print(f"Backup geschrieben: {args.file} ({len(data)} Bytes)")
        else:
            if not args.yes and input("Alle vorhandenen Daten werden ERSETZT. Zum Fortfahren WIEDERHERSTELLEN eingeben: ") != "WIEDERHERSTELLEN":
                print("Abgebrochen.")
                return 1
            private_key = load_recovery_key(args.key.read_bytes(), _passphrase(confirm=False))
            with SessionLocal() as db:
                counts = restore_backup(db, args.file.read_bytes(), private_key, "cli")
            print(f"Wiederhergestellt: {sum(counts.values())} Datensätze in {len(counts)} Tabellen")
    except (BackupError, OSError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
