
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import shutil
import hashlib

app = FastAPI(title="Backup Restore Verification")

# Project folders
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
DOCUMENTS_DIR = BASE_DIR / "documents"
BACKUP_DIR = BASE_DIR / "backups" / "documents"

# Create folders if they do not exist
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


# Calculate SHA-256 hash of a file
def calculate_hash(file_path: Path) -> str:
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


# Dashboard
@app.get("/")
def dashboard():
    html_file = FRONTEND_DIR / "index.html"

    if not html_file.is_file():
        raise HTTPException(
            status_code=404,
            detail="index.html not found inside frontend folder"
        )

    return FileResponse(html_file, media_type="text/html")


# Check server status
@app.get("/health")
def health():
    return {"status": "online"}


# Upload documents
@app.post("/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    uploaded_files = []

    for uploaded_file in files:
        filename = Path(uploaded_file.filename or "").name

        if not filename or filename in {".", ".."}:
            await uploaded_file.close()
            continue

        destination = DOCUMENTS_DIR / filename

        try:
            with destination.open("wb") as output:
                shutil.copyfileobj(uploaded_file.file, output)

            uploaded_files.append(filename)
        finally:
            await uploaded_file.close()

    if not uploaded_files:
        raise HTTPException(
            status_code=400,
            detail="No valid files were uploaded"
        )

    return {
        "message": "Documents uploaded successfully",
        "uploaded_files": uploaded_files,
        "count": len(uploaded_files)
    }


# List original and backup documents
@app.get("/documents")
def list_documents():
    originals = sorted(
        p.name for p in DOCUMENTS_DIR.iterdir() if p.is_file()
    )

    backups = sorted(
        p.name for p in BACKUP_DIR.iterdir() if p.is_file()
    )

    return {
        "documents": originals,
        "backups": backups,
        "document_count": len(originals),
        "backup_count": len(backups)
    }


# Create backup copies
@app.post("/backup")
def create_backup():
    original_files = [
        p for p in DOCUMENTS_DIR.iterdir() if p.is_file()
    ]

    if not original_files:
        raise HTTPException(
            status_code=400,
            detail="No documents found. Upload files first."
        )

    copied_files = []

    for original in original_files:
        backup_file = BACKUP_DIR / original.name
        shutil.copy2(original, backup_file)
        copied_files.append(original.name)

    return {
        "message": "Backup created successfully",
        "backup_files": copied_files,
        "count": len(copied_files)
    }


# Restore missing documents from backup
@app.post("/restore")
def restore_documents():
    backup_files = [
        p for p in BACKUP_DIR.iterdir() if p.is_file()
    ]

    if not backup_files:
        raise HTTPException(
            status_code=400,
            detail="No backup found. Create a backup first."
        )

    restored_files = []
    already_existing = []

    for backup_file in backup_files:
        original_file = DOCUMENTS_DIR / backup_file.name

        # Restore only if the original file is missing
        if not original_file.exists():
            shutil.copy2(backup_file, original_file)
            restored_files.append(backup_file.name)
        else:
            already_existing.append(backup_file.name)

    return {
        "message": "Restore operation completed",
        "restored_files": restored_files,
        "restored_count": len(restored_files),
        "already_existing": already_existing
    }


# Verify original files against backup copies
@app.get("/verify")
def verify_backup():
    original_files = {
        p.name: p
        for p in DOCUMENTS_DIR.iterdir()
        if p.is_file()
    }

    backup_files = {
        p.name: p
        for p in BACKUP_DIR.iterdir()
        if p.is_file()
    }

    missing_originals = sorted(
        name for name in backup_files
        if name not in original_files
    )

    missing_backups = sorted(
        name for name in original_files
        if name not in backup_files
    )

    mismatched_files = []

    for name in original_files.keys() & backup_files.keys():
        original_hash = calculate_hash(original_files[name])
        backup_hash = calculate_hash(backup_files[name])

        if original_hash != backup_hash:
            mismatched_files.append(name)

    mismatched_files.sort()

    verified = (
        len(backup_files) > 0
        and len(original_files) == len(backup_files)
        and not missing_originals
        and not missing_backups
        and not mismatched_files
    )

    return {
        "verified": verified,
        "message": (
            "All documents verified successfully"
            if verified
            else "Missing files or content differences detected"
        ),
        "original_count": len(original_files),
        "backup_count": len(backup_files),
        "missing_originals": missing_originals,
        "missing_backups": missing_backups,
        "mismatched_files": mismatched_files
    }
