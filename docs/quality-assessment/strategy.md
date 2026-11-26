# Post-migration quality assessment strategy

How we decide that the farmer data moved from Gen1 (farmer profile) to Gen2
(Farmer Registry) is complete, correct and traceable.

## 1. What we are assessing

**The question:** did the migration lose, change or fail to load anything, other than
what was agreed?

| In scope | Out of scope |
|---|---|
| Every Gen1 farmer, household, member, phone, land and crop is accounted for | Whether Gen1's data was right to begin with. A wrong age that arrives unchanged is a correct migration |
| Values arrive as the agreed mapping says | Data entered or edited in Gen2 after the load |
| Records are linked correctly and can be used in Gen2 | Finding the same person held as two records (a separate piece of work) |
| Every record and the IDs people use can be traced to Gen1 | |

Farmer documents are in scope too: the files are copied separately, and then linked to
their records in Gen2 (section 6).

## 2. Principles

1. **Account for everything.** Every Gen1 record is in exactly one group. "Unexplained" must be 0.
2. **Compare against the source,** not only against what the migration meant to do.
3. **More than one kind of check.** Automated checks cover every record but share some of
   the migration's own rules. People checking a sample in both applications don't.
4. **No single score.** One good average can hide a serious problem. A blocking check that
   fails blocks sign-off, however good the rest is.
5. **Not checked is never a pass.**
6. **Tell apart** what was already so in Gen1, and what the migration caused.

## 3. What "quality" means here

| Dimension | The question | Measured by | Target | Blocks sign-off |
|---|---|---|---|---|
| **Completeness: records** | Is every Gen1 record loaded, or accounted for? | Health: Reconciliation | 0 unexplained, 0 failed households | **Yes** |
| | Is everything in scope loaded? | Health: Reconciliation | 100%, or each exception accepted | Accepted before sign-off |
| **Completeness: values** | Is a value Gen1 had missing in Gen2, with no reason recorded? | Health: Quality | 0 | Reviewed |
| | Do all Gen1 fields that hold data have somewhere to go? | Mapping sheets | 0 "Not reviewed"; the rest accepted | Accepted before sign-off |
| **Accuracy** | Do the values match Gen1, by the agreed mapping? | Verify, all records | 100% | **Yes** |
| | Does what a person sees in Gen2 match what they see in Gen1? | Sample check | No critical difference in the random sample | **Yes** |
| **Validity** | Are codes and locations in Master Data? | Verify | 100% | Reviewed |
| | What was left empty because Gen2 has no such value? | Health: Quality | Each kind accepted, or fixed | Accepted before sign-off |
| **Consistency** | Does every link resolve, every household have one head, every farmer with a phone one primary number? | Health: Quality | 100% | **Yes** |
| **Uniqueness** | Do farmers share a Fayda ID, with each other or with a farmer already in Gen2? | Health: Quality | 0 | Reviewed (see section 9) |
| **Traceability** | Has every record both its Gen1 and its Gen2 ID saved? | Health: IDs | 100% | **Yes** |
| | Did the Gen1 Farmer IDs arrive unchanged? | Health: IDs | 100% | **Yes** |
| **Documents** | Is every document's file there, and linked to the right record? | Checks 8 and 9 | 100% | **Yes** |
| **Usability** | Do farmers and households have their numbers, and farmers their scores? | Health: Run health | 0 failed, 0 waiting at sign-off | Reviewed |
| | Can staff find, open and edit migrated records? | Acceptance test | All test cases pass | **Yes** |

## 4. The checks

| # | Check | Covers | How | Status |
|---|---|---|---|---|
| 1 | **Reconciliation** | Every record | `./run.sh health` puts each Gen1 record in one group: loaded, failed, not added, left out with a reason, out of scope, not reached, unexplained | Built |
| 2 | **Value comparison** | Every loaded record | `./run.sh verify` compares each migrated column with what Gen1's record should give | Built |
| 3 | **Direct comparison** | Every loaded farmer | `verify` compares names, birth date, gender, phones, and the number of lands, crops and members with Gen1's own rows, without the migration's mapping | Built |
| 4 | **Structure and codes** | Every loaded record | `verify` and `health`: links, heads, primary phones, codes and locations in Master Data | Built |
| 5 | **Traceability** | Every loaded record | `health`, from the saved Gen1 and Gen2 ID pairs | Built |
| 6 | **Sample check** | A random sample of farmers, and chosen cases | People compare the same records in both applications | See [`sample-check.md`](sample-check.md) |
| 7 | **Acceptance test** | Main tasks in Gen2 | Staff search, open, edit and approve migrated records | See [`acceptance-test.md`](acceptance-test.md) |
| 8 | **Documents: files** | Every file in the documents bucket | `move_to_garage.sh check` compares name, size and MD5 of every file | Built |
| 9 | **Documents: links and content** | Every document of a loaded record | Links by `health`; files by a documents check that reads the storage: section 6 | To do, after the linking is built |

Checks 2 and 3 complement each other. Check 2 covers every column, but uses the
migration's own mapping, so a wrong mapping can agree with itself. Check 3 doesn't use
the mapping, but covers fewer fields. **Neither can tell whether the mapping itself is
what people want. Only checks 6 and 7 can.**

## 5. The sample check against the legacy application

Two people compare a random sample of farmers by hand in both applications, and some
chosen difficult cases besides. The sample size is agreed beforehand: a larger
sample finds rarer differences. How to draw it, what to compare and how to record it:
[`sample-check.md`](sample-check.md).

## 6. Documents

A document has arrived when three things are true: **the file was copied, the Gen2 record
points to it, and it opens.** A file can be copied perfectly and still be linked to
nobody, or to the wrong land.

| Gen1 document | Where its file is | In Gen2 |
|---|---|---|
| Land certificate (`land_certificate`) | Documents storage (MinIO) | `certificate_storage_id` of the land |
| Supporting documents of a farmer | Documents storage (MinIO) | To be decided |
| Farmer photo (`image_1920`) | Odoo's own attachments: **not in the bucket `move_to_garage.sh` copies** | `record_image_document_id` of the farmer |

The migration doesn't link documents yet. Once it does, these are checked for **every
document of every loaded record**, by program:

| Check | How | Target | Blocks sign-off |
|---|---|---|---|
| **Linked:** every Gen1 document is linked in Gen2, or has a recorded reason | Gen1's documents against Gen2's, through `migrated_record` | 0 unexplained | **Yes** |
| **To the right record:** the one its Gen1 owner became | The same | 100% | **Yes** |
| **It is the same file:** what Gen2 serves is what Gen1 has for that record | Read it through Gen2's storage client; compare size and checksum with Gen1's | 100% | **Yes** |
| **It is there:** the link leads to the document catalogue (`g2p_registry_documents`), and that to a file | The same read | 100% | **Yes** |
| **It can be read:** a JPEG or PNG decodes, a PDF parses, and the content is of the type its name says | Open it with a library | Same as in Gen1: a file already broken there is reported | **Yes**, if broken by the move |
| **Gen2 serves it:** a user with the right role gets it, one without doesn't | Download through Gen2's API with test users, for some of each kind | 100% | **Yes** |
| Files copied that no record points to | Storage against the catalogue | Reported | Reviewed |
| Gen1 documents whose file is missing in Gen1 itself | Gen1 against its storage | Reported | Reviewed |
| Lands marked as having a certificate in Gen1, with no file | Gen1 | Reported | Information |

**Left for people,** for a few of each kind (sample check, acceptance test case 10):

- It shows properly on Gen2's screen, in the browsers staff use.
- The content is what it should be, e.g. the certificate of that land. If Gen1 has the wrong
  file on a record, the same file in Gen2 is a correct migration: it is reported, not a failure.

## 7. When

| Phase | What is done | Passing it means |
|---|---|---|
| **1. Baseline**, before any load | Dry run over everything. Agree what is out of scope, the mapping exceptions, and what may be left empty | Every kind of issue is fixed in Gen1 or accepted |
| **2. Rehearsal**, on a copy of production | Load, verify, health, then checks 6, 7 and 9 | No blocking check fails; time and capacity known |
| **3. Production load** | Load, verify, health, both documents checks. The registry's workers give out numbers and scores | No blocking check fails; reports kept |
| **3a. Changes until cutover**, only if Gen1 is still used | `migrate --all` again, as often as agreed: it brings what changed in Gen1. Then verify and health | No blocking check fails, and no conflict is left unsettled |
| **4. Sign-off** | `health` once more, when the numbers and scores are done. Sample check on production. The decision (section 8) | Signed, with accepted exceptions listed |

**Staff start working in Gen2 after sign-off.** The checks compare Gen2 with Gen1, so they are
done before anyone edits Gen2, and not repeated afterwards: from then on Gen2 is the record,
and differences from Gen1 are expected.

**If Gen1 is still used after the production load (phase 3a),** each later run writes Gen1's changes
over Gen2, **unless staff have edited that household in Gen2 since: then Gen2 is not touched,** and
the household is a conflict for a person to decide: keep Gen2 as it is (`migrate --resolve`) or
write Gen1 over the edits (`migrate --overwrite`), for one or more households at a time.
Records no longer in Gen1 are set inactive, never deleted. A household edited in Gen2 is not
compared by `verify` or `health`.

## 8. Deciding

| Result | Decision |
|---|---|
| Any blocking check fails or isn't checked | **No sign-off** |
| Only reviewed items are open, each accepted in writing | **Sign-off with exceptions** |
| Everything is as targeted | **Sign-off** |

### When a check fails

| What | First question | Usually fixed by |
|---|---|---|
| Unexplained records | Were they deleted in Gen2, or never loaded? | Migration team; load again |
| Failed households | Is the record wrong in Gen1? | Gen1 team corrects, then run again: only those are retried |
| Values that don't match | Was it edited in Gen2 since, or is the mapping wrong? | Migration team. A wrong mapping needs a decision on records already loaded |
| Values left empty | Is the code missing from Master Data, or from the mapping? | Registry or migration team, **before** the load: a rerun only updates records that changed in Gen1 |
| Conflicts not settled | What changed in Gen1, and what did staff change in Gen2? | A person decides: `migrate --resolve` keeps Gen2, `migrate --overwrite` writes Gen1 over it |
| Out of scope or deleted since, still active | Did the last run over every farmer finish? | `migrate --all` |
| Broken links, heads or phones | Was it edited in Gen2? | Registry team |
| Numbers or scores failed | Are the registry's workers running? | Registry team |

## 9. Known risks to settle before production

| Risk | Effect on quality | Needs |
|---|---|---|
| Draft and rejected farmers load as `ACTIVE` (issue 10) | They appear among approved farmers | A decision |
| Archived farmers, disabled phone numbers and ended memberships are not migrated | They stay in Gen1 only | Confirmation before the production load; archived farmers: issue 10 |
| The same person as two records isn't detected | Duplicates in Gen2. The report counts shared Fayda IDs, RIDs and ODK IDs only | The duplicates work, before the load |
| Gen2 could generate a number a Gen1 farmer has | A household that fails, or one number for two people | Reserve Gen1's numbers in the generator (planned) |
| Some ID values have no place in Gen2, e.g. the FAN of a farmer who has a UID | They stay in Gen1 only | Accept, or keep them elsewhere |
| Some Gen1 values have no Gen2 code, e.g. land ownership "family gift" | Left empty | Mapping or Master Data, before the load |
| Not yet tried: the live Master Data Service, the Kubernetes Job, real household groups | Surprises in production | The rehearsal (phase 2) |
| Documents are copied but not yet linked to their records | Files nobody can open from a farmer or land | Build the linking, then check 9 |
| Farmer photos are not in the bucket that is copied | Photos would stay behind | Find out if production has any; copy and link them |

## 10. Evidence kept for sign-off

| Evidence | From | Personal data |
|---|---|---|
| `health-report.xlsx` | `health` | No, counts only |
| Results of each measurement | `migration_report` in the registry database | No, counts only |
| `migration-report.xlsx`, `issues.csv` | `migrate` | **Yes** |
| `verify-report.xlsx`, `differences.csv` | `verify` | **Yes** |
| Audit and ID tables (`migration`) | `migrate` | **Yes** |
| Sample check results | Sample check | **Yes** |
| Documents check log | `move_to_garage.sh check` | File names: may be personal |
| Signed decision with accepted exceptions | Sign-off | No |

How long evidence with personal data is kept, and where, is to be decided.

## 11. Running it

```sh
./run.sh dry-run     # phase 1: what would happen; nothing is kept
./run.sh migrate     # load; run again after a stop, a fix, or to bring Gen1's changes
./run.sh verify      # every value against Gen1
./run.sh health      # the health report; after verify
```

`health` ends with 0 when green or amber, 3 when something blocks sign-off, and 1 when
it couldn't measure. See the README's "Health report" for what each part means.

**A green or amber report is not sign-off by itself:** it doesn't include the sample
check, the acceptance test or the documents checks.

## 12. To agree

1. The targets in section 3
2. The sample size and the list of critical fields (`sample-check.md`)
3. Which exceptions are acceptable, before the load rather than after
4. How long evidence is kept
5. When Gen1 becomes read-only
6. Where a farmer's supporting documents go in Gen2, and what happens to photos
