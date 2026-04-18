//! Initial session.md template generation.
//!
//! Must emit the canonical `SOURCES_START_MARKER` / `SOURCES_END_MARKER`
//! pair between a `## Sources` heading; subsequent `research add` rewrites
//! the content between markers and must find them intact.

use super::layout::{SOURCES_END_MARKER, SOURCES_START_MARKER};

pub fn render(topic: &str, preset: &str) -> String {
    format!(
        "# Research: {topic}\n\
         \n\
         ## Objective\n\
         <!-- fill in before synthesize -->\n\
         \n\
         ## Preset\n\
         {preset}\n\
         \n\
         ## Sources\n\
         {SOURCES_START_MARKER}\n\
         _(auto-managed by `research add` — do not hand-edit between markers)_\n\
         {SOURCES_END_MARKER}\n\
         \n\
         ## Overview\n\
         <!-- required by `research synthesize`; describe the main story here -->\n\
         \n\
         ## Findings\n\
         <!-- `### Title` + body, one heading per finding -->\n\
         \n\
         ## Notes\n\
         <!-- free-form prose; become the Detailed Analysis section -->\n\
         "
    )
}

#[cfg(test)]
mod tests {
    use super::super::layout::locate_sources_block;
    use super::*;

    #[test]
    fn template_contains_both_markers() {
        let md = render("Some Topic", "tech");
        assert!(md.contains("# Research: Some Topic"));
        assert!(md.contains("## Preset"));
        assert!(md.contains("tech"));
        let range = locate_sources_block(&md).unwrap();
        assert!(!md[range].is_empty());
    }
}
