"""
Script to extract all question sections from the survey page HTML
This will help map section IDs to question types and CSV columns
"""

import asyncio
from playwright.async_api import async_playwright

SURVEY_URL = "https://samtranscore.sjc1.qualtrics.com/jfe/form/SV_1Sr8UDzSeUWm20e?RID=CGC_NlYyJUotAxWDit6&Q_CHL=email"

"""
Script to extract and save question sections to JSON for mapping
Records: Question ID, input elements, dropdown options, button IDs
"""

import asyncio
import json
import datetime
from playwright.async_api import async_playwright

SURVEY_URL = "https://samtranscore.sjc1.qualtrics.com/jfe/form/SV_1Sr8UDzSeUWm20e?RID=CGC_NlYyJUotAxWDit6&Q_CHL=email"
OUTPUT_FILE = "survey_mapping.json"

# Global data structure to store all pages
survey_data = {
    "survey_url": SURVEY_URL,
    "extraction_date": datetime.datetime.now().isoformat(),
    "pages": []
}

async def extract_and_save_page(page, page_number):
    """Extract current page structure and save to JSON"""
    print(f"\n{'='*60}")
    print(f"📄 RECORDING PAGE {page_number}")
    print('='*60)
    
    page_data = {
        "page_number": page_number,
        "questions": [],
        "navigation": {},
        "page_info": {}
    }
    
    # Get page URL
    page_data["page_info"]["url"] = page.url
    
    # Extract all question sections
    question_sections = await page.locator('section.question').all()
    
    if question_sections:
        print(f"📝 Found {len(question_sections)} question(s)")
        
        for i, sec in enumerate(question_sections, 1):
            try:
                question_data = {
                    "question_number": i,
                    "section_id": "",
                    "question_text": "",
                    "css_classes": "",
                    "input_elements": {
                        "radio_buttons": [],
                        "text_inputs": [],
                        "textareas": [],
                        "checkboxes": [],
                        "dropdowns": [],
                        "selects": []
                    },
                    "element_counts": {}
                }
                
                # Get section ID
                sec_id = await sec.get_attribute('id')
                question_data["section_id"] = sec_id or ""
                
                # Get question heading
                heading_element = sec.locator('.question-display')
                if await heading_element.count() > 0:
                    heading = await heading_element.inner_text()
                    question_data["question_text"] = heading.strip()
                
                # Get section classes
                sec_classes = await sec.get_attribute('class')
                question_data["css_classes"] = sec_classes or ""
                
                print(f"   🏷️  Question {i}: {sec_id}")
                print(f"   📋 Text: {question_data['question_text'][:50]}...")
                
                # Extract radio buttons
                radios = await sec.locator('input[type="radio"]').all()
                question_data["element_counts"]["radio_buttons"] = len(radios)
                
                for radio in radios:
                    radio_id = await radio.get_attribute('id')
                    radio_name = await radio.get_attribute('name')
                    radio_value = await radio.get_attribute('value')
                    
                    # Get associated label
                    label_text = ""
                    if radio_id:
                        label = page.locator(f'label[for="{radio_id}"]')
                        if await label.count() > 0:
                            label_text = await label.inner_text()
                    
                    question_data["input_elements"]["radio_buttons"].append({
                        "id": radio_id,
                        "name": radio_name,
                        "value": radio_value,
                        "label": label_text.strip()
                    })
                
                # Extract text inputs
                texts = await sec.locator('input[type="text"]').all()
                question_data["element_counts"]["text_inputs"] = len(texts)
                
                for text in texts:
                    text_id = await text.get_attribute('id')
                    text_name = await text.get_attribute('name')
                    text_placeholder = await text.get_attribute('placeholder')
                    
                    question_data["input_elements"]["text_inputs"].append({
                        "id": text_id,
                        "name": text_name,
                        "placeholder": text_placeholder
                    })
                
                # Extract textareas
                textareas = await sec.locator('textarea').all()
                question_data["element_counts"]["textareas"] = len(textareas)
                
                for textarea in textareas:
                    textarea_id = await textarea.get_attribute('id')
                    textarea_name = await textarea.get_attribute('name')
                    
                    question_data["input_elements"]["textareas"].append({
                        "id": textarea_id,
                        "name": textarea_name
                    })
                
                # Extract checkboxes
                checkboxes = await sec.locator('input[type="checkbox"]').all()
                question_data["element_counts"]["checkboxes"] = len(checkboxes)
                
                for checkbox in checkboxes:
                    checkbox_id = await checkbox.get_attribute('id')
                    checkbox_name = await checkbox.get_attribute('name')
                    checkbox_value = await checkbox.get_attribute('value')
                    
                    # Get associated label
                    label_text = ""
                    if checkbox_id:
                        label = page.locator(f'label[for="{checkbox_id}"]')
                        if await label.count() > 0:
                            label_text = await label.inner_text()
                    
                    question_data["input_elements"]["checkboxes"].append({
                        "id": checkbox_id,
                        "name": checkbox_name,
                        "value": checkbox_value,
                        "label": label_text.strip()
                    })
                
                # Extract custom dropdowns
                dropdowns = await sec.locator('.select-menu').all()
                question_data["element_counts"]["dropdowns"] = len(dropdowns)
                
                for dropdown in dropdowns:
                    dropdown_id = await dropdown.get_attribute('id')
                    dropdown_classes = await dropdown.get_attribute('class')
                    
                    dropdown_data = {
                        "id": dropdown_id,
                        "classes": dropdown_classes,
                        "options": []
                    }
                    
                    # Try to get dropdown options
                    try:
                        await dropdown.click()
                        await page.wait_for_timeout(500)
                        
                        # Look for menu items
                        menu_selector = f'#select-menu-{sec_id.replace("question-", "")}' if sec_id else 'ul[role="listbox"]'
                        menu_items = await page.locator(f'{menu_selector} li[role="option"]').all()
                        
                        for item in menu_items:
                            item_id = await item.get_attribute('id')
                            item_text = await item.inner_text()
                            
                            if item_text.strip() and item_text.strip() != "Select one":
                                dropdown_data["options"].append({
                                    "id": item_id,
                                    "text": item_text.strip()
                                })
                        
                        # Close dropdown
                        await page.keyboard.press('Escape')
                        await page.wait_for_timeout(200)
                        
                    except Exception as e:
                        print(f"   ⚠️  Could not extract dropdown options: {e}")
                    
                    question_data["input_elements"]["dropdowns"].append(dropdown_data)
                
                # Extract regular selects
                selects = await sec.locator('select').all()
                question_data["element_counts"]["selects"] = len(selects)
                
                for select in selects:
                    select_id = await select.get_attribute('id')
                    select_name = await select.get_attribute('name')
                    
                    # Get options
                    options = await select.locator('option').all()
                    option_data = []
                    
                    for option in options:
                        option_value = await option.get_attribute('value')
                        option_text = await option.inner_text()
                        option_data.append({
                            "value": option_value,
                            "text": option_text.strip()
                        })
                    
                    question_data["input_elements"]["selects"].append({
                        "id": select_id,
                        "name": select_name,
                        "options": option_data
                    })
                
                # Print summary
                total_inputs = sum(question_data["element_counts"].values())
                print(f"   📊 Inputs: {total_inputs} total")
                
                survey_data["pages"].append({"questions": [question_data]} if i == 1 else None)
                if i == 1:
                    page_data["questions"].append(question_data)
                else:
                    page_data["questions"].append(question_data)
                
            except Exception as e:
                print(f"   ❌ Error extracting question {i}: {e}")
    
    else:
        print("ℹ️  No questions found - gate/intro page")
        page_data["page_info"]["type"] = "gate_page"
        
        # Get page content for gate pages
        try:
            page_content = await page.locator('#survey-canvas').inner_text()
            page_data["page_info"]["content"] = page_content[:500]  # First 500 chars
        except:
            pass
    
    # Extract navigation buttons
    nav_data = {}
    
    # Next button
    next_button = page.locator('#next-button')
    if await next_button.is_visible():
        nav_data["next_button"] = {
            "id": "next-button",
            "visible": True,
            "text": await next_button.inner_text() if await next_button.count() > 0 else "Next"
        }
    else:
        nav_data["next_button"] = {"visible": False}
    
    # Previous button
    prev_button = page.locator('#previous-button')
    if await prev_button.is_visible():
        nav_data["previous_button"] = {
            "id": "previous-button", 
            "visible": True
        }
    else:
        nav_data["previous_button"] = {"visible": False}
    
    page_data["navigation"] = nav_data
    
    # Add to survey data
    if not survey_data["pages"] or len(survey_data["pages"]) < page_number:
        survey_data["pages"].append(page_data)
    else:
        survey_data["pages"][page_number - 1] = page_data
    
    # Save to JSON file
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(survey_data, f, indent=2, ensure_ascii=False)
        print(f"   💾 Saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"   ❌ Error saving JSON: {e}")
    
    return nav_data.get("next_button", {}).get("visible", False)

async def extract_all_questions():
    """Main function to extract all survey pages"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        print("🔍 Starting JSON survey mapping extraction...")
        print("📋 Fill out the page manually, then press Enter to record the page structure")
        print("🔄 The script will automatically navigate to next page")
        print("⏹️  Type 'quit' to stop extraction")
        print(f"💾 Data will be saved to: {OUTPUT_FILE}\n")
        
        await page.goto(SURVEY_URL)
        await page.wait_for_selector('#survey-canvas', timeout=15000)
        
        page_count = 1
        
        while True:
            print(f"\n{'🔹' * 20}")
            print(f"📄 CURRENT PAGE: {page_count}")
            print(f"📍 URL: {page.url}")
            print('🔹' * 20)
            print("👉 Fill out this page manually, then press Enter to record it...")
            
            # Wait for user input
            user_input = input("\n📝 Press Enter to record this page, or type 'quit' to stop: ").strip().lower()
            
            if user_input == 'quit':
                print("🛑 Extraction stopped by user")
                break
            
            # Extract and save current page
            has_next = await extract_and_save_page(page, page_count)
            
            if has_next:
                print("🔄 Moving to next page...")
                try:
                    next_button = page.locator('#next-button')
                    await next_button.click()
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    page_count += 1
                except Exception as e:
                    print(f"❌ Error navigating to next page: {e}")
                    break
            else:
                print("🏁 No next button found - survey complete or at end")
                
                # Ask if user wants to continue (maybe they need to submit)
                continue_input = input("Continue recording? Press Enter for yes, 'quit' to stop: ").strip().lower()
                if continue_input == 'quit':
                    break
                page_count += 1
        
        await browser.close()
        print(f"\n✅ Survey mapping extraction completed!")
        print(f"📁 Data saved to: {OUTPUT_FILE}")
        
        # Print summary
        print(f"\n📊 SUMMARY:")
        print(f"   Pages recorded: {len(survey_data['pages'])}")
        total_questions = sum(len(page.get('questions', [])) for page in survey_data['pages'])
        print(f"   Total questions: {total_questions}")
        print(f"   Output file: {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(extract_all_questions())