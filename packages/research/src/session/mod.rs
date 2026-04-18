//! Session state: on-disk layout, slug rules, event log schema, active pointer.
//!
//! No subprocess invocations, no network. Pure filesystem operations
//! and data-shape definitions. `commands::*` builds on top of this layer.

pub mod active;
pub mod event;
pub mod layout;
pub mod slug;
