// Copyright (c) 2019 DDN. All rights reserved.
// Use of this source code is governed by a MIT-style
// license that can be found in the LICENSE file.

use crate::{
    action_plugins::{manage_stratagem::StratagemData, AgentResult},
    agent_error::{ImlAgentError, NoPluginError, Result},
    daemon_plugins::{action_runner, stratagem},
};
use futures::{future, Future};
use std::collections::HashMap;

/// Valid input types
/// for `DaemonPlugin`s
#[derive(Debug, serde::Deserialize)]
#[serde(untagged)]
pub enum Input {
    Action(action_runner::Action),
}

/// Valid output types
/// for `DaemonPlugin`s.
#[derive(Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(untagged)]
pub enum Output {
    String(String),
    Stratagem(StratagemData),
}

/// Plugin interface for extensible behavior
/// between the agent and manager.
///
/// Maintains internal state and sends and receives messages.
///
/// Implementors of this trait should add themselves
/// to the `plugin_registry` below.
pub trait DaemonPlugin: std::fmt::Debug {
    /// Returns full listing of information upon session esablishment
    fn start_session(&self) -> Box<Future<Item = Option<Output>, Error = ImlAgentError> + Send> {
        Box::new(future::ok(None))
    }
    ///  Return information needed to maintain a manager-agent session, i.e. what
    /// has changed since the start of the session or since the last update.
    ///
    /// If you need to refer to any data from the start_session call, you can
    /// store it as property on this DaemonPlugin instance.
    ///
    /// This will never be called concurrently with respect to start_session, or
    /// before start_session.
    fn update_session(&self) -> Box<Future<Item = Option<Output>, Error = ImlAgentError> + Send> {
        self.start_session()
    }
    /// Handle a message sent from the manager (may be called concurrently with respect to
    /// start_session and update_session).
    fn on_message(
        &mut self,
        _body: Input,
    ) -> Box<Future<Item = AgentResult, Error = ImlAgentError> + Send> {
        Box::new(future::ok(AgentResult::default()))
    }
    fn teardown(&mut self) -> Result<()> {
        Ok(())
    }
}

pub type DaemonBox = Box<DaemonPlugin + Send + Sync>;

#[derive(Eq, PartialEq, Hash, Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(transparent)]
pub struct PluginName(pub String);

type Callback = Box<Fn() -> DaemonBox + Send + Sync>;

fn mk_callback<D: 'static>(f: &'static (impl Fn() -> D + Sync)) -> Callback
where
    D: DaemonPlugin + Send + Sync,
{
    Box::new(move || Box::new(f()) as DaemonBox)
}

pub type DaemonPlugins = HashMap<PluginName, Callback>;

/// Returns a `HashMap` of plugins available for usage.
pub fn plugin_registry() -> DaemonPlugins {
    let mut hm = HashMap::new();

    hm.insert(
        PluginName("stratagem".into()),
        mk_callback(&stratagem::create),
    );

    hm.insert(
        PluginName("action_runner".into()),
        mk_callback(&action_runner::create),
    );

    hm
}

/// Get a plugin instance, if it exists
///
/// # Arguments
///
/// * `name` - The plugin to instantiate
/// * `registry` - Plugin registry to use
pub fn get_plugin(name: &PluginName, registry: &DaemonPlugins) -> Result<DaemonBox> {
    match registry.get(name) {
        Some(f) => Ok(f()),
        None => Err(NoPluginError(name.clone()).into()),
    }
}
