# helpers_ack.py
async def force_ack_gopass(page):
    sec = page.locator('#question-QID4')
    if not await sec.count():
        print("[ack] QID4 not on page.")
        return False

    await sec.scroll_into_view_if_needed()

    # BEFORE: see if it's already checked
    inp = sec.locator('input[type="radio"]').first
    before = await inp.is_checked() if await inp.count() else False
    print(f"[ack] before checked => {before}")

    # 1) Try the visible label
    lab = sec.locator('label:has-text("I certify")')
    if await lab.count():
        try:
            await lab.first.click()
        except:
            pass

    # 2) Try the stylized circle
    if not (await inp.is_checked() if await inp.count() else False):
        circle = sec.locator('.radio-button.radio').first
        if await circle.count():
            try:
                await circle.click()
            except:
                pass

    # 3) Directly check the input + dispatch events
    if not (await inp.is_checked() if await inp.count() else False) and await inp.count():
        try:
            await inp.check(force=True)
            # dispatch change/input so Qualtrics registers it
            await page.evaluate(
                """(el)=>{
                    el.dispatchEvent(new Event('input',{bubbles:true}));
                    el.dispatchEvent(new Event('change',{bubbles:true}));
                }""",
                await inp.element_handle(),
            )
        except:
            pass

    after = await inp.is_checked() if await inp.count() else False
    print(f"[ack] after checked  => {after}")
    return after
