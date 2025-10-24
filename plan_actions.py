import json, csv, re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# ---------- helpers ----------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()

def _to_css(entry: Dict[str, Any]) -> str:
    """Return a CSS selector string from a mapping entry supporting 'id' or 'css'."""
    if "id" in entry and entry["id"]:
        return f"#{entry['id']}"
    if "css" in entry and entry["css"]:
        css = entry["css"]
        return css if css.startswith(("css=","#",".")) else f"css={css}"
    raise ValueError("Mapping entry needs 'id' or 'css'")

def _resolve_radio_target(group: str, value_map: Dict[str, str], csv_value: str
                          ) -> Optional[Tuple[str, str]]:
    """
    Return (selector_to_click, matched_label) for a radio value, or None if not resolvable.
    value_map maps CSV labels -> index (e.g., 'Yes' -> '1'), we synthesize id:
       #mc-choice-input-{group}-{idx}
    """
    if not csv_value:
        return None
    want_idx = value_map.get(csv_value)
    if want_idx is None:
        # try case-insensitive match on keys
        for k, v in value_map.items():
            if _norm(k).lower() == _norm(csv_value).lower():
                want_idx = v
                csv_value = k  # normalize to canonical label
                break
    if not want_idx:
        return None
    selector = f"#mc-choice-input-{group}-{str(want_idx)}"
    return selector, csv_value

def _resolve_checkbox_targets(group: str, value_map: Optional[Dict[str, str]], csv_cell: str,
                              delimiter: str = ";") -> Tuple[List[Tuple[str, str]], List[str]]:
    """
    Return (to_check, unmatched), where:
      - to_check is a list of (selector, matched_label)
      - unmatched is a list of raw tokens from the CSV we couldn't resolve
    """
    if not csv_cell:
        return [], []
    tokens = [_norm(p) for p in str(csv_cell).split(delimiter) if _norm(p)]
    to_check: List[Tuple[str, str]] = []
    unmatched: List[str] = []
    if not tokens:
        return [], []
    if value_map:
        for tok in tokens:
            idx = value_map.get(tok)
            if idx is None:
                for k, v in value_map.items():
                    if _norm(k).lower() == tok.lower():
                        idx = v
                        tok = k  # normalized label
                        break
            if idx:
                to_check.append((f"#mc-choice-input-{group}-{str(idx)}", tok))
            else:
                unmatched.append(tok)
    else:
        # If no map, we can't generate ids; return unmatched for visibility
        unmatched = tokens
    return to_check, unmatched

# ---------- core planner ----------
def build_action_plan(mapping: Dict[str, Any], csv_row: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Build a list of planned actions based solely on mapping.json + the given CSV row.
    Does NOT touch the browser/DOM. It just resolves targets.
    Returns a list of dicts like:
      {"action":"TYPE", "selector":"#form-text-input-QID9-1", "value":"Shannon", "csv":"First Name"}
      {"action":"CLICK", "selector":"#mc-choice-input-QID71-1", "group":"QID71", "label":"Yes", "csv":"..."}
      {"action":"CHECK", "selector":"#mc-choice-input-QIDxx-3", "group":"QIDxx", "label":"Option A", "csv":"..."}
      {"action":"COMBOBOX", "selector":"#StateMenu", "visible_text":"California", "csv":"State"}
    """
    actions: List[Dict[str, Any]] = []
    used_headers = set()

    # Start URL (optional)
    if "start_url" in mapping and mapping["start_url"]:
        actions.append({"action": "NAVIGATE", "url": mapping["start_url"]})

    # TEXT / TEXTAREA
    for entry in mapping.get("text", []):
        header = entry.get("csv", "")
        sel = _to_css(entry)
        val = csv_row.get(header, "")
        used_headers.add(header)
        if _norm(val):
            actions.append({
                "action": "TYPE",
                "selector": sel,
                "value": val,
                "csv": header
            })
        else:
            actions.append({
                "action": "SKIP",
                "reason": "empty CSV",
                "selector": sel,
                "csv": header
            })

    # RADIO
    for r in mapping.get("radio", []):
        group = r.get("group")
        header = r.get("csv", "")
        used_headers.add(header)
        cell = csv_row.get(header, "")
        if not group:
            actions.append({"action":"SKIP","reason":"radio missing group","csv":header})
            continue

        # default_if_nonempty path
        if r.get("default_if_nonempty") and _norm(cell):
            actions.append({
                "action": "CLICK",
                "selector": r["default_if_nonempty"],
                "group": group,
                "label": "(default_if_nonempty)",
                "csv": header,
                "csv_value": cell
            })
            continue

        # value_map path
        vm = r.get("value_map") or {}
        resolved = _resolve_radio_target(group, vm, cell)
        if resolved:
            selector, label = resolved
            actions.append({
                "action": "CLICK",
                "selector": selector,
                "group": group,
                "label": label,
                "csv": header,
                "csv_value": cell
            })
        else:
            actions.append({
                "action": "SKIP",
                "reason": "radio value not mapped or empty",
                "group": group,
                "csv": header,
                "csv_value": cell
            })

        # Optional "Other" free-text field
        if r.get("other_text_css") and cell and _norm(cell).lower().startswith("other"):
            # Extract free text after "Other:" if present
            free = re.sub(r'^\s*other.*?:\s*', '', cell, flags=re.I).strip()
            if free:
                actions.append({
                    "action": "TYPE",
                    "selector": r["other_text_css"],
                    "value": free,
                    "csv": f"{header} (other)"
                })

    # CHECKBOX (multi select)
    for c in mapping.get("checkbox", []):
        group = c.get("group")
        header = c.get("csv", "")
        used_headers.add(header)
        if not group:
            actions.append({"action":"SKIP","reason":"checkbox missing group","csv":header})
            continue
        cell = csv_row.get(header, "")
        to_check, unmatched = _resolve_checkbox_targets(
            group,
            c.get("value_map"),
            cell,
            c.get("multi_delimiter", ";")
        )
        for selector, label in to_check:
            actions.append({
                "action": "CHECK",
                "selector": selector,
                "group": group,
                "label": label,
                "csv": header
            })
        if unmatched:
            actions.append({
                "action": "SKIP",
                "reason": "checkbox entries not mapped",
                "group": group,
                "csv": header,
                "unmatched": unmatched
            })

    # COMBOBOX (visible text)
    for cb in mapping.get("combobox", []):
        header = cb.get("csv", "")
        used_headers.add(header)
        desired = csv_row.get(header, "")
        cid = cb.get("id")
        if cid and _norm(desired):
            actions.append({
                "action": "COMBOBOX",
                "selector": f"#{cid}",
                "visible_text": desired,
                "csv": header
            })
        else:
            actions.append({
                "action": "SKIP",
                "reason": "combobox empty or missing id",
                "csv": header
            })

    # Any CSV headers that went unused
    unused_headers = [h for h in csv_row.keys() if h not in used_headers]
    if unused_headers:
        actions.append({
            "action": "INFO",
            "note": "CSV columns not referenced in mapping.json",
            "columns": unused_headers
        })

    return actions

def print_action_plan(actions: List[Dict[str, Any]]) -> None:
    """Pretty-print the plan so you can eyeball what will happen."""
    print("\n=== ACTION PLAN ===")
    for i, a in enumerate(actions, 1):
        act = a.get("action")
        if act == "NAVIGATE":
            print(f"{i:02d}. NAVIGATE → {a['url']}")
        elif act == "TYPE":
            print(f"{i:02d}. TYPE    {a['selector']}  ←  {a.get('value','')!r}   (csv: {a.get('csv','')})")
        elif act == "CLICK":
            print(f"{i:02d}. CLICK   {a['selector']}  (group={a.get('group')}, label={a.get('label')!r}, csv={a.get('csv')})")
        elif act == "CHECK":
            print(f"{i:02d}. CHECK   {a['selector']}  (group={a.get('group')}, label={a.get('label')!r}, csv={a.get('csv')})")
        elif act == "COMBOBOX":
            print(f"{i:02d}. COMBOBOX {a['selector']}  ←  {a.get('visible_text','')!r}   (csv: {a.get('csv','')})")
        elif act == "SKIP":
            why = a.get("reason","")
            details = []
            if "group" in a:   details.append(f"group={a['group']}")
            if "csv" in a:     details.append(f"csv={a['csv']}")
            if "csv_value" in a and a["csv_value"] is not None:
                details.append(f"csv_value={a['csv_value']!r}")
            if "selector" in a: details.append(f"selector={a['selector']}")
            if "unmatched" in a: details.append(f"unmatched={a['unmatched']}")
            print(f"{i:02d}. SKIP    ({why})  " + ("; ".join(details)))
        elif act == "INFO":
            print(f"{i:02d}. INFO    {a.get('note','')}: {a.get('columns',[])}")
        else:
            print(f"{i:02d}. {act}  {a}")

# ---------- convenience: load from files & print ----------
def plan_from_files(mapping_path: str, csv_path: str, row_index: int = 0) -> None:
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    # read csv row
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
    if not rows:
        print("[plan] CSV has no data rows.")
        return
    if row_index < 0 or row_index >= len(rows):
        print(f"[plan] Row index {row_index} out of range (0..{len(rows)-1}). Using 0.")
        row_index = 0
    row = rows[row_index]
    actions = build_action_plan(mapping, row)
    print_action_plan(actions)
