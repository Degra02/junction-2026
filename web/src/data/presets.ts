import type { InputKind } from "../lib/contracts";

/**
 * Documented demo items from `evals/labelled.jsonl`, each with a finished VPS run that
 * `/analyses/{id}?replay=true` plays back. Keep in sync with `docs/pitch/demo-script.md`.
 */
export interface DemoPreset {
  /** `evals/labelled.jsonl` item ID. */
  readonly key: string;
  readonly beat: string;
  readonly language: string;
  readonly kind: InputKind;
  readonly title: string;
  readonly note: string;
  /** The submitted input, for "Prefill". */
  readonly value: string;
  readonly replayAnalysisId: string;
}

export const DEMO_PRESETS: readonly DemoPreset[] = [
  {
    key: "pk_de_002",
    beat: "Coordinated",
    language: "de",
    kind: "url",
    title: "Yuri Kotenok: Leidenschaften nach Konstantinovka (deutsch.news-pravda.com)",
    note: "The same piece ran the same day on the French, Spanish and English editions. Coordinated 62%, carried by the domain's place on VIGINUM's Portal Kombat list; single-actor abstains with 1 other report.",
    value: "https://deutsch.news-pravda.com/world/2026/11/14/917786.html",
    replayAnalysisId: "01a1dae7-401d-731c-af9d-b08a42306086",
  },
  {
    key: "fcd_de_002",
    beat: "Single-actor",
    language: "de",
    kind: "url",
    title: "Sind die Klimadaten manipuliert? (achgut.com)",
    note: "Claims NASA manipulated the climate data. Single-actor 83%: a fact-check matched across languages (Climate Feedback: Inaccurate) and persuasion techniques in the text.",
    value: "https://www.achgut.com/artikel/sind_die_klimadaten_manipuliert",
    replayAnalysisId: "01a1db57-b2d1-75b2-a829-61bb61a365d9",
  },
  {
    key: "fc_de_005",
    beat: "Hard negative · abstains",
    language: "de",
    kind: "url",
    title: "#Faktenfuchs: Nein, die NASA hat die Klimadaten nicht verfälscht (BR24)",
    note: "The fact-check of the claim above; it quotes the hoax. Both dimensions abstain: no other report on the same event was found.",
    value:
      "https://www.br.de/nachrichten/wissen/faktenfuchs-nein-die-nasa-hat-die-klimadaten-nicht-verfaelscht,Ugd68jr",
    replayAnalysisId: "01a1db57-b426-76d0-8eaa-2ca77c6e86d6",
  },
  {
    key: "ansa_it",
    beat: "Wire copy",
    language: "it",
    kind: "url",
    title: "Duffy ringrazia controllori e passeggeri, tornata la piena operatività (ANSA)",
    note: "News agency copy from a well-covered event. Both dimensions stay at 8%: 3 other reports on the same event, no copied passages, and ansa.it is recognised as a news agency.",
    value:
      "https://www.ansa.it/sito/notizie/topnews/2026/11/14/duffy-ringrazia-controllori-e-passeggeri-tornata-la-piena-operativita_9a004811-983a-4ceb-a328-41f9c37a0285.html",
    replayAnalysisId: "01a1dadf-ae67-7207-a174-62efae9b62ba",
  },
  {
    key: "fcd_en_001",
    beat: "Single-actor, 2nd language",
    language: "en",
    kind: "url",
    title: "Christians being crucified in Syria (cdm.press)",
    note: "DW Faktencheck rated the claim false. Single-actor abstains with 1 other report; coordinated 15%: the same text appears on one other site that is not a news agency.",
    value:
      "https://cdm.press/news/middle-east/2025/03/10/us-and-russia-request-emergency-un-security-council-meeting-over-syrian-islamic-slaughter-of-minorities-including-christians/",
    replayAnalysisId: "01a1dae8-3d1f-7648-b402-a830ed249618",
  },
];
