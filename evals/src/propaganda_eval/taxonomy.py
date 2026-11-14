"""Propaganda technique taxonomy and mapping across SemEval editions.

Maps SemEval-2020 (14 merged techniques) to 6 coarse categories aligned with
the SemEval-2023 Task 3 taxonomy. When SemEval-2023/2024 data arrives, extend
SEMEVAL2023_TO_CATEGORY and add a second fine→coarse map here.
"""

from __future__ import annotations

SEMEVAL2020_TECHNIQUES: list[str] = [
    "Appeal_to_Authority",
    "Appeal_to_fear-prejudice",
    "Bandwagon,Reductio_ad_hitlerum",
    "Black-and-White_Fallacy",
    "Causal_Oversimplification",
    "Doubt",
    "Exaggeration,Minimisation",
    "Flag-Waving",
    "Loaded_Language",
    "Name_Calling,Labeling",
    "Repetition",
    "Slogans",
    "Thought-terminating_Cliches",
    "Whataboutism,Straw_Men,Red_Herring",
]

CATEGORIES = [
    "Justification",
    "Simplification",
    "Distraction",
    "Call",
    "Manipulation",
    "Attack_on_Reputation",
]

TECHNIQUE_TO_CATEGORY: dict[str, str] = {
    "Appeal_to_Authority":                  "Justification",
    "Flag-Waving":                          "Justification",
    "Bandwagon,Reductio_ad_hitlerum":       "Justification",
    "Appeal_to_fear-prejudice":             "Justification",
    "Causal_Oversimplification":            "Simplification",
    "Black-and-White_Fallacy":              "Simplification",
    "Whataboutism,Straw_Men,Red_Herring":   "Distraction",
    "Slogans":                              "Call",
    "Thought-terminating_Cliches":          "Call",
    "Loaded_Language":                       "Manipulation",
    "Exaggeration,Minimisation":            "Manipulation",
    "Repetition":                           "Manipulation",
    "Name_Calling,Labeling":                "Attack_on_Reputation",
    "Doubt":                                "Attack_on_Reputation",
}

TECHNIQUE_TO_ID: dict[str, int] = {t: i for i, t in enumerate(SEMEVAL2020_TECHNIQUES)}
CATEGORY_TO_ID: dict[str, int] = {c: i for i, c in enumerate(CATEGORIES)}

DISPLAY_NAMES: dict[str, str] = {
    "Appeal_to_Authority":                  "Appeal to Authority",
    "Appeal_to_fear-prejudice":             "Appeal to Fear/Prejudice",
    "Bandwagon,Reductio_ad_hitlerum":       "Bandwagon / Reductio ad Hitlerum",
    "Black-and-White_Fallacy":              "Black-and-White Fallacy",
    "Causal_Oversimplification":            "Causal Oversimplification",
    "Doubt":                                "Doubt",
    "Exaggeration,Minimisation":            "Exaggeration / Minimisation",
    "Flag-Waving":                          "Flag-Waving",
    "Loaded_Language":                      "Loaded Language",
    "Name_Calling,Labeling":                "Name Calling / Labeling",
    "Repetition":                           "Repetition",
    "Slogans":                              "Slogans",
    "Thought-terminating_Cliches":          "Thought-terminating Cliches",
    "Whataboutism,Straw_Men,Red_Herring":   "Whataboutism / Straw Man / Red Herring",
}


def technique_to_category(technique: str) -> str:
    return TECHNIQUE_TO_CATEGORY[technique]


def technique_display(technique: str) -> str:
    return DISPLAY_NAMES.get(technique, technique)
