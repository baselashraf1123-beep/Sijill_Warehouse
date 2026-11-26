"""
نواة نظام سِجِلّ المخازن (Sijill Warehouse Core) - محرك أرشفة مستندات المخازن وسلاسل الإمداد
يعتمد على SQLite3 مع FTS5 للبحث النصي الفائق + SHA-256 لمنع التكرار + Pillow لمعالجة الصور وتصدير PDF وCSV.
"""

from __future__ import annotations

import csv
import hashlib
import shutil
import sqlite3
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageOps


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


@dataclass
class DocumentRecord:
    id: str
    title: str
    folder_id: Optional[str]
    doc_type: str
    ref_number: str
    po_number: str
    warehouse: str
    issuer: str
    keeper: str
    batch_number: str
    audit_status: str
    doc_date: str
    expiry_date: Optional[str]
    ocr_text: str
    notes: str
    file_name: str
    file_path: str
    thumb_path: str
    sha256: str
    file_size: int
    width: int
    height: int
    is_starred: int
    created_at: str
    updated_at: str
    tags: List[str]


class DuplicateDocumentError(Exception):
    """يُرفع عند محاولة أرشفة صورة مستند مكررة بنفس بصمة SHA-256."""

    def __init__(self, existing_id: str, existing_title: str):
        self.existing_id = existing_id
        self.existing_title = existing_title
        super().__init__(f"المستند موجود مسبقاً بعنوان '{existing_title}' (ID: {existing_id})")


class SijillArchive:
    """المدير الرئيسي لخزانة أرشيف المخازن المحلية."""

    def __init__(self, archive_dir: str | Path):
        self.root = Path(archive_dir).resolve()
        self.vault_dir = self.root / "vault"
        self.thumbs_dir = self.root / "thumbs"
        self.exports_dir = self.root / "exports"
        self.db_path = self.root / "sijill.db"

        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS folders (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                parent_id TEXT REFERENCES folders(id) ON DELETE CASCADE,
                icon TEXT DEFAULT 'folder',
                color TEXT DEFAULT '#2563eb',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL,
                doc_type TEXT DEFAULT 'إذن إضافة',
                ref_number TEXT DEFAULT '',
                po_number TEXT DEFAULT '',
                warehouse TEXT DEFAULT 'المخزن الرئيسي',
                issuer TEXT DEFAULT '',
                keeper TEXT DEFAULT '',
                batch_number TEXT DEFAULT '',
                audit_status TEXT DEFAULT 'قيد المراجعة',
                doc_date TEXT NOT NULL,
                expiry_date TEXT,
                ocr_text TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                thumb_path TEXT NOT NULL,
                sha256 TEXT NOT NULL UNIQUE,
                file_size INTEGER NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                is_starred INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS document_tags (
                doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (doc_id, tag_id)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                doc_id TEXT,
                details TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                doc_id UNINDEXED,
                title,
                doc_type,
                ref_number,
                po_number,
                warehouse,
                issuer,
                keeper,
                batch_number,
                ocr_text,
                notes,
                tags_text
            );
            """
        )
        self.conn.commit()

    def _log(self, action: str, doc_id: Optional[str], details: str = "") -> None:
        self.conn.execute(
            "INSERT INTO audit_log (action, doc_id, details, created_at) VALUES (?, ?, ?, ?)",
            (action, doc_id, details, datetime.now().isoformat(timespec="seconds")),
        )

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _make_thumbnail(self, src_path: Path, thumb_path: Path, max_size: Tuple[int, int] = (480, 480)) -> Tuple[int, int]:
        with Image.open(src_path) as img:
            img = ImageOps.exif_transpose(img)
            w, h = img.size
            thumb = img.copy()
            thumb.thumbnail(max_size, Image.Resampling.LANCZOS)
            if thumb.mode in ("RGBA", "P"):
                thumb = thumb.convert("RGB")
            thumb.save(thumb_path, format="JPEG", quality=85, optimize=True)
            return w, h

    def create_folder(self, name: str, parent_id: Optional[str] = None, icon: str = "folder", color: str = "#2563eb") -> str:
        folder_id = f"fld_{uuid.uuid4().hex[:10]}"
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO folders (id, name, parent_id, icon, color, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (folder_id, name.strip(), parent_id, icon, color, now),
        )
        self._log("CREATE_FOLDER", None, f"إنشاء خزانة مخزنية: {name}")
        self.conn.commit()
        return folder_id

    def list_folders(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT f.*, COUNT(d.id) AS doc_count
            FROM folders f
            LEFT JOIN documents d ON d.folder_id = f.id
            GROUP BY f.id
            ORDER BY f.created_at ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def add_document(
        self,
        source_image: str | Path,
        title: str,
        folder_id: Optional[str] = None,
        doc_type: str = "إذن إضافة",
        ref_number: str = "",
        po_number: str = "",
        warehouse: str = "المخزن الرئيسي",
        issuer: str = "",
        keeper: str = "",
        batch_number: str = "",
        audit_status: str = "قيد المراجعة",
        doc_date: Optional[str] = None,
        expiry_date: Optional[str] = None,
        ocr_text: str = "",
        notes: str = "",
        tags: Optional[List[str]] = None,
        allow_duplicate: bool = False,
    ) -> DocumentRecord:
        src = Path(source_image).resolve()
        if not src.exists():
            raise FileNotFoundError(f"الملف غير موجود: {src}")
        if src.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"صيغة غير مدعومة: {src.suffix}")

        sha = self.compute_sha256(src)
        if not allow_duplicate:
            existing = self.conn.execute("SELECT id, title FROM documents WHERE sha256 = ?", (sha,)).fetchone()
            if existing:
                raise DuplicateDocumentError(existing["id"], existing["title"])

        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat(timespec="seconds")
        doc_date = doc_date or date.today().isoformat()

        ym = doc_date[:7] if len(doc_date) >= 7 else datetime.now().strftime("%Y-%m")
        safe_wh = warehouse.strip().replace("/", "-") or "عام"
        dest_dir = self.vault_dir / safe_wh / ym
        dest_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{doc_id}{src.suffix.lower()}"
        dest_path = dest_dir / stored_name
        shutil.copy2(src, dest_path)

        thumb_path = self.thumbs_dir / f"{doc_id}.jpg"
        width, height = self._make_thumbnail(dest_path, thumb_path)
        file_size = dest_path.stat().st_size

        clean_tags = sorted({t.strip() for t in (tags or []) if t.strip()})

        self.conn.execute(
            """
            INSERT INTO documents (
                id, title, folder_id, doc_type, ref_number, po_number, warehouse, issuer, keeper,
                batch_number, audit_status, doc_date, expiry_date, ocr_text, notes,
                file_name, file_path, thumb_path, sha256, file_size, width, height,
                is_starred, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                doc_id,
                title.strip(),
                folder_id,
                doc_type.strip(),
                ref_number.strip(),
                po_number.strip(),
                warehouse.strip(),
                issuer.strip(),
                keeper.strip(),
                batch_number.strip(),
                audit_status.strip(),
                doc_date,
                expiry_date,
                ocr_text.strip(),
                notes.strip(),
                src.name,
                str(dest_path.relative_to(self.root)),
                str(thumb_path.relative_to(self.root)),
                sha,
                file_size,
                width,
                height,
                now,
                now,
            ),
        )

        self._sync_tags(doc_id, clean_tags)
        self._sync_fts(doc_id)
        self._log("ADD_DOCUMENT", doc_id, f"أرشفة ({warehouse}): {title}")
        self.conn.commit()
        return self.get_document(doc_id)  # type: ignore

    def _sync_tags(self, doc_id: str, tags: List[str]) -> None:
        self.conn.execute("DELETE FROM document_tags WHERE doc_id = ?", (doc_id,))
        for tag in tags:
            self.conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            tag_row = self.conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()
            self.conn.execute(
                "INSERT OR IGNORE INTO document_tags (doc_id, tag_id) VALUES (?, ?)",
                (doc_id, tag_row["id"]),
            )

    def _get_doc_tags(self, doc_id: str) -> List[str]:
        rows = self.conn.execute(
            """
            SELECT t.name FROM tags t
            JOIN document_tags dt ON dt.tag_id = t.id
            WHERE dt.doc_id = ?
            ORDER BY t.name ASC
            """,
            (doc_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def _sync_fts(self, doc_id: str) -> None:
        row = self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            return
        tags_text = " ".join(self._get_doc_tags(doc_id))
        self.conn.execute("DELETE FROM documents_fts WHERE doc_id = ?", (doc_id,))
        self.conn.execute(
            """
            INSERT INTO documents_fts (
                doc_id, title, doc_type, ref_number, po_number, warehouse,
                issuer, keeper, batch_number, ocr_text, notes, tags_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                row["title"],
                row["doc_type"],
                row["ref_number"],
                row["po_number"],
                row["warehouse"],
                row["issuer"],
                row["keeper"],
                row["batch_number"],
                row["ocr_text"],
                row["notes"],
                tags_text,
            ),
        )

    def get_document(self, doc_id: str) -> Optional[DocumentRecord]:
        row = self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["tags"] = self._get_doc_tags(doc_id)
        return DocumentRecord(**d)

    def update_document(self, doc_id: str, **fields: Any) -> DocumentRecord:
        allowed = {
            "title", "folder_id", "doc_type", "ref_number", "po_number",
            "warehouse", "issuer", "keeper", "batch_number", "audit_status",
            "doc_date", "expiry_date", "ocr_text", "notes", "is_starred",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if updates:
            updates["updated_at"] = datetime.now().isoformat(timespec="seconds")
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            self.conn.execute(
                f"UPDATE documents SET {set_clause} WHERE id = ?",
                (*updates.values(), doc_id),
            )
        if "tags" in fields and fields["tags"] is not None:
            clean_tags = sorted({t.strip() for t in fields["tags"] if t.strip()})
            self._sync_tags(doc_id, clean_tags)

        self._sync_fts(doc_id)
        self._log("UPDATE_DOCUMENT", doc_id, f"تحديث: {', '.join(fields.keys())}")
        self.conn.commit()
        rec = self.get_document(doc_id)
        if not rec:
            raise KeyError(f"المستند غير موجود: {doc_id}")
        return rec

    def delete_document(self, doc_id: str) -> None:
        rec = self.get_document(doc_id)
        if not rec:
            return
        for rel in (rec.file_path, rec.thumb_path):
            p = self.root / rel
            if p.exists():
                p.unlink()
        self.conn.execute("DELETE FROM documents_fts WHERE doc_id = ?", (doc_id,))
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self._log("DELETE_DOCUMENT", doc_id, f"حذف: {rec.title}")
        self.conn.commit()

    def search_documents(
        self,
        query: str = "",
        folder_id: Optional[str] = None,
        warehouse: Optional[str] = None,
        audit_status: Optional[str] = None,
        tag: Optional[str] = None,
        doc_type: Optional[str] = None,
        starred_only: bool = False,
        expiring_within_days: Optional[int] = None,
    ) -> List[DocumentRecord]:
        sql = "SELECT DISTINCT d.id FROM documents d"
        joins: List[str] = []
        where: List[str] = []
        params: List[Any] = []

        q = query.strip()
        if q:
            joins.append("JOIN documents_fts f ON f.doc_id = d.id")
            tokens = [t.replace('"', "") for t in q.split() if t.strip()]
            fts_expr = " AND ".join(f'"{tok}"*' for tok in tokens)
            where.append("documents_fts MATCH ?")
            params.append(fts_expr)

        if folder_id:
            where.append("d.folder_id = ?")
            params.append(folder_id)

        if warehouse:
            where.append("d.warehouse = ?")
            params.append(warehouse)

        if audit_status:
            where.append("d.audit_status = ?")
            params.append(audit_status)

        if tag:
            joins.append("JOIN document_tags dt ON dt.doc_id = d.id JOIN tags tg ON tg.id = dt.tag_id")
            where.append("tg.name = ?")
            params.append(tag)

        if doc_type:
            where.append("d.doc_type = ?")
            params.append(doc_type)

        if starred_only:
            where.append("d.is_starred = 1")

        if expiring_within_days is not None:
            today_str = date.today().isoformat()
            where.append("d.expiry_date IS NOT NULL AND d.expiry_date != '' AND date(d.expiry_date) <= date(?, '+' || ? || ' days')")
            params.extend([today_str, expiring_within_days])

        full_sql = " ".join([sql, *joins])
        if where:
            full_sql += " WHERE " + " AND ".join(where)
        full_sql += " ORDER BY d.is_starred DESC, d.doc_date DESC, d.created_at DESC"

        ids = [r["id"] for r in self.conn.execute(full_sql, params).fetchall()]
        return [self.get_document(i) for i in ids if self.get_document(i) is not None]  # type: ignore

    def rotate_document(self, doc_id: str, angle_cw: int = 90) -> DocumentRecord:
        rec = self.get_document(doc_id)
        if not rec:
            raise KeyError(doc_id)
        img_path = self.root / rec.file_path
        thumb_path = self.root / rec.thumb_path
        with Image.open(img_path) as img:
            rotated = img.rotate(-angle_cw, expand=True)
            rotated.save(img_path)
        w, h = self._make_thumbnail(img_path, thumb_path)
        sha = self.compute_sha256(img_path)
        self.conn.execute(
            "UPDATE documents SET width = ?, height = ?, sha256 = ?, updated_at = ? WHERE id = ?",
            (w, h, sha, datetime.now().isoformat(timespec="seconds"), doc_id),
        )
        self._log("ROTATE_DOCUMENT", doc_id, f"تدوير {angle_cw} درجة")
        self.conn.commit()
        return self.get_document(doc_id)  # type: ignore

    def enhance_scan(self, doc_id: str, contrast: float = 1.35, grayscale: bool = False) -> DocumentRecord:
        rec = self.get_document(doc_id)
        if not rec:
            raise KeyError(doc_id)
        img_path = self.root / rec.file_path
        thumb_path = self.root / rec.thumb_path
        with Image.open(img_path) as img:
            out = ImageOps.grayscale(img).convert("RGB") if grayscale else img.convert("RGB")
            out = ImageEnhance.Contrast(out).enhance(contrast)
            out = ImageEnhance.Sharpness(out).enhance(1.25)
            out.save(img_path)
        w, h = self._make_thumbnail(img_path, thumb_path)
        sha = self.compute_sha256(img_path)
        self.conn.execute(
            "UPDATE documents SET width = ?, height = ?, sha256 = ?, updated_at = ? WHERE id = ?",
            (w, h, sha, datetime.now().isoformat(timespec="seconds"), doc_id),
        )
        self._log("ENHANCE_SCAN", doc_id, f"تحسين المسح (تباين={contrast}, رمادي={grayscale})")
        self.conn.commit()
        return self.get_document(doc_id)  # type: ignore

    def export_to_pdf(self, doc_ids: List[str], out_pdf: str | Path) -> Path:
        images: List[Image.Image] = []
        try:
            for doc_id in doc_ids:
                rec = self.get_document(doc_id)
                if not rec:
                    continue
                img = Image.open(self.root / rec.file_path).convert("RGB")
                images.append(img)
            if not images:
                raise ValueError("لا توجد مستندات صالحة للتصدير.")
            out_path = Path(out_pdf).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            images[0].save(out_path, "PDF", resolution=150.0, save_all=True, append_images=images[1:])
            self._log("EXPORT_PDF", None, f"تصدير {len(images)} مستند إلى {out_path.name}")
            self.conn.commit()
            return out_path
        finally:
            for im in images:
                im.close()

    def export_register_csv(self, out_csv: str | Path, warehouse: Optional[str] = None) -> Path:
        docs = self.search_documents(warehouse=warehouse)
        out_path = Path(out_csv).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "المعرف", "العنوان", "النوع", "الرقم المرجعي", "أمر الشراء PO",
                "المخزن", "المورد/الجهة", "أمين المخزن", "رقم التشغيلة",
                "حالة الاعتماد", "تاريخ المستند", "تاريخ الانتهاء", "الوسوم",
            ])
            for d in docs:
                writer.writerow([
                    d.id, d.title, d.doc_type, d.ref_number, d.po_number,
                    d.warehouse, d.issuer, d.keeper, d.batch_number,
                    d.audit_status, d.doc_date, d.expiry_date or "", ", ".join(d.tags),
                ])
        self._log("EXPORT_CSV", None, f"تصدير سجل المخازن ({len(docs)} سجل)")
        self.conn.commit()
        return out_path

    def create_backup_zip(self, out_zip: str | Path) -> Path:
        out_path = Path(out_zip).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn.commit()
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for folder in (self.vault_dir, self.thumbs_dir):
                for p in folder.rglob("*"):
                    if p.is_file():
                        zf.write(p, p.relative_to(self.root))
            zf.write(self.db_path, self.db_path.name)
        return out_path

    def get_stats(self) -> Dict[str, Any]:
        total_docs = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        total_size = self.conn.execute("SELECT COALESCE(SUM(file_size), 0) FROM documents").fetchone()[0]
        total_folders = self.conn.execute("SELECT COUNT(*) FROM folders").fetchone()[0]
        pending_review = self.conn.execute("SELECT COUNT(*) FROM documents WHERE audit_status = 'قيد المراجعة'").fetchone()[0]
        expiring_soon = len(self.search_documents(expiring_within_days=30))
        return {
            "total_docs": total_docs,
            "total_size_bytes": total_size,
            "total_folders": total_folders,
            "pending_review": pending_review,
            "expiring_30_days": expiring_soon,
        }
