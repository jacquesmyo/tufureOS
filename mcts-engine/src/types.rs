use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct GameState {
    pub price: f64,
    pub position: f64,
    pub balance: f64,
    pub timestamp: u64,
    pub features: Vec<f64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TradeAction {
    Hold,
    Buy,
    Sell,
    IncreasePosition,
    DecreasePosition,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct NodeStats {
    pub visits: u64,
    pub total_value: f64,
    pub mean_value: f64,
    pub min_value: f64,
    pub max_value: f64,
}

impl NodeStats {
    pub fn update(&mut self, value: f64) {
        self.visits += 1;
        self.total_value += value;
        self.mean_value = self.total_value / self.visits as f64;
        if value < self.min_value || self.visits == 1 {
            self.min_value = value;
        }
        if value > self.max_value || self.visits == 1 {
            self.max_value = value;
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MCTSConfig {
    pub num_simulations: usize,
    pub exploration_constant: f64,
    pub max_depth: u32,
    pub seed: u64,
}

impl Default for MCTSConfig {
    fn default() -> Self {
        Self {
            num_simulations: 10000,
            exploration_constant: 1.414,
            max_depth: 150,
            seed: 42,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub best_action: TradeAction,
    pub action_values: Vec<(TradeAction, f64)>,
    pub total_visits: u64,
    pub best_line: Vec<TradeAction>,
    pub estimated_value: f64,
}
