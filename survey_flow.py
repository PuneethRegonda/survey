import re

async def get_visible_questions(page):
    # returns list of (qid, heading_text)
    qs = []
    for sec in await page.locator("section.question").all():
        try:
            qid = await sec.get_attribute("id")  # e.g., question-QID66
            title = (await sec.locator(".question-display").inner_text()).strip()
            qs.append((qid, title))
        except Exception:
            continue
    return qs

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()

async def find_question_by_heading(page, needle_substring: str):
    """Find a visible question whose heading contains the substring (case/space-insensitive).
       Returns (qid_str_without_prefix, full_heading) or (None, None)"""
    tgt = norm(needle_substring)
    for qid_full, heading in await get_visible_questions(page):
        if not qid_full:
            continue
        if tgt in norm(heading):
            # qid_full like 'question-QID66' -> 'QID66'
            m = re.search(r"(QID\d+)", qid_full)
            if m:
                return m.group(1), heading
    return None, None

async def click_radio_in_question(page, qid: str, choice_text: str):
    # First try ARIA by role/name, then fallback to label :has-text
    # Use exact=False for fuzzy matches because Qualtrics often injects spaces/non-breaking spaces.
    radio = page.locator(f'#{qid}').get_by_role("radio", name=choice_text, exact=False)
    if await radio.count() == 0:
        radio = page.locator(f'#{qid} label:has-text("{choice_text}")')
    await radio.first.click()

async def click_checkbox_in_question(page, qid: str, choice_text: str):
    box = page.locator(f'#{qid}').get_by_role("checkbox", name=choice_text, exact=False)
    if await box.count() == 0:
        box = page.locator(f'#{qid} label:has-text("{choice_text}")')
    await box.first.click()

async def fill_text_inputs_in_question(page, qid: str, values: list[str]):
    """Fill all text inputs found in a question (in order). Useful for multi-part name forms."""
    inputs = await page.locator(f'#{qid} input[type="text"]').all()
    for i, v in enumerate(values):
        if i < len(inputs):
            await inputs[i].fill(v or "")

async def debug_dump_page(page, note=""):
    qs = await get_visible_questions(page)
    print("\n=== DEBUG: Visible questions on page ===========================")
    if note:
        print(note)
    print(f"Count: {len(qs)}")
    for qid_full, heading in qs:
        print(f"- {qid_full}: {heading.splitlines()[0][:120]}")
        # optional: show first few options if radios/checkboxes
        opts = await page.locator(f'#{qid_full} [role="radio"], #{qid_full} [role="checkbox"]').all()
        for o in opts[:4]:
            try:
                print("    • choice:", (await o.text_content()) or "")
            except:
                pass
    nb = await page.locator("#next-button").is_visible()
    print("----------------------------------------------------------------")
    print("Next button visible:", nb)
    print("================================================================\n")

# survey_flow.py
from utils import (
    get_val, split_multi, split_other,
    click_next, advance_if_gate_or_welcome,
    debug_dump, prompt_yes_to_continue
)
from playwright.async_api import TimeoutError as PlaywrightTimeout
async def click_ack_if_present(page, verbose=True) -> bool:
    """
    If the GoPass Use Acknowledgement (QID4) is on the page,
    tick its checkbox and return True. Otherwise return False.
    """
    root = page.locator('#question-QID4')
    if await root.count() == 0:
        return False

    if verbose:
        print("[hit ] GoPass Acknowledgement (QID4) → checking box")

    # Try an exact accessible name first
    label_text = (
        "I certify that I read, understand, and agree with the GoPass Use "
        "Acknowledgement terms and conditions."
    )
    el = root.get_by_role("checkbox", name=label_text, exact=True)

    # Fallback to partial text (Qualtrics can sometimes compress whitespace)
    if await el.count() == 0:
        el = root.locator('label:has-text("I certify that I read")')

    await el.first.scroll_into_view_if_needed()
    await el.first.click()

    if verbose:
        print("[done] QID4 checked")

    return True

async def click_radio_by_text(page, qid: str, text: str, verbose=True):
    root = page.locator(f'#question-{qid}')
    if verbose: print(f"[seek] radio {qid} => '{text}'")
    await root.wait_for(state="visible", timeout=5000)
    el = root.get_by_role("radio", name=text, exact=True)
    if await el.count() == 0:
        el = root.locator(f'label:has-text("{text}")')
    await el.first.scroll_into_view_if_needed()
    await el.first.click()
    if verbose: print(f"[done] radio {qid} => '{text}'")

async def click_checkbox_by_text(page, qid: str, text: str, verbose=True):
    root = page.locator(f'#question-{qid}')
    if verbose: print(f"[seek] checkbox {qid} => '{text}'")
    await root.wait_for(state="visible", timeout=5000)
    el = root.get_by_role("checkbox", name=text, exact=True)
    if await el.count() == 0:
        el = root.locator(f'label:has-text("{text}")')
    await el.first.scroll_into_view_if_needed()
    await el.first.click()
    if verbose: print(f"[done] checkbox {qid} => '{text}'")

async def select_dropdown_by_text(page, qid: str, text: str, verbose=True):
    root = page.locator(f'#question-{qid}')
    if verbose: print(f"[seek] dropdown {qid} => '{text}'")
    await root.wait_for(state="visible", timeout=5000)
    btn = root.locator('.select-menu.menu-button')
    await btn.scroll_into_view_if_needed()
    await btn.click()
    item = page.locator(f'ul.select-menu li:has-text("{text}")').first
    await item.wait_for(state="visible", timeout=4000)
    await item.click()
    if verbose: print(f"[done] dropdown {qid} => '{text}'")

async def fill_text_in_question(page, qid: str, value: str, verbose=True):
    root = page.locator(f'#question-{qid}')
    if verbose: print(f"[seek] text {qid} => '{value}'")
    await root.wait_for(state="visible", timeout=5000)
    inp = root.locator('input[type="text"]').first
    if await inp.count() > 0:
        await inp.scroll_into_view_if_needed()
        await inp.fill(value)
        if verbose: print(f"[done] text {qid} (direct)")
        return
    inp2 = root.locator('.choice-te-wrapper input[type="text"]').first
    if await inp2.count() > 0:
        await inp2.scroll_into_view_if_needed()
        await inp2.fill(value)
        if verbose: print(f"[done] text {qid} (other wrapper)")
        return
    if verbose: print(f"[warn] text {qid} no input found!")

async def do_debug_pause(page, debug_step: bool):
    if debug_step:
        await debug_dump(page)
        ok = await prompt_yes_to_continue()
        if not ok:
            raise SystemExit("Stopped by user during debug step.")

async def fill_flow(page, row, debug_step=True, verbose=True):
    # Gate / welcome
    await advance_if_gate_or_welcome(page, verbose=verbose)

    try:
        from survey_flow import click_ack_if_present  # if top of file imports are static, ignore this line
    except:
        pass

    if await click_ack_if_present(page, verbose=verbose):
        await click_next(page)

    # Debug pause after we’ve dealt with any welcome/ack page(s)
    await do_debug_pause(page, debug_step)

    # ---- QID9: GoPass User Name (First, Middle, Last)
    # pull from your CSV columns
    first = get_val(row, "First Name", "First")
    middle = get_val(row, "Middle Name", "Middle")
    last = get_val(row, "Last Name", "Last")

    if await page.locator("#question-QID9").count() > 0:
        if first:
            await fill_text_in_question(page, "QID9", first)
        # optional: handle individual inputs precisely if needed
        try:
            await page.fill("#form-text-input-QID9-1", first or "")
            await page.fill("#form-text-input-QID9-2", middle or "")
            await page.fill("#form-text-input-QID9-3", last or "")
        except Exception:
            pass
        print(f"[done] Filled GoPass User Name → {first} {middle} {last}")
        await click_next(page)
        await do_debug_pause(page, debug_step)


    # === Fare category (by heading, not hard-coded QID) ===
    fare_heading = "In which fare category do you belong?"
    qid, head = await find_question_by_heading(page, fare_heading)
    if qid:
        sec_id = f"question-{qid}"
        fare = row.get('In which fare category do you belong?', '') or row.get('In which fare category do you belong?\n', '')
        if fare:
            print(f"[seek] radio {qid} => '{fare}'")
            await click_radio_in_question(page, sec_id, fare)
        await click_next(page)
    else:
        print(f"[skip] Fare category not on this page.")

    await debug_dump_page(page, note="After fare category")

    # === Adult Clipper Card you already own? (Yes/No) ===
    clipper_heading = "Would you like to receive your GoPass on an Adult Clipper Card"
    qid, head = await find_question_by_heading(page, clipper_heading)
    if qid:
        sec_id = f"question-{qid}"
        # Use CSV column; e.g. 'Clipper Card Already Own? (Yes/No)'
        clipper_choice = row.get('Would you like to receive your GoPass on an Adult Clipper Card (digital or physical) that you already own?', '')
        # Accept a few variations
        val = norm(clipper_choice)
        if val in ("yes", "y", "true", "1"):
            print(f"[seek] radio {qid} => 'Yes'")
            await click_radio_in_question(page, sec_id, "Yes")
        elif val in ("no", "n", "false", "0"):
            print(f"[seek] radio {qid} => 'No'")
            await click_radio_in_question(page, sec_id, "No")
        else:
            # Default logic: if we have a serial in CSV, assume Yes; else No.
            serial_hint = (row.get("Clipper Serial", "") or row.get("If you have a Clipper Card...serial", "")).strip()
            choose = "Yes" if serial_hint else "No"
            print(f"[seek] radio {qid} => '{choose}' (auto)")
            await click_radio_in_question(page, sec_id, choose)
        await click_next(page)
    else:
        print("[skip] Clipper Yes/No not on this page.")

    await debug_dump_page(page, note="After Clipper Yes/No")

    # === Clipper serial capture page (appears only if Yes previously) ===
    serial_heading = "If you have a Clipper Card"  # substring from that serial-entry page
    qid, head = await find_question_by_heading(page, serial_heading)
    if qid:
        sec_id = f"question-{qid}"
        serial = (row.get("Clipper Serial", "") or row.get("If you have a Clipper Card...serial", "")).strip()
        if serial:
            print(f"[fill] {qid} serial => {serial}")
            await fill_text_inputs_in_question(page, sec_id, [serial])
        else:
            print(f"[warn] {qid} expected serial but CSV empty; leaving blank.")
        await click_next(page)
    else:
        print("[skip] Clipper serial page not on this page.")


    # QID10
    fare = get_val(row, 'In which fare category do you belong?', 'In which fare category do you belong?\n')
    if fare:
        await click_radio_by_text(page, "QID10", fare, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    # QID11
    when = get_val(row, 'When were you first issued with a GoPass?')
    if when:
        await select_dropdown_by_text(page, "QID11", when, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    # QID72 (optional)
    serial = get_val(row, 'If you have a Clipper Card...serial', 'Please enter the serial number from your Adult Clipper Card')
    if serial and await page.locator('#question-QID72').count() > 0:
        await fill_text_in_question(page, "QID72", serial, verbose)
        await click_next(page); await do_debug_pause(page, debug_step)

    # QID15
    prior = get_val(row, 'Did you ride Caltrain before having a GoPass?')
    if prior:
        await click_radio_by_text(page, "QID15", prior, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    if prior.lower().startswith('y'):
        # QID63
        prior_ticket = get_val(row, 'What ticket did you typically use prior to the GoPass?')
        if prior_ticket:
            label, other_text = split_other(prior_ticket)
            await click_radio_by_text(page, "QID63", label, verbose)
            if other_text:
                await fill_text_in_question(page, "QID63", other_text, verbose)
        await click_next(page); await do_debug_pause(page, debug_step)

        # QID17
        prior_freq = get_val(row, 'Prior to the GoPass, how often did you ride Caltrain?')
        if prior_freq:
            await click_radio_by_text(page, "QID17", prior_freq, verbose)
        await click_next(page); await do_debug_pause(page, debug_step)

        # QID18
        prior_purpose = get_val(row, 'Prior to the GoPass, what was your most common trip purpose?')
        if prior_purpose:
            label, other_text = split_other(prior_purpose)
            await click_radio_by_text(page, "QID18", label, verbose)
            if other_text:
                await fill_text_in_question(page, "QID18", other_text, verbose)
        await click_next(page); await do_debug_pause(page, debug_step)

        # QID19
        prior_on = get_val(
            row,
            'Prior to the GoPass, which Caltrain stations did you use for your most common trip? ON',
            'Prior to the GoPass, which Caltrain stations did you use for your most common trip? (Boarding Station): The station where you get on the train.'
        )
        if prior_on:
            await select_dropdown_by_text(page, "QID19", prior_on, verbose)
        await click_next(page); await do_debug_pause(page, debug_step)

        # QID79
        prior_off = get_val(row, 'Prior to the GoPass, which Caltrain stations did you use for your most common trip? OFF')
        if prior_off:
            await select_dropdown_by_text(page, "QID79", prior_off, verbose)
        await click_next(page); await do_debug_pause(page, debug_step)

    # AFTER section
    # QID21
    after_purpose = get_val(row, 'After receiving your 2026 GoPass, what will be your most common trip purpose?')
    if after_purpose:
        label, other_text = split_other(after_purpose)
        await click_radio_by_text(page, "QID21", label, verbose)
        if other_text:
            await fill_text_in_question(page, "QID21", other_text, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    # QID22
    after_freq = get_val(row, 'How often do you plan to ride Caltrain after receiving your 2026 GoPass?')
    if after_freq:
        await click_radio_by_text(page, "QID22", after_freq, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    # QID46
    after_on = get_val(row, 'Which Caltrain stations will you use for your most common trip? ON')
    if after_on:
        await select_dropdown_by_text(page, "QID46", after_on, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    # QID80
    after_off = get_val(row, 'Which Caltrain stations will you use for your most common trip? OFF')
    if after_off:
        await select_dropdown_by_text(page, "QID80", after_off, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    # Demographics (optional)
    you_english = get_val(row, 'How well do you speak English?')
    if you_english:
        await click_radio_by_text(page, "QID24", you_english, verbose)
        await click_next(page); await do_debug_pause(page, debug_step)

    home_english = get_val(row, 'In your home, is English spoken:')
    if home_english:
        await click_radio_by_text(page, "QID25", home_english, verbose)
        await click_next(page); await do_debug_pause(page, debug_step)

    langs = get_val(row, 'Which languages are spoken in your home?')
    if langs:
        for val in split_multi(langs):
            await click_checkbox_by_text(page, "QID27", val, verbose)
        await click_next(page); await do_debug_pause(page, debug_step)

    eth = get_val(row, 'Which of the following best describes your race/ethnic background?')
    if eth:
        for val in split_multi(eth):
            await click_checkbox_by_text(page, "QID28", val, verbose)
        await click_next(page); await do_debug_pause(page, debug_step)

    hh = get_val(row, 'Including yourself, how many people live in your household?')
    if hh:
        label, other_text = split_other(hh)
        await click_radio_by_text(page, "QID30", label, verbose)
        if other_text:
            await fill_text_in_question(page, "QID30", other_text, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    income = get_val(row, 'Annual household income (before taxes):')
    if income:
        await click_radio_by_text(page, "QID31", income, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    zipc = get_val(row, 'What is your home ZIP code?')
    if zipc:
        await fill_text_in_question(page, "QID35", zipc, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    email = get_val(row, 'Please enter your organization or personal email address', 'Email')
    if email:
        await fill_text_in_question(page, "QID12", email, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    comms = get_val(row, 'Future communications from Caltrain (optional)').lower()
    if "survey" in comms:
        await click_checkbox_by_text(page, "QID73", "Check this box if you would like to participate in future Caltrain surveys", verbose)
    if "update" in comms or "information" in comms:
        await click_checkbox_by_text(page, "QID73", "Check this box if you would like to receive Caltrain updates and information", verbose)
    await click_next(page); await do_debug_pause(page, debug_step)

    confirm_email = get_val(row, 'Please confirm the email address where you would like to receive communications from Caltrain:', default=email)
    if confirm_email:
        await fill_text_in_question(page, "QID74", confirm_email, verbose)
    await click_next(page); await do_debug_pause(page, debug_step)
