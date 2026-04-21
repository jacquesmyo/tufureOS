use std::env;
use mcts_trader::{GameState, MCTSConfig, MCTSEngine};

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: mcts-trader-cli <game_state_json> <config_json>");
        std::process::exit(1);
    }

    let state: GameState = serde_json::from_str(&args[1]).unwrap_or_else(|e| {
        eprintln!("Invalid game state JSON: {}", e);
        std::process::exit(1);
    });

    let config: MCTSConfig = serde_json::from_str(&args[2]).unwrap_or_else(|e| {
        eprintln!("Invalid config JSON: {}", e);
        std::process::exit(1);
    });

    let engine = MCTSEngine::new(config);
    let result = engine.search(&state);

    println!("{}", serde_json::to_string(&result).unwrap());
}
