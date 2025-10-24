# main_auto_fill.py
import argparse
import asyncio
import csv
import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import async_playwright, Page, Locator, TimeoutError as PWTimeout

# -----------------------
# Utilities
# -----------------------

def norm_space(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()

def norm_case(s: Any) -> str:
    return norm_space(s).lower()

def parse_multi(cell: str, delim: Optional[str]) -> List[str]:
    if not cell:
        return []
    if delim:
        parts = [norm_space(p) for p in str(cell).split(delim)]
    else:
        parts = [norm_space(p) for p in re.split(r"[;,]", str(cell))]
    return [p for p in parts if p]

def css_from_entry(entry: Dict[str, Any]) -> str:
    if entry.get("id"):
        return f"#{entry['id']}"
    if entry.get("css"):
        css = entry["css"]
        return css[len("css="):] if css.startswith("css=") else css
    raise ValueError("Mapping entry missing 'id' or 'css'.")

def jitter(base_ms: int, spread: int = 30) -> int:
    lo = max(0, base_ms - spread)
    hi = base_ms + spread
    return random.randint(lo, hi)

# -----------------------
# Fast presence checks (no long waits)
# -----------------------

async def selector_visible(page: Page, selector: str) -> bool:
    loc = page.locator(selector)
    try:
        if await loc.count() == 0:
            return False
        return await loc.first.is_visible()
    except Exception:
        return False

async def radio_group_present(page: Page, group: str) -> bool:
    try:
        return (await page.locator(f"input[type='radio'][name='{group}']").count()) > 0
    except Exception:
        return False

async def checkbox_group_present(page: Page, group: str) -> bool:
    try:
        return (await page.locator(f"input[type='checkbox'][name='{group}']").count()) > 0
    except Exception:
        return False

async def combobox_present(page: Page, combo_id: str) -> bool:
    return await selector_visible(page, f"div[role='combobox']#{combo_id}")

# -----------------------
# Debug Scan
# -----------------------

async def debug_scan_page(page: Page) -> None:
    try:
        radio_groups = await page.evaluate("""
            () => {
              const out = [];
              const inputs = Array.from(document.querySelectorAll("input[type='radio'][id^='mc-choice-input-']"));
              const byGroup = new Map();
              for (const el of inputs) {
                const name = el.name;
                if (!name) continue;
                if (!byGroup.has(name)) byGroup.set(name, []);
                const labelId = el.getAttribute('aria-labelledby');
                let labelText = '';
                if (labelId) {
                  const lab = document.getElementById(labelId);
                  labelText = lab ? lab.textContent.trim() : '';
                }
                byGroup.get(name).push({
                  id: el.id || '',
                  value: el.getAttribute('value') || null,
                  aria: labelId || '',
                  label: labelText,
                  selected: el.checked === true
                });
              }
              return Array.from(byGroup.entries()).map(([group, options]) => ({group, options}));
            }
        """)
        for g in radio_groups:
            print(f"[debug] Group {g['group']} options:")
            for o in g["options"]:
                print(f"  id='{o['id']}' value={o['value']} aria='{o['aria']}' label='{o['label']}' selected={o['selected']}")
    except Exception as e:
        print(f"[warn] debug_scan_page error: {e}")

# -----------------------
# Typing / Clicking
# -----------------------

async def type_like_human(page: Page, locator: Locator, text: str, per_char_ms: int, debug: bool) -> bool:
    try:
        # Click + clear (no long wait)
        await locator.first.click()
        try:
            await locator.first.clear()
        except Exception:
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Delete")
        await page.wait_for_timeout(jitter(100, 40))
        for ch in str(text):
            await locator.first.type(ch, delay=jitter(per_char_ms, int(per_char_ms * 0.3)))
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(jitter(150, 50))
        # verify
        try:
            val = await locator.first.input_value()
            if norm_space(val) != norm_space(text):
                print(f"[retry] Typed mismatch. got='{val}' expected='{text}'. Using .fill()")
                await locator.first.fill(str(text))
        except Exception:
            pass
        # blur
        await page.mouse.click(10, 10)
        await page.wait_for_timeout(jitter(150, 50))
        return True
    except Exception as e:
        if debug:
            print(f"[warn] type_like_human failed: {e}")
        return False

async def click_selector(page: Page, selector: str, debug: bool = False) -> bool:
    try:
        loc = page.locator(selector)
        await loc.first.scroll_into_view_if_needed()
        await page.wait_for_timeout(jitter(80, 30))
        await loc.first.click()
        await page.wait_for_timeout(jitter(100, 30))
        if debug:
            print(f"[DEBUG] Clicked: {selector}")
        return True
    except Exception as e:
        if debug:
            print(f"[warn] click failed {selector}: {e}")
        return False

# -----------------------
# Resolvers
# -----------------------

def resolve_radio_selector(group: str, value_map: Dict[str, str], desired: str) -> Optional[str]:
    if not desired:
        return None
    if desired in value_map:
        return f"#mc-choice-input-{group}-{value_map[desired]}"
    want = norm_case(desired)
    for k, v in value_map.items():
        if norm_case(k) == want:
            return f"#mc-choice-input-{group}-{v}"
    return None

def resolve_checkboxes(group: str, value_map: Optional[Dict[str, str]], cell: str, multi_delim: Optional[str]) -> Tuple[List[str], List[str]]:
    items = parse_multi(cell, multi_delim)
    if not items:
        return [], []
    to_select, unmatched = [], []
    if value_map:
        for it in items:
            if it in value_map:
                to_select.append(f"#mc-choice-input-{group}-{value_map[it]}")
                continue
            hit = None
            for k, v in value_map.items():
                if norm_case(k) == norm_case(it):
                    hit = v; break
            if hit:
                to_select.append(f"#mc-choice-input-{group}-{hit}")
            else:
                unmatched.append(it)
    else:
        unmatched = items
    return to_select, unmatched

# -----------------------
# Combobox (Qualtrics)
# -----------------------

async def choose_combobox_by_text(page: Page, combo_id: str, visible_text: str, debug: bool) -> bool:
    try:
        combo = page.locator(f"div[role='combobox']#{combo_id}")
        await combo.first.click()
        menu = page.locator(f"ul#select-menu-{combo_id}")
        await menu.first.wait_for(state="visible", timeout=3000)
        candidates = menu.locator("li.menu-item")
        n = await candidates.count()
        want = norm_space(visible_text).lower()
        idx = -1
        for i in range(n):
            tx = norm_space(await candidates.nth(i).inner_text()).lower()
            if tx == want:
                idx = i; break
        if idx < 0:
            for i in range(n):
                tx = norm_space(await candidates.nth(i).inner_text()).lower()
                if want in tx:
                    idx = i; break
        if idx < 0:
            print(f"[warn] COMBO '{combo_id}' option not found for {visible_text!r}")
            await combo.press("Escape")
            return False
        await candidates.nth(idx).click()
        await page.wait_for_timeout(jitter(100, 30))
        if debug:
            print(f"[DEBUG] Combobox {combo_id} → '{visible_text}'")
        return True
    except Exception as e:
        print(f"[warn] Combobox {combo_id} failed: {e}")
        return False

# -----------------------
# Fill visible page only (returns number of actions performed)
# -----------------------

async def fill_current_page(page: Page, mapping: Dict[str, Any], row: Dict[str, str], human_delay: int, debug: bool) -> int:
    actions = 0

    # TEXT
    for entry in mapping.get("text", []):
        header = entry.get("csv", "")
        val = row.get(header, "")
        if not norm_space(val):
            if debug: print(f"[skip] empty CSV for text {header}")
            continue
        sel = css_from_entry(entry)
        if not await selector_visible(page, sel):
            if debug: print(f"[skip] control not on page: {sel} (csv: {header})")
            continue
        if debug: print(f"[TYPE] {sel} ← {val!r}  (csv: {header})")
        if await type_like_human(page, page.locator(sel), val, per_char_ms=human_delay, debug=debug):
            actions += 1

    # RADIO
    for r in mapping.get("radio", []):
        group = r.get("group"); header = r.get("csv","")
        if not group or not header:
            continue
        cell = norm_space(row.get(header, ""))
        if not cell:
            if debug: print(f"[skip] empty CSV for radio {group}/{header}")
            continue
        if not await radio_group_present(page, group):
            if debug: print(f"[skip] radio group not on page: {group}")
            continue

        # default-if-nonempty shortcut
        if r.get("default_if_nonempty"):
            sel = r["default_if_nonempty"]
            if debug: print(f"[CLICK] {sel} (default_if_nonempty) (group={group}, csv={header})")
            if await click_selector(page, sel, debug=debug): actions += 1
            continue

        # 1) Try to map the CSV value to a known option
        mapped_sel = resolve_radio_selector(group, r.get("value_map", {}), cell)
        if mapped_sel:
            if debug: print(f"[CLICK] {mapped_sel} (group={group}, csv={header}, csv_value={cell!r})")
            if await click_selector(page, mapped_sel, debug=debug): actions += 1
            # If the CSV literally starts with "Other: ..." also type its free text
            if r.get("other_text_css") and norm_case(cell).startswith("other"):
                free = re.sub(r'^\s*other.*?:\s*', '', cell, flags=re.I).strip()
                if free and await selector_visible(page, r["other_text_css"]):
                    if debug: print(f"[TYPE] (other) {r['other_text_css']} ← {free!r}")
                    if await type_like_human(page, page.locator(r["other_text_css"]), free, human_delay, debug): actions += 1
            continue

        # 2) Not mapped → if we have an Other textbox, auto-select Other and type the CSV as free text
        if r.get("other_text_css"):
            other_radio = r.get("other_choice_selector") or derive_other_radio_selector(group, r["other_text_css"])
            if other_radio:
                if debug: print(f"[CLICK] {other_radio} (auto-select Other; group={group}, csv={header})")
                await click_selector(page, other_radio, debug=debug)
                # small wait for DOM to enable the textbox
                await page.wait_for_timeout(120)

            # Start with mapping selector
            other_sel = r["other_text_css"]
            # If multiple <input> match, try to refine to the one under the 'Other' label
            # Example: label[for='mc-choice-input-QID63-4'] input[type='text']
            refined = None
            m = re.search(r"#mc-choice-input-(QID\d+)-(\d+)$", other_radio or "")
            if m:
                g, idx = m.group(1), m.group(2)
                candidate = f"label[for='mc-choice-input-{g}-{idx}'] input[type='text']"
                if await page.locator(candidate).count() > 0:
                    refined = candidate

            target_sel = refined or other_sel
            loc = page.locator(target_sel)
            # If still ambiguous, narrow to text type to avoid the radio
            if await loc.count() > 1:
                loc = page.locator(f"{target_sel}[type='text']")

            if await selector_visible(page, target_sel):
                if debug: print(f"[TYPE] (radio other auto) {target_sel} ← {cell!r}")
                ok = await type_like_human(page, loc, cell, human_delay, debug)
                if not ok:
                    # last resort: force fill on the first visible text input within the other option
                    cand = page.locator("label[for^='mc-choice-input-{}'] input[type='text']".format(group)).first
                    try:
                        await cand.fill(cell); actions += 1
                    except Exception:
                        if debug: print(f"[warn] failed to type into Other textbox for group={group}")
                else:
                    actions += 1
            else:
                if debug: print(f"[skip] Other textbox not visible for group={group}")

    # CHECKBOX
    for c in mapping.get("checkbox", []):
        group = c.get("group"); header = c.get("csv","")
        if not group or not header: continue
        cell = row.get(header, "")
        if not norm_space(cell):
            if debug: print(f"[skip] empty CSV for checkbox {group}/{header}")
            continue
        if not await checkbox_group_present(page, group):
            if debug: print(f"[skip] checkbox group not on page: {group}")
            continue

        to_check, unmatched = resolve_checkboxes(group, c.get("value_map"), cell, c.get("multi_delimiter"))
        for sel in to_check:
            if debug: print(f"[CHECK] {sel} (group={group}, csv={header})")
            if await click_selector(page, sel, debug=debug): actions += 1
        if unmatched:
            print(f"[skip] (checkbox entries not mapped) group={group}; csv={header}; unmatched={unmatched}")

        # checkbox 'other'
        if c.get("other_text_css") and any(norm_case(x).startswith("other") for x in parse_multi(cell, c.get("multi_delimiter"))):
            free_vals = []
            for tok in parse_multi(cell, c.get("multi_delimiter")):
                if norm_case(tok).startswith("other"):
                    v = re.sub(r'^\s*other.*?:\s*', '', tok, flags=re.I).strip()
                    if v: free_vals.append(v)
            if free_vals and await selector_visible(page, c["other_text_css"]):
                txt = "; ".join(free_vals)
                if debug: print(f"[TYPE] (checkbox other) {c['other_text_css']} ← {txt!r}")
                if await type_like_human(page, page.locator(c["other_text_css"]), txt, human_delay, debug): actions += 1

    # COMBOBOX
    for cb in mapping.get("combobox", []):
        header = cb.get("csv",""); cid = cb.get("id"); want = row.get(header, "")
        if not cid or not header or not norm_space(want): 
            if debug and header and not norm_space(want):
                print(f"[skip] empty CSV for combobox {cid}/{header}")
            continue
        if not await combobox_present(page, cid):
            if debug: print(f"[skip] combobox not on page: {cid}")
            continue
        if cb.get("choose_by_text", True):
            if debug: print(f"[COMBO] #{cid} ← {want!r} (by text)")
            if await choose_combobox_by_text(page, cid, want, debug): actions += 1

    return actions

# -----------------------
# Navigation
# -----------------------

async def click_next_and_wait(page: Page, debug: bool) -> None:
    try:
        prev_qids = await page.eval_on_selector_all("section.question[id^='question-QID']", "els => els.map(e=>e.id)")
        await click_selector(page, "#next-button", debug=debug)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(250)
        for _ in range(40):
            curr_qids = await page.eval_on_selector_all("section.question[id^='question-QID']", "els => els.map(e=>e.id)")
            if set(curr_qids) != set(prev_qids):
                break
            await page.wait_for_timeout(150)
        if debug: print("[debug] advanced to next page")
    except Exception as e:
        print(f"[warn] next-page wait issue: {e}")

# -----------------------
# Plan preview (optional)
# -----------------------

def print_action_plan(mapping: Dict[str, Any], row: Dict[str, str]) -> None:
    print("=== ACTION PLAN (preview) ===")
    i = 1
    if mapping.get("start_url"):
        print(f"{i:02d}. NAVIGATE → {mapping['start_url']}"); i += 1
    for entry in mapping.get("text", []):
        header = entry.get("csv",""); val = row.get(header,""); sel = css_from_entry(entry)
        print(f"{i:02d}. {'TYPE' if norm_space(val) else 'SKIP '}  {sel}  ←  {val!r}   (csv: {header})"); i += 1
    for r in mapping.get("radio", []):
        group = r.get("group"); header = r.get("csv",""); cell = row.get(header,"")
        if r.get("default_if_nonempty") and norm_space(cell):
            print(f"{i:02d}. CLICK   {r['default_if_nonempty']}  (group={group}, csv={header})"); i+=1
        else:
            print(f"{i:02d}. RADIO   group={group}  csv={header}  value={cell!r}"); i+=1
    for c in mapping.get("checkbox", []):
        header = c.get("csv",""); print(f"{i:02d}. CHECKBOX group={c.get('group')} csv={header}"); i+=1
    for cb in mapping.get("combobox", []):
        header = cb.get("csv",""); cid = cb.get("id"); want = row.get(header,"")
        print(f"{i:02d}. COMBO   #{cid} ← {want!r} (csv: {header})"); i+=1

# -----------------------
# Helpers
# -----------------------
OTHER_RE = re.compile(r"choice-display-(QID\d+)-(\d+)")

def derive_other_radio_selector(group: str, other_text_css: str) -> Optional[str]:
    """
    Try to compute the '#mc-choice-input-<group>-<idx>' for the Other option
    from a CSS like "input[aria-labelledby='choice-display-QID63-4']".
    """
    m = OTHER_RE.search(other_text_css)
    if not m:
        return None
    qid, idx = m.group(1), m.group(2)
    # group is like 'QID63'; make sure it matches
    if qid != group:
        return None
    return f"#mc-choice-input-{group}-{idx}"


# -----------------------
# Main
# -----------------------

async def run(opts):
    mapping = json.loads(Path(opts.mapping).read_text(encoding="utf-8"))
    if opts.start_url:
        mapping["start_url"] = opts.start_url

    # CSV
    import csv as _csv
    with open(opts.csv, newline="", encoding="utf-8-sig") as f:
        rdr = _csv.DictReader(f)
        rows = list(rdr)
    if not rows:
        print("[error] CSV has no data rows"); return
    if opts.row_index < 0 or opts.row_index >= len(rows):
        print(f"[error] --row-index out of range (0..{len(rows)-1})"); return
    row = rows[opts.row_index]

    print_action_plan(mapping, row)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not opts.headful, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(viewport={"width": 1360, "height": 900})
        page = await ctx.new_page()

        # start
        if mapping.get("start_url"):
            print(f"[nav] {mapping['start_url']}")
            await page.goto(mapping["start_url"], wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")

        step = 0
        while True:
            step += 1
            print(f"\n[page] Filling visible page (step {step}) …")
            if opts.debug:
                await debug_scan_page(page)

            did = await fill_current_page(page, mapping, row, human_delay=opts.human_delay, debug=opts.debug)

            # If nothing to do on this page (e.g., QID66 interstitial), just hit Next.
            if did == 0:
                if opts.debug: print("[info] No mapped controls on this page. Auto-click Next.")
                next_btn = page.locator("#next-button")
                if await next_btn.count() and await next_btn.first.is_enabled():
                    await click_next_and_wait(page, debug=opts.debug)
                else:
                    print("[halt] Next not available/enabled on an unmapped page."); break
            else:
                if opts.manual_continue:
                    input("Press Enter after you review this page and click Next yourself…")
                else:
                    next_btn = page.locator("#next-button")
                    if await next_btn.count() and await next_btn.first.is_enabled():
                        await click_next_and_wait(page, debug=opts.debug)
                    else:
                        print("[warn] Next disabled; pausing for manual fix.")
                        break

            # stop if no more questions
            if (await page.locator("section.question[id^='question-QID']").count()) == 0:
                print("[done] No questions detected on page; reached end.")
                break

        await ctx.close()
        await browser.close()

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Qualtrics form auto-fill (visible-controls-only)")
    p.add_argument("--csv", required=True, help="Path to CSV with short headers.")
    p.add_argument("--mapping", required=True, help="Path to mapping.json.")
    p.add_argument("--start-url", default=None, help="Override start URL.")
    p.add_argument("--row-index", type=int, default=0, help="CSV row index (0-based).")
    p.add_argument("--human-delay", type=int, default=55, help="Typing delay per character (ms).")
    p.add_argument("--headful", action="store_true", help="Visible browser window.")
    p.add_argument("--manual-continue", action="store_true", help="Pause on each page for manual Next.")
    p.add_argument("--debug", action="store_true", help="Verbose logs & scans.")
    return p.parse_args(argv)

if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("\n[cancelled]")
