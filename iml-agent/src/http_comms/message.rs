// Copyright (c) 2019 DDN. All rights reserved.
// Use of this source code is governed by a MIT-style
// license that can be found in the LICENSE file.

use crate::{
    daemon_plugins::{Input, PluginName},
    http_comms::session,
    server_properties::BOOT_TIME,
};

/// The payload sent to the manager.
/// One or many can be packed into an `Envelope`
#[derive(serde::Serialize, Debug)]
#[serde(tag = "type")]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Message<T: serde::Serialize> {
    Data {
        fqdn: String,
        plugin: PluginName,
        session_id: session::Id,
        session_seq: session::Seq,
        body: T,
    },
    SessionCreateRequest {
        fqdn: String,
        plugin: PluginName,
    },
}

/// `Envelope` of `Messages` sent to the manager.
#[derive(serde::Serialize, Debug)]
pub struct Envelope<T: serde::Serialize> {
    collection: u8,
    messages: Vec<Message<T>>,
    server_boot_time: String,
    client_start_time: String,
}

impl<T: serde::Serialize> Envelope<T> {
    pub fn new(messages: Vec<Message<T>>, client_start_time: impl Into<String>) -> Self {
        Envelope {
            collection: 2,
            messages,
            server_boot_time: BOOT_TIME.to_string(),
            client_start_time: client_start_time.into(),
        }
    }
}

#[derive(serde::Deserialize, Debug)]
#[serde(tag = "type")]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ManagerMessage {
    SessionCreateResponse {
        plugin: PluginName,
        session_id: session::Id,
    },
    Data {
        plugin: PluginName,
        session_id: session::Id,
        body: Input,
    },
    SessionTerminate {
        plugin: PluginName,
        session_id: session::Id,
    },
    SessionTerminateAll,
}

#[derive(serde::Deserialize, Debug)]
pub struct ManagerMessages {
    pub messages: Vec<ManagerMessage>,
}
