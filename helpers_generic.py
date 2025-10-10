async def print_section_details(page):
    """
    Prints all section ids, question headings, and input types for mapping to CSV records.
    """
    qs = await visible_questions(page)
    print("\n=== SECTION DETAILS FOR MAPPING ===========================")
    print("Count:", len(qs))
    for q in qs:
        print(f'- Section ID: {q["sec_id"]}')
        print(f'  QID: {q["qid"]}')
        print(f'  Heading: {q["heading"][:120]}')
        # Find input types in the section
        sec = page.locator(f'#{q["sec_id"]}')
        radios = await sec.locator('input[type="radio"]').count()
        checkboxes = await sec.locator('input[type="checkbox"]').count()
        texts = await sec.locator('input[type="text"]').count()
        print(f'  Inputs: {radios} radio, {checkboxes} checkbox, {texts} text')
    print("==========================================================\n")
# helpers_generic.py
import re

def norm(s:str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def ilike(hay:str, needle:str) -> bool:
    return needle.lower() in (hay or "").lower()

async def visible_questions(page):
    out = []
    for sec in await page.locator("section.question").all():
        try:
            sec_id = await sec.get_attribute("id")            # e.g., question-QID66
            head = await sec.locator(".question-display").inner_text()
            qid = re.search(r"(QID\d+)", sec_id or "")
            out.append({"sec_id":sec_id, "qid":qid.group(1) if qid else None, "heading":norm(head)})
        except:
            pass
    return out

async def click_radio(page, sec_id:str, text:str|None):
    """
    Tries by role name and label text. If that fails, checks the FIRST radio input in the section.
    This solves pages where Qualtrics hides ARIA names and uses long block labels.
    """
    sec = page.locator(f'#{sec_id}')
    clicked = False

    if text:
        # try role first
        r = sec.get_by_role("radio", name=text, exact=False)
        if await r.count() > 0:
            await r.first.click()
            return True

        # try label text (normalized, partial match)
        labels = await sec.locator('label.choice-label').all()
        found = False
        for lbl in labels:
            lbl_text = await lbl.inner_text()
            if ilike(norm(lbl_text), norm(text)) or norm(text) in norm(lbl_text):
                await lbl.click()
                found = True
                break
        if found:
            return True

        # If not found, print all available radio labels for debugging
        print(f"[DEBUG] Could not match radio label for section {sec_id} with text '{text}'. Available labels:")
        for lbl in labels:
            lbl_text = await lbl.inner_text()
            print(f"    - {lbl_text}")

    # FALLBACK: click the first radio input directly
    inputs = sec.locator('input[type="radio"]')
    if await inputs.count() > 0:
        # Check if already selected
        if not await inputs.first.is_checked():
            await inputs.first.check(force=True)
        else:
            # Already checked, skip .check()
            pass
        return True

    # LAST RESORT: click any element that looks like the radio "button"
    any_radio = sec.locator('[role="radio"], .radio-button.radio')
    if await any_radio.count() > 0:
        await any_radio.first.click()
        return True

    return False

async def click_checkbox(page, sec_id:str, text:str):
    sec = page.locator(f'#{sec_id}')
    c = sec.get_by_role("checkbox", name=text, exact=False)
    if await c.count() == 0:
        c = sec.locator(f'label:has-text("{text}")')
    if await c.count() > 0:
        await c.first.click()
        return True

    # fallback: first checkbox
    boxes = sec.locator('input[type="checkbox"]')
    if await boxes.count() > 0:
        await boxes.first.check(force=True)
        return True

    return False

async def select_dropdown(page, sec_id:str, text:str):
    btn = page.locator(f'#{sec_id} .select-menu.menu-button')
    await btn.click()
    await page.locator(f'ul.select-menu li:has-text("{text}")').first.click()

async def fill_all_text_inputs(page, sec_id:str, values:list[str]):
    inputs = await page.locator(f'#{sec_id} input[type="text"]').all()
    for i, v in enumerate(values):
        if i < len(inputs):
            await inputs[i].fill(v or "")

async def fill_first_text(page, sec_id:str, value:str):
    inp = page.locator(f'#{sec_id} input[type="text"]').first
    await inp.fill(value)

async def debug_dump(page, note=""):
    qs = await visible_questions(page)
    print("\n=== DEBUG: Visible questions on page ===========================")
    if note: print(note)
    print("Count:", len(qs))
    for q in qs:
        print(f'- {q["sec_id"]}: {q["heading"][:120]}')
        opts = await page.locator(
            f'#{q["sec_id"]} [role="radio"], #{q["sec_id"]} [role="checkbox"], #{q["sec_id"]} input[type="radio"], #{q["sec_id"]} input[type="checkbox"]'
        ).all()
        for o in opts[:4]:
            try:
                txt = await o.text_content()
            except:
                txt = ""
            print("    • choice:", txt or "(no aria/label text)")
    nb = await page.locator("#next-button").is_visible()
    print("----------------------------------------------------------------")
    print("Next button visible:", nb)
    print("================================================================\n")
