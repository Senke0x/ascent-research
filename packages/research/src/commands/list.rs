use serde_json::json;
use std::fs;

use crate::output::Envelope;
use crate::session::{config, event::SessionEvent, layout, log};

const CMD: &str = "research list";

pub fn run() -> Envelope {
    let root = layout::research_root();
    if !root.exists() {
        return Envelope::ok(CMD, json!({ "sessions": [] }));
    }

    let entries = match fs::read_dir(&root) {
        Ok(e) => e,
        Err(e) => return Envelope::fail(CMD, "IO_ERROR", format!("read root: {e}")),
    };

    let mut sessions = Vec::new();
    for ent in entries.flatten() {
        let path = ent.path();
        if !path.is_dir() {
            continue;
        }
        let slug = match path.file_name().and_then(|s| s.to_str()) {
            Some(s) if !s.starts_with('.') => s.to_string(),
            _ => continue,
        };
        if !config::exists(&slug) {
            continue;
        }
        let cfg = match config::read(&slug) {
            Ok(c) => c,
            Err(_) => continue,
        };
        let source_count = log::read_all(&slug)
            .map(|events| {
                events
                    .iter()
                    .filter(|e| matches!(e, SessionEvent::SourceAccepted { .. }))
                    .count() as u32
            })
            .unwrap_or(0);
        let status = if cfg.is_closed() { "closed" } else { "open" };
        sessions.push(json!({
            "slug": cfg.slug,
            "topic": cfg.topic,
            "preset": cfg.preset,
            "created_at": cfg.created_at,
            "source_count": source_count,
            "status": status,
        }));
    }

    Envelope::ok(CMD, json!({ "sessions": sessions }))
}
