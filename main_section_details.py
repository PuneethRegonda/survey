# main_section_details.py
import asyncio
from playwright.async_api import async_playwright
from helpers_generic import print_section_details

SURVEY_URL = "https://samtranscore.sjc1.qualtrics.com/jfe/form/SV_1Sr8UDzSeUWm20e?RID=CGC_NlYyJUotAxWDit6&Q_CHL=email"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto(SURVEY_URL)
        await page.wait_for_selector('#survey-canvas', timeout=15000)
        print("\nNavigate the survey manually. Press Enter to print section details for the current page. Press Ctrl+C to exit.")
        try:
            while True:
                input("\nPress Enter to print section details for this page...")
                await print_section_details(page)
        except KeyboardInterrupt:
            print("\nExiting...")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
