import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path("research/experiments/results")
CSV_PATH = ROOT / "evaluation_records_final.csv"
MUTATION_CSV = ROOT / "mutation_detection_final.csv"
OUTPUT = ROOT / "final_results.json"


def metrics(rows):
    tp = sum(r["classification"] == "true_positive" for r in rows)
    tn = sum(r["classification"] == "true_negative" for r in rows)
    fp = sum(r["classification"] == "false_positive" for r in rows)
    fn = sum(r["classification"] == "false_negative" for r in rows)

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0
    )
    accuracy = (tp + tn) / (tp + tn + fp + fn) if tp + tn + fp + fn else 0

    return {
        "records": tp + tn + fp + fn,
        "true_positive": tp,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
    }


with CSV_PATH.open(encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))

# -------------------------
# Dataset integrity
# -------------------------

families = Counter(r["experiment_family"] for r in rows)
systems = Counter(r["system"] for r in rows)

transport_errors = sum(bool(r["transport_error"]) for r in rows)
unclassified = sum(r["classification"] == "unclassified" for r in rows)

dataset = {
    "total_records": len(rows),
    "columns": len(rows[0]) if rows else 0,
    "families": dict(families),
    "systems": dict(systems),
    "transport_errors": transport_errors,
    "unclassified": unclassified,
}

# -------------------------
# Heldout results
# -------------------------

heldout = {}

for system in sorted(
    {r["system"] for r in rows if r["experiment_family"] == "heldout_final"}
):
    subset = [
        r for r in rows
        if r["experiment_family"] == "heldout_final"
        and r["system"] == system
    ]
    heldout[system] = metrics(subset)

# -------------------------
# Mutation results
# -------------------------

with MUTATION_CSV.open(encoding="utf-8", newline="") as f:
    mutation_rows = list(csv.DictReader(f))

mutations = []

for r in mutation_rows:
    mutations.append({
        "mutation_id": r["mutant_id"],
        "description": r["description"],
        "detected": r["detected"] == "true",
        "f1_delta_vs_b2": (
            None
            if not r["f1_delta_vs_b2"]
            else float(r["f1_delta_vs_b2"])
        ),
        "caught_scenarios": (
            []
            if not r["scenario_ids_that_caught_it"]
            else r["scenario_ids_that_caught_it"].split(";")
        ),
    })

detected = sum(m["detected"] for m in mutations)

# -------------------------
# Stateful mutation details
# -------------------------

stateful = {}

for mid in ["M14", "M15", "M16", "M17", "M20"]:
    p = ROOT / "mutations_final" / mid / "b2_aegis_stateful.json"

    if not p.exists():
        continue

    with p.open(encoding="utf-8") as f:
        d = json.load(f)

    stateful[mid] = {
        "description": d.get("description"),
        "mutation_status": d.get("mutation_status"),
        "summary": d.get("summary", {}),
    }

# -------------------------
# Final artifact
# -------------------------

result = {
    "artifact_version": "1.0",
    "dataset": dataset,
    "heldout_results": heldout,
    "mutation_testing": {
        "total_mutants": len(mutations),
        "detected_mutants": detected,
        "survived_mutants": len(mutations) - detected,
        "mutation_detection_rate": (
            detected / len(mutations) if mutations else 0
        ),
        "mutants": mutations,
    },
    "stateful_mutations": stateful,
}

OUTPUT.write_text(
    json.dumps(result, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

print(f"Wrote: {OUTPUT}")
print(f"Total records: {len(rows):,}")
print(f"Heldout records: {families.get('heldout_final', 0):,}")
print(f"Mutation records: {families.get('mutations_final', 0):,}")
print(f"Mutants detected: {detected}/{len(mutations)}")
print(f"Transport errors: {transport_errors}")
print(f"Unclassified: {unclassified}")
print("PASS")
