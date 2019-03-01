// Copyright (c) 2019 DDN. All rights reserved.
// Use of this source code is governed by a MIT-style
// license that can be found in the LICENSE file.

use exitcode;
use futures::Future;
use iml_agent::action_plugins::manage_stratagem;
use prettytable::{cell, row, Table};
use std::process;
use structopt::StructOpt;

#[derive(Debug, StructOpt)]
pub enum Command {
    #[structopt(name = "start")]
    /// Start the Stratagem server
    Start,
    #[structopt(name = "stop")]
    /// Stop the Stratagem server
    Stop,
    #[structopt(name = "status")]
    /// Check Stratagem server status
    Status,
    #[structopt(name = "groups")]
    /// Get Stratagem Groups
    Groups,
}

#[derive(StructOpt, Debug)]
#[structopt(name = "iml-agent")]
/// The Integrated Manager for Lustre Agent CLI
pub enum App {
    #[structopt(name = "stratagem")]
    /// Work with Stratagem server
    Stratagem {
        #[structopt(subcommand)]
        command: Command,
    },
}

fn main() {
    env_logger::init();

    let matches = App::from_args();

    match matches {
        App::Stratagem { command } => match command {
            Command::Start => {
                let started = manage_stratagem::status_stratagem()
                    .wait()
                    .expect("Could not check Stratagem status");

                if started {
                    println!("Stratagem already running");
                    process::exit(exitcode::OK);
                } else {
                    println!("Starting...");
                    manage_stratagem::start_stratagem(None)
                        .wait()
                        .expect("Could not start Stratagem");
                    println!("Started");
                }

                process::exit(exitcode::OK);
            }
            Command::Stop => {
                let started = manage_stratagem::status_stratagem()
                    .wait()
                    .expect("Could not check Stratagem status");

                if !started {
                    println!("stratagem already stopped");
                } else {
                    println!("Stopping...");
                    manage_stratagem::stop_stratagem(None)
                        .wait()
                        .expect("Could not stop Stratagem");
                    println!("Stopped")
                }

                process::exit(exitcode::OK);
            }
            Command::Status => {
                let started = manage_stratagem::status_stratagem()
                    .wait()
                    .expect("Could not check Stratagem status");

                if started {
                    println!("Stratagem is running");
                    process::exit(exitcode::OK);
                } else {
                    eprintln!("Stratagem is not running");
                    process::exit(1);
                }
            }
            Command::Groups => {
                let groups = manage_stratagem::stratagem_groups()
                    .wait()
                    .expect("Could not get Stratagem groups");

                for x in groups {
                    println!("\n\nGroup {}", x.name);

                    let mut table = Table::new();

                    table.add_row(row!["Action", "Expression", "Argument"]);

                    for y in x.rules {
                        table.add_row(row![y.action, y.expression, y.argument]);
                    }

                    table.printstd();
                }
            }
        },
    };
}