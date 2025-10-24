"""
Simple script to extract current page question structure
"""

import asyncio
from playwright.async_api import async_playwright

SURVEY_URL = "https://samtranscore.sjc1.qualtrics.com/jfe/form/SV_1Sr8UDzSeUWm20e?RID=CGC_NlYyJUotAxWDit6&Q_CHL=email"

async def extract_current_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        print("Opening survey page...")
        await page.goto(SURVEY_URL)
        await page.wait_for_selector('#survey-canvas', timeout=15000)
        
        print("\n" + "="*80)
        print("EXTRACTING QUESTION STRUCTURE FROM CURRENT PAGE")
        print("="*80)
        
        # Extract all question sections
        question_sections = await page.locator('section.question').all()
        
        if question_sections:
            print(f"\nFound {len(question_sections)} question section(s):\n")
            
            for i, sec in enumerate(question_sections, 1):
                try:
                    # Get section ID
                    sec_id = await sec.get_attribute('id')
                    
                    # Get question heading  
                    heading_element = sec.locator('.question-display')
                    heading = await heading_element.inner_text() if await heading_element.count() > 0 else "No heading"
                    
                    # Get section classes
                    sec_classes = await sec.get_attribute('class')
                    
                    print(f"QUESTION {i}:")
                    print(f"  Section ID: {sec_id}")
                    print(f"  CSS Classes: {sec_classes}")
                    print(f"  Question Text: {heading.strip()}")
                    
                    # Detect input types
                    radios = await sec.locator('input[type="radio"]').count()
                    texts = await sec.locator('input[type="text"]').count()
                    textareas = await sec.locator('textarea').count()
                    checkboxes = await sec.locator('input[type="checkbox"]').count()
                    selects = await sec.locator('select').count()
                    dropdowns = await sec.locator('.select-menu').count()
                    
                    print(f"  Input Types:")
                    print(f"    - Radio buttons: {radios}")
                    print(f"    - Text inputs: {texts}")
                    print(f"    - Text areas: {textareas}")
                    print(f"    - Checkboxes: {checkboxes}")
                    print(f"    - Select dropdowns: {selects}")
                    print(f"    - Custom dropdowns: {dropdowns}")
                    
                    # Get HTML structure
                    html = await sec.inner_html()
                    print(f"  HTML Preview: {html[:200]}...")
                    
                    print("-" * 60)
                    
                except Exception as e:
                    print(f"Error extracting question {i}: {e}")
        else:
            print("No question sections found. This might be a gate/intro page.")
            page_content = await page.locator('#survey-canvas').inner_text()
            print(f"Page content: {page_content[:300]}...")
        
        print("\nPage analysis complete. Browser will stay open for 30 seconds...")
        await page.wait_for_timeout(30000)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(extract_current_page())