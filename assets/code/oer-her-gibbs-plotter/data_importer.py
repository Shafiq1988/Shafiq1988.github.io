"""Friendly import of OER/HER tables from CSV, TXT, DAT, XLS, or XLSX files."""

from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import re
import shutil
import uuid

import pandas as pd


SUPPORTED = {".csv", ".txt", ".tsv", ".dat", ".xls", ".xlsx"}

ALIASES = {
    "state_index": {"stateindex", "index", "step", "reactioncoordinate", "coordinate"},
    "state": {"state", "intermediate", "label", "reactionstate", "species"},
    "dark": {"darkev", "dark", "darkenergy", "deltagdark", "freeenergydark"},
    "illuminated": {
        "illuminatedev", "illuminated", "light", "lightev", "lightenergy",
        "photo", "photoev", "photocorrected", "deltaglight",
    },
    "reaction": {"reaction", "reactiontype", "type"},
    "ph": {"ph"},
    "material": {"material", "system", "heterostructure", "sample"},
    "potential": {
        "carrierpotentialv", "carrierpotential", "potentialv",
        "uhv", "uev", "uh", "ue",
    },
}


def normalize_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def find_column(frame: pd.DataFrame, role: str) -> str | None:
    normalized = {normalize_name(column): str(column) for column in frame.columns}
    for alias in ALIASES[role]:
        if alias in normalized:
            return normalized[alias]
    return None


def read_candidates(path: Path) -> list[tuple[str, pd.DataFrame]]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported file type: {suffix}")
    if suffix in {".xlsx", ".xls"}:
        # Read raw rows first so tables with a title above their header are
        # detected automatically (common in scientific workbooks).
        sheets = pd.read_excel(path, sheet_name=None, header=None)
        return [(str(name), frame) for name, frame in sheets.items()]
    separator = "\t" if suffix in {".tsv", ".dat"} else None
    frame = pd.read_csv(path, sep=separator, engine="python")
    return [("table", frame)]


def promote_header(frame: pd.DataFrame) -> pd.DataFrame:
    """Find a compatible header within the first 15 rows when needed."""
    if compatible_mapping(frame):
        return frame
    dark_aliases = ALIASES["dark"]
    light_aliases = ALIASES["illuminated"]
    for row_index in range(min(15, len(frame))):
        normalized = {normalize_name(value) for value in frame.iloc[row_index].tolist()}
        if normalized.intersection(dark_aliases) and normalized.intersection(light_aliases):
            headers = []
            used = set()
            for column_index, value in enumerate(frame.iloc[row_index].tolist()):
                header = str(value).strip() if pd.notna(value) else f"column_{column_index}"
                while header in used:
                    header += "_2"
                used.add(header)
                headers.append(header)
            promoted = frame.iloc[row_index + 1:].copy()
            promoted.columns = headers
            return promoted.reset_index(drop=True)
    return frame


def compatible_mapping(frame: pd.DataFrame) -> dict[str, str | None] | None:
    mapping = {role: find_column(frame, role) for role in ALIASES}
    if mapping["dark"] and mapping["illuminated"]:
        return mapping
    return None


def scalar_value(frame: pd.DataFrame, column: str | None):
    if not column:
        return None
    values = frame[column].dropna().unique().tolist()
    return values[0] if values else None


def infer_reaction(frame: pd.DataFrame, mapping: dict, states: list[str]) -> str:
    declared = scalar_value(frame, mapping["reaction"])
    if declared is not None:
        declared = str(declared).strip().upper()
        if declared in {"OER", "HER"}:
            return declared
    if len(frame) == 5:
        return "OER"
    if len(frame) == 3:
        return "HER"
    combined = " ".join(states).upper()
    if "OOH" in combined or "O2" in combined:
        return "OER"
    if "H*" in combined or "H+" in combined:
        return "HER"
    raise ValueError(
        "Could not detect OER or HER. Use five OER rows or three HER rows, "
        "or add a Reaction column containing OER/HER."
    )


def import_dataset(path: str | Path) -> dict:
    """Read the first compatible table and return normalized rows plus metadata."""
    source = Path(path).resolve()
    errors = []
    for sheet, frame in read_candidates(source):
        frame = promote_header(frame.dropna(how="all").copy())
        mapping = compatible_mapping(frame)
        if not mapping:
            errors.append(f"{sheet}: missing dark/illuminated columns")
            continue
        dark = pd.to_numeric(frame[mapping["dark"]], errors="coerce")
        illuminated = pd.to_numeric(frame[mapping["illuminated"]], errors="coerce")
        valid = dark.notna() & illuminated.notna()
        work = frame.loc[valid].copy()
        dark = dark.loc[valid].astype(float).tolist()
        illuminated = illuminated.loc[valid].astype(float).tolist()
        if not dark:
            errors.append(f"{sheet}: no numeric rows")
            continue

        if mapping["state"]:
            states = work[mapping["state"]].astype(str).tolist()
        else:
            states = [f"State {index + 1}" for index in range(len(work))]
        if mapping["state_index"]:
            indices = pd.to_numeric(work[mapping["state_index"]], errors="coerce")
            if indices.isna().any():
                indices = list(range(len(work)))
            else:
                indices = indices.astype(int).tolist()
        else:
            indices = list(range(len(work)))

        rows = [
            {
                "State_index": int(indices[index]),
                "State": states[index],
                "Dark_eV": float(dark[index]),
                "Illuminated_eV": float(illuminated[index]),
            }
            for index in range(len(work))
        ]
        rows.sort(key=lambda row: row["State_index"])
        if not all(
            math.isfinite(row[key])
            for row in rows
            for key in ("Dark_eV", "Illuminated_eV")
        ):
            raise ValueError("The selected table contains non-finite energies.")

        reaction = infer_reaction(work, mapping, states)
        expected = 5 if reaction == "OER" else 3
        if len(rows) != expected:
            raise ValueError(f"{reaction} requires {expected} rows; found {len(rows)}.")

        material = scalar_value(work, mapping["material"])
        ph = scalar_value(work, mapping["ph"])
        potential = scalar_value(work, mapping["potential"])
        meta = {
            "reaction": reaction,
            "material": str(material) if material is not None else source.stem.replace("_", " "),
            "custom_title": None,
            "pH": float(ph) if ph is not None and pd.notna(ph) else None,
            "carrier_potential_V": (
                float(potential) if potential is not None and pd.notna(potential) else None
            ),
            "source_sheet": sheet,
        }
        if reaction == "OER":
            steps = [
                rows[index + 1]["Illuminated_eV"] - rows[index]["Illuminated_eV"]
                for index in range(4)
            ]
            meta["limiting_step"] = max(range(4), key=steps.__getitem__) + 1
            meta["residual_uphill_eV"] = max(steps)
        else:
            meta["limiting_step"] = "Volmer adsorption"
            meta["delta_G_H_star_light_eV"] = rows[1]["Illuminated_eV"]

        return {
            "id": f"imported_{uuid.uuid4().hex[:10]}",
            "name": source.stem,
            "meta": meta,
            "rows": rows,
            "built_in": False,
            "original_source": str(source),
        }
    raise ValueError(
        "No compatible table was found. Required energy columns are Dark_eV "
        "and Illuminated_eV. Details: " + "; ".join(errors)
    )


def persist_dataset(dataset: dict, import_dir: Path) -> dict:
    """Copy the original file and save a normalized JSON record without overwriting."""
    import_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source = Path(dataset["original_source"])
    prefix = f"{stamp}_{dataset['id']}"
    copied = import_dir / f"{prefix}_{source.name}"
    counter = 2
    while copied.exists():
        copied = import_dir / f"{prefix}_{counter}_{source.name}"
        counter += 1
    shutil.copy2(source, copied)
    saved = json.loads(json.dumps(dataset))
    saved["source_copy"] = str(copied)
    record = import_dir / f"{dataset['id']}.dataset.json"
    record.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    return saved


def load_persisted(import_dir: Path) -> list[dict]:
    datasets = []
    if not import_dir.exists():
        return datasets
    for path in sorted(import_dir.glob("*.dataset.json")):
        try:
            datasets.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return datasets
