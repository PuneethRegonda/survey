### Steps
1. Open up the Gopass Spreadsheet, and filter the list for people who have 'paid', but who's caltrain survey is not 'completed'.
2. Copy all the rows that come up after adding the above filter into a new tab named something like 'Automationxx' where xx is a number.
3. Now download the tab as a 'csv'. Then open up 'Visual Studio Code' application on the left screen.
4. Copy the downloaded csv file into the 'input' folder on the left side of the Visual Studio application.
5. Copy the entire contents of the newly copied over file and open up 'data.csv' file.
6. This file will contain the headers in the first row, DO NOT REMOVE this line, keep it as it is. Remove all the remaining rows in this file. Paste the contents from the previously copied over csv file into this file. Save the file.
7. Now run the below commands one by one in the terminal on the bottom side of Visual Studio code application.
8. Once the last command is run, it will start automatically filing each of the rows on Qualtrics. Once all the rows are processed, the command will exit.
9. Once the processing is complete, go back to the Gopass spreadsheet, and mark the Qualtrics survey as filled for all the processed rows.
10. Demo of all these steps is available here - `https://drive.google.com/file/d/1MSvCcKaZSh_1CnNxyT6anqMLF-69FBTM/view?usp=drive_link`

See [Run Sheet](https://docs.google.com/document/d/13aPEf1XBVAP9FI6QRKpgNnLmlMEht1ozWszECiMcj-A/edit?usp=sharing)

### Commands to run one by one in Terminal :-
```ps
cmd; 
.\qualtrics_env\Scripts\activate
python main_auto_fill.py --csv input/data.csv --mapping mapping.json --start-url "https://samtranscore.sjc1.qualtrics.com/jfe/form/SV_1Sr8UDzSeUWm20e?RID=CGC_NlYyJUotAxWDit6&Q_CHL=email" --all --headful --debug
```





