//! TOML preset schema + matcher + classify().
//!
//! ## Preset file schema
//!
//! ```toml
//! name = "tech"
//! description = "..."
//!
//! [[rule]]
//! kind = "hn-item"
//! host = "news.ycombinator.com"
//! path = "/item"                          # OR path_any_of = [...] OR path_segments = [...]
//! query_param = { id = "[0-9]+" }         # optional; each value is a Rust regex,
//!                                          # implicitly anchored to full value
//! executor = "postagent"                  # or "browser"
//! template = 'postagent send --anonymous "..."'
//!
//! [fallback]
//! executor = "browser"
//! kind = "browser-fallback"
//! template = "..."
//! ```
//!
//! Placeholders in `template` may be drawn from:
//! - `{url}`, `{host}`, `{path}` (universal)
//! - path_segments captures like `{owner}` `{repo}` `{num}` `{id}`
//! - query_param keys
//!
//! Any unbound placeholder in template = PLACEHOLDER_UNBOUND at load time.

use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

// ── Schema ──────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Preset {
    pub name: String,
    #[serde(default)]
    pub description: String,
    #[serde(default, rename = "rule")]
    pub rules: Vec<RuleSpec>,
    pub fallback: FallbackSpec,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuleSpec {
    pub kind: String,
    pub host: String,
    #[serde(default)]
    pub path: Option<String>,
    #[serde(default)]
    pub path_any_of: Option<Vec<String>>,
    #[serde(default)]
    pub path_segments: Option<Vec<String>>,
    #[serde(default)]
    pub query_param: Option<HashMap<String, String>>,
    pub executor: String,
    pub template: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FallbackSpec {
    pub kind: String,
    pub executor: String,
    pub template: String,
}

// ── Compiled preset (post-validation) ───────────────────────────────────────

#[derive(Debug, Clone)]
pub struct CompiledPreset {
    pub name: String,
    pub rules: Vec<CompiledRule>,
    pub fallback: FallbackSpec,
}

#[derive(Debug, Clone)]
pub struct CompiledRule {
    pub kind: String,
    pub host: String,
    pub path_matcher: PathMatcher,
    pub query_regexes: Vec<(String, Regex)>,
    pub executor: String,
    pub template: String,
}

#[derive(Debug, Clone)]
pub enum PathMatcher {
    Exact(String),
    AnyOf(Vec<String>),
    Segments(Vec<SegmentPattern>),
}

#[derive(Debug, Clone)]
pub enum SegmentPattern {
    Literal(String),
    /// Placeholder like `{owner}` — captures the segment by this name.
    Capture(String),
}

// ── Classify result ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Executor {
    Postagent,
    Browser,
}

impl Executor {
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "postagent" => Some(Executor::Postagent),
            "browser" => Some(Executor::Browser),
            _ => None,
        }
    }
    pub fn as_str(&self) -> &'static str {
        match self {
            Executor::Postagent => "postagent",
            Executor::Browser => "browser",
        }
    }
}

#[derive(Debug, Clone)]
pub struct Route {
    pub executor: Executor,
    pub kind: String,
    pub command_template: String,
    pub url: String,
}

#[derive(Debug, Clone)]
pub enum Classification {
    Matched(Route),
    Fallback(Route),
    Forced(Route),
}

impl Classification {
    pub fn route(&self) -> &Route {
        match self {
            Classification::Matched(r) | Classification::Fallback(r) | Classification::Forced(r) => r,
        }
    }
}

// ── Preset errors ───────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum PresetSubCode {
    FileNotFound,
    TomlSyntax,
    SchemaInvalid,
    PlaceholderUnbound,
}

impl PresetSubCode {
    pub fn as_str(&self) -> &'static str {
        match self {
            PresetSubCode::FileNotFound => "FILE_NOT_FOUND",
            PresetSubCode::TomlSyntax => "TOML_SYNTAX",
            PresetSubCode::SchemaInvalid => "SCHEMA_INVALID",
            PresetSubCode::PlaceholderUnbound => "PLACEHOLDER_UNBOUND",
        }
    }
}

#[derive(Debug, Clone)]
pub struct PresetError {
    pub sub_code: PresetSubCode,
    pub message: String,
    pub path: Option<String>,
}

impl std::fmt::Display for PresetError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match &self.path {
            Some(p) => write!(f, "[{}] {} ({})", self.sub_code.as_str(), self.message, p),
            None => write!(f, "[{}] {}", self.sub_code.as_str(), self.message),
        }
    }
}
impl std::error::Error for PresetError {}

// ── Loading ─────────────────────────────────────────────────────────────────

const BUILTIN_TECH: &str = include_str!("../../../../presets/tech.toml");

/// Load and compile a preset, honoring resolution order:
/// 1. `rules_path` (explicit file) if provided
/// 2. Otherwise, `preset` name:
///    a. `~/.actionbook/research/presets/<name>.toml` (user override)
///    b. built-in (currently only "tech" shipped embedded)
pub fn load_preset(
    preset: Option<&str>,
    rules_path: Option<&Path>,
) -> Result<CompiledPreset, PresetError> {
    if let Some(path) = rules_path {
        let text = std::fs::read_to_string(path).map_err(|e| PresetError {
            sub_code: PresetSubCode::FileNotFound,
            message: format!("cannot open rules file: {e}"),
            path: Some(path.display().to_string()),
        })?;
        return parse_and_compile(&text, Some(path.display().to_string()));
    }

    let name = preset.unwrap_or("tech");

    // user override lookup
    if let Some(home) = dirs::home_dir() {
        let user_path = home
            .join(".actionbook/research/presets")
            .join(format!("{name}.toml"));
        if user_path.exists() {
            let text = std::fs::read_to_string(&user_path).map_err(|e| PresetError {
                sub_code: PresetSubCode::FileNotFound,
                message: format!("cannot read user preset: {e}"),
                path: Some(user_path.display().to_string()),
            })?;
            return parse_and_compile(&text, Some(user_path.display().to_string()));
        }
    }

    // built-in
    match name {
        "tech" => parse_and_compile(BUILTIN_TECH, Some("<builtin:tech>".to_string())),
        other => Err(PresetError {
            sub_code: PresetSubCode::FileNotFound,
            message: format!("no preset named '{other}' (ship your own TOML with --rules)"),
            path: None,
        }),
    }
}

fn parse_and_compile(text: &str, src: Option<String>) -> Result<CompiledPreset, PresetError> {
    let p: Preset = toml::from_str(text).map_err(|e| PresetError {
        sub_code: PresetSubCode::TomlSyntax,
        message: format!("{e}"),
        path: src.clone(),
    })?;
    compile(p, src)
}

fn compile(p: Preset, src: Option<String>) -> Result<CompiledPreset, PresetError> {
    let mut compiled_rules = Vec::with_capacity(p.rules.len());
    for (idx, r) in p.rules.iter().enumerate() {
        let compiled = compile_rule(r, idx, src.as_deref())?;
        compiled_rules.push(compiled);
    }
    Ok(CompiledPreset {
        name: p.name,
        rules: compiled_rules,
        fallback: p.fallback,
    })
}

fn compile_rule(
    r: &RuleSpec,
    idx: usize,
    src: Option<&str>,
) -> Result<CompiledRule, PresetError> {
    // Validate path-matcher kind
    let matcher_specified = [r.path.is_some(), r.path_any_of.is_some(), r.path_segments.is_some()]
        .iter()
        .filter(|x| **x)
        .count();
    if matcher_specified != 1 {
        return Err(PresetError {
            sub_code: PresetSubCode::SchemaInvalid,
            message: format!(
                "rule[{idx}] (kind={}) must specify exactly one of path / path_any_of / path_segments",
                r.kind
            ),
            path: src.map(String::from),
        });
    }
    let path_matcher = if let Some(p) = &r.path {
        PathMatcher::Exact(p.clone())
    } else if let Some(any) = &r.path_any_of {
        PathMatcher::AnyOf(any.clone())
    } else {
        let segs: Vec<SegmentPattern> = r
            .path_segments
            .as_ref()
            .unwrap()
            .iter()
            .map(|s| {
                if s.starts_with('{') && s.ends_with('}') {
                    SegmentPattern::Capture(s[1..s.len() - 1].to_string())
                } else {
                    SegmentPattern::Literal(s.clone())
                }
            })
            .collect();
        PathMatcher::Segments(segs)
    };

    // Compile query regexes (implicit ^...$)
    let mut query_regexes = Vec::new();
    if let Some(qs) = &r.query_param {
        for (k, pat) in qs {
            let anchored = format!("^(?:{pat})$");
            let re = Regex::new(&anchored).map_err(|e| PresetError {
                sub_code: PresetSubCode::SchemaInvalid,
                message: format!("rule[{idx}] (kind={}) query_param.{k}: invalid regex: {e}", r.kind),
                path: src.map(String::from),
            })?;
            query_regexes.push((k.clone(), re));
        }
    }

    // Placeholder binding check
    let bound = bound_placeholders(&path_matcher, &query_regexes);
    let used = extract_placeholders(&r.template);
    for placeholder in &used {
        if !bound.contains(placeholder) && !is_universal(placeholder) {
            return Err(PresetError {
                sub_code: PresetSubCode::PlaceholderUnbound,
                message: format!(
                    "rule[{idx}] (kind={}) template has `{{{placeholder}}}` but it isn't in \
                    path_segments, query_param, or universal {{url,host,path}}",
                    r.kind
                ),
                path: src.map(String::from),
            });
        }
    }

    if Executor::parse(&r.executor).is_none() {
        return Err(PresetError {
            sub_code: PresetSubCode::SchemaInvalid,
            message: format!(
                "rule[{idx}] (kind={}) executor must be 'postagent' or 'browser', got '{}'",
                r.kind, r.executor
            ),
            path: src.map(String::from),
        });
    }

    Ok(CompiledRule {
        kind: r.kind.clone(),
        host: r.host.to_lowercase(),
        path_matcher,
        query_regexes,
        executor: r.executor.clone(),
        template: r.template.clone(),
    })
}

fn bound_placeholders(
    path: &PathMatcher,
    queries: &[(String, Regex)],
) -> std::collections::HashSet<String> {
    let mut set = std::collections::HashSet::new();
    if let PathMatcher::Segments(segs) = path {
        for s in segs {
            if let SegmentPattern::Capture(name) = s {
                set.insert(name.clone());
            }
        }
    }
    for (k, _) in queries {
        set.insert(k.clone());
    }
    set
}

fn extract_placeholders(template: &str) -> Vec<String> {
    let mut out = Vec::new();
    let bytes = template.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'{' {
            if let Some(end) = bytes[i + 1..].iter().position(|&b| b == b'}') {
                let name = &template[i + 1..i + 1 + end];
                if !name.is_empty() && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
                    out.push(name.to_string());
                }
                i += end + 2;
                continue;
            }
        }
        i += 1;
    }
    out
}

fn is_universal(name: &str) -> bool {
    matches!(name, "url" | "host" | "path")
}

// ── URL parsing (minimal; http/https only) ──────────────────────────────────

#[derive(Debug, Clone)]
pub struct ParsedUrl {
    pub host: String,
    pub path: String,
    pub query: String,
}

impl ParsedUrl {
    pub fn parse(url: &str) -> Option<Self> {
        let url = url.trim();
        let rest = url
            .strip_prefix("https://")
            .or_else(|| url.strip_prefix("http://"))?;
        let (authority_and_path, query) = match rest.split_once('?') {
            Some((prefix, q)) => (prefix, q.to_string()),
            None => (rest, String::new()),
        };
        let authority_and_path = authority_and_path.split('#').next().unwrap_or("");
        let (authority, path_raw) = match authority_and_path.find('/') {
            Some(i) => (&authority_and_path[..i], &authority_and_path[i..]),
            None => (authority_and_path, ""),
        };
        if authority.is_empty() {
            return None;
        }
        let host = authority.rsplit_once('@').map_or(authority, |(_, h)| h);
        let host = host.split(':').next().unwrap_or(host);
        Some(ParsedUrl {
            host: host.to_ascii_lowercase(),
            path: path_raw.to_string(),
            query,
        })
    }

    pub fn first_query_value(&self, key: &str) -> Option<&str> {
        for pair in self.query.split('&') {
            if let Some((k, v)) = pair.split_once('=')
                && k == key
            {
                return Some(v);
            }
        }
        None
    }
}

// ── Classification ──────────────────────────────────────────────────────────

/// Classify a URL against a compiled preset.
pub fn classify(
    preset: &CompiledPreset,
    url: &str,
    prefer_browser: bool,
) -> Result<Classification, String> {
    let parsed = ParsedUrl::parse(url).ok_or_else(|| format!("cannot parse '{url}' as http(s) URL"))?;

    if prefer_browser {
        let route = Route {
            executor: Executor::Browser,
            kind: "browser-forced".into(),
            command_template: interpolate(&preset.fallback.template, &url_to_map(url, &parsed, &HashMap::new())),
            url: url.into(),
        };
        return Ok(Classification::Forced(route));
    }

    for rule in &preset.rules {
        if let Some(captures) = match_rule(rule, &parsed) {
            let tpl_map = url_to_map(url, &parsed, &captures);
            let route = Route {
                executor: Executor::parse(&rule.executor).expect("validated at load"),
                kind: rule.kind.clone(),
                command_template: interpolate(&rule.template, &tpl_map),
                url: url.into(),
            };
            return Ok(Classification::Matched(route));
        }
    }

    let route = Route {
        executor: Executor::parse(&preset.fallback.executor)
            .ok_or_else(|| "fallback executor must be postagent or browser".to_string())?,
        kind: preset.fallback.kind.clone(),
        command_template: interpolate(
            &preset.fallback.template,
            &url_to_map(url, &parsed, &HashMap::new()),
        ),
        url: url.into(),
    };
    Ok(Classification::Fallback(route))
}

fn match_rule(rule: &CompiledRule, parsed: &ParsedUrl) -> Option<HashMap<String, String>> {
    if parsed.host != rule.host {
        return None;
    }
    // path
    let mut caps = HashMap::new();
    match &rule.path_matcher {
        PathMatcher::Exact(p) => {
            if &parsed.path != p {
                return None;
            }
        }
        PathMatcher::AnyOf(list) => {
            if !list.iter().any(|p| *p == parsed.path) {
                return None;
            }
        }
        PathMatcher::Segments(patterns) => {
            let segs: Vec<&str> = parsed
                .path
                .trim_matches('/')
                .split('/')
                .filter(|s| !s.is_empty())
                .collect();
            if segs.len() != patterns.len() {
                return None;
            }
            for (pat, seg) in patterns.iter().zip(segs.iter()) {
                match pat {
                    SegmentPattern::Literal(lit) => {
                        if lit != seg {
                            return None;
                        }
                    }
                    SegmentPattern::Capture(name) => {
                        caps.insert(name.clone(), (*seg).to_string());
                    }
                }
            }
        }
    }

    // query_param
    for (key, re) in &rule.query_regexes {
        let val = parsed.first_query_value(key)?;
        if !re.is_match(val) {
            return None;
        }
        caps.insert(key.clone(), val.to_string());
    }

    Some(caps)
}

fn url_to_map(
    url: &str,
    parsed: &ParsedUrl,
    captures: &HashMap<String, String>,
) -> HashMap<String, String> {
    let mut m = HashMap::new();
    m.insert("url".into(), url.into());
    m.insert("host".into(), parsed.host.clone());
    m.insert("path".into(), parsed.path.clone());
    for (k, v) in captures {
        m.insert(k.clone(), v.clone());
    }
    m
}

fn interpolate(template: &str, vars: &HashMap<String, String>) -> String {
    let mut out = String::with_capacity(template.len());
    let bytes = template.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'{' {
            if let Some(end) = bytes[i + 1..].iter().position(|&b| b == b'}') {
                let name = &template[i + 1..i + 1 + end];
                if let Some(val) = vars.get(name) {
                    out.push_str(val);
                    i += end + 2;
                    continue;
                }
            }
        }
        out.push(bytes[i] as char);
        i += 1;
    }
    out
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn tech() -> CompiledPreset {
        load_preset(Some("tech"), None).expect("builtin tech must load")
    }

    #[test]
    fn builtin_tech_loads() {
        let p = tech();
        assert_eq!(p.name, "tech");
        assert!(!p.rules.is_empty());
    }

    #[test]
    fn hn_item_route() {
        let c = classify(&tech(), "https://news.ycombinator.com/item?id=12345", false).unwrap();
        let r = c.route();
        assert_eq!(r.executor, Executor::Postagent);
        assert_eq!(r.kind, "hn-item");
        assert!(r.command_template.contains("/v0/item/12345.json"));
    }

    #[test]
    fn hn_item_non_numeric_id_falls_back() {
        let c = classify(&tech(), "https://news.ycombinator.com/item?id=abc", false).unwrap();
        assert_eq!(c.route().executor, Executor::Browser);
    }

    #[test]
    fn hn_topstories_routes() {
        for url in [
            "https://news.ycombinator.com/",
            "https://news.ycombinator.com/news",
        ] {
            let c = classify(&tech(), url, false).unwrap();
            assert_eq!(c.route().kind, "hn-topstories", "for {url}");
        }
    }

    #[test]
    fn github_repo_readme() {
        let c = classify(&tech(), "https://github.com/bytedance/monoio", false).unwrap();
        assert_eq!(c.route().kind, "github-repo-readme");
        assert!(c.route().command_template.contains("/repos/bytedance/monoio/readme"));
    }

    #[test]
    fn github_issue() {
        let c = classify(&tech(), "https://github.com/tokio-rs/tokio/issues/8056", false).unwrap();
        assert_eq!(c.route().kind, "github-issue");
        assert!(c.route().command_template.contains("/repos/tokio-rs/tokio/issues/8056"));
    }

    #[test]
    fn arxiv_abs() {
        let c = classify(&tech(), "https://arxiv.org/abs/2601.12345", false).unwrap();
        assert_eq!(c.route().kind, "arxiv-abs");
        assert!(c.route().command_template.contains("id_list=2601.12345"));
    }

    #[test]
    fn unknown_falls_back() {
        let c = classify(&tech(), "https://corrode.dev/blog/async/", false).unwrap();
        assert!(matches!(c, Classification::Fallback(_)));
        assert_eq!(c.route().executor, Executor::Browser);
        assert_eq!(c.route().kind, "browser-fallback");
    }

    #[test]
    fn prefer_browser_forces() {
        let c = classify(&tech(), "https://github.com/foo/bar", true).unwrap();
        assert!(matches!(c, Classification::Forced(_)));
        assert_eq!(c.route().kind, "browser-forced");
    }

    #[test]
    fn invalid_url_errors() {
        let err = classify(&tech(), "not-a-url", false).unwrap_err();
        assert!(err.contains("cannot parse"));
    }

    #[test]
    fn placeholder_unbound_fails_load() {
        let bad = r#"
name = "bad"
[[rule]]
kind = "x"
host = "example.com"
path = "/x"
executor = "postagent"
template = "echo {missing}"
[fallback]
kind = "fb"
executor = "browser"
template = "fb"
"#;
        let err = parse_and_compile(bad, Some("test".into())).unwrap_err();
        assert_eq!(err.sub_code, PresetSubCode::PlaceholderUnbound);
    }

    #[test]
    fn toml_syntax_error() {
        let err = parse_and_compile("this is not = valid = toml\n[[", None).unwrap_err();
        assert_eq!(err.sub_code, PresetSubCode::TomlSyntax);
    }

    #[test]
    fn schema_invalid_missing_path_matcher() {
        let bad = r#"
name = "bad"
[[rule]]
kind = "x"
host = "example.com"
executor = "postagent"
template = "echo"
[fallback]
kind = "fb"
executor = "browser"
template = "fb"
"#;
        let err = parse_and_compile(bad, None).unwrap_err();
        assert_eq!(err.sub_code, PresetSubCode::SchemaInvalid);
    }

    #[test]
    fn file_not_found() {
        let err = load_preset(None, Some(Path::new("/no/such/path.toml"))).unwrap_err();
        assert_eq!(err.sub_code, PresetSubCode::FileNotFound);
    }

    #[test]
    fn universal_placeholders_always_bound() {
        let p = r#"
name = "uni"
[[rule]]
kind = "k"
host = "example.com"
path = "/p"
executor = "browser"
template = 'fetch "{url}" host={host} path={path}'
[fallback]
kind = "fb"
executor = "browser"
template = "fb"
"#;
        let preset = parse_and_compile(p, None).unwrap();
        let c = classify(&preset, "https://example.com/p", false).unwrap();
        let tpl = &c.route().command_template;
        assert!(tpl.contains("fetch \"https://example.com/p\""));
        assert!(tpl.contains("host=example.com"));
        assert!(tpl.contains("path=/p"));
    }
}
