# ADR 0003: The cover week wins over the file name

## Status

Accepted (2026-10-29)

## Context

Every branch workbook names its ISO week twice: in the cell ISO week on the cover and in the file name. They disagree in practice. Branch managers copy last week's file and change the figures, so the copy keeps an old name; sometimes the cover cell is left blank. The report must assign each file to exactly one week and say what it did.

## Decision

The cover cell wins. When cover and file name differ, the cover week is used and the finding `WEEK_NAME_MISMATCH` names both. When the cover cell is blank or not an ISO week, the week comes from the file name (`WEEK_MISSING`). When neither gives a week, the file is excluded (`WEEK_INVALID`). Duplicates are settled after the weeks are known: identical content keeps the first file by name (`DUPLICATE_IDENTICAL`); different content keeps the later Submitted at (`DUPLICATE_REPLACED`); equal Submitted at excludes every copy (`DUPLICATE_AMBIGUOUS`), because the tool cannot know which is right.

## Consequences

- A copied file with an old name lands in the right week, with a warning that tells the administrator to check it.
- A cover that is wrong but filled in wins over a correct file name; the warning makes this visible, and [handover](../handover.md) says what to ask the branch.
- The decision never depends on file modification times, which mail and git do not keep.

## Alternatives considered

- The file name wins: rejected, because copied files keep old names, which is the most frequent deviation.
- Rejecting every file whose cover and name disagree: rejected, because one renamed copy would leave a branch out of the Monday report.
- The newest file modification time for duplicates: rejected, because it is lost when files travel by e-mail or git.
