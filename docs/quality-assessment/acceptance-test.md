# Acceptance test

Registry staff do their normal work in Gen2 on migrated records. The automated checks say the
data is there and right. This says it can be used.

> **To do:** name the testers, agree the cases with the registry team, and choose the test
> records. Run it in the rehearsal (strategy, phase 2) and a short version after the
> production load.

**Where:** the rehearsal environment, with the roles staff will have. Cases marked **W** write.
After the production load, run only the others, unless the registry team agrees.

**Passing:** every case passes. A case that fails for a reason that isn't the migration's is
recorded and passed to the registry team, and the sign-off authority decides.

| # | Case | Expected | |
|---|---|---|---|
| | **Finding** | | |
| 1 | Search a farmer by Farmer ID brought from Gen1 | Found, the same ID as in Gen1 | |
| 2 | Search by name, by local-language name, by phone, by Fayda ID | Found; the right person first | |
| 3 | Filter the list by region, zone, woreda and kebele | Migrated farmers are in their location | |
| 4 | Look for a farmer who is draft or rejected in Gen1 | Shown, or not, as agreed (issue 10) | |
| 5 | Look for a farmer who is archived in Gen1 | Not found | |
| | **Reading** | | |
| 6 | Open a farmer with household, lands, crops and phones | Every section opens and is filled | |
| 7 | Open the farmer's household | Members and head are right; the farmer is in it | |
| 8 | Open a farmer who was in no household in Gen1 | Has one of their own | |
| 9 | Look at a land with a map shape | Shown in the right place | |
| 10 | Open a land certificate, photo or document on the screen | It shows properly (once documents are linked; that it is the right file is checked by program) | |
| 11 | Look at the Farmer ID and household number | A number, not `TEMP-`, once the workers have run | |
| 12 | Look at the completion score | There, once the workers have run | |
| | **Changing** | | |
| 13 | Edit a migrated farmer and save | Saved; or a clear message of what must be filled in first | W |
| 14 | Edit a farmer whose required fields are empty | A clear message; can be completed and saved | W |
| 15 | Take a change through approval | Approved, and the farmer shows it | W |
| 16 | Add a phone, a land and a crop to a migrated farmer | Saved, and the totals change | W |
| 17 | Add a member to a migrated household | Saved; still one head | W |
| 18 | Change the head of a migrated household | Saved; exactly one head | W |
| | **New beside old** | | |
| 19 | Register a new farmer in Gen2 | Gets a number no migrated farmer has | W |
| 20 | Register a farmer whose Fayda ID a migrated farmer has | Refused | W |
| 21 | Register a farmer into a migrated household | Joins it | W |
| | **Around it** | | |
| 22 | Dashboards and reports | Include migrated farmers, after their refresh; totals match `health-report.xlsx` | |
| 23 | Export a list | Migrated farmers are in it, readable | |
| 24 | A user of one region | Sees what their role allows, migrated records included | |

Record for each: the record used (Gen1 and Gen2 ID), the tester, the date, pass or fail, and
what happened.
