// Copyright (c) 2019 DDN. All rights reserved.
// Use of this source code is governed by a MIT-style
// license that can be found in the LICENSE file.

use futures::Future;

use crate::{
    agent_error::ImlAgentError,
    daemon_plugins,
    http_comms::{crypto_client, message, session},
    server_properties,
};
use reqwest::r#async::{Chunk, Client};

/// A wrapper around `CryptoClient`.
///
/// Provides abstraction for common requests to the manager.
#[derive(Debug, Clone)]
pub struct AgentClient {
    start_time: String,
    message_endpoint: url::Url,
    client: Client,
}

impl AgentClient {
    pub fn new(start_time: String, message_endpoint: url::Url, client: Client) -> Self {
        AgentClient {
            start_time,
            message_endpoint,
            client,
        }
    }
    /// Send a request to the manager
    ///
    /// # Arguments
    ///
    /// * `message` - The message to send
    pub fn post(
        &self,
        message: message::Message<impl serde::Serialize + std::fmt::Debug>,
    ) -> impl Future<Item = Chunk, Error = ImlAgentError> {
        let envelope = message::Envelope::new(vec![message], self.start_time.clone());

        crypto_client::post(&self.client, self.message_endpoint.clone(), &envelope)
    }
    /// Send a new session request to the manager
    ///
    /// # Arguments
    ///
    /// * `plugin` - The plugin to initiate a session over
    pub fn create_session(
        &self,
        plugin: daemon_plugins::PluginName,
    ) -> impl Future<Item = (), Error = ImlAgentError> {
        log::info!("Requesting new session for: {:?}.", plugin);

        let m: message::Message<()> = message::Message::SessionCreateRequest {
            fqdn: server_properties::FQDN.to_string(),
            plugin,
        };

        self.post(m).map(|_| ())
    }
    /// Send data to the manager
    ///
    /// # Arguments
    ///
    /// * `plugin` - The manager plugin to communicate with
    /// * `info` - Bundle of session info
    /// * `output` - The data to send
    pub fn send_data(
        &self,
        info: session::SessionInfo,
        body: impl serde::Serialize + std::fmt::Debug,
    ) -> impl Future<Item = (), Error = ImlAgentError> {
        log::debug!(
            "Sending session data for {:?}({:?}): {:?}",
            info.name,
            info.id,
            body
        );

        let m = message::Message::Data {
            fqdn: server_properties::FQDN.to_string(),
            plugin: info.name,
            session_id: info.id,
            session_seq: info.seq,
            body,
        };

        self.post(m).map(|_| ())
    }
    /// Get data from the manager
    ///
    /// # Arguments
    ///
    pub fn get(&self) -> impl Future<Item = message::ManagerMessages, Error = ImlAgentError> {
        let get_params: Vec<(String, String)> = vec![
            (
                "server_boot_time".into(),
                server_properties::BOOT_TIME.to_string(),
            ),
            ("client_start_time".into(), self.start_time.clone()),
            ("collection".into(), "2".into()),
        ];

        log::debug!("Sending get {:?}", get_params);

        crypto_client::get(&self.client, self.message_endpoint.clone(), &get_params)
            .and_then(|x| serde_json::from_slice(&x).map_err(|e| e.into()))
    }
}
