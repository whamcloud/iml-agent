// Copyright (c) 2019 DDN. All rights reserved.
// Use of this source code is governed by a MIT-style
// license that can be found in the LICENSE file.

use crate::{agent_error::ImlAgentError, fs::read_file_to_end, systemd};
use futures::Future;
use serde;
use serde_json;

static SERVICE_NAME: &str = "lipe_web";

static STRATAGEM_DATA_FILE: &str = "/var/www/lipe/static/lipe_web.json";

#[derive(Debug, Eq, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Devices {
    pub path: String,
    pub host_id: String,
    pub groups: Vec<String>,
    pub device_id: String,
}

#[derive(Debug, Eq, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Groups {
    pub rules: Vec<Rules>,
    pub name: String,
}

#[derive(Debug, Eq, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Rules {
    pub action: String,
    pub expression: String,
    pub argument: String,
}

#[derive(Debug, Eq, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct SshHosts {
    pub host_id: String,
    pub hostname: String,
    pub ssh_identity_file: String,
}

#[derive(Debug, Eq, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct StratagemData {
    pub ssh_hosts: Vec<SshHosts>,
    pub groups: Vec<Groups>,
    pub devices: Vec<Devices>,
    pub dump_flist: bool,
    pub dry_run: bool,
    pub only_scan_active: bool,
}

/// Tries to read the lipe_web.json file and
/// returns a `Result` of the serialized `StratagemData`.
fn read_stratagem_data() -> impl Future<Item = StratagemData, Error = ImlAgentError> {
    read_file_to_end(STRATAGEM_DATA_FILE)
        .and_then(|b| serde_json::from_slice(&b).map_err(|e| e.into()))
}

pub fn start_stratagem(_: Option<()>) -> impl Future<Item = bool, Error = ImlAgentError> {
    systemd::systemctl_start(SERVICE_NAME.to_string())
}

pub fn stop_stratagem(_: Option<()>) -> impl Future<Item = bool, Error = ImlAgentError> {
    systemd::systemctl_stop(SERVICE_NAME.to_string())
}

pub fn status_stratagem() -> impl Future<Item = bool, Error = ImlAgentError> {
    systemd::systemctl_status(SERVICE_NAME.to_string()).map(systemd::did_succeed)
}

pub fn stratagem_data() -> impl Future<Item = StratagemData, Error = ImlAgentError> {
    read_stratagem_data()
}

pub fn stratagem_groups() -> impl Future<Item = Vec<Groups>, Error = ImlAgentError> {
    read_stratagem_data().map(|x| x.groups)
}
