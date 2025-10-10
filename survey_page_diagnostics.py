# survey_page_diagnostics.py
import asyncio
from playwright.async_api import async_playwright

SURVEY_URL = "https://samtranscore.sjc1.qualtrics.com/jfe/form/SV_1Sr8UDzSeUWm20e?RID=CGC_NlYyJUotAxWDit6&Q_CHL=email"

def norm(s):
    return " ".join((s or "").split()).strip()

async def print_page_details(page):
    question_sections = await page.locator("section.question").all()
    print("\n--- Survey Page Diagnostics ---")
    if not question_sections:
        print("No survey questions found on this page.")
        return
    for sec in question_sections:
        sec_id = await sec.get_attribute("id")
        heading = await sec.locator(".question-display").inner_text()
        print(f"Section ID: {sec_id}")
        print(f"Heading: {norm(heading)[:120]}")
        # Radios
        radios = await sec.locator('input[type="radio"]').all()
        if radios:
            print("  Radio choices:")
            for idx, r in enumerate(radios):
                label = await r.evaluate("el => el.parentElement.innerText")
                print(f"    [{idx}] {norm(label)}")
        # Checkboxes
        checkboxes = await sec.locator('input[type="checkbox"]').all()
        if checkboxes:
            print("  Checkbox choices:")
            for idx, c in enumerate(checkboxes):
                label = await c.evaluate("el => el.parentElement.innerText")
                print(f"    [{idx}] {norm(label)}")
        # Text inputs
        texts = await sec.locator('input[type="text"]').all()
        if texts:
            print(f"  Text inputs: {len(texts)}")
        # Dropdowns
        selects = await sec.locator('select').all()
        if selects:
            print(f"  Dropdowns: {len(selects)}")
        print("--- End Diagnostics ---\n")
    print("========================\n")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto(SURVEY_URL)
        await page.wait_for_selector('#survey-canvas', timeout=15000)
        print("Navigate the survey manually. Press Enter to print page details. Press Ctrl+C to exit.")
        try:
            while True:
                input("\nPress Enter to print details for this page...")
                await print_page_details(page)
        except KeyboardInterrupt:
            print("Exiting...")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
