// Copyright (c) 2019 DDN. All rights reserved.
// Use of this source code is governed by a MIT-style
// license that can be found in the LICENSE file.

use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
};

use futures::{
    future::{self, Either},
    sync::oneshot,
    Future,
};

use crate::{
    action_plugins::{agent_err, create_registry, ActionName, AgentResult},
    agent_error::{ImlAgentError, RequiredError, Result},
    daemon_plugins::{DaemonPlugin, Input},
};

/// Things we can do with actions
#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ActionCommand {
    ActionStart,
    ActionCancel,
}

#[derive(Debug, Clone, Eq, PartialEq, Hash, serde::Deserialize)]
#[serde(transparent)]
struct Id(String);

#[derive(Debug, serde::Deserialize)]
pub struct Action {
    #[serde(rename = "type")]
    action_type: ActionCommand,
    id: Id,
    action: Option<ActionName>,
    args: Option<serde_json::value::Value>,
}

#[derive(Debug)]
pub struct ActionRunner {
    ids: Arc<Mutex<HashMap<Id, oneshot::Sender<()>>>>,
}

pub fn create() -> impl DaemonPlugin {
    ActionRunner {
        ids: Arc::new(Mutex::new(HashMap::new())),
    }
}

impl DaemonPlugin for ActionRunner {
    fn on_message(
        &mut self,
        input: Input,
    ) -> Box<Future<Item = AgentResult, Error = ImlAgentError> + Send> {
        let mut registry = create_registry();

        match input {
            Input::Action(action) => match action.action_type {
                ActionCommand::ActionStart => {
                    let (a, args, id) = match action {
                        Action {
                            action: Some(a),
                            args: Some(args),
                            id,
                            ..
                        } => (a, args, id),
                        Action { .. } => {
                            return Box::new(future::ok(agent_err(
                                RequiredError(
                                    "action and args required to start action".to_string(),
                                )
                                .into(),
                            )));
                        }
                    };

                    let action_plugin_fn = match registry.get_mut(&a) {
                        Some(p) => p,
                        None => {
                            return Box::new(future::ok(agent_err(
                                RequiredError(
                                    "action and args required to start action".to_string(),
                                )
                                .into(),
                            )));
                        }
                    };

                    let (tx, rx) = oneshot::channel();

                    match self.ids.lock() {
                        Ok(mut x) => x.insert(id.clone(), tx),
                        Err(e) => return Box::new(future::err(e.into())),
                    };

                    let fut = action_plugin_fn(args);

                    let ids = self.ids.clone();

                    Box::new(
                        fut.select2(rx)
                            .map(move |r| match r {
                                Either::A((b, _)) => {
                                    ids.lock().unwrap().remove(&id);
                                    b
                                }
                                Either::B((_, z)) => {
                                    drop(z);
                                    AgentResult::default()
                                }
                            })
                            .map_err(|e| match e {
                                _ => unreachable!(),
                            }),
                    )
                }
                ActionCommand::ActionCancel => {
                    let tx = match self.ids.lock() {
                        Ok(mut x) => x.remove(&action.id),
                        Err(e) => return Box::new(future::err(e.into())),
                    };

                    if let Some(tx) = tx {
                        // We don't care what the result is here.
                        tx.send(()).is_ok();
                    }

                    Box::new(future::ok(AgentResult::default()))
                }
            },
        }
    }
    fn teardown(&mut self) -> Result<()> {
        for (_, tx) in self.ids.lock()?.drain() {
            // We don't care what the result is here.
            tx.send(()).is_ok();
        }

        Ok(())
    }
}
