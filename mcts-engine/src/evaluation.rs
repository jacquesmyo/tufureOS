use crate::types::{GameState, TradeAction};

#[derive(Debug, Clone)]
pub struct PositionEvaluator {
    pub max_position_fraction: f64,
}

impl Default for PositionEvaluator {
    fn default() -> Self {
        Self { max_position_fraction: 0.2 }
    }
}

impl PositionEvaluator {
    pub fn evaluate(&self, state: &GameState) -> f64 {
        // Simple PnL-based evaluation stub
        // Replace with real edge model
        state.balance + state.position * state.price
    }

    pub fn kelly_fraction(&self, win_prob: f64, odds: f64) -> f64 {
        let loss_prob = 1.0 - win_prob;
        let kelly = (win_prob * odds - loss_prob) / odds;
        (kelly * 0.5).clamp(0.0, self.max_position_fraction)
    }

    pub fn is_terminal(&self, state: &GameState, depth: u32, max_depth: u32) -> bool {
        state.balance <= 0.0 || depth >= max_depth
    }
}

#[derive(Debug, Clone)]
pub struct ActionGenerator {
    evaluator: PositionEvaluator,
}

impl ActionGenerator {
    pub fn new(evaluator: PositionEvaluator) -> Self {
        Self { evaluator }
    }

    pub fn generate(&self, state: &GameState) -> Vec<TradeAction> {
        // Stub: all actions always available
        // Replace with action masking based on state
        vec![
            TradeAction::Hold,
            TradeAction::Buy,
            TradeAction::Sell,
            TradeAction::IncreasePosition,
            TradeAction::DecreasePosition,
        ]
    }

    pub fn apply_action(&self, state: &GameState, action: &TradeAction) -> Option<GameState> {
        let mut new_state = state.clone();
        match action {
            TradeAction::Hold => {}
            TradeAction::Buy => {
                // Stub: buy 1 unit
                new_state.position += 1.0;
                new_state.balance -= state.price;
            }
            TradeAction::Sell => {
                new_state.position -= 1.0;
                new_state.balance += state.price;
            }
            TradeAction::IncreasePosition => {
                new_state.position += 0.5;
                new_state.balance -= state.price * 0.5;
            }
            TradeAction::DecreasePosition => {
                new_state.position -= 0.5;
                new_state.balance += state.price * 0.5;
            }
        }
        Some(new_state)
    }
}
