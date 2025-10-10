async def handle_gate_page(page):
    print("[PAGE] Gate/Optional Page: Just clicking Next.")
    # Just click Next for gate/optional pages
    if await page.locator('#next-button').is_visible():
        await page.click('#next-button')
        await page.wait_for_load_state('networkidle')

async def handle_acknowledgement_page(page):
    print("[PAGE] GoPass Use Acknowledgement Page: Selecting required radio.")
    sec = page.locator('#question-QID4')
    # Print section ID, heading, and raw HTML
    sec_id = 'question-QID4'
    heading = await sec.locator('.question-display').inner_text()
    html = await sec.inner_html()
    print(f"[DIAGNOSTIC] Section ID: {sec_id}")
    print(f"[DIAGNOSTIC] Heading: {heading.strip()}")
    print(f"[DIAGNOSTIC] Raw HTML:\n{html}\n")
    # Wait 3 seconds to ensure page is fully loaded
    await page.wait_for_timeout(3000)
    radio = sec.locator('input[type="radio"]')
    radio_count = await radio.count()
    if radio_count > 0:
        try:
            checked = await radio.first.is_checked()
            print(f"Radio checked state before: {checked}")
            if not checked:
                try:
                    await radio.first.check(force=True)
                    print("Radio checked.")
                except Exception as e:
                    print(f"Error checking radio: {e}")
            else:
                print("Radio already selected, skipping .check()")
            checked_after = await radio.first.is_checked()
            print(f"Radio checked state after: {checked_after}")
        except Exception as e:
            print(f"[ERROR] Could not check radio: {e}")
    else:
        print("[WARNING] No radio input found on acknowledgement page!")
    # Sleep before clicking Next
    await page.wait_for_timeout(500)
    if await page.locator('#next-button').is_visible():
        await page.click('#next-button')
        await page.wait_for_load_state('networkidle')

async def handle_user_name_page(page, row):
    print("[PAGE] GoPass User Name Page: Filling First, Middle, Last Name.")
    sec = page.locator('#question-QID9')
    # Print section ID, heading, and raw HTML
    sec_id = 'question-QID9'
    heading = await sec.locator('.question-display').inner_text()
    html = await sec.inner_html()
    print(f"[DIAGNOSTIC] Section ID: {sec_id}")
    print(f"[DIAGNOSTIC] Heading: {heading.strip()}")
    print(f"[DIAGNOSTIC] Raw HTML:\n{html}\n")
    # Extract and print name data from CSV
    first_name = row.get('First Name', '')
    middle_name = row.get('Middle Name', '')
    last_name = row.get('Last Name', '')
    print(f"[DATA] First Name: {first_name}")
    print(f"[DATA] Middle Name: {middle_name}")
    print(f"[DATA] Last Name: {last_name}")
    # Fill First Name, Middle Name, Last Name by input IDs using type() to trigger events
    input1 = sec.locator('#form-text-input-QID9-1')
    input2 = sec.locator('#form-text-input-QID9-2')
    input3 = sec.locator('#form-text-input-QID9-3')
    
    # Clear and type first name with retry logic
    await input1.click()
    await input1.clear()
    await page.wait_for_timeout(100)
    await input1.type(str(first_name), delay=80)
    # Verify it was typed correctly
    value1 = await input1.input_value()
    print(f"First name typed: '{value1}', expected: '{first_name}'")
    if value1 != str(first_name):
        print("[RETRY] First name not typed correctly, retrying...")
        await input1.clear()
        await input1.fill(str(first_name))
    await page.keyboard.press('Tab')
    await page.wait_for_timeout(300)
    
    # Clear and type middle name
    await input2.click()
    await input2.clear()
    await page.wait_for_timeout(100)
    await input2.type(str(middle_name), delay=80)
    await page.keyboard.press('Tab')
    await page.wait_for_timeout(300)
    
    # Clear and type last name
    await input3.click()
    await input3.clear()
    await page.wait_for_timeout(100)
    await input3.type(str(last_name), delay=80)
    await page.keyboard.press('Tab')
    await page.wait_for_timeout(300)
    
    # Extra blur by clicking outside and wait for validation
    await page.mouse.click(10, 10)
    await page.wait_for_timeout(800)
    # Extra blur/click outside and wait for validation
    await page.wait_for_timeout(800)
    # Check for error messages before clicking Next
    error_locators = page.locator('.error-message')
    error_count = await error_locators.count()
    error_visible = False
    for i in range(error_count):
        if await error_locators.nth(i).is_visible():
            error_visible = True
            break
    # Define inputs for error handling
    inputs = [sec.locator('#form-text-input-QID9-1'), sec.locator('#form-text-input-QID9-2'), sec.locator('#form-text-input-QID9-3')]
    if error_visible:
        print("[ERROR] Validation error detected on user name page! Trying to refocus and blur...")
        for inp in inputs:
            await inp.focus()
            await page.wait_for_timeout(200)
            await page.mouse.click(10, 10)
            await page.wait_for_timeout(400)
        # Wait again for validation
        await page.wait_for_timeout(1000)
        # Recheck error messages
        error_visible = False
        for i in range(error_count):
            if await error_locators.nth(i).is_visible():
                error_visible = True
                break
        if error_visible:
            print("[ERROR] Validation error still present after refocus/blur!")
    # Click Next
    if await page.locator('#next-button').is_visible():
        await page.click('#next-button')
        await page.wait_for_load_state('networkidle')

async def handle_clipper_serial_page(page, row):
    print("[PAGE] Clipper Card Serial Number Page: Filling serial number from CSV.")
    sec = page.locator('#question-QID72')
    sec_id = 'question-QID72'
    
    # Wait for section to be fully loaded
    try:
        await sec.wait_for(state='visible', timeout=5000)
    except Exception as e:
        print(f"[ERROR] Section not visible: {e}")
        return
    
    heading = await sec.locator('.question-display').inner_text()
    print(f"[DIAGNOSTIC] Section ID: {sec_id}")
    print(f"[DIAGNOSTIC] Heading: {heading.strip()}")
    
    # Get value from CSV - try multiple possible column names
    possible_cols = [
        'If you have a Clipper Card, please enter the ten digital serial number from your Adult Clipper Card. This is required if you have a Clipper Card. ',
        'Clipper Card Serial Number',
        'Serial Number',
        'Clipper Serial'
    ]
    value = ''
    found_col = None
    for col in possible_cols:
        if col in row and str(row[col]).strip():
            value = str(row[col]).strip()
            found_col = col
            break
    
    print(f"[DATA] CSV Serial Number: {value}")
    print(f"[DATA] Found in column: {found_col}")
    print(f"[DATA] Available CSV columns: {list(row.keys())}")
    
    if not value:
        print("[WARNING] No serial number found in CSV data!")
        # Use a default value or skip
        value = "1234567890"  # Default for testing
        print(f"[DEFAULT] Using default serial number: {value}")
    
    # Wait for page to settle
    await page.wait_for_timeout(1000)
    
    # Find text inputs with multiple fallback methods
    text_input = None
    input_methods = [
        sec.locator('input[type="text"]'),
        sec.locator('input[data-automation-id="textEntry"]'),
        sec.locator('textarea'),
        sec.locator('input:not([type="radio"]):not([type="checkbox"]):not([type="submit"]):not([type="button"])')
    ]
    
    for method in input_methods:
        try:
            if await method.count() > 0:
                text_input = method.first
                print(f"Found text input using method: {method}")
                break
        except Exception as e:
            print(f"Input detection method failed: {e}")
    
    if not text_input:
        print("[ERROR] No text input found on serial number page!")
        return
    
    try:
        # Wait for input to be ready
        await text_input.wait_for(state='visible', timeout=3000)
        
        # Click, clear, and type the serial number
        await text_input.click(timeout=3000)
        await text_input.clear()
        await page.wait_for_timeout(200)
        await text_input.type(str(value), delay=80)
        
        # Verify it was typed correctly
        typed_value = await text_input.input_value()
        print(f"Serial number typed: '{typed_value}', expected: '{value}'")
        
        if typed_value != str(value):
            print("[RETRY] Serial number not typed correctly, retrying with .fill()...")
            await text_input.clear()
            await text_input.fill(str(value))
            # Verify again
            typed_value = await text_input.input_value()
            print(f"After retry: '{typed_value}'")
        
        # Press Tab to blur and trigger validation
        await page.keyboard.press('Tab')
        await page.wait_for_timeout(300)
        
        # Extra blur by clicking outside
        await page.mouse.click(10, 10)
        await page.wait_for_timeout(500)
        
        print("Serial number filled successfully.")
        
    except Exception as e:
        print(f"[ERROR] Could not fill serial number: {e}")
        # Try a simple fill as last resort
        try:
            await text_input.fill(str(value))
            print("Used simple fill as fallback.")
        except Exception as e2:
            print(f"[ERROR] Even fallback fill failed: {e2}")
    
    # Click Next
    if await page.locator('#next-button').is_visible():
        await page.click('#next-button')
        await page.wait_for_load_state('networkidle')

async def handle_fare_category_page(page, row):
    print("[PAGE] Fare Category Page: Selecting fare category based on CSV.")
    sec = page.locator('#question-QID10')
    sec_id = 'question-QID10'
    heading = await sec.locator('.question-display').inner_text()
    html = await sec.inner_html()
    print(f"[DIAGNOSTIC] Section ID: {sec_id}")
    print(f"[DIAGNOSTIC] Heading: {heading.strip()}")
    print(f"[DIAGNOSTIC] Raw HTML:\n{html}\n")
    
    # Get value from CSV - try multiple possible column names
    possible_cols = [
        'In which fare category do you belong?\n',
        'In which fare category do you belong?',
        'Fare Category',
        'Category',
        'Age Category'
    ]
    value = ''
    found_col = None
    for col in possible_cols:
        if col in row and str(row[col]).strip():
            value = str(row[col]).strip().lower()
            found_col = col
            break
    
    print(f"[DATA] CSV Fare Category: {value}")
    print(f"[DATA] Found in column: {found_col}")
    
    # Wait 1 second for page to settle
    await page.wait_for_timeout(1000)
    
    # Get all radio options and their labels to find the best match
    radio_labels = sec.locator('label')
    label_count = await radio_labels.count()
    options = []
    
    for i in range(label_count):
        try:
            label_text = await radio_labels.nth(i).inner_text()
            input_id = await radio_labels.nth(i).get_attribute('for')
            if input_id and 'mc-choice-input-QID10' in input_id:
                options.append({'text': label_text.strip(), 'id': f'#{input_id}'})
        except:
            continue
    
    print(f"[DIAGNOSTIC] Available options: {[opt['text'] for opt in options]}")
    
    # Try to find the best match in available options
    best_match = None
    if value:
        # First try exact or partial matches
        for opt in options:
            opt_text = opt['text'].lower()
            if value in opt_text or opt_text in value:
                best_match = opt
                print(f"[MATCH] Found match: '{value}' matches '{opt['text']}'")
                break
        
        # If no direct match, try keyword matching
        if not best_match:
            if any(word in value for word in ['youth', '18', 'young']):
                best_match = next((opt for opt in options if 'youth' in opt['text'].lower() or '18' in opt['text']), None)
            elif any(word in value for word in ['adult', '19', '64']):
                best_match = next((opt for opt in options if 'adult' in opt['text'].lower()), None)
            elif any(word in value for word in ['senior', '65', 'older']):
                best_match = next((opt for opt in options if 'senior' in opt['text'].lower() or '65' in opt['text']), None)
            elif any(word in value for word in ['disabled', 'disability']):
                best_match = next((opt for opt in options if 'disabled' in opt['text'].lower()), None)
            elif 'medicare' in value:
                best_match = next((opt for opt in options if 'medicare' in opt['text'].lower()), None)
            
            if best_match:
                print(f"[KEYWORD_MATCH] Found keyword match: '{value}' → '{best_match['text']}'")
    
    # If still no match, use "Other" option or default to first option
    if not best_match:
        other_option = next((opt for opt in options if 'other' in opt['text'].lower()), None)
        if other_option and value:  # Only use "Other" if there's a value to fill
            best_match = other_option
            print(f"[OTHER] Using 'Other' option for unmatched value: '{value}'")
        else:
            # Default to Adult if available, otherwise first option
            best_match = next((opt for opt in options if 'adult' in opt['text'].lower()), options[0] if options else None)
            print(f"[DEFAULT] No match found, using default: '{best_match['text'] if best_match else 'None'}'")
    
    if not best_match:
        print("[ERROR] No options found on the page!")
        return
    
    radio_id = best_match['id']
    print(f"[SELECTION] Selecting: '{best_match['text']}' (ID: {radio_id})")
    
    try:
        radio = sec.locator(radio_id)
        # Check if radio is already selected
        parent_div = page.locator(f'label[for="{radio_id.replace("#", "")}"]').locator('..')
        is_selected = await parent_div.locator('.selected').count() > 0
        print(f"Radio selected state (by CSS): {is_selected}")
        
        if not is_selected:
            await radio.check(force=True)
            print("Radio checked successfully.")
        else:
            print("Radio already selected, skipping .check()")
            
        # If "Other" is selected and there's additional text, fill it
        if 'other' in best_match['text'].lower() and value:
            text_input = sec.locator(f'label[for="{radio_id.replace("#", "")}"] input[type="text"]')
            if await text_input.count() > 0:
                await text_input.click()
                await text_input.clear()
                await text_input.type(value, delay=80)
                print(f"Filled 'Other' text field with: {value}")
                
    except Exception as e:
        print(f"[ERROR] Could not select fare category: {e}")
        # Fallback: click the label
        try:
            await page.locator(f'label[for="{radio_id.replace("#", "")}"]').click()
            print("Clicked radio label as fallback.")
        except Exception as e2:
            print(f"[ERROR] Fallback click also failed: {e2}")
    
    # Wait before clicking Next
    await page.wait_for_timeout(500)
    if await page.locator('#next-button').is_visible():
        await page.click('#next-button')
        await page.wait_for_load_state('networkidle')

async def handle_generic_page(page, row):
    # Handles any page with visible question sections, prints diagnostics, and fills inputs based on CSV mapping
    question_sections = await page.locator("section.question").all()
    if not question_sections:
        print("[GENERIC] No question sections found.")
        return
    for sec in question_sections:
        sec_id = await sec.get_attribute("id")
        heading = await sec.locator(".question-display").inner_text()
        html = await sec.inner_html()
        print(f"[GENERIC] Section ID: {sec_id}")
        print(f"[GENERIC] Heading: {heading.strip()}")
        print(f"[GENERIC] Raw HTML:\n{html}\n")
        # Find best matching CSV column for this heading
        csv_columns = list(row.keys())
        best_match = difflib.get_close_matches(heading, csv_columns, n=1, cutoff=0.5)
        value = None
        if best_match:
            col = best_match[0]
            value = row.get(col, "")
        print(f"[GENERIC] CSV Value: {value}")
        # Detect input types
        radios = sec.locator('input[type="radio"]')
        texts = sec.locator('input[type="text"]')
        checkboxes = sec.locator('input[type="checkbox"]')
        # For radio
        if await radios.count() > 0:
            radio_labels = sec.locator('label')
            label_texts = [await radio_labels.nth(i).inner_text() for i in range(await radio_labels.count())]
            selected_index = None
            for i, label in enumerate(label_texts):
                if value and value.lower() in label.lower():
                    selected_index = i
                    break
            if selected_index is not None:
                try:
                    checked = await radios.nth(selected_index).is_checked()
                    print(f"[GENERIC] Radio checked state before: {checked}")
                    if not checked:
                        await radios.nth(selected_index).check(force=True)
                        print(f"[GENERIC] Radio checked for label: {label_texts[selected_index]}")
                    else:
                        print("[GENERIC] Radio already selected, skipping .check()")
                    checked_after = await radios.nth(selected_index).is_checked()
                    print(f"[GENERIC] Radio checked state after: {checked_after}")
                except Exception as e:
                    print(f"[GENERIC][ERROR] Could not check radio: {e}")
            else:
                print(f"[GENERIC][WARNING] Could not match CSV value '{value}' to any radio label!")
        # For text
        if await texts.count() > 0:
            for i in range(await texts.count()):
                fill_val = str(value) if i == 0 and value else ""
                await texts.nth(i).fill(fill_val)
        # For checkbox
        if await checkboxes.count() > 0:
            for i in range(await checkboxes.count()):
                if value and not await checkboxes.nth(i).is_checked():
                    await checkboxes.nth(i).check(force=True)
                elif not await checkboxes.nth(i).is_checked():
                    await checkboxes.nth(i).check(force=True)
    # Click Next
    if await page.locator('#next-button').is_visible():
        await page.click('#next-button')
        await page.wait_for_load_state('networkidle')

async def handle_caltrain_before_gopass_page(page, row):
    print("[PAGE] Caltrain Before GoPass Page: Selecting Yes/No based on CSV.")
    sec = page.locator('#question-QID15')
    sec_id = 'question-QID15'
    
    # Wait for section to be fully loaded
    try:
        await sec.wait_for(state='visible', timeout=5000)
    except Exception as e:
        print(f"[ERROR] Section not visible: {e}")
        return
    
    heading = await sec.locator('.question-display').inner_text()
    print(f"[DIAGNOSTIC] Section ID: {sec_id}")
    print(f"[DIAGNOSTIC] Heading: {heading.strip()}")
    
    # Get value from CSV - try multiple possible column names
    possible_cols = [
        'Did you ride Caltrain before having a GoPass?',
        'Caltrain Before GoPass',
        'Rode Caltrain Before',
        'Caltrain Usage Before GoPass'
    ]
    value = ''
    found_col = None
    for col in possible_cols:
        if col in row and str(row[col]).strip():
            value = str(row[col]).strip().lower()
            found_col = col
            break
    
    print(f"[DATA] CSV Caltrain Before GoPass: {value}")
    print(f"[DATA] Found in column: {found_col}")
    
    # Wait for page to settle and detect available radios
    await page.wait_for_timeout(1000)
    
    # First, check what radio options are actually available
    all_radios = sec.locator('input[type="radio"]')
    radio_count = await all_radios.count()
    print(f"[DIAGNOSTIC] Found {radio_count} radio buttons")
    
    if radio_count == 0:
        print("[ERROR] No radio buttons found on this page!")
        return
    
    # Get all radio IDs and labels
    radio_info = []
    for i in range(radio_count):
        try:
            radio_id = await all_radios.nth(i).get_attribute('id')
            label = page.locator(f'label[for="{radio_id}"]')
            label_text = await label.inner_text() if await label.count() > 0 else f"Radio {i+1}"
            radio_info.append({'id': radio_id, 'text': label_text.strip()})
        except Exception as e:
            print(f"[WARNING] Could not get info for radio {i}: {e}")
    
    print(f"[DIAGNOSTIC] Available radios: {radio_info}")
    
    # Determine which radio to select based on CSV value
    target_radio = None
    if value:
        if 'yes' in value or 'y' == value or 'true' in value or '1' == value:
            # Look for Yes option
            target_radio = next((r for r in radio_info if 'yes' in r['text'].lower()), radio_info[0] if radio_info else None)
            print("[SELECTION] Looking for 'Yes' option")
        elif 'no' in value or 'n' == value or 'false' in value or '0' == value:
            # Look for No option
            target_radio = next((r for r in radio_info if 'no' in r['text'].lower()), radio_info[1] if len(radio_info) > 1 else radio_info[0] if radio_info else None)
            print("[SELECTION] Looking for 'No' option")
        else:
            # Try partial matching
            for radio in radio_info:
                if value in radio['text'].lower() or radio['text'].lower() in value:
                    target_radio = radio
                    print(f"[SELECTION] Found partial match: '{value}' ~ '{radio['text']}'")
                    break
    
    # Default to first option if no match found
    if not target_radio:
        target_radio = radio_info[0] if radio_info else None
        print(f"[DEFAULT] No match found, using default: '{target_radio['text'] if target_radio else 'None'}'")
    
    if not target_radio:
        print("[ERROR] Could not determine target radio!")
        return
    
    print(f"[SELECTION] Selecting: '{target_radio['text']}' (ID: {target_radio['id']})")
    
    # Try multiple selection methods
    success = False
    
    # Method 1: Direct radio check with timeout
    try:
        radio_element = sec.locator(f'#{target_radio["id"]}')
        await radio_element.wait_for(state='visible', timeout=3000)
        
        # Check if already selected
        is_checked = await radio_element.is_checked()
        print(f"Radio checked state: {is_checked}")
        
        if not is_checked:
            await radio_element.check(force=True, timeout=3000)
            print("Radio checked successfully via .check()")
        else:
            print("Radio already selected, skipping")
        success = True
        
    except Exception as e:
        print(f"[WARNING] Method 1 failed: {e}")
    
    # Method 2: Click the label
    if not success:
        try:
            label_element = page.locator(f'label[for="{target_radio["id"]}"]')
            await label_element.wait_for(state='visible', timeout=3000)
            await label_element.click(timeout=3000)
            print("Radio selected via label click")
            success = True
        except Exception as e:
            print(f"[WARNING] Method 2 failed: {e}")
    
    # Method 3: Click the radio directly
    if not success:
        try:
            radio_element = sec.locator(f'#{target_radio["id"]}')
            await radio_element.click(force=True, timeout=3000)
            print("Radio selected via direct click")
            success = True
        except Exception as e:
            print(f"[WARNING] Method 3 failed: {e}")
    
    if not success:
        print("[ERROR] All selection methods failed!")
    
    # Wait before clicking Next
    await page.wait_for_timeout(500)
    if await page.locator('#next-button').is_visible():
        await page.click('#next-button')
        await page.wait_for_load_state('networkidle')

async def handle_gopass_issuance_page(page, row):
    print("[PAGE] GoPass Issuance Date Page: Selecting from dropdown based on CSV.")
    sec = page.locator('#question-QID11')
    sec_id = 'question-QID11'
    
    # Wait for section to be fully loaded
    try:
        await sec.wait_for(state='visible', timeout=5000)
    except Exception as e:
        print(f"[ERROR] Section not visible: {e}")
        return
    
    heading = await sec.locator('.question-display').inner_text()
    print(f"[DIAGNOSTIC] Section ID: {sec_id}")
    print(f"[DIAGNOSTIC] Heading: {heading.strip()}")
    
    # Get value from CSV - try multiple possible column names
    possible_cols = [
        'When were you first issued with a GoPass?\n\nSelect "First time GoPass user" if this is the first time you have been issued with a GoPass.',
        'When were you first issued with a GoPass?',
        'GoPass Issuance Date',
        'First GoPass Date',
        'GoPass Year'
    ]
    value = ''
    found_col = None
    for col in possible_cols:
        if col in row and str(row[col]).strip():
            value = str(row[col]).strip().lower()
            found_col = col
            break
    
    print(f"[DATA] CSV GoPass Issuance: {value}")
    print(f"[DATA] Found in column: {found_col}")
    
    # Wait for page to settle
    await page.wait_for_timeout(1000)
    
    # Find the dropdown menu button and click to open it
    dropdown_button = sec.locator('.select-menu.menu-button')
    
    try:
        await dropdown_button.wait_for(state='visible', timeout=3000)
        print("[DROPDOWN] Opening dropdown menu...")
        await dropdown_button.click(timeout=3000)
        await page.wait_for_timeout(500)  # Wait for dropdown to expand
        
        # Get all available options from the dropdown
        dropdown_menu = page.locator('#select-menu-QID11')
        menu_items = dropdown_menu.locator('li.menu-item:not(.selected)')  # Exclude the "Select one" item
        
        option_count = await menu_items.count()
        print(f"[DIAGNOSTIC] Found {option_count} dropdown options")
        
        # Get all option texts and IDs
        options = []
        for i in range(option_count):
            try:
                item = menu_items.nth(i)
                option_text = await item.locator('.rich-text').inner_text()
                option_id = await item.get_attribute('id')
                options.append({'text': option_text.strip(), 'id': option_id, 'element': item})
            except Exception as e:
                print(f"[WARNING] Could not get option {i}: {e}")
        
        print(f"[DIAGNOSTIC] Available options: {[opt['text'] for opt in options]}")
        
        # Find the best match
        best_match = None
        if value:
            # First try exact matches
            for opt in options:
                opt_text = opt['text'].lower()
                if value == opt_text:
                    best_match = opt
                    print(f"[EXACT_MATCH] Found exact match: '{value}' = '{opt['text']}'")
                    break
            
            # Then try partial matches
            if not best_match:
                for opt in options:
                    opt_text = opt['text'].lower()
                    if value in opt_text or opt_text in value:
                        best_match = opt
                        print(f"[PARTIAL_MATCH] Found partial match: '{value}' ~ '{opt['text']}'")
                        break
            
            # Try keyword matching for common patterns
            if not best_match:
                if any(word in value for word in ['first', 'new', 'never']):
                    best_match = next((opt for opt in options if 'first time' in opt['text'].lower()), None)
                    if best_match:
                        print(f"[KEYWORD_MATCH] Matched 'first time user' for: '{value}'")
                elif value.isdigit() or any(year in value for year in ['2024', '2023', '2022', '2021', '2020']):
                    # Try to match year
                    year_in_value = None
                    for year in ['2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018', '2017', '2016']:
                        if year in value:
                            year_in_value = year
                            break
                    if year_in_value:
                        best_match = next((opt for opt in options if year_in_value in opt['text']), None)
                        if best_match:
                            print(f"[YEAR_MATCH] Matched year {year_in_value}: '{value}' → '{best_match['text']}'")
        
        # Default to "First time GoPass user" if no match found
        if not best_match:
            best_match = next((opt for opt in options if 'first time' in opt['text'].lower()), options[0] if options else None)
            print(f"[DEFAULT] No match found, using default: '{best_match['text'] if best_match else 'None'}'")
        
        if not best_match:
            print("[ERROR] No dropdown options found!")
            return
        
        print(f"[SELECTION] Selecting: '{best_match['text']}' (ID: {best_match['id']})")
        
        # Click the selected option
        await best_match['element'].click(timeout=3000)
        print("Dropdown option selected successfully.")
        
        # Wait for dropdown to close
        await page.wait_for_timeout(500)
        
    except Exception as e:
        print(f"[ERROR] Could not handle dropdown: {e}")
        # Try to close dropdown if it's open
        try:
            await page.keyboard.press('Escape')
        except:
            pass
    
    # Wait before clicking Next
    await page.wait_for_timeout(500)
    if await page.locator('#next-button').is_visible():
        await page.click('#next-button')
        await page.wait_for_load_state('networkidle')

async def handle_clipper_card_page(page, row):
    print("[PAGE] Clipper Card Page: Selecting Yes/No based on CSV.")
    sec = page.locator('#question-QID71')
    
    # Wait for section to be visible
    try:
        await sec.wait_for(state='visible', timeout=5000)
        print("[SUCCESS] Section is visible")
    except Exception as e:
        print(f"[ERROR] Section not visible: {e}")
        return
    
    heading = await sec.locator('.question-display').inner_text()
    print(f"[DIAGNOSTIC] Heading: {heading.strip()}")
    
    # Get value from CSV - try multiple possible column names
    possible_cols = [
        'Would you like to receive your GoPass on an Adult Clipper Card (digital or physical) that you already own?',
        'Clipper Card GoPass',
        'GoPass on Clipper Card',
        'Adult Clipper Card'
    ]
    value = ''
    found_col = None
    for col in possible_cols:
        if col in row and str(row[col]).strip():
            value = str(row[col]).strip().lower()
            found_col = col
            break
    
    print(f"[DATA] CSV Value: '{value}'")
    print(f"[DATA] Found in column: {found_col}")
    
    # Wait for page to settle
    await page.wait_for_timeout(1000)
    
    # Use the exact radio IDs from the HTML
    yes_radio_id = 'mc-choice-input-QID71-1'
    no_radio_id = 'mc-choice-input-QID71-2'
    
    # Determine which radio to select
    select_yes = False
    if value:
        if any(word in value for word in ['yes', 'y', 'true', '1']):
            select_yes = True
            print("[SELECTION] Will select 'Yes' option")
        else:
            select_yes = False
            print("[SELECTION] Will select 'No' option")
    else:
        select_yes = False  # Default to No
        print("[DEFAULT] No CSV value found, defaulting to 'No'")
    
    target_id = yes_radio_id if select_yes else no_radio_id
    target_text = "Yes" if select_yes else "No"
    
    print(f"[SELECTION] Targeting radio: {target_id} ({target_text})")
    
    # Try multiple methods to select the radio
    success = False
    
    # Method 1: Direct ID selection
    try:
        radio = page.locator(f'#{target_id}')
        await radio.wait_for(state='visible', timeout=3000)
        
        is_checked = await radio.is_checked()
        print(f"Radio {target_text} checked state: {is_checked}")
        
        if not is_checked:
            await radio.check(force=True, timeout=2000)
            print(f"✅ Radio {target_text} checked successfully")
        else:
            print(f"✅ Radio {target_text} already selected")
        success = True
        
    except Exception as e:
        print(f"❌ Method 1 (direct ID) failed: {e}")
    
    # Method 2: Click the label
    if not success:
        try:
            label = page.locator(f'label[for="{target_id}"]')
            await label.wait_for(state='visible', timeout=3000)
            await label.click(timeout=2000)
            print(f"✅ Radio {target_text} selected via label click")
            success = True
        except Exception as e:
            print(f"❌ Method 2 (label click) failed: {e}")
    
    # Method 3: Force click the radio
    if not success:
        try:
            radio = page.locator(f'#{target_id}')
            await radio.click(force=True, timeout=2000)
            print(f"✅ Radio {target_text} selected via force click")
            success = True
        except Exception as e:
            print(f"❌ Method 3 (force click) failed: {e}")
    
    # Method 4: JavaScript execution as last resort
    if not success:
        try:
            await page.evaluate(f'''
                const radio = document.getElementById('{target_id}');
                if (radio) {{
                    radio.checked = true;
                    radio.click();
                    // Trigger change event
                    radio.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            ''')
            print(f"✅ Radio {target_text} selected via JavaScript")
            success = True
        except Exception as e:
            print(f"❌ Method 4 (JavaScript) failed: {e}")
    
    if not success:
        print("❌ All selection methods failed!")
    else:
        print("🎉 Radio selection completed successfully")
    
    # Small wait before clicking Next
    await page.wait_for_timeout(500)
    
    # Click Next button
    try:
        next_button = page.locator('#next-button')
        if await next_button.is_visible():
            await next_button.click()
            await page.wait_for_load_state('networkidle')
            print("✅ Clicked Next button and loaded next page")
        else:
            print("❌ Next button not visible")
    except Exception as e:
        print(f"❌ Failed to click Next button: {e}")

async def handle_gopass_clipper_card_page(page, row):
    print("[PAGE] GoPass Clipper Card Page: Selecting radio based on CSV.")
    sec = page.locator('#question-QID71')
    sec_id = 'question-QID71'
    heading = await sec.locator('.question-display').inner_text()
    html = await sec.inner_html()
    print(f"[DIAGNOSTIC] Section ID: {sec_id}")
    print(f"[DIAGNOSTIC] Heading: {heading.strip()}")
    print(f"[DIAGNOSTIC] Raw HTML:\n{html}\n")
    # Get value from CSV
    col = 'Would you like to receive your GoPass on an Adult Clipper Card (digital or physical) that you already own?'
    value = row.get(col, '').strip()
    print(f"[DATA] CSV Value: {value}")
    # Wait 2 seconds for page to settle
    await page.wait_for_timeout(2000)
    radios = sec.locator('input[type="radio"]')
    radio_labels = sec.locator('label')
    radio_count = await radios.count()
    label_texts = [await radio_labels.nth(i).inner_text() for i in range(await radio_labels.count())]
    print(f"[DIAGNOSTIC] Radio labels: {label_texts}")
    # Try to match value to label
    selected_index = None
    for i, label in enumerate(label_texts):
        if value.lower() in label.lower():
            selected_index = i
            break
    if selected_index is not None and selected_index < radio_count:
        try:
            checked = await radios.nth(selected_index).is_checked()
            print(f"Radio checked state before: {checked}")
            if not checked:
                await radios.nth(selected_index).check(force=True)
                print(f"Radio checked for label: {label_texts[selected_index]}")
            else:
                print("Radio already selected, skipping .check()")
            checked_after = await radios.nth(selected_index).is_checked()
            print(f"Radio checked state after: {checked_after}")
        except Exception as e:
            print(f"[ERROR] Could not check radio: {e}")
    else:
        print(f"[WARNING] Could not match CSV value '{value}' to any radio label!")
    # Sleep before clicking Next
    await page.wait_for_timeout(500)
    if await page.locator('#next-button').is_visible():
        await page.click('#next-button')
        await page.wait_for_load_state('networkidle')
import difflib
async def get_page_signature(page):
    # Returns a string signature of visible section headings
    try:
        qs = await page.locator("section.question .question-display").all_inner_texts()
        return " || ".join([s.strip() for s in qs])
    except:
        return ""
# main_autofill.py
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from helpers_generic import click_radio, fill_all_text_inputs

SURVEY_URL = "https://samtranscore.sjc1.qualtrics.com/jfe/form/SV_1Sr8UDzSeUWm20e?RID=CGC_NlYyJUotAxWDit6&Q_CHL=email"
CSV_PATH = "./data.csv"

CSV_TO_SECTION_MAP = {
    "Agreement": {"section_id": "question-QID4", "type": "radio"},
    "First Name": {"section_id": "question-QID9", "type": "text", "input_index": 0},
    "Middle Name": {"section_id": "question-QID9", "type": "text", "input_index": 1},
    "Last Name": {"section_id": "question-QID9", "type": "text", "input_index": 2},
    "Would you like to receive your GoPass on an Adult Clipper Card (digital or physical) that you already own?": {"section_id": "question-QID71", "type": "radio"},
    "If you have a Clipper Card, please enter the ten digital serial number from your Adult Clipper Card. This is required if you have a Clipper Card. ": {"section_id": "question-QID72", "type": "text", "input_index": 0},
    "In which fare category do you belong?\n": {"section_id": "question-QID10", "type": "radio"},
    "When were you first issued with a GoPass?\n\nSelect \"First time GoPass user\" if this is the first time you have been issued with a GoPass.": {"section_id": "question-QID11", "type": "radio"},
    "Did you ride Caltrain before having a GoPass?": {"section_id": "question-QID15", "type": "radio"},
    # Add more mappings as needed
}

async def fill_survey(page, row):
    # Detect all visible survey questions
    question_sections = await page.locator("section.question").all()
    if not question_sections:
        print("[INFO] No survey questions found. This is likely a gate/confirm-start page.")
        confirm = input("Press 'y' to click Next and continue, or any other key to stop: ").strip().lower()
        if confirm == 'y':
            await click_next(page)
        else:
            print("Stopping at this page.")
        return

    # For each question section, detect heading and input types
    for sec in question_sections:
        sec_id = await sec.get_attribute("id")
        heading = await sec.locator(".question-display").inner_text()
        # Find best matching CSV column for this heading
        csv_columns = list(row.keys())
        best_match = difflib.get_close_matches(heading, csv_columns, n=1, cutoff=0.5)
        value = None
        if best_match:
            col = best_match[0]
            value = row.get(col, "")
        # Detect input types
        radios = await sec.locator('input[type="radio"]').all()
        texts = await sec.locator('input[type="text"]').all()
        checkboxes = await sec.locator('input[type="checkbox"]').all()
        # For radio
        if radios:
            if value:
                await click_radio(page, sec_id, str(value))
            else:
                # Only check if not already checked
                if not await radios[0].is_checked():
                    await radios[0].check(force=True)
        # For text
        if texts:
            if value:
                for i, t in enumerate(texts):
                    fill_val = str(value) if i == 0 else ""
                    await t.fill(fill_val)
            else:
                for t in texts:
                    await t.fill("")
        # For checkbox
        if checkboxes:
            if value:
                for c in checkboxes:
                    if not await c.is_checked():
                        await c.check(force=True)
            else:
                if not await checkboxes[0].is_checked():
                    await checkboxes[0].check(force=True)

async def click_next(page):
    if await page.locator("#next-button").is_visible():
        await page.click("#next-button")
        await page.wait_for_load_state("networkidle")

async def main():
    df = pd.read_csv(CSV_PATH).fillna("")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        for i, row in df.iterrows():
            print(f"\n================= START ROW {i} =================")
            await page.goto(SURVEY_URL)
            await page.wait_for_selector('#survey-canvas', timeout=15000)
            for step in range(0, 20):
                # Detect all visible question sections
                question_sections = await page.locator('section.question').all()
                handled = False
                for sec in question_sections:
                    sec_id = await sec.get_attribute('id')
                    if sec_id == 'question-QID9':
                        print("[PAGE] GoPass User Name Page detected. Printing diagnostics...")
                        try:
                            from survey_page_diagnostics import print_page_details
                            await print_page_details(page)
                        except Exception as e:
                            print(f"Diagnostics error: {e}")
                        await handle_user_name_page(page, row)
                        handled = True
                        await page.wait_for_timeout(5000)  # 2 second sleep
                        # input("Press Enter to continue to the next page...")
                        break
                    elif sec_id == 'question-QID71':
                        print("[PAGE] Clipper Card Page detected. Printing diagnostics...")
                        try:
                            from survey_page_diagnostics import print_page_details
                            await print_page_details(page)
                        except Exception as e:
                            print(f"Diagnostics error: {e}")
                        await handle_clipper_card_page(page, row)
                        handled = True
                        break
                    elif sec_id == 'question-QID10':
                        print("[PAGE] Fare Category Page detected. Printing diagnostics...")
                        try:
                            from survey_page_diagnostics import print_page_details
                            await print_page_details(page)
                        except Exception as e:
                            print(f"Diagnostics error: {e}")
                        await handle_fare_category_page(page, row)
                        handled = True
                        break
                    elif sec_id == 'question-QID11':
                        print("[PAGE] GoPass Issuance Date Page detected. Printing diagnostics...")
                        try:
                            from survey_page_diagnostics import print_page_details
                            await print_page_details(page)
                        except Exception as e:
                            print(f"Diagnostics error: {e}")
                        await handle_gopass_issuance_page(page, row)
                        handled = True
                        input("Press Enter to continue to the next page...")
                        break
                    elif sec_id == 'question-QID15':
                        print("[PAGE] Caltrain Before GoPass Page detected. Printing diagnostics...")
                        try:
                            from survey_page_diagnostics import print_page_details
                            await print_page_details(page)
                        except Exception as e:
                            print(f"Diagnostics error: {e}")
                        await handle_caltrain_before_gopass_page(page, row)
                        handled = True
                        break
                    elif sec_id == 'question-QID72':
                        print("[PAGE] Clipper Card Serial Number Page detected. Printing diagnostics...")
                        try:
                            from survey_page_diagnostics import print_page_details
                            await print_page_details(page)
                        except Exception as e:
                            print(f"Diagnostics error: {e}")
                        await handle_clipper_serial_page(page, row)
                        handled = True
                        # input("Press Enter to continue to the next page...")

                        break
                    elif sec_id == 'question-QID4':
                        await handle_acknowledgement_page(page)
                        handled = True
                        break
                if not handled:
                    if len(question_sections) > 0:
                        await handle_generic_page(page, row)
                    elif await page.locator('section.question').count() == 0:
                        await handle_gate_page(page)
                    else:
                        print("[PAGE] Unknown page type. Skipping.")
                        if await page.locator('#next-button').is_visible():
                            await page.click('#next-button')
                            await page.wait_for_load_state('networkidle')
                # Stop if Thank You page is visible
                if await page.locator("text=Thank you").first.is_visible():
                    print("[done] Thank you page.")
                    break
                
                # Single pause at the end of each step
                # input("Press Enter to continue to the next page...")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
