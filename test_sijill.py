import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from PIL import Image, ImageDraw

from sijill_core import SijillArchive, DuplicateDocumentError


def _make_sample_image(path: Path, color: tuple[int, int, int], text: str) -> Path:
    img = Image.new("RGB", (800, 1100), color=color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, 760, 1060], outline=(30, 41, 59), width=4)
    draw.text((80, 100), text, fill=(15, 23, 42))
    img.save(path, format="PNG")
    return path


class TestSijillWarehouseArchive(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="sijill_wh_test_"))
        self.archive = SijillArchive(self.tmp / "archive_vault")
        self.samples = self.tmp / "samples"
        self.samples.mkdir()

    def tearDown(self) -> None:
        self.archive.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_warehouse_archive_workflow(self) -> None:
        grn_fld = self.archive.create_folder("أذون الإضافة والاستلام", icon="package-plus", color="#059669")
        audit_fld = self.archive.create_folder("محاضر الجرد والتسويات", icon="clipboard-check", color="#2563eb")

        img1 = _make_sample_image(self.samples / "grn_501.png", (245, 250, 248), "GRN-501 PO-2026-991")
        img2 = _make_sample_image(self.samples / "coa_12.png", (255, 250, 240), "COA Batch B-884")

        soon = (date.today() + timedelta(days=12)).isoformat()
        rec1 = self.archive.add_document(
            img1,
            title="إذن إضافة خامات تغليف - شحنة النيل",
            folder_id=grn_fld,
            doc_type="إذن إضافة",
            ref_number="GRN-2026-501",
            po_number="PO-2026-991",
            warehouse="مخزن المواد الخام",
            issuer="شركة النيل للتغليف",
            keeper="أحمد محمود",
            batch_number="B-2026-11",
            audit_status="معتمد",
            ocr_text="استلام 500 كرتونة سليمة مطابقة للمواصفات",
            tags=["خامات", "استلام", "2026"],
        )
        rec2 = self.archive.add_document(
            img2,
            title="شهادة صلاحية وجودة تشغيلة B-884",
            folder_id=audit_fld,
            doc_type="شهادة جودة",
            ref_number="COA-884",
            po_number="PO-2026-991",
            warehouse="المخزن الرئيسي",
            issuer="مختبر الجودة المركزي",
            keeper="كريم حسن",
            batch_number="B-884",
            audit_status="قيد المراجعة",
            expiry_date=soon,
            tags=["جودة", "صلاحية"],
        )

        with self.assertRaises(DuplicateDocumentError):
            self.archive.add_document(img1, title="مكرر")

        # البحث برقم أمر الشراء يربط الإذن بالشهادة (3-Way Matching)
        po_matches = self.archive.search_documents(query="PO-2026-991")
        self.assertEqual(len(po_matches), 2)

        # الفلترة بالمخزن وحالة الاعتماد
        pending = self.archive.search_documents(audit_status="قيد المراجعة")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].id, rec2.id)

        raw_wh = self.archive.search_documents(warehouse="مخزن المواد الخام")
        self.assertEqual(len(raw_wh), 1)
        self.assertEqual(raw_wh[0].id, rec1.id)

        # تصدير سجل CSV وPDF والنسخ الاحتياطي
        csv_out = self.archive.export_register_csv(self.tmp / "warehouse_register.csv")
        self.assertTrue(csv_out.exists())
        self.assertIn("GRN-2026-501", csv_out.read_text(encoding="utf-8-sig"))

        pdf_out = self.archive.export_to_pdf([rec1.id, rec2.id], self.tmp / "bundle.pdf")
        self.assertTrue(pdf_out.exists())

        zip_out = self.archive.create_backup_zip(self.tmp / "backup.zip")
        self.assertTrue(zip_out.exists())

        stats = self.archive.get_stats()
        self.assertEqual(stats["total_docs"], 2)
        self.assertEqual(stats["pending_review"], 1)
        self.assertEqual(stats["expiring_30_days"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
