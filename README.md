# GeoSearch-IR

**A Hybrid Spatio-Textual Search Engine for Point-of-Interest Retrieval**  
CS 410 Term Project · Fall 2026

GeoSearch-IR is a planned search engine for finding New York City restaurants that match both a keyword query and a location. For a request like “quiet café with outdoor seating near Union Square,” the engine will use restaurant tips to estimate textual relevance and geographic distance to favor nearby venues. The project will compare a hybrid ranker with text-only and distance-only baselines.

## Team roles and deliverables

### Taeyang Song (`taeyang4`) — Project coordination and hybrid ranking

- Coordinate milestones and agree on venue IDs, query inputs, and ranked-run formats with the team.
- Combine normalized BM25 scores with distance decay, expose the ranking weight and decay scale, and integrate the text and spatial components into top-k search.
- Run end-to-end smoke tests and coordinate the final demo and submission.
- **Handoff.** Provide a runnable hybrid search mode and ranked-run output for evaluation.

### Isaac Simms (`isimms2`) — Dataset preparation and BM25 retrieval

- Inspect the Foursquare files, group and clean tips by venue ID, and join venue metadata and coordinates. Report how many venues have usable text and coordinates and record any exclusions.
- Build the BM25 index over venue documents and implement the text-only baseline. Expose BM25 scores for venue IDs passed by the hybrid ranker.
- **Handoff.** Provide the reproducible preprocessing and BM25 indexing commands, the shared venue schema, and the text-only run output.

### Suman Mookherjee (`sumanm2`) — Spatial indexing and distance retrieval

- Compare H3 and S2 for candidate lookup and implement the selected index over the shared venue corpus.
- Retrieve candidates from cells that cover the search area, compute great-circle distances, and apply exact radius filtering when a radius is specified. Test queries near cell and radius boundaries.
- Implement the distance-only baseline against the same venue corpus used by the other runs.
- **Handoff.** Provide the candidate lookup interface, distance scores for the hybrid ranker, and the distance-only run output.

### Swarvanu Sanyal (`ssanyal4`) — Relevance judgments and benchmarking

- Lead the creation of about 25 geo-keyword topics and pool the top results from all three runs. Deduplicate by venue ID and define the grading rubric.
- Split judging across all four teammates, coordinate a shared calibration round, and consolidate grades into qrels.
- Compute MAP and NDCG@K against the shared qrels. Benchmark end-to-end latency under the same conditions for all three modes and report median and 95th-percentile latency.
- **Handoff.** Provide the topics, qrels, evaluation commands, and results for the final report and presentation.

All four teammates will review integration changes, judge a share of the pooled results, and contribute to the report and presentation.

## Dataset

The project uses Dingqi Yang’s **Foursquare NYC Restaurant Rich Dataset**. It covers October 24, 2011 through February 20, 2012 and contains 3,298 venues, 3,112 users, 27,149 check-ins, and 10,377 English-language tips, along with venue tags. Choose the **NYC Restaurant Rich Dataset (Check-ins, Tips, Tags)** entry for the archive and its schema notes. [Dataset download and documentation](https://sites.google.com/site/yangdingqi/home/foursquare-dataset)

- **Retrieval unit.** Build one document per venue ID by grouping that venue’s tips. Join venue metadata and validate coordinates for spatial indexing. Record how many venues have usable text and coordinates after preprocessing.
- **Text signal.** Index tip text with BM25. Tips can provide evidence about dishes, atmosphere, and amenities.
- **Spatial signal.** Use validated venue latitude and longitude. Confirm coordinate coverage during ingestion and document how missing coordinates are handled. The experiment uses historical venue records and tips.

Dataset citation: Dingqi Yang, Daqing Zhang, Zhiyong Yu, and Zhiwen Yu. “Fine-Grained Preference-Aware Location Search Leveraging Crowdsourced Digital Footprints from LBSNs.” UbiComp 2013. [Paper](https://www-public.imtbs-tsp.eu/~zhang_da/pub/UbiComp_2013_Yang.pdf)

## Planned search workflow

```mermaid
flowchart TD
    subgraph Offline["Offline indexing"]
        A["Foursquare restaurant data"] --> B["Group tips and validate venue coordinates"]
        B --> T["BM25 text index"]
        B --> S["Spatial index using H3 or S2"]
    end

    subgraph Online["Query-time retrieval"]
        Q["Keywords and query coordinates"] --> C["Find nearby candidates using spatial cells"]
        S --> C
        C --> R["Score candidates with BM25 and geographic distance"]
        T --> R
        Q --> R
        R --> H["Combine normalized BM25 and distance decay"]
        H --> O["Return top-k ranked venues"]
    end
```

The spatial index will find candidate venues in cells covering the search area. The ranker will compute great-circle distance from the query coordinates to each candidate venue and apply a decay function so closer venues receive a higher spatial score. The planned hybrid score is a weighted sum of normalized BM25 and the distance-decay score. The spatial index, candidate radius, decay scale, and ranking weight are design choices to test.

## Planned evaluation

1. Write approximately 25 realistic queries. Each topic will specify keywords, a latitude and longitude, and a short description of the intended result.
2. Run **BM25-only**, **distance-only**, and **hybrid** retrieval against a common venue corpus. Pool their top results for each query and deduplicate by venue ID.
3. Grade each pooled query–venue pair using the topic description, available tip evidence, and geographic proximity. Use a proposed scale of **0** (irrelevant), **1** (partially relevant), and **2** (highly relevant). Record the grades as relevance judgments (qrels).
4. Evaluate all runs against the same qrels. Use **MAP** for binary relevance with grades 1 and 2 counted as relevant, and **NDCG@K** for graded relevance near the top of the ranking. Record the pool depth and evaluation cutoff with the results.
5. Measure end-to-end query latency over repeated runs on the same hardware. Report median and 95th-percentile latency for each approach.

```mermaid
flowchart LR
    Q["About 25 geo-keyword queries"] --> B["BM25 only"]
    Q --> D["Distance only"]
    Q --> H["Hybrid"]
    B --> P["Pool and deduplicate top results per query"]
    D --> P
    H --> P
    P --> J["Manually grade query–venue pairs"]
    J --> G["Shared qrels"]
    G --> M["Evaluate each run with MAP and NDCG at K"]
```

## Course submissions

- **Progress report** — pending
- **Project code and documentation** — submission link pending
- **Project presentation** — submission link pending

`#SpatioTextualSearch` `#GeoAwareRanking` `#SpatialIndexing` `#POIRetrieval` `#HybridSearch`
