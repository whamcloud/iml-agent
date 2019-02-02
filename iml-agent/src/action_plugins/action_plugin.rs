// Copyright (c) 2019 DDN. All rights reserved.
// Use of this source code is governed by a MIT-style
// license that can be found in the LICENSE file.

use crate::{
    action_plugins::manage_stratagem,
    agent_error::{ImlAgentError, Result},
};
use futures::{future::IntoFuture, Future};
use std::collections::HashMap;

// The following fns are ported from
// https://github.com/whamcloud/iml-common/blob/5617e9c89a3a5d2f02f499a3497035faf942bf1d/iml_common/lib/agent_rpc.py#L6-L38
// They represent the interface expected from action plugins.
static AGENT_RPC_WRAPPER_VERSION: i8 = 1;

#[derive(serde::Serialize)]
pub enum AgentResult {
    AgentOk {
        wrapper_version: i8,
        result: Box<erased_serde::Serialize + Send>,
    },
    AgentErr {
        wrapper_version: i8,
        error: String,
    },
}

impl std::fmt::Debug for AgentResult {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            AgentResult::AgentOk {
                wrapper_version,
                result,
            } => write!(
                f,
                "AgentOk {{ wrapper_version: {:?}, result: {:?} }}",
                wrapper_version,
                serde_json::to_string_pretty(&result)
            ),
            AgentResult::AgentErr {
                wrapper_version,
                error,
            } => write!(
                f,
                "AgentErr {{ wrapper_version: {:?}, error: {:?} }}",
                wrapper_version, error
            ),
        }
    }
}

impl<T> From<Result<T>> for AgentResult
where
    T: erased_serde::Serialize + 'static + Send,
{
    fn from(r: Result<T>) -> Self {
        match r {
            Ok(result) => AgentResult::AgentOk {
                wrapper_version: AGENT_RPC_WRAPPER_VERSION,
                result: Box::new(result),
            },
            Err(e) => AgentResult::AgentErr {
                wrapper_version: AGENT_RPC_WRAPPER_VERSION,
                error: format!("{:?}", e),
            },
        }
    }
}

impl Default for AgentResult {
    fn default() -> Self {
        let opt: Option<()> = None;

        AgentResult::AgentOk {
            wrapper_version: AGENT_RPC_WRAPPER_VERSION,
            result: Box::new(opt),
        }
    }
}

pub fn agent_ok<T>(t: T) -> AgentResult
where
    T: erased_serde::Serialize + 'static + Send,
{
    AgentResult::AgentOk {
        wrapper_version: AGENT_RPC_WRAPPER_VERSION,
        result: Box::new(t),
    }
}

pub fn agent_err(e: ImlAgentError) -> AgentResult {
    AgentResult::AgentErr {
        wrapper_version: AGENT_RPC_WRAPPER_VERSION,
        error: format!("{:?}", e),
    }
}

#[derive(Debug, Eq, PartialEq, Hash, serde::Deserialize)]
pub struct ActionName(pub String);

type BoxedFuture = Box<Future<Item = AgentResult, Error = ()> + 'static + Send>;

type Callback = Box<Fn(serde_json::value::Value) -> BoxedFuture>;

fn mk_boxed_future<T: 'static, F: 'static, R, Fut: 'static>(
    v: serde_json::value::Value,
    f: F,
) -> BoxedFuture
where
    T: serde::de::DeserializeOwned + Send,
    R: serde::Serialize + 'static + Send,
    F: Fn(T) -> Fut + Send,
    Fut: Future<Item = R, Error = ImlAgentError> + Send,
{
    Box::new(
        serde_json::from_value(v)
            .into_future()
            .map_err(|e| e.into())
            .and_then(move |x| f(x))
            .then(|result| Ok(result.into()))
            .map_err(|_: ImlAgentError| ()),
    ) as BoxedFuture
}

fn mk_callback<Fut: 'static, F: 'static, T: 'static, R: 'static>(f: &'static F) -> Callback
where
    Fut: Future<Item = R, Error = ImlAgentError> + Send,
    F: Fn(T) -> Fut + Send + Sync,
    T: serde::de::DeserializeOwned + Send,
    R: serde::Serialize + Send,
{
    Box::new(move |v| mk_boxed_future(v, f))
}

pub fn create_registry() -> HashMap<ActionName, Callback> {
    let mut map = HashMap::new();

    map.insert(
        ActionName("start_stratagem".into()),
        mk_callback(&manage_stratagem::start_stratagem),
    );

    map.insert(
        ActionName("stop_stratagem".into()),
        mk_callback(&manage_stratagem::stop_stratagem),
    );

    log::info!("Loaded the following ActionPlugins:");

    for ActionName(key) in map.keys() {
        log::info!("{}", key)
    }

    map
}
