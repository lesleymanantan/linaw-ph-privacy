# Roadmap

Known gaps and open questions. This is a list of what is not done, not a schedule. Items may change, be
dropped or stay open.

## Search quality
- **Filipino and Taglish questions are found less often than English ones.** On the dev set, the right passage
  is in the top three for about half of English questions and far fewer Filipino and Taglish ones.
- **The glossary is small, and adding to it needs a change to how it is built.** It holds only English terms
  that the corpus defines, so concepts the documents do not define in a definitions section (for example,
  correcting or erasing your data, complaints, fines or children's data) have no row to attach a Filipino term
  to. Filipino terms come only from human reviewers. Keyword expansion from the glossary is switched off until
  the dev set shows it helps more than it hurts.
- **Bare terms rank poorly.** A short query such as "DPA" does not reliably bring up the most relevant passage
  first.

## Knowing when not to answer
- **The "not sure" threshold is not set.** Until it is set from the dev set, every search shows results,
  even when none of them fit.
- **What to do with off-topic questions is undecided.** Questions outside data privacy still return the
  closest passages.

## Coverage
- **NPC Advisory 2022-01** (requests for personal data of public officers) is listed on the NPC website but is
  not in the catalogue or the corpus.

## Audience
- Whether and how the tool should serve individuals asking about their own data, and not only organisations,
  is an open question.

## Setup
- Running it needs a Mac or Linux computer and the 28 source PDFs, which are not in the repository and have to
  be obtained separately (see `SOURCES.md` for where each comes from).
- The Python module is still named `ph_privacy_guide` after the project's earlier name.
