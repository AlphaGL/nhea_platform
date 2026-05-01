"""
NHEA Voting System — Nominee Image Upload Script
=================================================
Place this file at:
    voting/management/commands/upload_images.py

USAGE
─────
Auto-generate placeholder avatars for all nominees (no images needed):
    python manage.py upload_images --placeholders

Upload your own images from the nominee_images/ folder:
    python manage.py upload_images

Other flags:
    --dry-run          Show what would happen without uploading
    --overwrite        Re-upload even if nominee already has an image
    --list             List all nominees and their current image status
    --folder FOLDER    Cloudinary folder name (default: nominees)
"""

import difflib
import urllib.request
import urllib.parse
from django.core.management.base import BaseCommand, CommandError
import cloudinary
import cloudinary.uploader


# ─── Supported image extensions ───────────────────────────────────────────────
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}

# ─── Manual filename → nominee name overrides ─────────────────────────────────
MANUAL_MAP = {
    # "luth": "Lagos University Teaching Hospital",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_initials(name: str) -> str:
    """Extract up to 2 initials from a name, skipping titles."""
    skip = {"dr", "prof", "nurse", "pharm", "mls", "mr", "mrs", "ms"}
    words = [w for w in name.split() if w.lower() not in skip and w[0].isalpha()]
    if len(words) >= 2:
        return (words[0][0] + words[-1][0]).upper()
    return words[0][:2].upper() if words else "NA"


def pick_color(name: str) -> str:
    """Pick a consistent background colour based on the name."""
    COLORS = [
        "1abc9c", "2ecc71", "3498db", "9b59b6", "e74c3c",
        "e67e22", "16a085", "2980b9", "8e44ad", "c0392b",
        "27ae60", "f39c12", "d35400", "1565C0", "6A1B9A",
    ]
    return COLORS[sum(ord(c) for c in name) % len(COLORS)]


def download_avatar(name: str, size: int = 256) -> bytes:
    """Download a coloured initial-avatar PNG from ui-avatars.com."""
    params = urllib.parse.urlencode({
        "name":       get_initials(name),
        "size":       size,
        "background": pick_color(name),
        "color":      "ffffff",
        "bold":       "true",
        "font-size":  "0.45",
        "format":     "png",
    })
    url = f"https://ui-avatars.com/api/?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "nhea-upload/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read()


def upload_bytes_to_cloudinary(image_bytes: bytes, public_id: str, folder: str) -> str:
    result = cloudinary.uploader.upload(
        image_bytes,
        public_id=public_id,
        folder=folder,
        overwrite=True,
        resource_type="image",
    )
    return result["public_id"]


def upload_file_to_cloudinary(filepath: str, public_id: str, folder: str) -> str:
    result = cloudinary.uploader.upload(
        filepath,
        public_id=public_id,
        folder=folder,
        overwrite=True,
        resource_type="image",
    )
    return result["public_id"]


def normalise(text: str) -> str:
    text = text.lower().strip().replace("_", " ").replace("-", " ")
    for prefix in ("dr ", "prof ", "nurse ", "pharm ", "mls "):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return " ".join(text.split())


def best_match(stem: str, names: list, cutoff: float = 0.70):
    needle = normalise(stem)
    best_name, best_score = None, 0.0
    for name in names:
        score = difflib.SequenceMatcher(None, needle, normalise(name)).ratio()
        if score > best_score:
            best_score, best_name = score, name
    return (best_name, best_score) if best_score >= cutoff else (None, best_score)


# ─── Command ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Upload nominee images to Cloudinary (local files or auto-generated placeholders)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--placeholders", action="store_true",
            help="Auto-generate and upload coloured avatar placeholders (no local images needed).",
        )
        parser.add_argument(
            "--images-dir", default="nominee_images", metavar="DIR",
            help="Local folder containing images (default: nominee_images/)",
        )
        parser.add_argument(
            "--folder", default="nominees", metavar="FOLDER",
            help="Cloudinary destination folder (default: nominees)",
        )
        parser.add_argument("--dry-run", action="store_true",
                            help="Preview without uploading.")
        parser.add_argument("--overwrite", action="store_true",
                            help="Re-upload even if nominee already has an image.")
        parser.add_argument("--list", action="store_true",
                            help="Show all nominees and image status, then exit.")

    def handle(self, *args, **options):
        if options["list"]:
            self._list_nominees()
            return

        if options["placeholders"]:
            self._upload_placeholders(options["folder"], options["dry_run"], options["overwrite"])
        else:
            self._upload_from_folder(
                options["images_dir"], options["folder"],
                options["dry_run"], options["overwrite"],
            )

    # ── Mode 1: Auto placeholder avatars ──────────────────────────────

    def _upload_placeholders(self, folder, dry_run, overwrite):
        from voting.models import Nominee

        nominees = list(Nominee.objects.select_related("category").all())
        if not nominees:
            raise CommandError("No nominees found. Run populate_nhea first.")

        self.stdout.write(self.style.WARNING(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"Generating avatars for {len(nominees)} nominees…\n"
        ))

        uploaded = skipped = errors = 0

        for nominee in nominees:
            current = str(nominee.image) if nominee.image else ""
            if current and not overwrite:
                self.stdout.write(f"  [skip] {nominee.name}  (already has image)")
                skipped += 1
                continue

            self.stdout.write(f"  → {nominee.name}  ({nominee.category.name})")

            if dry_run:
                self.stdout.write(self.style.SUCCESS(
                    f"      would upload avatar  initials={get_initials(nominee.name)}  "
                    f"bg=#{pick_color(nominee.name)}"
                ))
                uploaded += 1
                continue

            try:
                img_bytes = download_avatar(nominee.name)
                safe      = nominee.name.lower().replace(" ", "_")[:40]
                public_id = f"nhea_nominee_{nominee.pk}_{safe}"
                pid       = upload_bytes_to_cloudinary(img_bytes, public_id, folder)
                nominee.image = pid
                nominee.save(update_fields=["image"])
                self.stdout.write(self.style.SUCCESS(f"      ✓ {pid}"))
                uploaded += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"      ✗ failed: {exc}"))
                errors += 1

        self._summary(uploaded, skipped, 0, errors, dry_run)

    # ── Mode 2: Upload from local folder ──────────────────────────────

    def _upload_from_folder(self, images_dir, folder, dry_run, overwrite):
        from pathlib import Path
        from voting.models import Nominee

        images_path = Path(images_dir)
        if not images_path.exists():
            raise CommandError(
                f"Directory '{images_dir}' not found.\n"
                f"Run with --placeholders to auto-generate avatars instead:\n\n"
                f"    python manage.py upload_images --placeholders\n"
            )

        image_files = [
            f for f in images_path.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
        ]
        if not image_files:
            raise CommandError(
                f"No images in '{images_dir}'.\n"
                f"Run with --placeholders to auto-generate avatars instead:\n\n"
                f"    python manage.py upload_images --placeholders\n"
            )

        all_nominees  = list(Nominee.objects.select_related("category").all())
        nominee_names = [n.name for n in all_nominees]

        self.stdout.write(self.style.WARNING(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"Scanning {len(image_files)} image(s) in '{images_dir}/'…\n"
        ))

        uploaded = skipped = no_match = errors = 0

        for img_path in sorted(image_files):
            stem   = img_path.stem
            manual = MANUAL_MAP.get(stem.lower())
            if manual:
                matched, score, via = manual, 1.0, "manual"
            else:
                matched, score = best_match(stem, nominee_names)
                via = f"auto {score:.0%}"

            if not matched:
                self.stdout.write(self.style.WARNING(
                    f"  [no match] {img_path.name}  (best {score:.0%})"
                ))
                no_match += 1
                continue

            for nominee in [n for n in all_nominees if n.name == matched]:
                current = str(nominee.image) if nominee.image else ""
                if current and not overwrite:
                    self.stdout.write(f"  [skip] {nominee.name}  (already has image)")
                    skipped += 1
                    continue

                self.stdout.write(f"  [{via}] {img_path.name} → {nominee.name}")

                if dry_run:
                    self.stdout.write(self.style.SUCCESS(f"      would upload to {folder}/"))
                    uploaded += 1
                    continue

                try:
                    safe      = nominee.name.lower().replace(" ", "_")[:40]
                    public_id = f"nhea_nominee_{nominee.pk}_{safe}"
                    pid       = upload_file_to_cloudinary(str(img_path), public_id, folder)
                    nominee.image = pid
                    nominee.save(update_fields=["image"])
                    self.stdout.write(self.style.SUCCESS(f"      ✓ {pid}"))
                    uploaded += 1
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"      ✗ failed: {exc}"))
                    errors += 1

        self._summary(uploaded, skipped, no_match, errors, dry_run)

    # ── List ──────────────────────────────────────────────────────────

    def _list_nominees(self):
        from voting.models import Nominee, Category
        self.stdout.write("\nNominee Image Status\n" + "─" * 60)
        for cat in Category.objects.order_by("importance"):
            self.stdout.write(f"\n{cat.name}")
            for nom in Nominee.objects.filter(category=cat):
                has  = bool(nom.image and str(nom.image))
                self.stdout.write(
                    f"  {'✓' if has else '✗'}  {nom.name:<45}  "
                    f"{str(nom.image) if has else '(no image)'}"
                )
        total    = Nominee.objects.count()
        with_img = sum(1 for n in Nominee.objects.all() if n.image and str(n.image))
        self.stdout.write(f"\n{'─'*60}\n  {with_img}/{total} nominees have images\n")

    # ── Summary ───────────────────────────────────────────────────────

    def _summary(self, uploaded, skipped, no_match, errors, dry_run):
        label = " (dry run)" if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{'─'*50}\n"
            f"  Uploaded{label}  : {uploaded}\n"
            f"  Skipped        : {skipped}\n"
            f"  No match       : {no_match}\n"
            f"  Errors         : {errors}\n"
            f"{'─'*50}\n"
        ))