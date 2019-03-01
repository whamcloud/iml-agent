// Copyright (c) 2019 DDN. All rights reserved.
// Use of this source code is governed by a MIT-style
// license that can be found in the LICENSE file.

use tokio::prelude::*;

use crate::{
    action_plugins::manage_stratagem::stratagem_data,
    agent_error::ImlAgentError,
    daemon_plugins::{DaemonPlugin, Output},
};

pub fn create() -> impl DaemonPlugin {
    Stratagem {}
}

#[derive(Debug)]
pub struct Stratagem {}

impl DaemonPlugin for Stratagem {
    fn start_session(&self) -> Box<Future<Item = Option<Output>, Error = ImlAgentError> + Send> {
        Box::new(stratagem_data().map(Output::Stratagem).map(Some).or_else(|e| {
            match e {
                ImlAgentError::Io(_) => {
                    log::debug!("IO Error while reading Stratagem JSON file. It may not be installed yet.");

                    Ok(None)
                },
                err => Err(err)
            }
        }))
    }
}
