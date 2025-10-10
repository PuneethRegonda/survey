# main.py
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from helpers_generic import debug_dump
from processor import process_page

SURVEY_URL = "https://samtranscore.sjc1.qualtrics.com/jfe/form/SV_1Sr8UDzSeUWm20e?RID=CGC_NlYyJUotAxWDit6&Q_CHL=email"
CSV_PATH   = "./data.csv"

async def click_next(page):
    if await page.locator("#next-button").is_visible():
        await page.click("#next-button")
        await page.wait_for_load_state("networkidle")

async def pass_gate_if_present(page):
    # handles confirm-start or welcome-only pages where nothing matches our map
    await click_next(page)

async def fill_one(page, row):
    await page.goto(SURVEY_URL)
    await page.wait_for_selector('#survey-canvas', timeout=15000)

    for step in range(0, 80):  # hard stop to avoid infinite loops
        await debug_dump(page, note=f"STEP {step}")
        handled = await process_page(page, row)
        if handled:
            await click_next(page)
        else:
            # maybe a welcome/gate/thanks page—advance
            await pass_gate_if_present(page)

        # you can break if you detect a terminal “Thank you” message
        if await page.locator("text=Thank you").first.is_visible():
            print("[done] Thank you page.")
            break

# main.py (only the fill_one function shown)
async def page_signature(page):
    try:
        qs = await page.locator("section.question .question-display").all_inner_texts()
        return " || ".join([s.strip() for s in qs])
    except:
        return ""

async def click_next(page):
    if await page.locator("#next-button").is_visible():
        await page.click("#next-button")
        await page.wait_for_load_state("networkidle")

async def pass_gate_if_present(page):
    await click_next(page)

async def fill_one(page, row):
    await page.goto(SURVEY_URL)
    await page.wait_for_selector('#survey-canvas', timeout=15000)

    prev_sig = ""
    stuck_ticks = 0

    for step in range(0, 120):
        sig = await page_signature(page)
        await debug_dump(page, note=f"STEP {step}")

        handled = await process_page(page, row)
        await click_next(page) if handled else await pass_gate_if_present(page)

        # detect thanks
        if await page.locator("text=Thank you").first.is_visible():
            print("[done] Thank you page.")
            break

        new_sig = await page_signature(page)
        if new_sig == sig:
            stuck_ticks += 1
        else:
            stuck_ticks = 0

        if stuck_ticks >= 3:
            print("[WARN] Page did not change after 3 attempts. Stopping to avoid infinite loop.")
            break



async def main():
    df = pd.read_csv(CSV_PATH).fillna("")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        for i, row in df.iterrows():
            print(f"\n================= START ROW {i} =================")
            await fill_one(page, row)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
