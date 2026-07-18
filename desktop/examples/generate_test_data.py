"""
examples/generate_test_data.py
==============================

Generate large, realistic test datasets for Rask.

Useful for:
  • Stress-testing the UI with thousands of activities
  • Generating sample data for screenshots / demos
  • Populating a development database for manual testing
  • Creating synthetic datasets for analytics experiments

Usage:
    python examples/generate_test_data.py --activities 5000 --days 365
    python examples/generate_test_data.py --output sample.json
    python examples/generate_test_data.py --seed-db --activities 10000

The generator produces realistic distributions:
  • More activities during work hours (9-17) and evening (19-22)
  • Weekdays have ~30% more activities than weekends
  • Durations weighted toward 15-90 minute range (Pomodoro-style)
  • Titles drawn from a realistic pool per category
  • Tags consistent with title
  • ~10% of activities have notes
  • ~5% are stopwatch-kind (longer durations)
  • Jalali dates correlated with Gregorian
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESKTOP = HERE.parent
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))


# =============================================================================
# === Realistic data pools                                                     ===
# =============================================================================

CATEGORY_TITLES: dict[str, list[str]] = {
    "FOCUS": [
        "Deep work session", "Coding sprint", "Writing blog post",
        "Reading research paper", "Design review", "Architecture planning",
        "Bug investigation", "Code review", "Documentation writing",
        "Prototype building", "Algorithm practice", "Pair programming",
    ],
    "LEARN": [
        "Online course", "Tutorial video", "Book reading",
        "Documentation reading", "Workshop", "Conference talk",
        "Language practice", "Skill building", "Lecture notes",
        "Research reading", "MOOC assignment", "Coding challenge",
    ],
    "WORK": [
        "Team meeting", "Client call", "Email triage",
        "Project planning", "Sprint review", "Stand-up meeting",
        "Performance review", "1:1 with manager", "Cross-team sync",
        "Quarterly OKR planning", "Incident response", "On-call rotation",
    ],
    "HEALTH": [
        "Morning run", "Gym workout", "Yoga session",
        "Evening walk", "Cycling", "Swimming",
        "Meditation", "Stretching routine", "Hiking",
        "Home workout", "Pilates", "Basketball game",
    ],
    "CREATIVE": [
        "Sketching", "Photography", "Music practice",
        "Songwriting", "Creative writing", "Painting",
        "Video editing", "Pottery", "Knitting",
        "Calligraphy", "Digital art", " Poetry writing",
    ],
    "SOCIAL": [
        "Coffee with friend", "Family dinner", "Phone call with mom",
        "Birthday celebration", "Networking event", "Dinner party",
        "Movie night", "Game night", "Weekend trip",
        "Brunch with friends", "Wedding rehearsal", "Reunion planning",
    ],
    "REST": [
        "Power nap", "Evening unwind", "Mindful breathing",
        "Quiet reading", "Bath time", "Sleep meditation",
        "Garden time", "Stargazing", "Spa session",
        "Listening to music", "Doing nothing", "Cup of tea",
    ],
}

CATEGORY_TAGS: dict[str, list[str]] = {
    "FOCUS": ["deep-work", "flow-state", "priority", "important", "deadline"],
    "LEARN": ["growth", "skill", "course", "study", "practice"],
    "WORK": ["team", "client", "deadline", "priority", "meeting"],
    "HEALTH": ["cardio", "strength", "flexibility", "wellness", "morning"],
    "CREATIVE": ["art", "expression", "play", "joy", "flow"],
    "SOCIAL": ["family", "friends", "community", "quality-time", "love"],
    "REST": ["recovery", "calm", "quiet", "self-care", "recharge"],
}

NOTES_POOL: list[str] = [
    "Great session, really focused today.",
    "Felt distracted at first but recovered.",
    "Need to prepare better next time.",
    "Surprised by how fast time went.",
    "Hit a flow state around the 20-min mark.",
    "Took a quick break in the middle.",
    "Better than expected.",
    "Need more sleep before this kind of work.",
    "Will revisit this topic tomorrow.",
    "Made good progress on the project.",
    "Bit tired but pushed through.",
    "Going to celebrate this one.",
]


# =============================================================================
# === Generator                                                                ===
# =============================================================================

class TestDataGenerator:
    """Generate realistic test data for Rask."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.categories: list[dict] = []
        self.activities: list[dict] = []

    def load_categories(self) -> None:
        """Load categories from the DB (or seed defaults)."""
        from rask import database
        self.categories = database.category_list()
        if not self.categories:
            database._seed_defaults(database.get_conn())
            self.categories = database.category_list()

    def generate_activity(self, date_iso: str) -> dict:
        """Generate one realistic activity for the given date."""
        # Pick a category weighted by typical distribution
        weights = [25, 18, 22, 12, 8, 10, 5]  # FOCUS, LEARN, WORK, HEALTH, CREATIVE, SOCIAL, REST
        cat_idx = self.rng.choices(range(len(self.categories)), weights=weights, k=1)[0]
        cat = self.categories[cat_idx]
        cat_key = cat["key"]

        # Pick a title from the category pool
        titles = CATEGORY_TITLES.get(cat_key, ["Activity"])
        title = self.rng.choice(titles)

        # Pick a time of day weighted by typical patterns
        # Work hours: 9-17 (high), Evening: 19-22 (med), Morning: 6-9 (med), Night: 22-24 (low)
        hour_weights = []
        for h in range(24):
            if 9 <= h <= 17:
                hour_weights.append(10)
            elif 19 <= h <= 22:
                hour_weights.append(6)
            elif 6 <= h <= 9:
                hour_weights.append(4)
            elif 22 <= h <= 24:
                hour_weights.append(2)
            else:
                hour_weights.append(1)
        hour = self.rng.choices(range(24), weights=hour_weights, k=1)[0]
        minute = self.rng.choice([0, 15, 30, 45])

        # Duration weighted toward 15-90 min
        duration = self.rng.choices(
            [15, 25, 30, 45, 60, 90, 120, 180, 240],
            weights=[15, 20, 25, 15, 12, 8, 3, 1, 1],
            k=1,
        )[0]

        # 5% are stopwatch (longer)
        kind = "stopwatch" if self.rng.random() < 0.05 else "manual"
        if kind == "stopwatch":
            duration = duration + self.rng.randint(10, 60)

        # Compute end time
        start_dt = datetime.fromisoformat(f"{date_iso}T{hour:02d}:{minute:02d}:00+00:00")
        end_dt = start_dt + timedelta(minutes=duration)

        # Tags
        tags_pool = CATEGORY_TAGS.get(cat_key, [])
        n_tags = self.rng.choice([0, 1, 1, 2, 2, 3])
        tags = self.rng.sample(tags_pool, min(n_tags, len(tags_pool)))

        # Notes (10% chance)
        notes = self.rng.choice(NOTES_POOL) if self.rng.random() < 0.10 else None

        # Jalali date
        try:
            from rask.core import jalali
            jy, jm, jd = jalali.gregorian_to_jalali(
                start_dt.year, start_dt.month, start_dt.day,
            )
            jalali_iso = f"{jy:04d}-{jm:02d}-{jd:02d}"
        except Exception:
            jalali_iso = None

        return {
            "title": title,
            "category_id": cat["id"],
            "duration_min": duration,
            "date_iso": date_iso,
            "jalali_iso": jalali_iso,
            "start_ts": start_dt.isoformat(),
            "end_ts": end_dt.isoformat(),
            "notes": notes,
            "tags": tags,
            "kind": kind,
            "source": "generator",
        }

    def generate_day(self, date_iso: str, density: float = 1.0) -> list[dict]:
        """Generate all activities for one day.

        `density` scales the number of activities (1.0 = typical, 0.5 = quiet day).
        """
        # Determine day of week (0=Mon..6=Sun)
        dt = datetime.fromisoformat(f"{date_iso}T12:00:00+00:00")
        weekday = dt.weekday()
        # Weekdays (0-4) get more activities than weekends (5-6)
        is_weekend = weekday >= 5
        base_count = 4 if not is_weekend else 2
        # Add randomness
        count = max(0, int((base_count + self.rng.randint(-1, 3)) * density))
        return [self.generate_activity(date_iso) for _ in range(count)]

    def generate_range(self, days: int = 30,
                        end_date_iso: str | None = None,
                        density: float = 1.0) -> list[dict]:
        """Generate activities for `days` days ending on `end_date_iso`."""
        end = end_date_iso or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        end_dt = datetime.fromisoformat(f"{end}T12:00:00+00:00")
        for d in range(days):
            day_dt = end_dt - timedelta(days=d)
            date_iso = day_dt.strftime("%Y-%m-%d")
            self.activities.extend(self.generate_day(date_iso, density=density))
        return self.activities

    def to_json(self) -> dict:
        """Return all generated activities as a JSON-serializable dict."""
        return {
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "count": len(self.activities),
                "categories": [{"id": c["id"], "key": c["key"],
                                "name_fa": c["name_fa"], "name_en": c["name_en"],
                                "color": c["color"]}
                                for c in self.categories],
            },
            "activities": self.activities,
        }

    def seed_database(self) -> int:
        """Insert all generated activities into the database."""
        from rask import database
        count = 0
        for a in self.activities:
            try:
                database.activity_add(
                    title=a["title"],
                    category_id=a["category_id"],
                    duration_min=a["duration_min"],
                    date_iso=a["date_iso"],
                    jalali_iso=a.get("jalali_iso"),
                    start_ts=a.get("start_ts"),
                    end_ts=a.get("end_ts"),
                    notes=a.get("notes"),
                    tags=a.get("tags"),
                    kind=a.get("kind", "manual"),
                    source="generator",
                )
                count += 1
            except Exception as e:
                print(f"  Failed to insert: {e}", file=sys.stderr)
        return count


# =============================================================================
# === CLI                                                                     ===
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate test data for Rask")
    parser.add_argument("--activities", type=int, default=1000,
                        help="Target number of activities (approx)")
    parser.add_argument("--days", type=int, default=90,
                        help="Number of days to spread activities across")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("--density", type=float, default=1.0,
                        help="Activity density multiplier (default: 1.0)")
    parser.add_argument("--end-date", type=str, default=None,
                        help="End date ISO (default: today)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON file (default: stdout)")
    parser.add_argument("--seed-db", action="store_true",
                        help="Insert generated data into the database")
    parser.add_argument("--clear-first", action="store_true",
                        help="Clear all activities before seeding")
    args = parser.parse_args()

    print(f"Generating test data: seed={args.seed}, days={args.days}, "
          f"density={args.density}", file=sys.stderr)

    gen = TestDataGenerator(seed=args.seed)
    print("Loading categories...", file=sys.stderr)
    gen.load_categories()
    print(f"  Loaded {len(gen.categories)} categories", file=sys.stderr)

    print(f"Generating ~{args.activities} activities over {args.days} days...",
          file=sys.stderr)
    # Calculate density to hit target
    avg_per_day = args.activities / args.days
    density = avg_per_day / 4.0 * args.density  # 4 is the weekday base count
    gen.generate_range(days=args.days, end_date_iso=args.end_date, density=density)

    print(f"  Generated {len(gen.activities)} activities", file=sys.stderr)

    # Summary
    by_kind: dict[str, int] = {}
    by_category: dict[int, int] = {}
    total_min = 0
    for a in gen.activities:
        by_kind[a["kind"]] = by_kind.get(a["kind"], 0) + 1
        by_category[a["category_id"]] = by_category.get(a["category_id"], 0) + 1
        total_min += a["duration_min"]
    print(f"  By kind: {by_kind}", file=sys.stderr)
    print(f"  By category id: {by_category}", file=sys.stderr)
    print(f"  Total minutes: {total_min} ({total_min / 60:.1f} hours)", file=sys.stderr)

    # Output
    if args.output:
        data = gen.to_json()
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  Wrote {args.output}", file=sys.stderr)
    else:
        # Print summary to stdout
        print(f"\nGenerated {len(gen.activities)} activities.")
        print(f"Total time: {total_min} minutes ({total_min / 60:.1f} hours)")
        print(f"By kind: {by_kind}")
        print(f"By category id: {by_category}")

    # Seed DB
    if args.seed_db:
        from rask import database
        database.open_db()
        if args.clear_first:
            print("Clearing existing activities...", file=sys.stderr)
            database.get_conn().execute("DELETE FROM activities")
            database.get_conn().commit()
        print("Inserting into database...", file=sys.stderr)
        inserted = gen.seed_database()
        print(f"  Inserted {inserted} activities", file=sys.stderr)
        print(f"  Database now has {database.activity_count()} activities",
              file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
