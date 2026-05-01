"""
NHEA Voting System — Data Population Script
============================================
Place this file at:
    voting/management/commands/populate_nhea.py

Make sure the directory structure exists:
    voting/
    ├── management/
    │   ├── __init__.py
    │   └── commands/
    │       ├── __init__.py
    │       └── populate_nhea.py   ← this file

Run with:
    python manage.py populate_nhea
    python manage.py populate_nhea --clear           # wipe existing data first
    python manage.py populate_nhea --voters-only     # only add voters
    python manage.py populate_nhea --no-voters       # skip voters
    python manage.py populate_nhea --images-only     # only update nominee images
    python manage.py populate_nhea --no-images       # skip image population

──────────────────────────────────────────────────────────────────────────────
HOW TO ADD IMAGES
──────────────────────────────────────────────────────────────────────────────
1.  Upload your images to Cloudinary (via the Cloudinary dashboard or CLI).
2.  Copy the **public_id** of each uploaded image.
    e.g. if the full URL is
         https://res.cloudinary.com/dgzjegrcm/image/upload/v1234567890/nominees/akth.jpg
    then the public_id is:  nominees/akth
3.  Paste it into the NOMINEE_IMAGES dict below, keyed by nominee name.

    NOMINEE_IMAGES = {
        "Lagos University Teaching Hospital": "nominees/luth",
        "Dr. Amaka Okonkwo":                 "nominees/dr_okonkwo",
        ...
    }

4.  Re-run:  python manage.py populate_nhea --images-only
──────────────────────────────────────────────────────────────────────────────
"""

import os
import random
from django.core.management.base import BaseCommand


# ─── Image Map ────────────────────────────────────────────────────────────────
# Key   → nominee name (must match exactly what is in NOMINEES below)
# Value → Cloudinary public_id  (no file extension needed)
#
# Leave the value as an empty string "" or omit the key entirely to skip
# that nominee's image.

NOMINEE_IMAGES = {
    # ── Hospital of the Year ──────────────────────────────────────────────
    "Lagos University Teaching Hospital":       "",   # e.g. "nominees/luth"
    "National Hospital Abuja":                  "",
    "University of Nigeria Teaching Hospital":  "",
    "Aminu Kano Teaching Hospital":             "",

    # ── Doctor of the Year ────────────────────────────────────────────────
    "Dr. Amaka Okonkwo":                        "",
    "Dr. Emeka Nwachukwu":                      "",
    "Dr. Fatima Al-Amin":                       "",
    "Dr. Chidi Eze":                            "",

    # ── Nurse of the Year ─────────────────────────────────────────────────
    "Nurse Ngozi Adeyemi":                      "",
    "Nurse Halima Bello":                       "",
    "Nurse Chinwe Okafor":                      "",
    "Nurse Aisha Usman":                        "",

    # ── Healthcare Innovation Award ───────────────────────────────────────
    "TeleMed Nigeria Initiative":               "",
    "LifeBank Blood Logistics":                 "",
    "54gene Genomics Platform":                 "",
    "Helium Health EHR System":                 "",

    # ── Community Health Initiative of the Year ───────────────────────────
    "Rural Immunisation Drive — Kebbi":         "",
    "Lagos Free Eye Clinic Programme":          "",
    "Maternal & Child Health Outreach":         "",
    "Clean Water & Sanitation Campaign":        "",

    # ── Pharmacist of the Year ────────────────────────────────────────────
    "Pharm. Kelechi Nwosu":                     "",
    "Pharm. Rashida Yusuf":                     "",
    "Pharm. Tunde Adebayo":                     "",
    "Pharm. Grace Obi":                         "",

    # ── Medical Laboratory Scientist of the Year ──────────────────────────
    "MLS Obiora Nzeogwu":                       "",
    "MLS Suleiman Garba":                       "",
    "MLS Bisi Adeleke":                         "",
    "MLS Ifeoma Chukwu":                        "",

    # ── Health Facility of the Year (Primary Care) ────────────────────────
    "Surulere PHC, Lagos":                      "",
    "Kubwa General Hospital":                   "",
    "Bodija Health Centre":                     "",
    "Sabon Gari PHC, Kano":                     "",

    # ── Allied Health Professional of the Year ────────────────────────────
    "Physiotherapist Emeka Obi":                "",
    "Radiographer Zara Mohammed":               "",
    "Dietitian Adaeze Nnadi":                   "",
    "Occupational Therapist Tolu Afolabi":      "",

    # ── Health Administrator of the Year ─────────────────────────────────
    "Dr. Olusegun Adeyinka":                    "",
    "Prof. Maimuna Ibrahim":                    "",
    "Dr. Uche Obi":                             "",
    "Dr. Yusuf Salisu":                         "",

    # ── Mental Health Champion of the Year ───────────────────────────────
    "She Writes Woman Foundation":              "",
    "Mentally Aware Nigeria Initiative":        "",
    "Dr. Maymunah Kadiri":                      "",
    "Asido Foundation":                         "",

    # ── Young Healthcare Professional of the Year ─────────────────────────
    "Dr. Adaeze Oreh":                          "",
    "Dr. Jide Idowu":                           "",
    "Nurse Miriam Danjuma":                     "",
    "Pharm. Tobi Adeleke":                      "",
}


# ─── Sample Data ──────────────────────────────────────────────────────────────

CATEGORIES = [
    {
        "name": "Hospital of the Year",
        "description": "Recognising the hospital that delivered the highest standard of patient care, innovation and community impact.",
        "importance": 1,
    },
    {
        "name": "Doctor of the Year",
        "description": "Awarded to a physician who demonstrated exceptional clinical excellence and compassionate patient care.",
        "importance": 2,
    },
    {
        "name": "Nurse of the Year",
        "description": "Celebrating a nurse whose dedication and skill transformed patient outcomes across the year.",
        "importance": 3,
    },
    {
        "name": "Healthcare Innovation Award",
        "description": "Honouring a team or individual that introduced a groundbreaking solution to a pressing healthcare challenge.",
        "importance": 4,
    },
    {
        "name": "Community Health Initiative of the Year",
        "description": "For the programme or campaign that most effectively improved health outcomes in underserved communities.",
        "importance": 5,
    },
    {
        "name": "Pharmacist of the Year",
        "description": "Recognising outstanding pharmaceutical care, patient education, and medication management.",
        "importance": 6,
    },
    {
        "name": "Medical Laboratory Scientist of the Year",
        "description": "Awarded to a laboratory professional whose accuracy and diligence supported life-saving diagnoses.",
        "importance": 7,
    },
    {
        "name": "Health Facility of the Year (Primary Care)",
        "description": "Celebrating a primary-care facility that excelled in accessibility, quality, and preventive health services.",
        "importance": 8,
    },
    {
        "name": "Allied Health Professional of the Year",
        "description": "For a physiotherapist, radiographer, dietitian, or other allied-health practitioner who went above and beyond.",
        "importance": 9,
    },
    {
        "name": "Health Administrator of the Year",
        "description": "Recognising exemplary leadership in managing and improving healthcare delivery systems.",
        "importance": 10,
    },
    {
        "name": "Mental Health Champion of the Year",
        "description": "Honouring the individual or organisation that most advanced mental health awareness and access to care.",
        "importance": 11,
    },
    {
        "name": "Young Healthcare Professional of the Year",
        "description": "Celebrating an emerging talent (under 35) who has already made a significant mark in their field.",
        "importance": 12,
    },
]

# Nominees per category — 4 nominees each
NOMINEES = {
    "Hospital of the Year": [
        {"name": "Lagos University Teaching Hospital", "organization": "LUTH, Lagos"},
        {"name": "National Hospital Abuja",            "organization": "NHA, FCT"},
        {"name": "University of Nigeria Teaching Hospital", "organization": "UNTH, Enugu"},
        {"name": "Aminu Kano Teaching Hospital",       "organization": "AKTH, Kano"},
    ],
    "Doctor of the Year": [
        {"name": "Dr. Amaka Okonkwo",  "organization": "LUTH, Lagos"},
        {"name": "Dr. Emeka Nwachukwu","organization": "UNTH, Enugu"},
        {"name": "Dr. Fatima Al-Amin", "organization": "AKTH, Kano"},
        {"name": "Dr. Chidi Eze",      "organization": "UCH, Ibadan"},
    ],
    "Nurse of the Year": [
        {"name": "Nurse Ngozi Adeyemi",  "organization": "LUTH, Lagos"},
        {"name": "Nurse Halima Bello",   "organization": "NHA, FCT"},
        {"name": "Nurse Chinwe Okafor",  "organization": "UNTH, Enugu"},
        {"name": "Nurse Aisha Usman",    "organization": "AKTH, Kano"},
    ],
    "Healthcare Innovation Award": [
        {"name": "TeleMed Nigeria Initiative",   "organization": "E-Health Africa"},
        {"name": "LifeBank Blood Logistics",     "organization": "LifeBank Ltd"},
        {"name": "54gene Genomics Platform",     "organization": "54gene Inc"},
        {"name": "Helium Health EHR System",     "organization": "Helium Health"},
    ],
    "Community Health Initiative of the Year": [
        {"name": "Rural Immunisation Drive — Kebbi",    "organization": "NPHCDA"},
        {"name": "Lagos Free Eye Clinic Programme",     "organization": "Sight Savers Nigeria"},
        {"name": "Maternal & Child Health Outreach",    "organization": "MSF Nigeria"},
        {"name": "Clean Water & Sanitation Campaign",   "organization": "WaterAid Nigeria"},
    ],
    "Pharmacist of the Year": [
        {"name": "Pharm. Kelechi Nwosu",  "organization": "LUTH, Lagos"},
        {"name": "Pharm. Rashida Yusuf",  "organization": "AKTH, Kano"},
        {"name": "Pharm. Tunde Adebayo",  "organization": "UCH, Ibadan"},
        {"name": "Pharm. Grace Obi",      "organization": "UNTH, Enugu"},
    ],
    "Medical Laboratory Scientist of the Year": [
        {"name": "MLS Obiora Nzeogwu",   "organization": "UNTH, Enugu"},
        {"name": "MLS Suleiman Garba",   "organization": "AKTH, Kano"},
        {"name": "MLS Bisi Adeleke",     "organization": "UCH, Ibadan"},
        {"name": "MLS Ifeoma Chukwu",    "organization": "LUTH, Lagos"},
    ],
    "Health Facility of the Year (Primary Care)": [
        {"name": "Surulere PHC, Lagos",    "organization": "Lagos State MOH"},
        {"name": "Kubwa General Hospital", "organization": "FCT-AHCPRS"},
        {"name": "Bodija Health Centre",   "organization": "Oyo State MOH"},
        {"name": "Sabon Gari PHC, Kano",   "organization": "Kano State MOH"},
    ],
    "Allied Health Professional of the Year": [
        {"name": "Physiotherapist Emeka Obi",    "organization": "LUTH, Lagos"},
        {"name": "Radiographer Zara Mohammed",   "organization": "NHA, FCT"},
        {"name": "Dietitian Adaeze Nnadi",       "organization": "UNTH, Enugu"},
        {"name": "Occupational Therapist Tolu Afolabi", "organization": "UCH, Ibadan"},
    ],
    "Health Administrator of the Year": [
        {"name": "Dr. Olusegun Adeyinka",   "organization": "Lagos State MOH"},
        {"name": "Prof. Maimuna Ibrahim",   "organization": "NHA, FCT"},
        {"name": "Dr. Uche Obi",            "organization": "Rivers State MOH"},
        {"name": "Dr. Yusuf Salisu",        "organization": "Kano State MOH"},
    ],
    "Mental Health Champion of the Year": [
        {"name": "She Writes Woman Foundation", "organization": "Lagos"},
        {"name": "Mentally Aware Nigeria Initiative", "organization": "Pan-Nigeria"},
        {"name": "Dr. Maymunah Kadiri",     "organization": "Pinnacle Medical Services"},
        {"name": "Asido Foundation",         "organization": "Abuja"},
    ],
    "Young Healthcare Professional of the Year": [
        {"name": "Dr. Adaeze Oreh",      "organization": "Federal MOH"},
        {"name": "Dr. Jide Idowu",       "organization": "LUTH, Lagos"},
        {"name": "Nurse Miriam Danjuma", "organization": "NHA, FCT"},
        {"name": "Pharm. Tobi Adeleke",  "organization": "UCH, Ibadan"},
    ],
}

# Sample voters from healthcare organisations
VOTERS = [
    {"full_name": "Dr. Samuel Okafor",       "organization": "LUTH, Lagos"},
    {"full_name": "Prof. Ngozi Ekwueme",     "organization": "UNTH, Enugu"},
    {"full_name": "Nurse Hauwa Musa",        "organization": "AKTH, Kano"},
    {"full_name": "Dr. Tunde Adesanya",      "organization": "UCH, Ibadan"},
    {"full_name": "Pharm. Blessing Okeke",   "organization": "NHA, FCT"},
    {"full_name": "Dr. Yemi Adewale",        "organization": "LUTH, Lagos"},
    {"full_name": "MLS Chukwuemeka Eze",     "organization": "UNTH, Enugu"},
    {"full_name": "Dr. Zainab Aliyu",        "organization": "AKTH, Kano"},
    {"full_name": "Nurse Funke Oladele",     "organization": "UCH, Ibadan"},
    {"full_name": "Dr. Patrick Nweze",       "organization": "UNTH, Enugu"},
    {"full_name": "Dr. Mariam Sule",         "organization": "NHA, FCT"},
    {"full_name": "Pharm. Eze Obiechina",    "organization": "LUTH, Lagos"},
    {"full_name": "Dr. Kemi Babalola",       "organization": "UCH, Ibadan"},
    {"full_name": "Nurse Abdullahi Garba",   "organization": "AKTH, Kano"},
    {"full_name": "Dr. Chioma Obi",          "organization": "LUTH, Lagos"},
    {"full_name": "Prof. Ibrahim Yusuf",     "organization": "AKTH, Kano"},
    {"full_name": "Dr. Adaeze Eze",          "organization": "UNTH, Enugu"},
    {"full_name": "Nurse Taiwo Akinwande",   "organization": "UCH, Ibadan"},
    {"full_name": "Dr. Musa Tanko",          "organization": "NHA, FCT"},
    {"full_name": "Pharm. Amaka Onyekachi",  "organization": "LUTH, Lagos"},
]

DEFAULT_PASSWORD = "nhea2026"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _apply_image(nominee, public_id, stdout, style):
    """
    Assign a Cloudinary public_id to nominee.image and save.

    CloudinaryField stores the public_id string directly — no upload needed
    here because the file already lives in your Cloudinary account.
    """
    if not public_id:
        return  # nothing to do

    try:
        nominee.image = public_id          # CloudinaryField accepts a public_id string
        nominee.save(update_fields=['image'])
        stdout.write(style.SUCCESS(f"      ✓ image set  →  {public_id}"))
    except Exception as exc:
        stdout.write(style.ERROR(f"      ✗ image failed for {nominee.name}: {exc}"))


# ─── Command ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Populate the NHEA database with categories, nominees, voters, and images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete ALL existing categories, nominees, votes, and voters before populating.",
        )
        parser.add_argument(
            "--voters-only",
            action="store_true",
            help="Only create voter accounts (skip categories, nominees, and images).",
        )
        parser.add_argument(
            "--no-voters",
            action="store_true",
            help="Skip creating voter accounts.",
        )
        parser.add_argument(
            "--images-only",
            action="store_true",
            help="Only update nominee images from NOMINEE_IMAGES (skip categories, nominees, voters).",
        )
        parser.add_argument(
            "--no-images",
            action="store_true",
            help="Skip image population entirely.",
        )

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        from voting.models import Category, Nominee, Voter, Vote, generate_voter_id

        clear        = options["clear"]
        voters_only  = options["voters_only"]
        no_voters    = options["no_voters"]
        images_only  = options["images_only"]
        no_images    = options["no_images"]

        # ── Optional wipe ────────────────────────────────────────────
        if clear:
            self.stdout.write(self.style.WARNING("Clearing existing data…"))
            Vote.objects.all().delete()
            Nominee.objects.all().delete()
            Category.objects.all().delete()
            Voter.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("  ✓ All data cleared."))

        # ── Images-only shortcut ─────────────────────────────────────
        if images_only:
            self._populate_images()
            return

        # ── Categories & Nominees ────────────────────────────────────
        if not voters_only:
            self.stdout.write("\nCreating categories…")
            for cat_data in CATEGORIES:
                cat, created = Category.objects.get_or_create(
                    name=cat_data["name"],
                    defaults={
                        "description": cat_data["description"],
                        "importance":  cat_data["importance"],
                    },
                )
                status = "created" if created else "already exists"
                self.stdout.write(f"  [{status}] {cat.name}")

                for nom_data in NOMINEES.get(cat_data["name"], []):
                    nom, nom_created = Nominee.objects.get_or_create(
                        category=cat,
                        name=nom_data["name"],
                        defaults={"organization": nom_data["organization"]},
                    )
                    nom_status = "created" if nom_created else "exists"
                    self.stdout.write(f"    [{nom_status}] {nom.name}")

                    # Apply image if provided and not suppressed
                    if not no_images:
                        public_id = NOMINEE_IMAGES.get(nom_data["name"], "")
                        _apply_image(nom, public_id, self.stdout, self.style)

            self.stdout.write(self.style.SUCCESS("\n✓ Categories and nominees done."))

        # ── Voters ───────────────────────────────────────────────────
        if not no_voters and not voters_only or voters_only:
            self.stdout.write("\nCreating voters…")
            created_voters = []

            for v_data in VOTERS:
                if Voter.objects.filter(full_name=v_data["full_name"]).exists():
                    self.stdout.write(f"  [exists] {v_data['full_name']}")
                    continue

                voter = Voter(
                    voter_id=generate_voter_id(),
                    full_name=v_data["full_name"],
                    organization=v_data["organization"],
                )
                voter.set_password(DEFAULT_PASSWORD)
                voter.save()
                created_voters.append(voter)
                self.stdout.write(f"  [created] {voter.full_name}  →  {voter.voter_id}")

            self.stdout.write(self.style.SUCCESS(f"\n✓ {len(created_voters)} voters created."))

        # ── Summary ──────────────────────────────────────────────────
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'─'*50}\n"
                f"  Categories : {Category.objects.count()}\n"
                f"  Nominees   : {Nominee.objects.count()}\n"
                f"  Voters     : {Voter.objects.count()}\n"
                f"{'─'*50}\n"
                f"  Default password for all new voters: {DEFAULT_PASSWORD}\n"
                f"  Voters can log in with their Voter ID (printed above)\n"
                f"  and change their password at /reset_password/\n"
            )
        )

    # ------------------------------------------------------------------

    def _populate_images(self):
        """Walk NOMINEE_IMAGES and apply each public_id to its matching Nominee row."""
        from voting.models import Nominee

        self.stdout.write("\nUpdating nominee images…")
        updated = skipped = missing = 0

        for name, public_id in NOMINEE_IMAGES.items():
            if not public_id:
                self.stdout.write(f"  [skip – no image] {name}")
                skipped += 1
                continue

            try:
                nom = Nominee.objects.get(name=name)
            except Nominee.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"  [not found] {name}"))
                missing += 1
                continue
            except Nominee.MultipleObjectsReturned:
                # If the same name exists in multiple categories, update all
                noms = Nominee.objects.filter(name=name)
                for nom in noms:
                    _apply_image(nom, public_id, self.stdout, self.style)
                updated += noms.count()
                continue

            _apply_image(nom, public_id, self.stdout, self.style)
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'─'*50}\n"
                f"  Images set   : {updated}\n"
                f"  Skipped      : {skipped}  (no public_id provided)\n"
                f"  Not found    : {missing}  (nominee name mismatch)\n"
                f"{'─'*50}\n"
            )
        )