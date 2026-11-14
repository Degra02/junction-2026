"""The source graph: outlets tied by what stored analyses observed (plans/source-graph.md).

Not a pipeline stage yet. `python -m pipeline.graph.build` builds the graph offline from stored
analyses:

- `corpus`: the articles, outlet profiles and hyperlinks found in the analyses.
- `build`: ties between outlets (shared analytics IDs, copied text, translations, hyperlinks),
  their strength, the clusters, and the JSON written for `GET /api/graph`.
"""
