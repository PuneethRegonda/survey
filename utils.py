# utils.py
import asyncio
from playwright.async_api import TimeoutError as PlaywrightTimeout

def get_val(row, *possible_headers, default=""):
    """Return the first non-empty value from the given header list."""
    for h in possible_headers:
        if h in row and str(row[h]).strip():
            return str(row[h]).strip()
    return default

def split_multi(val: str):
    """Split multi-select CSV values on common delimiters."""
    if not isinstance(val, str):
        return []
    s = val.strip()
    if not s:
        return []
    # normalize to semicolons then split
    for d in ["|", ","]:
        s = s.replace(d, ";")
    return [v.strip() for v in s.split(";") if v.strip()]

def split_other(label: str):
    """
    If a value starts with 'Other' and includes a colon, return ('Other (please specify):', 'text').
    Else return (label, '') untouched.
    """
    if not isinstance(label, str):
        return label, ""
    low = label.lower().strip()
    if low.startswith("other"):
        parts = label.split(":", 1)
        other_text = parts[1].strip() if len(parts) > 1 else ""
        return "Other (please specify):", other_text
    return label, ""

async def debug_dump(page):
    """Print what the page currently shows: question IDs, texts, first few choices, next button presence."""
    try:
        # All visible question blocks
        qroots = page.locator('section.question')
        count = await qroots.count()
        print("\n=== DEBUG: Visible questions on page ===========================")
        print(f"Count: {count}")
        for i in range(count):
            q = qroots.nth(i)
            try:
                qid = await q.get_attribute("id")  # e.g. 'question-QID10'
            except:
                qid = "question-<?>"
            textloc = q.locator('.question-display.rich-text')
            qtext = (await textloc.first.text_content() or "").strip()
            print(f"- {qid}: {qtext[:300].replace('\\n',' ')}")
            # show the first few choice labels if any
            labels = q.locator("label .display-with-image-display.rich-text")
            for j in range(min(await labels.count(), 5)):
                t = (await labels.nth(j).text_content() or "").strip()
                print(f"    • choice: {t[:200]}")
        print("----------------------------------------------------------------")
        nb = page.locator("#next-button")
        print(f"Next button visible: {await nb.is_visible() if await nb.count() else False}")
        print("================================================================\n")
    except Exception as e:
        print(f"[debug_dump] error: {e}")

async def prompt_yes_to_continue():
    """Pause for manual step. Continue only if user enters 'y' or 'Y'."""
    loop = asyncio.get_running_loop()
    ans = await loop.run_in_executor(None, lambda: input("Press 'y' to continue, anything else to quit: ").strip().lower())
    return ans == "y"

async def click_next(page):
    """Click Next and wait a beat for transitions."""
    await page.locator("#next-button").click()
    await page.wait_for_timeout(300)
    try:
        await page.wait_for_load_state("networkidle", timeout=3000)
    except PlaywrightTimeout:
        pass

async def advance_if_gate_or_welcome(page, verbose=True):
    """
    Handle the optional 'confirm-start' gate and the 'Welcome' page (QID66).
    """
    if verbose: print("[seek] confirm-start gate")
    try:
        await page.wait_for_selector('#confirm-start-message', timeout=1200)
        if verbose: print("[hit ] confirm-start gate → Next")
        await click_next(page)
    except PlaywrightTimeout:
        if verbose: print("[miss] confirm-start gate")

    if verbose: print("[seek] Welcome page (QID66)")
    try:
        if await page.locator('#question-QID66').count() > 0:
            if verbose: print("[hit ] Welcome page → Next")
            await click_next(page)
            return
        if verbose: print("[miss] Welcome page")
    except Exception:
        pass

    # Safety: if Next is visible and first real question isn't, try one extra Next
    if verbose: print("[seek] safety extra Next if stuck before first question")
    try:
        if await page.locator('#next-button').count() > 0 and await page.locator('#question-QID10').count() == 0:
            if verbose: print("[hit ] safety Next")
            await click_next(page)
    except Exception:
        pass
