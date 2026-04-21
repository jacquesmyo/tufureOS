use pyo3::prelude::*;
use crate::mcts::MCTSEngine;
use crate::types::{GameState, MCTSConfig};

#[pyfunction]
fn search_best_action(state_json: &str, config_json: Option<&str>) -> PyResult<String> {
    let state: GameState = serde_json::from_str(state_json)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;

    let config: MCTSConfig = config_json
        .and_then(|s| serde_json::from_str(s).ok())
        .unwrap_or_default();

    let engine = MCTSEngine::new(config);
    let result = engine.search(&state);

    serde_json::to_string(&result)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}

#[pyfunction]
fn version() -> PyResult<String> {
    Ok(env!("CARGO_PKG_VERSION").to_string())
}

#[pymodule]
fn mcts_trader(_py: Python, m: &Bound<PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(search_best_action, m)?)?;
    m.add_function(wrap_pyfunction!(version, m)?)?;
    Ok(())
}
