# The4thLover in two pages

A plain-language summary of `report.pdf`. Live at <https://the4thlover.tech>.

## The problem
You read an article or a post and wonder: is this someone manipulating me, or one voice in a network pushing the same story? Checking by hand means reading for manipulation tricks, finding other coverage, looking for fact-checks, checking who runs the site and searching for copies. That is hours of work. Asking an AI "is this propaganda?" is not an answer: you can't check its reasoning, and it can be fooled.

## What we built
You paste a text, a link or an image. The system:
1. reads it and works out what it claims;
2. goes to the web and finds how other outlets, fact-checkers and copies covered the same event;
3. answers two separate questions, each with a confidence and the evidence behind it:
   - **Single-actor**: does the author manipulate? (persuasion techniques, a much angrier tone than other reports of the same event, claims other reports contradict, fact-checkers rating the claim false, a very new website);
   - **Coordinated**: is the message pushed by sites acting together? (the same paragraphs on unrelated sites, published within hours, shared tracking codes, membership of a documented network).

It never says "propaganda" or "not propaganda": that would pretend to be the truth. When there is too little to go on, it says **"Not enough evidence"** and why, instead of guessing.

The result page leads with one **combined** figure built from the two ("Content 83% · Network 8%"): roughly the chance that at least one of the two kinds of signal is present. Each question keeps its own score and evidence underneath, and the test results below are per question.

## Why you can trust the number
- **An AI never sets the score.** Measured signals do, added up by a simple statistical model (logistic regression) whose weights were learned from labelled examples. "Show how we calculated this" lists what each signal added.
- **Every piece of evidence links to its source**, and every quotation is checked word for word; anything that does not match is dropped.
- **It is built to avoid the classic mistakes**: a fact-check that quotes a hoax, news agency copy republished by hundreds of newspapers, satire, opinion columns and emotional but accurate reporting are not flagged.

## How well it works
Tested on 284 real items in 12 languages, labelled by outsiders (fact-checkers, the EU's EUvsDisinfo database, the French agency VIGINUM's list of Russian "Pravda" network sites), never by us.

| | Result | What it means |
|---|---|---|
| Single-actor | When it gives a score, it is right 98% of the time it flags something, and wrongly flags 3% of legitimate items (1 of 39, a satire piece) | Reliable when it speaks |
| | It gives a score on 43% of items and says "not enough evidence" on the rest; it catches 46% of all manipulative items | Cautious: it stays silent rather than guess |
| | It leans on fact-check matches: without them its ranking quality drops from 0.98 to 0.84 (AUC, where 0.5 is chance) | |
| Coordinated | Perfect on the test set | But only because the VIGINUM list is both how the test items were labelled and one of our signals |
| | Without that list: 0.38, worse than chance | Today it recognises a known network; it does not yet discover new ones |

We publish the uncomfortable numbers next to the good ones.

## Beyond the original plan
- **A map of sites that act together** (`/sources`): 908 sites from the analyses so far, linked when they share a tracking code, copied or translated text, or an owner. It groups all 18 listed Pravda sites together without using the list, and also finds 6 sister sites that are not on any list. It also groups the UN's sites or AFP's fact-check editions: a link means "related", never "bad".
- **Memes**: the system can now read memes and point out persuasion tricks in the picture and the words. This is shown to the reader but does not change the score yet; it needs another round of testing first.

## Where it runs
One Hostinger server with 2 processor cores and no graphics card. An analysis takes about a minute.

## Honest limits
- Coordinated detection depends on a published list until the site map is fed into the score.
- Old or niche items often get "not enough evidence".
- The good numbers were measured on the same items the model learned from; only the ranking quality (AUC) is cross-checked.
- The labelled examples lean towards pro-Kremlin operations.
- The combined figure on the result page is not tested on its own; the results above are per question.
