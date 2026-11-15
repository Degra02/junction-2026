//! Live SQLite storage and noisy-OR cluster assembly for the source graph (`D2`).
//!
//! Keeps the exact JSON response shape of `pipeline/graph/build.py` (`evals/graph.json`) so
//! `/sources` works identically on offline and live data. When a baseline `evals/graph.json`
//! exists alongside live SQLite rows, its outlets and ties are merged idempotently so production
//! starts from the 277-analysis corpus and grows with every new check.

use std::{
    collections::{BTreeMap, BTreeSet, HashMap, HashSet},
    fmt::Write as _,
    path::Path,
};

use chrono::{DateTime, SecondsFormat, Utc};
use junction_contracts::{Analysis, GraphPatch, InputKind, OutletType};
use serde_json::{Value, json};
use sha2::{Digest as _, Sha256};
use sqlx::SqlitePool;

const CLUSTER_STRENGTH: f64 = 0.5;
const MAX_CARRIERS: usize = 20;
const MAX_EVIDENCE: usize = 3;
const TRANSLATION_SIMILARITY: f32 = 0.93;
const WINDOW_DAYS: i64 = 7;

const HOSTING_SUFFIXES: &[&str] = &[
    "blogspot.com",
    "wordpress.com",
    "substack.com",
    "medium.com",
    "ghost.io",
    "wixsite.com",
    "squarespace.com",
    "weebly.com",
    "github.io",
    "pages.dev",
    "netlify.app",
    "vercel.app",
    "livejournal.com",
    "tumblr.com",
];

const OFFICIAL_LABELS: &[&str] = &["gov", "gouv", "gob", "govt", "gc", "mil"];

type EdgeMap = BTreeMap<(String, String), BTreeMap<String, LayerAcc>>;

#[derive(Clone, Default)]
struct OutletNode {
    domain: String,
    operator: String,
    outlet_type: Option<String>,
    country: Option<String>,
    known_network: Option<String>,
    seed_articles: usize,
    seed_analysed: usize,
    live_articles: BTreeSet<String>,
    live_analysed: BTreeSet<String>,
}

#[derive(Default)]
struct LayerAcc {
    seed_count: usize,
    keys_a: BTreeSet<String>,
    keys_b: BTreeSet<String>,
    evidence: Vec<Value>,
}

impl LayerAcc {
    fn count(&self) -> usize {
        self.seed_count
            .max(self.keys_a.len().min(self.keys_b.len()))
    }

    fn push_evidence(&mut self, item: Value) {
        if !self.evidence.contains(&item) {
            self.evidence.push(item);
        }
    }
}

struct StoredArticle {
    url: String,
    outlet: String,
    published_at: Option<DateTime<Utc>>,
    language: Option<String>,
    fact_check: bool,
    embedding: Option<Vec<f32>>,
}

struct GraphAcc {
    outlets: BTreeMap<String, OutletNode>,
    edges: EdgeMap,
    seed_analyses: usize,
    seed_articles: usize,
    evaluation: Option<Value>,
}

type DbOutletRow = (
    String,
    String,
    Option<String>,
    Option<String>,
    Option<String>,
);
type DbArticleRow = (
    String,
    String,
    Option<String>,
    Option<String>,
    i64,
    i64,
    Option<Vec<u8>>,
);

fn layer_params(kind: &str) -> Option<(f64, f64, bool)> {
    match kind {
        "analytics_id" => Some((1.0, 0.75, true)),
        "ad_account" => Some((1.0, 0.2, true)),
        "copy" | "translation" => Some((2.0, 0.8, true)),
        "link" => Some((3.0, 0.3, false)),
        _ => None,
    }
}

fn id_kind(tracking_id: &str) -> Option<&'static str> {
    if tracking_id.starts_with("UA-")
        || tracking_id.starts_with("G-")
        || tracking_id.starts_with("GTM-")
    {
        return Some("analytics_id");
    }
    let digits = tracking_id
        .strip_prefix("ca-pub-")
        .or_else(|| tracking_id.strip_prefix("pub-"))?;
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let all_same = digits.bytes().all(|b| b == digits.as_bytes()[0]);
    if all_same || "01234567890123456789".contains(digits) {
        return None;
    }
    Some("ad_account")
}

fn is_hosted(domain: &str) -> bool {
    HOSTING_SUFFIXES
        .iter()
        .any(|p| domain.ends_with(&format!(".{p}")))
}

fn is_official(domain: &str) -> bool {
    domain
        .split('.')
        .any(|part| OFFICIAL_LABELS.contains(&part))
}

fn is_not_copier(outlet_type: Option<&str>) -> bool {
    matches!(
        outlet_type,
        Some("wire_service" | "fact_checker" | "satire" | "national" | "local")
    )
}

const fn outlet_type_str(t: OutletType) -> &'static str {
    match t {
        OutletType::WireService => "wire_service",
        OutletType::National => "national",
        OutletType::Local => "local",
        OutletType::Partisan => "partisan",
        OutletType::StateAffiliated => "state_affiliated",
        OutletType::FactChecker => "fact_checker",
        OutletType::Satire => "satire",
    }
}

/// Deterministic story key so re-running the same URL or text updates rather than adds.
#[must_use]
pub fn story_key(analysis: &Analysis) -> String {
    if let Some(doc) = &analysis.document
        && let Some(url) = doc.url.as_deref().map(str::trim).filter(|s| !s.is_empty())
    {
        return format!("url:{url}");
    }
    if analysis.input.kind == InputKind::Url {
        return format!("url:{}", analysis.input.value.trim());
    }
    let normalized = analysis
        .input
        .value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    let digest = Sha256::new()
        .chain_update(normalized)
        .chain_update([0])
        .chain_update(analysis.input.context_url.as_deref().unwrap_or(""))
        .finalize();
    let mut hex = String::from("sha256:");
    for b in digest {
        let _ = write!(hex, "{b:02x}");
    }
    hex
}

fn pack_embedding(values: &[f32]) -> Option<Vec<u8>> {
    if values.is_empty() {
        return None;
    }
    let mut bytes = Vec::with_capacity(values.len() * 4);
    for &v in values {
        bytes.extend_from_slice(&v.to_le_bytes());
    }
    Some(bytes)
}

fn unpack_embedding(bytes: Option<&[u8]>) -> Option<Vec<f32>> {
    let raw = bytes?;
    if raw.is_empty() || !raw.len().is_multiple_of(4) {
        return None;
    }
    Some(
        raw.as_chunks::<4>()
            .0
            .iter()
            .copied()
            .map(f32::from_le_bytes)
            .collect(),
    )
}

/// Persists one [`GraphPatch`] inside a single SQLite transaction.
pub async fn ingest_patch(
    pool: &SqlitePool,
    analysis: &Analysis,
    patch: &GraphPatch,
) -> sqlx::Result<()> {
    if patch.outlets.is_empty() && patch.articles.is_empty() && patch.ties.is_empty() {
        return Ok(());
    }
    let key = story_key(analysis);
    let now = Utc::now().to_rfc3339();
    let mut tx = pool.begin().await?;

    sqlx::query(
        "INSERT INTO graph_ingested_stories (story_key, updated_at) VALUES (?, ?) \
         ON CONFLICT(story_key) DO UPDATE SET updated_at = excluded.updated_at",
    )
    .bind(&key)
    .bind(&now)
    .execute(&mut *tx)
    .await?;

    upsert_outlets(&mut tx, patch).await?;
    upsert_articles(&mut tx, patch, &key).await?;
    upsert_ties(&mut tx, patch, &key).await?;

    tx.commit().await
}

async fn upsert_outlets(
    tx: &mut sqlx::Transaction<'_, sqlx::Sqlite>,
    patch: &GraphPatch,
) -> sqlx::Result<()> {
    for outlet in &patch.outlets {
        let otype = outlet.outlet_type.map(outlet_type_str);
        sqlx::query(
            "INSERT INTO graph_outlets (domain, operator, outlet_type, country, known_network) \
             VALUES (?, ?, ?, ?, ?) \
             ON CONFLICT(domain) DO UPDATE SET \
                 operator = excluded.operator, \
                 outlet_type = COALESCE(excluded.outlet_type, graph_outlets.outlet_type), \
                 country = COALESCE(excluded.country, graph_outlets.country), \
                 known_network = COALESCE(excluded.known_network, graph_outlets.known_network)",
        )
        .bind(&outlet.domain)
        .bind(&outlet.operator)
        .bind(otype)
        .bind(&outlet.country)
        .bind(&outlet.known_network)
        .execute(&mut **tx)
        .await?;
    }
    Ok(())
}

async fn upsert_articles(
    tx: &mut sqlx::Transaction<'_, sqlx::Sqlite>,
    patch: &GraphPatch,
    story_key: &str,
) -> sqlx::Result<()> {
    for article in &patch.articles {
        let pub_at = article.published_at.map(|dt| dt.to_rfc3339());
        let emb = pack_embedding(&article.embedding);
        sqlx::query(
            "INSERT INTO graph_articles \
             (url, outlet, title, published_at, language, analysed, fact_check, embedding) \
             VALUES (?, ?, ?, ?, ?, ?, ?, ?) \
             ON CONFLICT(url) DO UPDATE SET \
                 outlet = excluded.outlet, \
                 title = COALESCE(excluded.title, graph_articles.title), \
                 published_at = COALESCE(excluded.published_at, graph_articles.published_at), \
                 language = COALESCE(excluded.language, graph_articles.language), \
                 analysed = MAX(graph_articles.analysed, excluded.analysed), \
                 fact_check = MAX(graph_articles.fact_check, excluded.fact_check), \
                 embedding = COALESCE(excluded.embedding, graph_articles.embedding)",
        )
        .bind(&article.url)
        .bind(&article.outlet)
        .bind(&article.title)
        .bind(pub_at)
        .bind(&article.language)
        .bind(i64::from(article.analysed))
        .bind(i64::from(article.fact_check))
        .bind(emb)
        .execute(&mut **tx)
        .await?;

        sqlx::query("DELETE FROM graph_article_ids WHERE article_url = ?")
            .bind(&article.url)
            .execute(&mut **tx)
            .await?;
        for tid in &article.tracking_ids {
            if let Some(kind) = id_kind(tid) {
                sqlx::query(
                    "INSERT OR IGNORE INTO graph_article_ids (article_url, tracking_id, kind) \
                     VALUES (?, ?, ?)",
                )
                .bind(&article.url)
                .bind(tid)
                .bind(kind)
                .execute(&mut **tx)
                .await?;
            }
        }

        if article.analysed {
            sqlx::query("DELETE FROM graph_article_links WHERE article_url = ?")
                .bind(&article.url)
                .execute(&mut **tx)
                .await?;
            for target in &article.outbound_domains {
                sqlx::query(
                    "INSERT OR IGNORE INTO graph_article_links \
                     (article_url, source_outlet, target_outlet, story_key) \
                     VALUES (?, ?, ?, ?)",
                )
                .bind(&article.url)
                .bind(&article.outlet)
                .bind(target)
                .bind(story_key)
                .execute(&mut **tx)
                .await?;
            }
        }
    }
    Ok(())
}

async fn upsert_ties(
    tx: &mut sqlx::Transaction<'_, sqlx::Sqlite>,
    patch: &GraphPatch,
    story_key: &str,
) -> sqlx::Result<()> {
    for tie in &patch.ties {
        let keys_a = if tie.keys_a.is_empty() {
            vec![story_key.to_owned()]
        } else {
            tie.keys_a.clone()
        };
        let keys_b = if tie.keys_b.is_empty() {
            vec![story_key.to_owned()]
        } else {
            tie.keys_b.clone()
        };
        let ev_json = serde_json::to_string(&tie.evidence).unwrap_or_else(|_| "[]".into());
        let pairs_len = keys_a.len().max(keys_b.len());
        for idx in 0..pairs_len {
            let ka = &keys_a[idx.min(keys_a.len() - 1)];
            let kb = &keys_b[idx.min(keys_b.len() - 1)];
            sqlx::query(
                "INSERT INTO graph_ties (a, b, kind, key_a, key_b, evidence) \
                 VALUES (?, ?, ?, ?, ?, ?) \
                 ON CONFLICT(a, b, kind, key_a, key_b) DO UPDATE SET evidence = excluded.evidence",
            )
            .bind(&tie.a)
            .bind(&tie.b)
            .bind(&tie.kind)
            .bind(ka)
            .bind(kb)
            .bind(&ev_json)
            .execute(&mut **tx)
            .await?;
        }
    }
    Ok(())
}

fn strongest_evidence(items: &[Value]) -> Vec<Value> {
    let mut ranked: Vec<(f64, String, Value)> = items
        .iter()
        .map(|v| {
            let score = v
                .get("share")
                .or_else(|| v.get("similarity"))
                .and_then(Value::as_f64)
                .unwrap_or(0.0);
            let key = serde_json::to_string(v).unwrap_or_default();
            (-score, key, v.clone())
        })
        .collect();
    ranked.sort_by(|x, y| x.0.total_cmp(&y.0).then_with(|| x.1.cmp(&y.1)));
    ranked
        .into_iter()
        .take(MAX_EVIDENCE)
        .map(|(_, _, v)| v)
        .collect()
}

fn layer_strength(layers: &BTreeMap<String, LayerAcc>, coord_only: bool) -> f64 {
    let mut miss = 1.0;
    for (kind, acc) in layers {
        let Some((tau, trust, is_coord)) = layer_params(kind) else {
            continue;
        };
        if coord_only && !is_coord {
            continue;
        }
        let n = u32::try_from(acc.count()).unwrap_or(u32::MAX);
        if n > 0 {
            miss *= 1.0 - trust * (1.0 - (-f64::from(n) / tau).exp());
        }
    }
    1.0 - miss
}

fn ordered_pair(x: &str, y: &str) -> (String, String, bool) {
    if x <= y {
        (x.to_owned(), y.to_owned(), false)
    } else {
        (y.to_owned(), x.to_owned(), true)
    }
}

fn load_seed_acc(seed: Option<&Value>) -> GraphAcc {
    let mut acc = GraphAcc {
        outlets: BTreeMap::new(),
        edges: BTreeMap::new(),
        seed_analyses: 0,
        seed_articles: 0,
        evaluation: None,
    };
    let Some(seed_val) = seed else {
        return acc;
    };
    let Some(seed_outlets) = seed_val.get("outlets").and_then(Value::as_array) else {
        return acc;
    };
    acc.seed_analyses = seed_val
        .pointer("/counts/analyses")
        .and_then(Value::as_u64)
        .and_then(|v| usize::try_from(v).ok())
        .unwrap_or(0);
    acc.seed_articles = seed_val
        .pointer("/counts/articles")
        .and_then(Value::as_u64)
        .and_then(|v| usize::try_from(v).ok())
        .unwrap_or(0);
    acc.evaluation = seed_val.get("evaluation").cloned();

    for o in seed_outlets {
        let Some(domain) = o.get("domain").and_then(Value::as_str) else {
            continue;
        };
        let operator = o
            .get("operator")
            .and_then(Value::as_str)
            .unwrap_or(domain)
            .to_owned();
        acc.outlets.insert(
            domain.to_owned(),
            OutletNode {
                domain: domain.to_owned(),
                operator,
                outlet_type: o
                    .get("outlet_type")
                    .and_then(Value::as_str)
                    .map(str::to_owned),
                country: o.get("country").and_then(Value::as_str).map(str::to_owned),
                known_network: o
                    .get("known_network")
                    .and_then(Value::as_str)
                    .map(str::to_owned),
                seed_articles: o
                    .get("articles")
                    .and_then(Value::as_u64)
                    .and_then(|v| usize::try_from(v).ok())
                    .unwrap_or(0),
                seed_analysed: o
                    .get("analysed")
                    .and_then(Value::as_u64)
                    .and_then(|v| usize::try_from(v).ok())
                    .unwrap_or(0),
                ..OutletNode::default()
            },
        );
    }

    if let Some(seed_edges) = seed_val.get("edges").and_then(Value::as_array) {
        for e in seed_edges {
            let (Some(a), Some(b), Some(layers)) = (
                e.get("a").and_then(Value::as_str),
                e.get("b").and_then(Value::as_str),
                e.get("layers").and_then(Value::as_array),
            ) else {
                continue;
            };
            for l in layers {
                let Some(kind) = l.get("kind").and_then(Value::as_str) else {
                    continue;
                };
                if kind == "same_operator" {
                    continue;
                }
                let count = l
                    .get("count")
                    .and_then(Value::as_u64)
                    .and_then(|v| usize::try_from(v).ok())
                    .unwrap_or(0);
                let slot = acc
                    .edges
                    .entry((a.to_owned(), b.to_owned()))
                    .or_default()
                    .entry(kind.to_owned())
                    .or_default();
                slot.seed_count = slot.seed_count.max(count);
                if let Some(evs) = l.get("evidence").and_then(Value::as_array) {
                    for ev in evs {
                        slot.push_evidence(ev.clone());
                    }
                }
            }
        }
    }
    acc
}

async fn load_live_nodes_and_ties(
    pool: &SqlitePool,
    acc: &mut GraphAcc,
) -> sqlx::Result<Vec<StoredArticle>> {
    let db_outlets: Vec<DbOutletRow> = sqlx::query_as(
        "SELECT domain, operator, outlet_type, country, known_network FROM graph_outlets",
    )
    .fetch_all(pool)
    .await?;

    for (domain, operator, outlet_type, country, known_network) in db_outlets {
        let entry = acc
            .outlets
            .entry(domain.clone())
            .or_insert_with(|| OutletNode {
                domain,
                operator: operator.clone(),
                ..OutletNode::default()
            });
        entry.operator = operator;
        if outlet_type.is_some() {
            entry.outlet_type = outlet_type;
        }
        if country.is_some() {
            entry.country = country;
        }
        if known_network.is_some() {
            entry.known_network = known_network;
        }
    }

    let db_articles_raw: Vec<DbArticleRow> = sqlx::query_as(
        "SELECT url, outlet, published_at, language, analysed, fact_check, embedding \
         FROM graph_articles",
    )
    .fetch_all(pool)
    .await?;

    let mut live_articles = Vec::with_capacity(db_articles_raw.len());
    for (url, outlet, published_at, language, analysed, fact_check, emb) in db_articles_raw {
        if let Some(node) = acc.outlets.get_mut(&outlet) {
            node.live_articles.insert(url.clone());
            if analysed != 0 {
                node.live_analysed.insert(url.clone());
            }
        }
        let parsed_pub = published_at
            .as_deref()
            .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
            .map(|dt| dt.with_timezone(&Utc));
        live_articles.push(StoredArticle {
            url,
            outlet,
            published_at: parsed_pub,
            language,
            fact_check: fact_check != 0,
            embedding: unpack_embedding(emb.as_deref()),
        });
    }

    let db_ties: Vec<(String, String, String, String, String, String)> =
        sqlx::query_as("SELECT a, b, kind, key_a, key_b, evidence FROM graph_ties")
            .fetch_all(pool)
            .await?;

    for (a, b, kind, key_a, key_b, ev_raw) in db_ties {
        if !acc.outlets.contains_key(&a) || !acc.outlets.contains_key(&b) {
            continue;
        }
        let slot = acc
            .edges
            .entry((a, b))
            .or_default()
            .entry(kind)
            .or_default();
        slot.keys_a.insert(key_a);
        slot.keys_b.insert(key_b);
        if let Ok(Value::Array(items)) = serde_json::from_str::<Value>(&ev_raw) {
            for item in items {
                slot.push_evidence(item);
            }
        }
    }
    Ok(live_articles)
}

async fn add_cross_analysis_id_and_link_ties(
    pool: &SqlitePool,
    acc: &mut GraphAcc,
) -> sqlx::Result<()> {
    let db_ids: Vec<(String, String, String)> = sqlx::query_as(
        "SELECT i.tracking_id, i.kind, a.outlet \
         FROM graph_article_ids i JOIN graph_articles a ON a.url = i.article_url",
    )
    .fetch_all(pool)
    .await?;

    let mut platform_ids: HashSet<String> = HashSet::new();
    let mut by_tid: BTreeMap<String, (String, BTreeSet<String>)> = BTreeMap::new();
    for (tid, kind, outlet) in db_ids {
        if is_hosted(&outlet) {
            platform_ids.insert(tid);
            continue;
        }
        by_tid
            .entry(tid)
            .or_insert_with(|| (kind, BTreeSet::new()))
            .1
            .insert(outlet);
    }
    for (tid, (kind, domains)) in by_tid {
        if platform_ids.contains(&tid) || domains.len() < 2 {
            continue;
        }
        let operators: HashSet<&str> = domains
            .iter()
            .filter_map(|d| acc.outlets.get(d).map(|o| o.operator.as_str()))
            .collect();
        if operators.len() > MAX_CARRIERS {
            continue;
        }
        let list: Vec<&String> = domains.iter().collect();
        for i in 0..list.len() {
            for j in (i + 1)..list.len() {
                let (a, b, _) = ordered_pair(list[i], list[j]);
                let slot = acc
                    .edges
                    .entry((a, b))
                    .or_default()
                    .entry(kind.clone())
                    .or_default();
                slot.keys_a.insert(tid.clone());
                slot.keys_b.insert(tid.clone());
                slot.push_evidence(json!({ "id": tid }));
            }
        }
    }

    let db_links: Vec<(String, String, String)> =
        sqlx::query_as("SELECT source_outlet, target_outlet, story_key FROM graph_article_links")
            .fetch_all(pool)
            .await?;
    for (src, dst, skey) in db_links {
        let (Some(so), Some(do_)) = (acc.outlets.get(&src), acc.outlets.get(&dst)) else {
            continue;
        };
        if so.operator == do_.operator {
            continue;
        }
        let (a, b, _) = ordered_pair(&src, &dst);
        let slot = acc
            .edges
            .entry((a, b))
            .or_default()
            .entry("link".into())
            .or_default();
        slot.keys_a.insert(skey.clone());
        slot.keys_b.insert(skey);
        slot.push_evidence(json!({ "from": src, "to": dst }));
    }
    Ok(())
}

fn add_cross_analysis_translation_ties(acc: &mut GraphAcc, articles: &[StoredArticle]) {
    for (i, x) in articles.iter().enumerate() {
        let Some(emb_x) = x.embedding.as_deref() else {
            continue;
        };
        let Some(ox) = acc.outlets.get(&x.outlet) else {
            continue;
        };
        if x.fact_check || is_official(&x.outlet) || is_not_copier(ox.outlet_type.as_deref()) {
            continue;
        }
        for y in &articles[(i + 1)..] {
            if x.outlet == y.outlet {
                continue;
            }
            let (Some(lx), Some(ly)) = (x.language.as_deref(), y.language.as_deref()) else {
                continue;
            };
            if lx == ly {
                continue;
            }
            if let (Some(px), Some(py)) = (x.published_at, y.published_at)
                && (px - py).num_days().abs() > WINDOW_DAYS
            {
                continue;
            }
            let Some(emb_y) = y.embedding.as_deref() else {
                continue;
            };
            let Some(oy) = acc.outlets.get(&y.outlet) else {
                continue;
            };
            if y.fact_check || is_official(&y.outlet) || is_not_copier(oy.outlet_type.as_deref()) {
                continue;
            }
            if emb_x.len() != emb_y.len() {
                continue;
            }
            let sim: f32 = emb_x.iter().zip(emb_y.iter()).map(|(u, v)| u * v).sum();
            if sim >= TRANSLATION_SIMILARITY {
                let (a, b, swapped) = ordered_pair(&x.outlet, &y.outlet);
                let (ua, ub) = if swapped {
                    (&y.url, &x.url)
                } else {
                    (&x.url, &y.url)
                };
                let slot = acc
                    .edges
                    .entry((a, b))
                    .or_default()
                    .entry("translation".into())
                    .or_default();
                slot.keys_a.insert(ua.clone());
                slot.keys_b.insert(ub.clone());
                let rounded = (f64::from(sim) * 1000.0).round() / 1000.0;
                slot.push_evidence(json!({ "a": ua, "b": ub, "similarity": rounded }));
            }
        }
    }
}

fn find_root(parent: &mut HashMap<String, String>, d: &str) -> String {
    let mut cur = d.to_owned();
    while parent[&cur] != cur {
        let gp = parent[&parent[&cur]].clone();
        parent.insert(cur.clone(), gp);
        cur = parent[&cur].clone();
    }
    cur
}

fn compute_clusters(acc: &GraphAcc) -> Vec<Vec<String>> {
    let domains: Vec<String> = acc.outlets.keys().cloned().collect();
    let mut parent: HashMap<String, String> =
        domains.iter().map(|d| (d.clone(), d.clone())).collect();

    for ((a, b), layers) in &acc.edges {
        if layer_strength(layers, true) >= CLUSTER_STRENGTH {
            let ra = find_root(&mut parent, a);
            let rb = find_root(&mut parent, b);
            parent.insert(ra, rb);
        }
    }

    let mut first_by_op: HashMap<String, String> = HashMap::new();
    for d in &domains {
        let op = &acc.outlets[d].operator;
        if !is_hosted(d) {
            let anchor = first_by_op
                .entry(op.clone())
                .or_insert_with(|| d.clone())
                .clone();
            let rd = find_root(&mut parent, d);
            let ra = find_root(&mut parent, &anchor);
            parent.insert(rd, ra);
        }
    }

    let mut grouped: HashMap<String, Vec<String>> = HashMap::new();
    for d in &domains {
        let r = find_root(&mut parent, d);
        grouped.entry(r).or_default().push(d.clone());
    }
    let mut groups: Vec<Vec<String>> = grouped
        .into_values()
        .filter(|g| g.len() > 1)
        .map(|mut g| {
            g.sort();
            g
        })
        .collect();
    groups.sort_by(|x, y| y.len().cmp(&x.len()).then_with(|| x.cmp(y)));
    groups
}

fn build_edges_json(acc: &GraphAcc) -> Vec<Value> {
    let mut by_op: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (d, node) in &acc.outlets {
        if !is_hosted(d) {
            by_op
                .entry(node.operator.clone())
                .or_default()
                .push(d.clone());
        }
    }
    let mut all_pairs: BTreeSet<(String, String)> = acc.edges.keys().cloned().collect();
    for group in by_op.values() {
        for i in 0..group.len() {
            for j in (i + 1)..group.len() {
                all_pairs.insert((group[i].clone(), group[j].clone()));
            }
        }
    }

    let empty = BTreeMap::new();
    let mut out_edges: Vec<(f64, f64, String, String, Value)> = Vec::with_capacity(all_pairs.len());
    for (a, b) in all_pairs {
        let same = !is_hosted(&a)
            && !is_hosted(&b)
            && acc.outlets[&a].operator == acc.outlets[&b].operator;
        let layers = acc.edges.get(&(a.clone(), b.clone())).unwrap_or(&empty);
        let s_all = if same {
            1.0
        } else {
            (layer_strength(layers, false) * 1000.0).round() / 1000.0
        };
        let s_coord = (layer_strength(layers, true) * 1000.0).round() / 1000.0;

        let mut layer_json = Vec::new();
        if same {
            layer_json.push(json!({ "kind": "same_operator" }));
        }
        for (kind, slot) in layers {
            let count = slot.count();
            if count > 0 {
                layer_json.push(json!({
                    "kind": kind,
                    "count": count,
                    "evidence": strongest_evidence(&slot.evidence),
                }));
            }
        }
        if layer_json.is_empty() {
            continue;
        }
        let obj = json!({
            "a": a,
            "b": b,
            "strength": s_all,
            "coordination": s_coord,
            "layers": layer_json,
        });
        out_edges.push((-s_coord, -s_all, a, b, obj));
    }
    out_edges.sort_by(|x, y| {
        x.0.total_cmp(&y.0)
            .then_with(|| x.1.total_cmp(&y.1))
            .then_with(|| x.2.cmp(&y.2))
            .then_with(|| x.3.cmp(&y.3))
    });
    out_edges.into_iter().map(|(_, _, _, _, v)| v).collect()
}

fn build_clusters_json(acc: &GraphAcc, cluster_groups: &[Vec<String>]) -> Vec<Value> {
    cluster_groups
        .iter()
        .enumerate()
        .map(|(idx, group)| {
            let mut kinds: BTreeSet<String> = BTreeSet::new();
            for i in 0..group.len() {
                for j in (i + 1)..group.len() {
                    let a = &group[i];
                    let b = &group[j];
                    if !is_hosted(a)
                        && !is_hosted(b)
                        && acc.outlets[a].operator == acc.outlets[b].operator
                    {
                        kinds.insert("same_operator".into());
                    }
                    if let Some(layers) = acc.edges.get(&(a.clone(), b.clone()))
                        && layer_strength(layers, true) >= CLUSTER_STRENGTH
                    {
                        for (k, slot) in layers {
                            if slot.count() > 0
                                && matches!(
                                    k.as_str(),
                                    "analytics_id" | "ad_account" | "copy" | "translation"
                                )
                            {
                                kinds.insert(k.clone());
                            }
                        }
                    }
                }
            }
            let listed = group
                .iter()
                .filter(|d| acc.outlets[*d].known_network.is_some())
                .count();
            json!({
                "id": idx + 1,
                "outlets": group,
                "listed": listed,
                "joined_by": kinds.into_iter().collect::<Vec<_>>(),
            })
        })
        .collect()
}

/// Builds the full `/api/graph` JSON payload, or `None` when neither SQLite nor `seed_path` has data.
pub async fn build_graph(pool: &SqlitePool, seed_path: &Path) -> anyhow::Result<Option<Value>> {
    let (live_story_count,): (i64,) = sqlx::query_as("SELECT COUNT(*) FROM graph_ingested_stories")
        .fetch_one(pool)
        .await?;

    let seed_json: Option<Value> = match tokio::fs::read(seed_path).await {
        Ok(bytes) => Some(serde_json::from_slice(&bytes)?),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
        Err(e) => return Err(anyhow::Error::from(e)),
    };

    if live_story_count == 0 {
        return Ok(seed_json);
    }

    let mut acc = load_seed_acc(seed_json.as_ref());
    let live_articles = load_live_nodes_and_ties(pool, &mut acc).await?;
    add_cross_analysis_id_and_link_ties(pool, &mut acc).await?;
    add_cross_analysis_translation_ties(&mut acc, &live_articles);

    let cluster_groups = compute_clusters(&acc);
    let mut cluster_of: HashMap<String, usize> = HashMap::new();
    for (idx, group) in cluster_groups.iter().enumerate() {
        for d in group {
            cluster_of.insert(d.clone(), idx + 1);
        }
    }

    let edges_json = build_edges_json(&acc);
    let clusters_json = build_clusters_json(&acc, &cluster_groups);
    let outlets_json: Vec<Value> = acc
        .outlets
        .values()
        .map(|o| {
            let articles_count = o.seed_articles + o.live_articles.len();
            let analysed_count = o.seed_analysed + o.live_analysed.len();
            json!({
                "domain": o.domain,
                "operator": o.operator,
                "outlet_type": o.outlet_type,
                "country": o.country,
                "known_network": o.known_network,
                "articles": articles_count,
                "analysed": analysed_count,
                "cluster": cluster_of.get(&o.domain),
            })
        })
        .collect();

    let live_stories = usize::try_from(live_story_count).unwrap_or(0);
    let total_analyses = acc.seed_analyses + live_stories;
    let total_articles = acc.seed_articles + live_articles.len();

    let mut payload = json!({
        "built_at": Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true),
        "counts": {
            "analyses": total_analyses,
            "articles": total_articles,
            "outlets": outlets_json.len(),
            "edges": edges_json.len(),
            "clusters": clusters_json.len(),
        },
        "outlets": outlets_json,
        "edges": edges_json,
        "clusters": clusters_json,
    });
    if let Some(eval) = acc.evaluation
        && let Some(obj) = payload.as_object_mut()
    {
        obj.insert("evaluation".into(), eval);
    }
    Ok(Some(payload))
}

/// Detail view of a single outlet (`GET /api/graph/outlets/{domain}`).
pub async fn build_outlet_detail(
    pool: &SqlitePool,
    seed_path: &Path,
    raw_domain: &str,
) -> anyhow::Result<Option<Value>> {
    let domain = raw_domain
        .trim()
        .to_ascii_lowercase()
        .trim_start_matches("www.")
        .to_owned();
    let Some(graph) = build_graph(pool, seed_path).await? else {
        return Ok(None);
    };
    let Some(outlet) = graph
        .get("outlets")
        .and_then(Value::as_array)
        .and_then(|arr| {
            arr.iter()
                .find(|o| o.get("domain").and_then(Value::as_str) == Some(domain.as_str()))
        })
        .cloned()
    else {
        return Ok(None);
    };

    let cluster = outlet
        .get("cluster")
        .and_then(Value::as_u64)
        .and_then(|cid| {
            graph
                .get("clusters")
                .and_then(Value::as_array)?
                .iter()
                .find(|c| c.get("id").and_then(Value::as_u64) == Some(cid))
                .cloned()
        });

    let ties: Vec<Value> =
        graph
            .get("edges")
            .and_then(Value::as_array)
            .map_or_else(Vec::new, |arr| {
                arr.iter()
                    .filter(|e| {
                        e.get("a").and_then(Value::as_str) == Some(domain.as_str())
                            || e.get("b").and_then(Value::as_str) == Some(domain.as_str())
                    })
                    .cloned()
                    .collect()
            });

    Ok(Some(json!({
        "outlet": outlet,
        "cluster": cluster,
        "ties": ties,
    })))
}
