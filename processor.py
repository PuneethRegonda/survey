# processor.py (drop-in replacement)

import re
from helpers_generic import (
    norm, visible_questions, click_radio, click_checkbox,
    select_dropdown, fill_all_text_inputs, fill_first_text, debug_dump
)
from mappings import QUESTION_MAP

def get(row, col):
    if col in row:
        return str(row[col])
    for k in row.index:
        if norm(k) == norm(col):
            return str(row[k])
    return ""

async def _force_check_first_radio(page, sec_id):
    """
    Last-resort fallback for radios whose accessible names/labels are blank.
    """
    radios = page.locator(f'#{sec_id} input[type="radio"]')
    if await radios.count() > 0:
        await radios.first.check(force=True)
        return True
    return False

async def _force_check_yes_no(page, sec_id, want_yes=True):
    """
    Last-resort fallback for Y/N radios with blank labels:
    assumes the first radio is "Yes" and last is "No" (typical Qualtrics order).
    """
    radios = page.locator(f'#{sec_id} input[type="radio"]')
    n = await radios.count()
    if n == 0:
        return False
    target = radios.first if want_yes else radios.nth(n - 1)
    await target.check(force=True)
    return True

async def _debug_checked_state(page, sec_id):
    # small helper to print which radio(s) are checked
    radios = page.locator(f'#{sec_id} input[type="radio"]')
    n = await radios.count()
    states = []
    for i in range(n):
        r = radios.nth(i)
        checked = await r.is_checked()
        states.append(f"{i}:{'✓' if checked else '·'}")
    print(f"    -> state {sec_id}: {' '.join(states) if states else '(no radios)'}")

async def process_page(page, row):
    handled_any = False
    qs = await visible_questions(page)

    for q in qs:
        heading = q["heading"]
        sec_id  = q["sec_id"]

        matched = None
        for m in QUESTION_MAP:
            if re.search(m["pattern"], heading, flags=re.I):
                matched = m
                break
        if not matched:
            continue

        typ = matched["type"]

        if typ == "radio":
            raw = get(row, matched.get("csv","")).strip()

            # Special handling for GoPass Use Acknowledgement
            want = raw
            if re.search(r"GoPass Use Acknowledgement", heading, re.I):
                if want.lower() in ("y","yes","true","1","i certify","agree"):
                    want = "I certify"  # partial match text
                else:
                    want = None  # if CSV is blank, still try “first radio” fallback

            print(f"[radio] {heading[:60]} => '{want or '(fallback first radio)'}'")
            ok = await click_radio(page, sec_id, want)
            if not ok:
                # Final fallback: directly check first radio
                ok = await _force_check_first_radio(page, sec_id)
            print("    -> clicked? ", ok)
            await _debug_checked_state(page, sec_id)
            handled_any = handled_any or ok

        elif typ == "radio-yn":
            raw = get(row, matched["csv"]).strip().lower()
            choice = "Yes" if raw in ("yes","y","true","1") else "No"
            want_yes = (choice == "Yes")
            print(f"[radio-yn] {heading[:60]} => '{choice}'")
            ok = await click_radio(page, sec_id, choice)
            if not ok:
                # Final fallback: choose first/last radio
                ok = await _force_check_yes_no(page, sec_id, want_yes=want_yes)
            print("    -> clicked? ", ok)
            await _debug_checked_state(page, sec_id)
            handled_any = handled_any or ok

        elif typ == "checkbox-multi":
            raw = get(row, matched["csv"]).strip()
            if not raw:
                continue
            parts = [p.strip() for p in re.split(r"[|;]", raw) if p.strip()]
            print(f"[checkbox*] {heading[:60]} => {parts}")
            any_ok = False
            for p in parts:
                ok = await click_checkbox(page, sec_id, p)
                any_ok = any_ok or ok
            handled_any = handled_any or any_ok

        elif typ == "dropdown":
            val = get(row, matched["csv"]).strip()
            if not val:
                continue
            print(f"[dropdown] {heading[:60]} => '{val}'")
            await select_dropdown(page, sec_id, val)
            handled_any = True

        elif typ == "text":
            val = get(row, matched["csv"]).strip()
            if not val:
                continue
            print(f"[text] {heading[:60]} => '{val}'")
            await fill_first_text(page, sec_id, val)
            handled_any = True

        elif typ == "name3":
            cols = matched["csv_cols"]
            vals = [ get(row, c).strip() for c in cols ]
            if any(vals):
                print(f"[name3] {heading[:60]} => {vals}")
                await fill_all_text_inputs(page, sec_id, vals)
                handled_any = True

        elif typ == "comms":
            raw = get(row, matched["csv"]).lower()
            any_ok = False
            if "survey" in raw:
                any_ok = await click_checkbox(page, sec_id, "participate in future Caltrain surveys") or any_ok
            if "update" in raw or "information" in raw or "info" in raw:
                any_ok = await click_checkbox(page, sec_id, "receive Caltrain updates and information") or any_ok
            handled_any = handled_any or any_ok

    return handled_any
