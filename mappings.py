# mappings.py
import re

QUESTION_MAP = [

    {"pattern": r"GoPass Use Acknowledgement", "type":"radio", "csv":"ACKNOWLEDGE"},

    # Welcome acknowledgement (checkbox/radio with long statement)
    {"pattern": r"GoPass Use Acknowledgement", "type":"radio", "csv":"ACKNOWLEDGE", "value_map":{"y":"I certify","yes":"I certify"}},

    # Name (3 text inputs)
    {"pattern": r"GoPass User Name", "type":"name3",
     "csv_cols":["First Name","Middle Name","Last Name"]},

    # Fare category (radio)
    {"pattern": r"In which fare category do you belong", "type":"radio",
     "csv":"In which fare category do you belong?"},

    # Adult Clipper Card you already own? (radio yes/no)
    {"pattern": r"Would you like to receive your GoPass on an Adult Clipper Card",
     "type":"radio-yn", "csv":"Would you like to receive your GoPass on an Adult Clipper Card (digital or physical) that you already own?"},

    # Serial page (text)
    {"pattern": r"Please enter the serial number.*Adult Clipper Card", "type":"text",
     "csv":"Clipper Serial"},

    # When first issued (dropdown)
    {"pattern": r"When were you first issued with a GoPass", "type":"dropdown",
     "csv":"When were you first issued with a GoPass?"},

    # Prior ride (radio)
    {"pattern": r"Did you ride Caltrain .* before .* GoPass", "type":"radio",
     "csv":"Did you ride Caltrain before having a GoPass?"},

    # Prior ticket (radio)
    {"pattern": r"What ticket did you typically use prior to the GoPass", "type":"radio",
     "csv":"What ticket did you typically use prior to the GoPass?"},

    # Prior frequency (radio)
    {"pattern": r"Prior .* how often did you ride Caltrain", "type":"radio",
     "csv":"Prior to the GoPass, how often did you ride Caltrain?"},

    # Prior purpose (radio)
    {"pattern": r"Prior .* most common trip purpose", "type":"radio",
     "csv":"Prior to the GoPass, what was your most common trip purpose?"},

    # Prior ON/OFF station (dropdown)
    {"pattern": r"Prior .* most common trip.*ON Station", "type":"dropdown",
     "csv":"Prior to the GoPass, which Caltrain stations did you use for your most common trip? ON"},
    {"pattern": r"Prior .* most common trip.*OFF Station", "type":"dropdown",
     "csv":"Prior to the GoPass, which Caltrain stations did you use for your most common trip? OFF"},

    # After purpose (radio)
    {"pattern": r"After .* most common trip purpose", "type":"radio",
     "csv":"After receiving your 2026 GoPass, what will be your most common trip purpose?"},

    # After frequency (radio)
    {"pattern": r"How often do you plan to ride Caltrain .* after .* 2026 GoPass", "type":"radio",
     "csv":"How often do you plan to ride Caltrain after receiving your 2026 GoPass?"},

    # After ON/OFF stations (dropdown)
    {"pattern": r"Which Caltrain stations .* most common trip.*ON Station", "type":"dropdown",
     "csv":"Which Caltrain stations will you use for your most common trip? ON"},
    {"pattern": r"Which Caltrain stations .* most common trip.*OFF Station", "type":"dropdown",
     "csv":"Which Caltrain stations will you use for your most common trip? OFF"},

    # English self (radio)
    {"pattern": r"How well do you speak English", "type":"radio",
     "csv":"How well do you speak English?"},

    # English at home (radio)
    {"pattern": r"In your home, is English spoken", "type":"radio",
     "csv":"In your home, is English spoken:"},

    # Languages at home (checkbox multi, semicolon or | delimited)
    {"pattern": r"Which languages are spoken in your home", "type":"checkbox-multi",
     "csv":"Which languages are spoken in your home?"},

    # Ethnicity (checkbox multi)
    {"pattern": r"best describes your race/ethnic background", "type":"checkbox-multi",
     "csv":"Which of the following best describes your race/ethnic background?"},

    # Household size (radio)
    {"pattern": r"how many people live in your household", "type":"radio",
     "csv":"Including yourself, how many people live in your household?"},

    # Income (radio)
    {"pattern": r"Annual household income", "type":"radio",
     "csv":"Annual household income (before taxes):"},

    # ZIP (text)
    {"pattern": r"What is your home ZIP code", "type":"text",
     "csv":"What is your home ZIP code?"},

    # Required email (text)
    {"pattern": r"enter your organization or personal email address", "type":"text",
     "csv":"Please enter your organization or personal email address"},

    # Future comms (checkboxes)
    {"pattern": r"Future communications from Caltrain", "type":"comms",
     "csv":"Future communications from Caltrain (optional)"},

    # Confirm email (text)
    {"pattern": r"Please confirm the email address", "type":"text",
     "csv":"Please confirm the email address where you would like to receive communications from Caltrain:"},
]
