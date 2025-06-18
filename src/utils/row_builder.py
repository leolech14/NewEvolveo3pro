from collections import defaultdict
from typing import List, Dict, Any


def cluster_words(words: List[Dict[str, Any]], y_tol: float = 2.0) -> List[List[Dict[str, Any]]]:
    """
    Group word dictionaries (pdfplumber or Textract/Azure‐normalised) into
    horizontal rows by Y-centroid proximity.

    Parameters
    ----------
    words : list of dict
        Must contain keys ``top`` (or ``y``) and ``x0``.
    y_tol : float
        Maximum vertical distance (in PDF points / pixels) to consider two
        words part of the same row.

    Returns
    -------
    List of rows where each row is a left-to-right sorted list of words.
    """
    if not words:
        return []

    # normalise key names
    for w in words:
        if "y" in w and "top" not in w:
            w["top"] = w["y"]

    buckets: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for w in words:
        key = int(round(w["top"] / y_tol))
        buckets[key].append(w)

    rows: List[List[Dict[str, Any]]] = []
    for _, group in sorted(buckets.items(), key=lambda kv: kv[0]):
        group_sorted = sorted(group, key=lambda o: o["x0"])
        rows.append(group_sorted)

    return rows


def rows_to_strings(rows: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Convert clustered rows into ``{"text": str, "bbox": tuple}`` dictionaries.
    """
    results: List[Dict[str, Any]] = []
    for row in rows:
        text = " ".join(w["text"] for w in row).strip()
        x0 = min(w["x0"] for w in row)
        x1 = max(w.get("x1", w["x0"] + w.get("width", 0)) for w in row)
        y0 = min(w["top"] for w in row)
        y1 = max(w.get("bottom", w["top"] + w.get("height", 0)) for w in row)
        bbox = (x0, y0, x1, y1)
        results.append({"text": text, "bbox": bbox})
    return results
