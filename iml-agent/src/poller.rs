// Copyright (c) 2019 DDN. All rights reserved.
// Use of this source code is governed by a MIT-style
// license that can be found in the LICENSE file.

use crate::{
    agent_error::ImlAgentError,
    daemon_plugins::{Output, PluginName},
    http_comms::{
        agent_client::AgentClient,
        session::{SessionInfo, Sessions, State},
    },
};
use std::time::{Duration, Instant};
use tokio::prelude::*;

fn send_if_data(
    agent_client: AgentClient,
) -> impl FnOnce(Option<(SessionInfo, Output)>) -> Box<Future<Item = (), Error = ImlAgentError> + Send>
{
    move |x| match x {
        Some((info, output)) => Box::new(agent_client.send_data(info, output)),
        None => Box::new(future::ok(())),
    }
}

/// Given a `Session` wrapped in some `State`
/// this function will handle the state and move it to it's next state.
///
fn handle_state(
    state: &mut State,
    agent_client: AgentClient,
    mut sessions: Sessions,
    name: PluginName,
    now: Instant,
) -> Box<Future<Item = (), Error = ImlAgentError> + Send> {
    match state {
        State::Empty(wait) if *wait <= now => Box::new(
            agent_client
                .create_session(name.clone())
                .then(move |r| match r {
                    Ok(_) => sessions.convert_to_pending(&name),
                    Err(_) => sessions.reset_empty(&name),
                }),
        ),
        State::Active(a) if a.instant <= now => Box::new(
            a.session
                .poll()
                .and_then(send_if_data(agent_client.clone()))
                .then(move |r| match r {
                    Ok(_) => sessions.reset_active(&name),
                    Err(_) => sessions.terminate_session(&name),
                }),
        ),
        _ => Box::new(future::ok(())),
    }
}

/// Given some `Sessions`, this fn will poll them once per second.
///
/// A `Session` or other `State` will only be handled if their internal timers have passed the tick of this
/// internal interval `Stream`.
pub fn create_poller(
    agent_client: AgentClient,
    sessions: Sessions,
) -> impl Future<Item = (), Error = ImlAgentError> + 'static {
    tokio::timer::Interval::new_interval(Duration::from_secs(1))
        .map_err(|e| e.into())
        .for_each(move |now| {
            log::trace!("interval triggered for {:?}", now);

            for (name, state) in sessions.clone().lock()?.iter_mut() {
                let fut = handle_state(
                    state,
                    agent_client.clone(),
                    sessions.clone(),
                    name.clone(),
                    now,
                );

                tokio::spawn(fut.map_err(|e| {
                    log::error!("{}", e);
                }));
            }

            Ok(())
        })
}
