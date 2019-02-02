// Copyright (c) 2019 DDN. All rights reserved.
// Use of this source code is governed by a MIT-style
// license that can be found in the LICENSE file.

use crate::agent_error::ImlAgentError;
use std::path::Path;
use tokio::prelude::*;

/// Given a path, attempts to do an async read to the end of the file.
///
/// # Arguments
///
/// * `p` - The `Path` to a file.
pub fn read_file_to_end<P>(p: P) -> impl Future<Item = Vec<u8>, Error = ImlAgentError>
where
    P: AsRef<Path> + Send + 'static,
{
    tokio::fs::File::open(p)
        .map_err(|e| e.into())
        .and_then(|file| {
            tokio::io::read_to_end(file, vec![])
                .map(|(_, d)| d)
                .map_err(|e| e.into())
        })
}
