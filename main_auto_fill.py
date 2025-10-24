import argparse
import asyncio
import csv
import json
import random
import re
import time
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

# Simple cross-version waiter (avoids wait_for_function signature issues)
async def wait_for_condition(page: Page, js_predicate: str, arg: Any = None, timeout_ms: int = 2000, interval_ms: int = 100) -> bool:
    """
    Polls a JS predicate until it returns truthy or timeout.
    js_predicate must be a function body with one argument 'arg', e.g.:
      "(arg) => { const el = document.querySelector(arg.sel); return !!el; }"
    """
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        try:
            ok = await page.evaluate(js_predicate, arg)
            if ok:
                return True
        except Exception:
            pass
        await page.wait_for_timeout(interval_ms)
    return False

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
# Debug Scans
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

async def list_visible_questions(page: Page) -> None:
    print("[page-scan] page waiting to scan questions…")
    await page.wait_for_timeout(600)  # settle DOM ~0.6s before scanning

    try:
        qinfo = await page.evaluate("""
            () => Array.from(document.querySelectorAll("section.question[id^='question-QID']"))
              .map(el => ({
                 id: el.id,
                 text: (el.querySelector(".question-display")?.innerText || "")
                         .replace(/\\s+/g," ").trim().slice(0,140)
              }))
        """)
        if qinfo:
            print("[page-scan] Visible questions:")
            for q in qinfo:
                print(f"  - {q['id']}: {q['text']}")
    except Exception:
        pass

# -----------------------
# Typing / Clicking
# -----------------------

async def type_like_human(page: Page, locator: Locator, text: str, per_char_ms: int, debug: bool) -> bool:
    try:
        target = locator.first
        await target.scroll_into_view_if_needed()
        await page.wait_for_timeout(jitter(50, 20))
        await target.click(force=True)
        # Clear
        try:
            await target.clear()
        except Exception:
            try:
                await target.fill("")
            except Exception:
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Delete")
        await page.wait_for_timeout(jitter(60, 30))
        for ch in str(text):
            await target.type(ch, delay=jitter(per_char_ms, int(per_char_ms * 0.3)))
        # verify
        try:
            val = await target.input_value()
            if norm_space(val) != norm_space(text):
                print(f"[retry] Typed mismatch. got='{val}' expected='{text}'. Using .fill()")
                await target.fill(str(text))
        except Exception:
            pass
        # blur
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(jitter(80, 30))
        await page.mouse.click(10, 10)
        await page.wait_for_timeout(jitter(70, 30))
        return True
    except Exception as e:
        if debug:
            print(f"[warn] type_like_human failed: {e}")
        return False

async def click_selector(page: Page, selector: str, debug: bool = False) -> bool:
    try:
        loc = page.locator(selector).first
        await loc.scroll_into_view_if_needed()
        await page.wait_for_timeout(jitter(40, 15))
        await loc.click(force=True)
        await page.wait_for_timeout(jitter(60, 25))
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
# Combobox (robust open + select) — no wait_for_function usage
# -----------------------

async def open_combobox(page: Page, combo_id: str, debug: bool) -> bool:
    """
    Robustly open a Qualtrics combobox that often detaches on click.
    Tries: force-click → focus+Enter → JS dispatch, then verifies via polling.
    """
    combo_sel = f"div[role='combobox']#{combo_id}"
    menu_sel  = f"ul#select-menu-{combo_id}"
    for attempt in range(3):
        try:
            combo = page.locator(combo_sel).first
            await combo.scroll_into_view_if_needed()
            try:
                await combo.click(force=True)
            except Exception:
                try:
                    await combo.focus()
                    await combo.press("Enter")
                except Exception:
                    await page.evaluate("""sel=>{
                        const el = document.querySelector(sel);
                        if (!el) return;
                        el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));
                        el.dispatchEvent(new MouseEvent('click',{bubbles:true}));
                    }""", combo_sel)

            # Verify menu is open (aria-expanded + menu visible) using our polling helper
            ok = await wait_for_condition(
                page,
                """(arg) => {
                    const c=document.querySelector(arg.combo);
                    const m=document.querySelector(arg.menu);
                    return !!(c && m && c.getAttribute('aria-expanded')==='true' &&
                              m.offsetParent!==null && m.style.display!=='none');
                }""",
                {"combo": combo_sel, "menu": menu_sel},
                timeout_ms=2000,
                interval_ms=80
            )
            if ok:
                return True
            else:
                if debug: print(f"[combobox] open attempt {attempt+1} did not expose menu")
        except Exception as e:
            if debug: print(f"[combobox] open attempt {attempt+1} failed: {e}")
        await page.wait_for_timeout(200)
    if debug: print(f"[warn] Could not open combobox #{combo_id}")
    return False

async def choose_combobox_by_text(page: Page, combo_id: str, visible_text: str, debug: bool) -> bool:
    """
    Open the menu, find an item by exact/contains match, click it, and verify the
    button reflects the chosen text. Retries on DOM detach.
    """
    want = norm_space(visible_text).lower()
    combo_sel = f"div[role='combobox']#{combo_id}"
    menu_sel  = f"ul#select-menu-{combo_id}"

    for attempt in range(3):
        try:
            opened = await open_combobox(page, combo_id, debug)
            if not opened:
                return False

            items = await page.evaluate(
                """(mSel) => {
                    const ul = document.querySelector(mSel);
                    if(!ul) return [];
                    const lis = Array.from(ul.querySelectorAll("li.menu-item"));
                    return lis.map((li,idx)=>({
                        id: li.id || "",
                        idx,
                        text: (li.innerText||"").trim()
                    }));
                }""",
                menu_sel
            )
            if not items:
                if debug: print(f"[warn] No items in combobox #{combo_id}")
                try: await page.locator(combo_sel).press("Escape")
                except Exception: pass
                continue

            def find_index():
                for it in items:
                    if norm_space(it["text"]).lower() == want:
                        return it["idx"]
                for it in items:
                    if want in norm_space(it["text"]).lower():
                        return it["idx"]
                return -1

            idx = find_index()
            if idx < 0:
                if debug: print(f"[warn] COMBO '{combo_id}' option not found for {visible_text!r}")
                try: await page.locator(combo_sel).press("Escape")
                except Exception: pass
                return False

            candidates = page.locator(f"{menu_sel} li.menu-item")
            try:
                await candidates.nth(idx).scroll_into_view_if_needed()
            except Exception:
                pass

            try:
                await candidates.nth(idx).click(force=True)
            except PWTimeout:
                # Re-open and try again by id
                await page.locator(combo_sel).press("Escape")
                await page.wait_for_timeout(120)
                if not await open_combobox(page, combo_id, debug):
                    return False
                items2 = await page.evaluate(
                    """(mSel)=>Array.from(document.querySelectorAll(mSel+' li.menu-item')).map(li=>li.id)""",
                    menu_sel
                )
                if items2 and idx < len(items2) and items2[idx]:
                    await page.locator(f"#{items2[idx]}").click(force=True)
                else:
                    await page.locator(f"{menu_sel} li.menu-item").nth(idx).click(force=True)

            # Verify the combobox button now shows the chosen text (poll)
            ok = await wait_for_condition(
                page,
                """(arg)=>{
                    const btn=document.querySelector(arg.combo);
                    if(!btn) return false;
                    const span=btn.querySelector('span.rich-text');
                    const txt=(span?.textContent||'').trim().toLowerCase();
                    return txt===arg.want || txt.indexOf(arg.want)>=0;
                }""",
                {"combo": combo_sel, "want": want},
                timeout_ms=1500,
                interval_ms=80
            )
            if not ok:
                try: await page.locator(combo_sel).press("Escape")
                except Exception: pass

            if debug: print(f"[DEBUG] Combobox {combo_id} → '{visible_text}'")
            return True

        except Exception as e:
            if debug: print(f"[warn] Combobox {combo_id} failed (attempt {attempt+1}): {e}")
            await page.wait_for_timeout(250)

    return False

# -----------------------
# Fill visible page only (returns number of actions performed)
# -----------------------

OTHER_RE = re.compile(r"choice-display-(QID\d+)-(\d+)")

def derive_other_radio_selector(group: str, other_text_css: str) -> Optional[str]:
    m = OTHER_RE.search(other_text_css)
    if not m:
        return None
    qid, idx = m.group(1), m.group(2)
    if qid != group:
        return None
    return f"#mc-choice-input-{group}-{idx}"

async def fill_current_page(page: Page, mapping: Dict[str, Any], row: Dict[str, str], human_delay: int, debug: bool) -> int:
    actions = 0

    # TEXT
    for entry in mapping.get("text", []):
        header = entry.get("csv", "")
        sel = css_from_entry(entry)

        raw = row.get(header, "")
        val = norm_space(raw)

        if not val:
            if entry.get("default_from_csv"):
                fallback_col = entry["default_from_csv"]
                val = norm_space(row.get(fallback_col, ""))
            if not val and entry.get("default_value"):
                val = entry["default_value"]
            if not val and entry.get("halt_if_empty"):
                print(f"[halt] required text '{header}' is empty; please fill CSV or remove halt_if_empty")
                raise SystemExit(1)

        if not val:
            if debug: print(f"[skip] empty CSV for text {header}")
            continue

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
        if not cell and r.get("default_choice"):
            cell = r["default_choice"]
        if not cell:
            if debug: print(f"[skip] empty CSV for radio {group}/{header}")
            continue
        if not await radio_group_present(page, group):
            if debug: print(f"[skip] radio group not on page: {group}")
            continue

        if r.get("default_if_nonempty"):
            sel = r["default_if_nonempty"]
            if debug: print(f"[CLICK] {sel} (default_if_nonempty) (group={group}, csv={header})")
            if await click_selector(page, sel, debug=debug): actions += 1
            continue

        mapped_sel = resolve_radio_selector(group, r.get("value_map", {}), cell)
        if mapped_sel:
            if debug: print(f"[CLICK] {mapped_sel} (group={group}, csv={header}, csv_value={cell!r})")
            if await click_selector(page, mapped_sel, debug=debug): actions += 1
            if r.get("other_text_css") and norm_case(cell).startswith("other"):
                free = re.sub(r'^\s*other.*?:\s*', '', cell, flags=re.I).strip()
                if free and await selector_visible(page, r["other_text_css"]):
                    if debug: print(f"[TYPE] (other) {r['other_text_css']} ← {free!r}")
                    if await type_like_human(page, page.locator(r["other_text_css"]), free, human_delay, debug): actions += 1
            continue

        # Unmapped → auto select "Other" & type CSV as free text (if configured)
        if r.get("other_text_css"):
            other_radio = r.get("other_choice_selector") or derive_other_radio_selector(group, r["other_text_css"])
            if other_radio:
                if debug: print(f"[CLICK] {other_radio} (auto-select Other; group={group}, csv={header})")
                await click_selector(page, other_radio, debug=debug)
                await page.wait_for_timeout(120)

            other_sel = r["other_text_css"]
            refined = None
            m = re.search(r"#mc-choice-input-(QID\\d+)-(\\d+)$", other_radio or "")
            if m:
                g, idx = m.group(1), m.group(2)
                candidate = f"label[for='mc-choice-input-{g}-{idx}'] input[type='text']"
                if await page.locator(candidate).count() > 0:
                    refined = candidate
            target_sel = refined or other_sel
            loc = page.locator(target_sel)
            if await loc.count() > 1:
                loc = page.locator(f"{target_sel}[type='text']")
            if await selector_visible(page, target_sel):
                if debug: print(f"[TYPE] (radio other auto) {target_sel} ← {cell!r}")
                ok = await type_like_human(page, loc, cell, human_delay, debug)
                if not ok:
                    try:
                        await loc.first.fill(cell); actions += 1
                    except Exception:
                        if debug: print(f"[warn] failed to type into Other textbox for group={group}")
                else:
                    actions += 1
            else:
                if debug: print(f"[skip] Other textbox not visible for group={group}")

    # CHECKBOX
    for c in mapping.get("checkbox", []):
        group = c.get("group"); header = c.get("csv", "")
        if not group or not header:
            continue

        cell = row.get(header, "")
        if not norm_space(cell):
            if debug: print(f"[skip] empty CSV for checkbox {group}/{header}")
            continue

        if not await checkbox_group_present(page, group):
            if debug: print(f"[skip] checkbox group not on page: {group}")
            continue

        to_check, unmatched = resolve_checkboxes(group, c.get("value_map"), cell, c.get("multi_delimiter"))

        # mapped → .check() is safer than click (avoids toggling off)
        for sel in to_check:
            loc = page.locator(sel).first
            try:
                await loc.scroll_into_view_if_needed()
                await loc.check(force=True)
                if debug: print(f"[CHECK] {sel} (group={group}, csv={header})")
                actions += 1
            except Exception:
                if await click_selector(page, sel, debug=debug):
                    actions += 1

        # explicit "Other: ..." tokens also feed the Other text
        explicit_others = []
        for tok in parse_multi(cell, c.get("multi_delimiter")):
            if norm_case(tok).startswith("other"):
                v = re.sub(r'^\s*other.*?:\s*', '', tok, flags=re.I).strip()
                if v:
                    explicit_others.append(v)

        need_other = (bool(unmatched) or bool(explicit_others)) and c.get("auto_other_if_unmatched") and c.get("other_text_css")
        if need_other:
            other_radio = c.get("other_choice_selector") or derive_other_radio_selector(group, c["other_text_css"])
            if other_radio:
                other_loc = page.locator(other_radio).first
                try:
                    await other_loc.scroll_into_view_if_needed()
                    await other_loc.check(force=True)
                except Exception:
                    await click_selector(page, other_radio, debug=debug)
                await page.wait_for_timeout(150)

            refined = None
            m = OTHER_RE.search(c["other_text_css"])
            if m:
                g, idx = m.group(1), m.group(2)
                refined = f"label[for='mc-choice-input-{g}-{idx}'] input[type='text']"
            target_sel = refined or c["other_text_css"]

            combined = []
            seen = set()
            for x in unmatched + explicit_others:
                k = norm_case(x)
                if k not in seen:
                    combined.append(x)
                    seen.add(k)
            txt = ", ".join(combined)

            if await selector_visible(page, target_sel):
                if debug: print(f"[TYPE] (checkbox other) {target_sel} ← {txt!r}")
                ok = await type_like_human(page, page.locator(target_sel), txt, human_delay, debug)
                if not ok:
                    try:
                        await page.locator(target_sel).first.fill(txt)
                        actions += 1
                    except Exception:
                        if debug: print(f"[warn] failed to type into checkbox Other textbox for group={group}")
                else:
                    actions += 1
            else:
                if debug: print(f"[skip] Other textbox not visible for group={group}")

        if unmatched:
            print(f"[skip] (checkbox entries not mapped) group={group}; csv={header}; unmatched={unmatched}")

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
        prev_qids = await page.eval_on_selector_all(
            "section.question[id^='question-QID']",
            "els => els.map(e=>e.id)"
        )
        await click_selector(page, "#next-button", debug=debug)

        # Detect DOM changes rather than networkidle (Qualtrics is client-driven)
        for _ in range(60):  # ~6-7s total
            await page.wait_for_timeout(120)
            curr_qids = await page.eval_on_selector_all(
                "section.question[id^='question-QID']",
                "els => els.map(e=>e.id)"
            )
            if set(curr_qids) != set(prev_qids):
                break

        await page.wait_for_timeout(120)

        if debug:
            await list_visible_questions(page)
            await debug_scan_page(page)
            print("[debug] advanced to next page")
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
# Batch processing
# -----------------------

async def process_single_row(pw, mapping: Dict[str, Any], row: Dict[str, str], idx: int, opts) -> None:
    print(f"\n[batch] Row {idx+1}: starting…")
    print_action_plan(mapping, row)

    # Fresh browser per row
    browser = await pw.chromium.launch(
        headless=not opts.headful,
        args=["--disable-blink-features=AutomationControlled"]
    )
    ctx = await browser.new_context(viewport={"width": 1360, "height": 900})
    page = await ctx.new_page()

    # Start URL
    if mapping.get("start_url"):
        print(f"[nav] {mapping['start_url']}")
        await page.goto(mapping["start_url"], wait_until="domcontentloaded")

    step = 0
    while True:
        step += 1
        print(f"\n[page] Filling visible page (step {step}) …")
        if opts.debug:
            
            await list_visible_questions(page)
            await debug_scan_page(page)

        did = await fill_current_page(page, mapping, row, human_delay=opts.human_delay, debug=opts.debug)

        next_btn = page.locator("#next-button")
        if did == 0:
            if opts.debug: print("[info] No mapped controls on this page. Auto-click Next.")
            if await next_btn.count() and await next_btn.first.is_enabled():
                await click_next_and_wait(page, debug=opts.debug)
            else:
                print("[halt] Next not available/enabled on an unmapped page — moving to next CSV row.")
                break
        else:
            if opts.manual_continue:
                input("Press Enter after you review this page and click Next yourself…")
            else:
                if await next_btn.count() and await next_btn.first.is_enabled():
                    await click_next_and_wait(page, debug=opts.debug)
                else:
                    print("[warn] Next disabled; pausing for manual fix.")
                    break

        # End condition: no more questions (finished or thank-you page)
        if (await page.locator("section.question[id^='question-QID']").count()) == 0:
            print("[done] No questions detected on page; reached end.")
            break

    await ctx.close()
    await browser.close()
    print(f"[batch] Row {idx+1}: done.")

# -----------------------
# Main
# -----------------------

async def run(opts):
    # Load mapping & allow CLI override of start URL
    mapping = json.loads(Path(opts.mapping).read_text(encoding="utf-8"))
    if opts.start_url:
        mapping["start_url"] = opts.start_url

    # CSV rows (DictReader handles the header row)
    with open(opts.csv, newline="", encoding="utf-8-sig") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)

    if not rows:
        print("[error] CSV has no data rows")
        return

    # Determine which rows to run (0-based over data rows)
    indices: List[int]
    if opts.all:
        indices = list(range(len(rows)))
    elif opts.row_index is not None:
        if opts.row_index < 0 or opts.row_index >= len(rows):
            print(f"[error] --row-index out of range (0..{len(rows)-1})"); return
        indices = [opts.row_index]
    else:
        start = 0 if opts.start_index is None else opts.start_index
        end = (len(rows) - 1) if (opts.end_index is None or opts.end_index < 0) else opts.end_index
        if start < 0: start = 0
        if end >= len(rows): end = len(rows) - 1
        if start > end:
            print(f"[error] start_index ({start}) > end_index ({end})"); return
        indices = list(range(start, end + 1))

    print(f"[batch] Will process {len(indices)} data row(s): {indices}")

    async with async_playwright() as pw:
        for i in indices:
            await process_single_row(pw, mapping, rows[i], i, opts)

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Qualtrics form auto-fill (batch-capable)")
    p.add_argument("--csv", required=True, help="Path to CSV with short headers.")
    p.add_argument("--mapping", required=True, help="Path to mapping.json.")
    p.add_argument("--start-url", default=None, help="Override start URL for this run.")
    # Single row OR range OR all
    p.add_argument("--row-index", type=int, default=None, help="Process a single CSV data row (0-based).")
    p.add_argument("--start-index", type=int, default=None, help="First CSV data row to process (0-based).")
    p.add_argument("--end-index", type=int, default=None, help="Last CSV data row to process (0-based). Use -1 for 'last'.")
    p.add_argument("--all", action="store_true", help="Process all CSV data rows.")
    # Behavior
    p.add_argument("--human-delay", type=int, default=28, help="Typing delay per character (ms).")
    p.add_argument("--headful", action="store_true", help="Visible browser window.")
    p.add_argument("--manual-continue", action="store_true", help="Pause on each page for manual Next.")
    p.add_argument("--debug", action="store_true", help="Verbose logs & scans.")
    return p.parse_args(argv)

if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("\n[cancelled]")
