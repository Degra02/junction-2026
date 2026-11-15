# Slide deck: speaker notes

`slides.pdf` (9 slides, 16:9, alternating light and dark in the website's design: its colour tokens, Newsreader headings, Geist text, Geist Mono data, logo mark; source `slides.html`, which loads the fonts from `web/node_modules`, so run `bun install` in `web/` before re-rendering). Target **about 4 minutes**; the times add up to 4:10, and the optional cuts bring it to 3:30. Numbers come from `report.pdf`. Never say "propaganda / not propaganda" (D4): say "signs of", "confidence", "evidence".

| # | Slide | Time | Say |
|---|---|---|---|
| 1 | The4thLover | 0:15 | "Paste a link. See how everyone else covered it, what's been copied, and how sure we are, with every source shown. That's The4thLover." |
| 2 | Is this manipulation, or one voice in a network? | 0:25 | "You read an article and wonder: is this someone manipulating me, or one node of a network pushing the same story? Today that's hours of OSINT. And asking an AI isn't an answer: you can't check it, and it can be fooled." |
| 3 | We go and find how everyone else covered it | 0:35 | "So we don't ask a model for its opinion. We extract what the content claims, go to the web and find other coverage, fact-checks and copies, and answer two separate questions: does the author manipulate, and is the message pushed by sites acting together?" |
| 4 | A confidence and its evidence. Never a verdict. | 0:40 | "You get a confidence and its evidence, never a label. Here, a German article claiming NASA faked the climate data: 84% combined, which is 83% for the content and 8% for the network. Where does the 83% come from? A fact-check found in English, rating the claim inaccurate, plus persuasion techniques in over a third of the paragraphs. Each piece links to its source. An LLM never sets the score, and when there's too little evidence we say so instead of guessing." |
| 5 | Built against the ways a naive detector fails | 0:25 *(optional)* | "A naive detector flags the fact-check that quotes the hoax, and agency copy republished everywhere. We mask quotations, recognise news agencies, compare tone with other reports of the same event. Each of these has its own test set." |
| 6 | Measured on third-party labels | 0:45 | "We measured it on 284 items in 12 languages, labelled by fact-checkers, the EU and the French agency VIGINUM, not by us. Single-actor: 98% precision, 3% false positives. It only scores 43% of items, and says not enough evidence on the rest. Coordinated looks perfect, and here's why you shouldn't believe that: the VIGINUM list labels the test items and is one of our signals. Without it, 0.38. We put that number on the metrics page next to the headline." |
| 7 | A map of sites that act together | 0:30 *(optional: cut to 0:15)* | "Every analysis also feeds a map of sites tied by shared tracking codes, copied and translated text. It finds the Pravda network as one group without using the list, and six sister sites that are on no list. A tie means related, never bad: the UN and AFP's fact-check sites are in there too." |
| 8 | Live on one Hostinger VPS | 0:20 | "It all runs on one Hostinger VPS, CPU only, about a minute per analysis. And a host could run the coordinated detector across all the sites it hosts, to surface networks only it can see." |
| 9 | What's next | 0:15 | "Next: find networks without a list, score memes, fewer abstentions. Try it at the4thlover.tech." |

## If there is time for a live demo
Insert between slides 3 and 4. Open the demo analysis and replay it, so it never waits on a source: <https://the4thlover.tech/analyses/01a1db57-b2d1-75b2-a829-61bb61a365d9>. Then skip the example on slide 4 and keep only its four bullets.

## Likely questions
- **"Isn't the coordinated score just the list?"** Today, yes, and we say so on slide 6. The source map (slide 7) is how we get off the list: it finds the network from copies and translations. It isn't in the score yet because it has to be fitted and measured first.
- **"Why so many abstentions?"** Old debunked articles have no fresh coverage to compare with. We'd rather say "not enough evidence" than guess; the metrics page counts abstentions as coverage, not wins.
- **"Is the 98% overfitted?"** The weights were fitted on the same 284 items, so precision and recall are in-sample; the AUCs (0.98, and 0.84 without fact-checks) are 5-fold cross-validated.
- **"How is the combined number calculated?"** 1 − (1 − content)(1 − network): the chance that at least one of the two kinds of signal is present, if they were independent. A dimension that abstained is shown as unrated. Our test results are per dimension; the combined number is not evaluated on its own.
- **"Where's the LLM?"** Two calls: understanding the claims and writing the explanation. Neither sets a score, and every quote it writes is checked word for word.
- **"Is it biased politically?"** We ran 10 meme texts with only the political target swapped (US, UK, DE, IT, FR, ES…), scored with the next version of the scorer (not live yet): mean difference 0.01, one pair at 0.11, traced to one technique flagged on one side. It is re-checked before that version goes live.
