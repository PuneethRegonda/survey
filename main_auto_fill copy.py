# main_auto_fill.py
# Qualtrics form auto-filler with batch CSV support, human-like typing, robust
# presence checks, and page-by-page DOM scans for easy debugging.
#
# Usage examples:
#   Single row:
#     python main_auto_fill.py --csv input/data.csv --mapping mapping.json \
#       --start-url "https://..." --row-index 0 --headful --debug --human-delay 2
#
#   All rows (skip header row 0, run the rest):
#     python main_auto_fill.py --csv input/data.csv --mapping mapping.json \
#       --start-url "https://..." --row-range 1 999999 --headful --debug --human-delay 2

import argparse
import asyncio
import csv
import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import async_playwright, Page, Locator


# =========================
# Small helpers
# =========================
def norm_space(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def norm_case(s: Any) -> str:
    return norm_space(s).lower()


def jitter(base: int, spread: int = 30) -> int:
    lo = max(0, base - spread)
    hi = base + spread
    return random.randint(lo, hi)


def parse_multi(cell: str, delim: Optional[str]) -> List[str]:
    if not cell:
        return []
    parts = str(cell).split(delim) if delim else re.split(r"[;,]", str(cell))
    return [norm_space(p) for p in parts if norm_space(p)]


def css_from_entry(entry: Dict[str, Any]) -> str:
    if entry.get("id"):
        return f"#{entry['id']}"
    if entry.get("css"):
        css = entry["css"]
        return css[len("css="):] if css.startswith("css=") else css
    raise ValueError("Mapping entry missing 'id' or 'css'.")


# For deriving “Other” radio selector from other_text_css like:
# "input[aria-labelledby='choice-display-QID63-4']" → "#mc-choice-input-QID63-4"
OTHER_RE = re.compile(r"choice-display-(QID\d+)-(\d+)")


def derive_other_radio_selector(group: str, other_text_css: str) -> Optional[str]:
    m = OTHER_RE.search(other_text_css)
    if not m:
        return None
    qid, idx = m.group(1), m.group(2)
    if qid != group:
        return None
    return f"#mc-choice-input-{group}-{idx}"


# =========================
# Active-page / overlay guards
# =========================
ACTIVE_JS = r"""
(sel) => {
  const vis = (el) => {
    if (!el) return false;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  // If a blocking overlay is visible, treat as not interactable.
  const ov = document.querySelector('.portal .overlay');
  if (ov && vis(ov)) return false;

  const el = document.querySelector(sel);
  if (!el) return false;

  // Find nearest content container like #content-8
  let node = el;
  while (node && !(node.id && node.id.startsWith('content-'))) node = node.parentElement;
  const container = node || document.getElementById('contents');
  if (!container || !vis(container)) return false;
  if (!container.contains(el)) return false;

  // If inside a question, ensure that question is visible
  const q = el.closest("section.question[id^='question-QID']");
  if (q && !vis(q)) return false;

  return vis(el);
}
"""


def mk_group_present_js(input_type: str) -> str:
    # More tolerant presence test: if the question section is visible OR
    # if any visible input[name=group] exists on the page.
    return r"""
(group) => {
  const vis = (el) => {
    if (!el) return false;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  // Do not block presence detection if overlay is up; we just want 'present'

  // visible section?
  const sec = document.querySelector("section#question-" + group);
  if (sec && vis(sec)) return true;

  // visible inputs?
  const inputs = document.querySelectorAll("input[type='""" + input_type + r"""'][name='" + group + "']");
  for (const el of inputs) {
    if (vis(el)) return true;
  }
  return false;
}
"""


async def wait_no_overlay(page: Page, timeout_ms: int = 3500):
    steps = max(1, timeout_ms // 100)
    for _ in range(steps):
        try:
            ok = await page.evaluate("""
                () => {
                  const ov = document.querySelector('.portal .overlay');
                  if (!ov) return true;
                  const cs = getComputedStyle(ov);
                  if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return true;
                  const r = ov.getBoundingClientRect();
                  return (r.width === 0 || r.height === 0);
                }
            """)
            if ok:
                return
        except Exception:
            return
        await page.wait_for_timeout(100)


async def control_in_active_content(page: Page, selector: str) -> bool:
    try:
        return await page.evaluate(ACTIVE_JS, selector)
    except Exception:
        try:
            loc = page.locator(selector).first
            if await loc.count() == 0:
                return False
            return await loc.is_visible()
        except Exception:
            return False


async def radio_group_present(page: Page, group: str) -> bool:
    try:
        return await page.evaluate(mk_group_present_js("radio"), group)
    except Exception:
        return await page.locator(f"section#question-{group}").count() > 0


async def checkbox_group_present(page: Page, group: str) -> bool:
    try:
        return await page.evaluate(mk_group_present_js("checkbox"), group)
    except Exception:
        return await page.locator(f"section#question-{group}").count() > 0


async def combobox_in_active(page: Page, cid: str) -> bool:
    return await control_in_active_content(page, f"div[role='combobox']#{cid}")


async def selector_visible(page: Page, selector: str) -> bool:
    loc = page.locator(selector).first
    try:
        if await loc.count() == 0:
            return False
        return await loc.is_visible()
    except Exception:
        return False


# =========================
# Debug helpers (page scanners)
# =========================
async def debug_scan_page(page: Page) -> None:
    try:
        print("[debug] Scanning page for radio groups...")
        radio = await page.evaluate("""
          () => {
            const out = {};
            for (const el of document.querySelectorAll("input[type='radio'][id^='mc-choice-input-']")) {
              const name = el.name; if (!name) continue;
              if (!out[name]) out[name] = [];
              const labId = el.getAttribute('aria-labelledby') || "";
              const lab = labId ? document.getElementById(labId) : null;
              out[name].push({
                id: el.id || '',
                label: lab ? lab.textContent.trim() : '',
                checked: el.checked === true
              });
            }
            return out;
          }options:
        """)
        for g, options in radio.items():
            print(f"[debug] Group {g} options:")
            for o in options:
                print(f"  id='{o['id']}' label='{o['label']}' selected={o['checked']}")
    except Exception as e:
        print(f"[warn] debug_scan_page: {e}")


async def log_active_dom_summary(page: Page) -> None:
    """Print visible question IDs & titles + present groups and inputs."""
    try:
        summary = await page.evaluate("""
          () => {
            const vis = (el) => {
              if (!el) return false;
              const cs = getComputedStyle(el);
              if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
              const r = el.getBoundingClientRect();
              return r.width > 0 && r.height > 0;
            };
            const out = { questions: [], radios: [], checks: [], texts: [] };

            const qs = Array.from(document.querySelectorAll("section.question[id^='question-QID']"));
            for (const q of qs) {
              if (!vis(q)) continue;
              const id = q.id || '';
              const titleEl = q.querySelector(".question-display");
              const title = titleEl ? titleEl.textContent.trim().replace(/\\s+/g,' ') : '';
              out.questions.push({ id, title: title.slice(0, 120) });
            }

            const radios = Array.from(document.querySelectorAll("input[type='radio'][id^='mc-choice-input-']"));
            const seen = new Set();
            for (const r of radios) {
              if (!vis(r)) continue;
              if (!seen.has(r.name)) {
                seen.add(r.name);
                out.radios.push(r.name);
              }
            }

            const checks = Array.from(document.querySelectorAll("input[type='checkbox'][id^='mc-choice-input-']"));
            const seenC = new Set();
            for (const c of checks) {
              if (!vis(c)) continue;
              if (!seenC.has(c.name)) {
                seenC.add(c.name);
                out.checks.push(c.name);
              }
            }

            const texts = Array.from(document.querySelectorAll("input[type='text'], textarea"));
            for (const t of texts) {
              if (!vis(t)) continue;
              const al = t.getAttribute('aria-labelledby') || '';
              const id = t.id || '';
              out.texts.push(al ? `input[aria-labelledby='${al}']` : (id ? `#${id}` : 'text-input'));
            }
            return out;
          }
        """)
        print("[page-scan] Visible questions:")
        for q in summary["questions"]:
            print(f"  - {q['id']}: {q['title']}")
        if summary["radios"]:
            print(f"[page-scan] Radio groups present: {', '.join(summary['radios'])}")
        if summary["checks"]:
            print(f"[page-scan] Checkbox groups present: {', '.join(summary['checks'])}")
        if summary["texts"]:
            print(f"[page-scan] Text inputs present: {', '.join(summary['texts'][:10])}{' …' if len(summary['texts'])>10 else ''}")
    except Exception as e:
        print(f"[warn] log_active_dom_summary: {e}")


# =========================
# Typing / Clicking
# =========================
async def type_like_human(page: Page, locator: Locator, text: str, per_char_ms: int, debug: bool) -> bool:
    try:
        await wait_no_overlay(page)
        loc = locator.first
        await loc.scroll_into_view_if_needed()
        await page.wait_for_timeout(jitter(80, 30))
        try:
            await loc.click()
        except Exception:
            await loc.click(force=True)
        # clear
        try:
            await loc.clear()
        except Exception:
            try:
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Delete")
            except Exception:
                pass
        await page.wait_for_timeout(jitter(80, 30))
        # type char by char
        for ch in str(text):
            await loc.type(ch, delay=jitter(per_char_ms, int(per_char_ms * 0.3)))
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(jitter(120, 40))
        # verify
        try:
            val = await loc.input_value()
            if norm_space(val) != norm_space(text):
                print(f"[retry] mismatch got='{val}' expected='{text}' → .fill()")
                await loc.fill(str(text))
        except Exception:
            pass
        # blur
        await page.mouse.click(10, 10)
        await page.wait_for_timeout(jitter(120, 40))
        return True
    except Exception as e:
        if debug:
            print(f"[warn] type_like_human failed: {e}")
        return False


async def click_selector(page: Page, selector: str, debug: bool = False) -> bool:
    try:
        await wait_no_overlay(page)
        loc = page.locator(selector).first
        await loc.scroll_into_view_if_needed()
        await page.wait_for_timeout(jitter(60, 25))
        try:
            await loc.click()
        except Exception:
            await loc.click(force=True)
        await page.wait_for_timeout(jitter(80, 30))
        if debug:
            print(f"[DEBUG] Clicked: {selector}")
        return True
    except Exception as e:
        if debug:
            print(f"[warn] click failed {selector}: {e}")
        return False


# =========================
# Resolvers
# =========================
def resolve_radio_selector(group: str, value_map: Dict[str, str], desired: str) -> Optional[str]:
    if not desired:
        return None
    # direct match
    if desired in value_map:
        return f"#mc-choice-input-{group}-{value_map[desired]}"
    # case-insensitive
    want = norm_case(desired)
    for k, v in value_map.items():
        if norm_case(k) == want:
            return f"#mc-choice-input-{group}-{v}"
    return None


def resolve_checkboxes(group: str, value_map: Optional[Dict[str, str]], cell: str, multi_delim: Optional[str]) -> Tuple[List[str], List[str]]:
    items = parse_multi(cell, multi_delim)
    if not items:
        return [], []
    sels, unmatched = [], []
    if value_map:
        for it in items:
            if it in value_map:
                sels.append(f"#mc-choice-input-{group}-{value_map[it]}")
                continue
            hit = None
            for k, v in value_map.items():
                if norm_case(k) == norm_case(it):
                    hit = v
                    break
            if hit:
                sels.append(f"#mc-choice-input-{group}-{hit}")
            else:
                unmatched.append(it)
    else:
        unmatched = items
    return sels, unmatched


# =========================
# Combobox (Qualtrics)
# =========================
async def choose_combobox_by_text(page: Page, cid: str, text: str, debug: bool) -> bool:
    try:
        await wait_no_overlay(page)
        combo = page.locator(f"div[role='combobox']#{cid}").first
        await combo.scroll_into_view_if_needed()
        await page.wait_for_timeout(jitter(60, 25))
        try:
            await combo.click()
        except Exception:
            await combo.click(force=True)

        menu = page.locator(f"ul#select-menu-{cid}")
        await menu.first.wait_for(state="visible", timeout=3000)

        items = menu.locator("li.menu-item")
        n = await items.count()
        want = norm_space(text).lower()

        idx = -1
        # exact
        for i in range(n):
            tx = norm_space(await items.nth(i).inner_text()).lower()
            if tx == want:
                idx = i
                break
        # contains
        if idx < 0:
            for i in range(n):
                tx = norm_space(await items.nth(i).inner_text()).lower()
                if want in tx:
                    idx = i
                    break

        if idx < 0:
            print(f"[warn] COMBO #{cid} option not found for {text!r}")
            try:
                await combo.press("Escape")
            except Exception:
                pass
            return False

        await items.nth(idx).click()
        await page.wait_for_timeout(jitter(80, 30))
        if debug:
            print(f"[DEBUG] Combobox {cid} → '{text}'")
        return True
    except Exception as e:
        print(f"[warn] Combobox {cid} failed: {e}")
        return False


# =========================
# Fill only what's visible on current page
# =========================
async def fill_current_page(page: Page, mapping: Dict[str, Any], row: Dict[str, str], human_delay: int, debug: bool) -> int:
    actions = 0

    # TEXT
    for entry in mapping.get("text", []):
        header = entry.get("csv", "")
        val = row.get(header, "")
        if not norm_space(val):
            if debug:
                print(f"[skip] empty CSV for text {header}")
            continue

        sel = css_from_entry(entry)
        if not await control_in_active_content(page, sel):
            if debug:
                print(f"[skip] control not on ACTIVE page: {sel} (csv: {header})")
            continue

        if debug:
            print(f"[TYPE] {sel} ← {val!r}  (csv: {header})")
        if await type_like_human(page, page.locator(sel), val, per_char_ms=human_delay, debug=debug):
            actions += 1

    # RADIO
    for r in mapping.get("radio", []):
        group = r.get("group")
        header = r.get("csv", "")
        if not group or not header:
            continue
        cell = norm_space(row.get(header, ""))
        if not cell:
            if debug:
                print(f"[skip] empty CSV for radio {group}/{header}")
            continue

        if not await radio_group_present(page, group):
            if debug:
                print(f"[skip] radio group not on ACTIVE page: {group}")
            continue

        # default-if-nonempty shortcut
        if r.get("default_if_nonempty"):
            sel = r["default_if_nonempty"]
            if debug:
                print(f"[CLICK] {sel} (default_if_nonempty) (group={group}, csv={header})")
            if await click_selector(page, sel, debug=debug):
                actions += 1
            continue

        # Try normal mapped selection
        mapped_sel = resolve_radio_selector(group, r.get("value_map", {}), cell)
        if mapped_sel:
            if debug:
                print(f"[CLICK] {mapped_sel} (group={group}, csv={header}, csv_value={cell!r})")
            if await click_selector(page, mapped_sel, debug=debug):
                actions += 1
            # If CSV literally starts with "Other:", also type its text
            if r.get("other_text_css") and norm_case(cell).startswith("other"):
                free = re.sub(r'^\s*other.*?:\s*', '', cell, flags=re.I).strip()
                if free and await control_in_active_content(page, r["other_text_css"]):
                    if debug:
                        print(f"[TYPE] (other) {r['other_text_css']} ← {free!r}")
                    if await type_like_human(page, page.locator(r["other_text_css"]), free, human_delay, debug):
                        actions += 1
            continue

        # Not mapped: if we have 'Other' textbox, auto-select Other and type CSV value
        if r.get("other_text_css"):
            other_radio = r.get("other_choice_selector") or derive_other_radio_selector(group, r["other_text_css"])
            if other_radio:
                if debug:
                    print(f"[CLICK] {other_radio} (auto-select Other; group={group}, csv={header})")
                await click_selector(page, other_radio, debug=debug)
                await page.wait_for_timeout(120)

            # refine to the textbox under the 'Other' label if possible
            other_sel = r["other_text_css"]
            refined = None
            m = re.search(r"#mc-choice-input-(QID\d+)-(\d+)$", other_radio or "")
            if m:
                g, idx = m.group(1), m.group(2)
                candidate = f"label[for='mc-choice-input-{g}-{idx}'] input[type='text']"
                if await page.locator(candidate).count() > 0:
                    refined = candidate
            target_sel = refined or other_sel
            loc = page.locator(target_sel)
            if await page.locator(target_sel).count() > 1:
                loc = page.locator(f"{target_sel}[type='text']")

            if await control_in_active_content(page, target_sel):
                if debug:
                    print(f"[TYPE] (radio other auto) {target_sel} ← {cell!r}")
                ok = await type_like_human(page, loc, cell, human_delay, debug)
                if ok:
                    actions += 1
                else:
                    # last resort
                    cand = page.locator(f"label[for^='mc-choice-input-{group}'] input[type='text']").first
                    try:
                        await cand.fill(cell)
                        actions += 1
                    except Exception:
                        if debug:
                            print(f"[warn] failed to type into Other textbox for group={group}")
            else:
                if debug:
                    print(f"[skip] Other textbox not visible for group={group}")
        else:
            if debug:
                print(f"[skip] radio value not mapped: group={group}; csv={header}; value={cell!r}")

    # CHECKBOX
    for c in mapping.get("checkbox", []):
        group = c.get("group")
        header = c.get("csv", "")
        cell = row.get(header, "")
        if not group or not header or not norm_space(cell):
            if debug and group:
                print(f"[skip] empty CSV for checkbox {group}/{header}")
            continue
        if not await checkbox_group_present(page, group):
            if debug:
                print(f"[skip] checkbox group not on ACTIVE page: {group}")
            continue

        sels, unmatched = resolve_checkboxes(group, c.get("value_map"), cell, c.get("multi_delimiter"))
        for sel in sels:
            if debug:
                print(f"[CHECK] {sel} (group={group}, csv={header})")
            if await click_selector(page, sel, debug=debug):
                actions += 1

        if unmatched:
            print(f"[skip] (checkbox entries not mapped) group={group}; csv={header}; unmatched={unmatched}")

        # 'Other' text for checkbox groups: support "Other: ..." tokens
        if c.get("other_text_css") and any(norm_case(x).startswith("other") for x in parse_multi(cell, c.get("multi_delimiter"))):
            free_vals = []
            for tok in parse_multi(cell, c.get("multi_delimiter")):
                if norm_case(tok).startswith("other"):
                    v = re.sub(r'^\s*other.*?:\s*', '', tok, flags=re.I).strip()
                    if v:
                        free_vals.append(v)
            if free_vals and await control_in_active_content(page, c["other_text_css"]):
                txt = "; ".join(free_vals)
                if debug:
                    print(f"[TYPE] (checkbox other) {c['other_text_css']} ← {txt!r}")
                if await type_like_human(page, page.locator(c["other_text_css"]), txt, human_delay, debug):
                    actions += 1

    # COMBOBOX
    for cb in mapping.get("combobox", []):
        header = cb.get("csv", "")
        cid = cb.get("id")
        want = row.get(header, "")
        if not cid or not header or not norm_space(want):
            if debug and header and not norm_space(want):
                print(f"[skip] empty CSV for combobox {cid}/{header}")
            continue
        if not await combobox_in_active(page, cid):
            if debug:
                print(f"[skip] combobox not on ACTIVE page: {cid}")
            continue
        if cb.get("choose_by_text", True):
            if debug:
                print(f"[COMBO] #{cid} ← {want!r}")
            if await choose_combobox_by_text(page, cid, want, debug):
                actions += 1

    return actions


# =========================
# Navigation
# =========================
async def _get_visible_qids(page: Page) -> List[str]:
    return await page.evaluate("""
      () => Array.from(document.querySelectorAll("section.question[id^='question-QID']"))
        .filter(el => {
          const st=getComputedStyle(el);
          if (st.display==='none'||st.visibility==='hidden') return false;
          if (!el.offsetParent && st.position!=='fixed') return false;
          return true;
        })
        .map(el=>el.id)
    """)

async def _get_visible_content_id(page: Page) -> Optional[str]:
    try:
        return await page.evaluate("""
          () => {
            const blocks = Array.from(document.querySelectorAll('.transition-content[id^="content-"]'));
            const vis = blocks.find(el => {
              const st = getComputedStyle(el);
              if (st.display==='none' || st.visibility==='hidden') return false;
              if (!el.offsetParent && st.position!=='fixed') return false;
              return true;
            });
            return vis ? vis.id : null;
          }
        """)
    except Exception:
        return None

async def _dismiss_overlays(page: Page, debug: bool):
    try:
        # Some Qualtrics UIs show a full-page overlay that intercepts clicks
        has_overlay = await page.evaluate("""() => !!document.querySelector('.portal .overlay')""")
        if has_overlay:
            if debug: print("[next-wait] overlay detected → sending Escape")
            try: await page.keyboard.press("Escape")
            except Exception: pass
            await page.wait_for_timeout(120)
    except Exception:
        pass
async def _get_visible_qids(page: Page) -> List[str]:
    return await page.evaluate("""
      () => Array.from(document.querySelectorAll("section.question[id^='question-QID']"))
        .filter(el => {
          const st=getComputedStyle(el);
          if (st.display==='none'||st.visibility==='hidden') return false;
          if (!el.offsetParent && st.position!=='fixed') return false;
          return true;
        })
        .map(el=>el.id)
    """)

async def _get_visible_content_id(page: Page) -> Optional[str]:
    try:
        return await page.evaluate("""
          () => {
            const blocks = Array.from(document.querySelectorAll('.transition-content[id^="content-"]'));
            const vis = blocks.find(el => {
              const st = getComputedStyle(el);
              if (st.display==='none' || st.visibility==='hidden') return false;
              if (!el.offsetParent && st.position!=='fixed') return false;
              return true;
            });
            return vis ? vis.id : null;
          }
        """)
    except Exception:
        return None

async def _dismiss_overlays(page: Page, debug: bool):
    try:
        # Some Qualtrics UIs show a full-page overlay that intercepts clicks
        has_overlay = await page.evaluate("""() => !!document.querySelector('.portal .overlay')""")
        if has_overlay:
            if debug: print("[next-wait] overlay detected → sending Escape")
            try: await page.keyboard.press("Escape")
            except Exception: pass
            await page.wait_for_timeout(120)
    except Exception:
        pass

async def click_next_and_wait(page: Page, debug: bool) -> None:
    try:
        before_qids    = await _get_visible_qids(page)
        before_content = await _get_visible_content_id(page)
        if debug:
            print(f"[next-wait] before content={before_content} qids={before_qids}")

        await _dismiss_overlays(page, debug)
        await click_selector(page, "#next-button", debug=debug)

        # Poll for either content id change OR visible QIDs set change
        t0 = time.time()
        changed = False
        for i in range(120):  # ~120 * 140ms ≈ 16–17s max
            await page.wait_for_timeout(140)
            curr_qids    = await _get_visible_qids(page)
            curr_content = await _get_visible_content_id(page)

            if (set(curr_qids) != set(before_qids)) or (curr_content != before_content):
                changed = True
                break

            # Heartbeat every ~1.4s
            if i % 10 == 0 and debug:
                elapsed = time.time() - t0
                print(f"[next-wait] {elapsed:0.1f}s ... content={curr_content} qids={len(curr_qids)} (waiting for change)")

            # Light nudges if it feels stuck
            if i in (20, 40, 80):  # after ~2.8s, 5.6s, 11.2s
                await _dismiss_overlays(page, debug)
                # re-click Next just in case the first click was swallowed by overlay/transition
                await click_selector(page, "#next-button", debug=debug)

        # Small settle
        await page.wait_for_timeout(150)

        if debug:
            after_qids    = await _get_visible_qids(page)
            after_content = await _get_visible_content_id(page)
            print(f"[debug] advanced to next page (changed={changed}) content={before_content}→{after_content} qids={len(before_qids)}→{len(after_qids)}")
            await list_visible_questions(page)
            await debug_scan_page(page)
            await log_active_qids(page)

    except Exception as e:
        print(f"[warn] next-page wait issue: {e}")


# =========================
# Plan preview
# =========================
def print_action_plan(mapping: Dict[str, Any], row: Dict[str, str]) -> None:
    print("=== ACTION PLAN (preview) ===")
    i = 1
    if mapping.get("start_url"):
        print(f"{i:02d}. NAVIGATE → {mapping['start_url']}")
        i += 1
    for entry in mapping.get("text", []):
        header = entry.get("csv", "")
        val = row.get(header, "")
        sel = css_from_entry(entry)
        print(f"{i:02d}. {'TYPE' if norm_space(val) else 'SKIP '}  {sel}  ←  {val!r}   (csv: {header})")
        i += 1
    for r in mapping.get("radio", []):
        group = r.get("group")
        header = r.get("csv", "")
        cell = row.get(header, "")
        if r.get("default_if_nonempty") and norm_space(cell):
            print(f"{i:02d}. CLICK   {r['default_if_nonempty']}  (group={group}, csv={header})")
            i += 1
        else:
            print(f"{i:02d}. RADIO   group={group}  csv={header}  value={cell!r}")
            i += 1
    for c in mapping.get("checkbox", []):
        header = c.get("csv", "")
        print(f"{i:02d}. CHECKBOX group={c.get('group')} csv={header}")
        i += 1
    for cb in mapping.get("combobox", []):
        header = cb.get("csv", "")
        cid = cb.get("id")
        want = row.get(header, "")
        print(f"{i:02d}. COMBO   #{cid} ← {want!r} (csv: {header})")
        i += 1


# =========================
# One survey run (single CSV row)
# =========================
async def run_one_row(pw, mapping: Dict[str, Any], row: Dict[str, str], opts, idx: int, total: int):
    browser = await pw.chromium.launch(
        headless=not opts.headful,
        args=["--disable-blink-features=AutomationControlled"]
    )
    ctx = await browser.new_context(viewport={"width": 1360, "height": 900})
    page = await ctx.new_page()

    print(f"\n[batch] Row {idx+1}/{total}: starting…")
    print_action_plan(mapping, row)

    if mapping.get("start_url"):
        print(f"[nav] {mapping['start_url']}")
        await page.goto(mapping["start_url"], wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        await wait_no_overlay(page)
        # initial snapshot of what's visible
        await log_active_dom_summary(page)
        if opts.debug:
            await debug_scan_page(page)

    step = 0
    while True:
        step += 1
        print(f"\n[page] Filling visible page (step {step}) …")
        if opts.debug:
            await debug_scan_page(page)

        did = await fill_current_page(page, mapping, row, human_delay=opts.human_delay, debug=opts.debug)

        # Next decision
        next_btn = page.locator("#next-button")
        if did == 0:
            if opts.debug:
                print("[info] No mapped controls on this page. Auto-click Next.")
            if await next_btn.count() and await next_btn.first.is_enabled():
                await click_next_and_wait(page, opts.debug)
            else:
                print("[halt] Next not available/enabled on an unmapped page — moving to next CSV row.")
                break
        else:
            if await next_btn.count() and await next_btn.first.is_enabled():
                await click_next_and_wait(page, opts.debug)
            else:
                print("[warn] Next disabled; stopping this row for manual fix.")
                break

        # stop if no more questions
        if (await page.locator("section.question[id^='question-QID']").count()) == 0:
            print("[done] No questions detected on page; reached end for this row.")
            break

    await ctx.close()
    await browser.close()


# =========================
# Main
# =========================
async def run(opts):
    mapping = json.loads(Path(opts.mapping).read_text(encoding="utf-8"))
    if opts.start_url:
        mapping["start_url"] = opts.start_url

    with open(opts.csv, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("[error] CSV has no data rows")
        return

    # Determine which rows to run
    indices: List[int] = []
    if opts.all_rows:
        indices = list(range(len(rows)))
    elif opts.row_range:
        a, b = opts.row_range
        a = max(0, a)
        b = min(len(rows) - 1, b)
        indices = list(range(a, b + 1))
    else:
        if not (0 <= opts.row_index < len(rows)):
            print(f"[error] --row-index out of range (0..{len(rows)-1})")
            return
        indices = [opts.row_index]

    async with async_playwright() as pw:
        total = len(indices)
        for j, idx in enumerate(indices):
            row = rows[idx]
            try:
                await run_one_row(pw, mapping, row, opts, j, total)
            except Exception as e:
                print(f"[row {idx}] error: {e} — continuing to next row")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Qualtrics auto-fill (batch mode + DOM scan)")
    p.add_argument("--csv", required=True, help="Path to CSV (short headers).")
    p.add_argument("--mapping", required=True, help="Path to mapping.json.")
    p.add_argument("--start-url", default=None, help="Override start URL.")
    p.add_argument("--row-index", type=int, default=0, help="CSV row index (0-based).")
    p.add_argument("--all-rows", action="store_true", help="Process ALL rows in the CSV.")
    p.add_argument("--row-range", nargs=2, type=int, metavar=("START", "END"),
                   help="Process a range of rows (inclusive).")
    p.add_argument("--human-delay", type=int, default=55, help="Typing delay per character (ms).")
    p.add_argument("--headful", action="store_true", help="Show browser.")
    p.add_argument("--debug", action="store_true", help="Verbose logs & DOM scans.")
    return p.parse_args(argv)


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("\n[cancelled]")
