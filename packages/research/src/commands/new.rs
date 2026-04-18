use chrono::Utc;
use serde_json::json;
use std::fs;

use crate::output::Envelope;
use crate::session::{active, config, event::SessionEvent, layout, log, md_template, slug as slugmod};

const CMD: &str = "research new";

pub fn run(topic: &str, preset: Option<&str>, slug_override: Option<&str>, force: bool) -> Envelope {
    let preset = preset.unwrap_or("tech").to_string();
    let root = layout::research_root();
    if let Err(e) = fs::create_dir_all(&root) {
        return Envelope::fail(CMD, "IO_ERROR", format!("create research root: {e}"));
    }

    let resolved = match slugmod::resolve_slug(topic, slug_override, &root) {
        Ok(s) => s,
        Err(slugmod::SlugError::Exists) if force && slug_override.is_some() => {
            let s = slug_override.unwrap().to_string();
            if let Err(e) = fs::remove_dir_all(root.join(&s)) {
                return Envelope::fail(CMD, "IO_ERROR", format!("remove existing {s}: {e}"));
            }
            s
        }
        Err(slugmod::SlugError::Exists) => {
            return Envelope::fail(
                CMD,
                "SLUG_EXISTS",
                format!(
                    "slug '{}' already exists — pass --force to overwrite or omit --slug to auto-derive",
                    slug_override.unwrap_or("")
                ),
            )
            .with_context(json!({ "slug": slug_override }));
        }
        Err(slugmod::SlugError::Invalid(msg)) => {
            return Envelope::fail(CMD, "INVALID_ARGUMENT", msg);
        }
    };

    let dir = layout::session_dir(&resolved);
    if let Err(e) = fs::create_dir_all(layout::session_raw_dir(&resolved)) {
        return Envelope::fail(CMD, "IO_ERROR", format!("create session dir: {e}"));
    }

    let cfg = config::SessionConfig::new(resolved.clone(), topic, preset.clone());
    if let Err(e) = config::write(&resolved, &cfg) {
        let _ = fs::remove_dir_all(&dir);
        return Envelope::fail(CMD, "IO_ERROR", format!("write session.toml: {e}"));
    }

    let md = md_template::render(topic, &preset);
    if let Err(e) = fs::write(layout::session_md(&resolved), md) {
        let _ = fs::remove_dir_all(&dir);
        return Envelope::fail(CMD, "IO_ERROR", format!("write session.md: {e}"));
    }

    let ev = SessionEvent::SessionCreated {
        timestamp: Utc::now(),
        slug: resolved.clone(),
        topic: topic.to_string(),
        preset: preset.clone(),
        session_dir_abs: dir
            .canonicalize()
            .unwrap_or(dir.clone())
            .to_string_lossy()
            .into_owned(),
        note: None,
    };
    if let Err(e) = log::append(&resolved, &ev) {
        let _ = fs::remove_dir_all(&dir);
        return Envelope::fail(CMD, "IO_ERROR", format!("append session_created: {e}"));
    }

    if let Err(e) = active::set_active(&resolved) {
        return Envelope::fail(CMD, "IO_ERROR", format!("set active: {e}"));
    }

    Envelope::ok(
        CMD,
        json!({
            "slug": resolved,
            "session_dir": dir.to_string_lossy(),
            "topic": topic,
            "preset": preset,
            "active": true,
        }),
    )
    .with_context(json!({ "session": resolved }))
}
