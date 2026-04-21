use crate::evaluation::{ActionGenerator, PositionEvaluator};
use crate::game_tree::{GameTree, NodeId};
use crate::types::{GameState, MCTSConfig, SearchResult, TradeAction};
use rand::SeedableRng;
use rand::rngs::StdRng;
use rand::seq::SliceRandom;
use std::sync::atomic::{AtomicU64, Ordering};

pub struct MCTSEngine {
    config: MCTSConfig,
    evaluator: PositionEvaluator,
    action_gen: ActionGenerator,
    global_sim_count: AtomicU64,
}

impl MCTSEngine {
    pub fn new(config: MCTSConfig) -> Self {
        let evaluator = PositionEvaluator::default();
        let action_gen = ActionGenerator::new(evaluator.clone());
        Self { config, evaluator, action_gen, global_sim_count: AtomicU64::new(0) }
    }

    pub fn search(&self, initial_state: &GameState) -> SearchResult {
        let mut tree = GameTree::with_capacity(self.config.num_simulations * 5);
        let root = tree.create_root(initial_state.clone());
        let mut rng = StdRng::seed_from_u64(
            self.config.seed + self.global_sim_count.load(Ordering::Relaxed)
        );

        for _ in 0..self.config.num_simulations {
            let leaf = self.select(&tree, root);
            let expanded = if !tree.get(leaf).unwrap().is_terminal {
                self.expand(&mut tree, leaf)
            } else { leaf };
            let value = self.simulate(&tree, expanded, &mut rng);
            self.backpropagate(&mut tree, expanded, value);
        }

        self.global_sim_count.fetch_add(self.config.num_simulations as u64, Ordering::Relaxed);
        self.build_result(&tree, root)
    }

    fn select(&self, tree: &GameTree, root: NodeId) -> NodeId {
        let mut current = root;
        loop {
            let node = tree.get(current).unwrap();
            if !node.is_expanded() || node.is_terminal {
                return current;
            }
            let parent_visits = node.stats.visits;
            let mut best_child = NodeId::NULL;
            let mut best_score = f64::NEG_INFINITY;
            let mut child = node.first_child;
            while !child.is_null() {
                if let Some(child_node) = tree.get(child) {
                    let score = child_node.ucb1_score(parent_visits, self.config.exploration_constant);
                    if score > best_score {
                        best_score = score;
                        best_child = child;
                    }
                    child = child_node.next_sibling;
                } else {
                    break;
                }
            }
            if best_child.is_null() {
                return current;
            }
            current = best_child;
        }
    }

    fn expand(&self, tree: &mut GameTree, leaf: NodeId) -> NodeId {
        let (node_state, is_terminal, is_expanded) = {
            let node = tree.get(leaf).unwrap();
            (node.state.clone(), node.is_terminal, node.is_expanded())
        };

        if is_expanded || is_terminal {
            return leaf;
        }

        let actions = self.action_gen.generate(&node_state);
        let mut first_child: Option<NodeId> = None;
        for action in actions {
            if let Some(new_state) = self.action_gen.apply_action(&node_state, &action) {
                if let Some(child_id) = tree.allocate(leaf, Some(action), new_state) {
                    if first_child.is_none() {
                        first_child = Some(child_id);
                    }
                }
            }
        }

        if let Some(fc) = first_child {
            fc
        } else {
            leaf
        }
    }

    fn simulate(&self, tree: &GameTree, node_id: NodeId, rng: &mut StdRng) -> f64 {
        let node = tree.get(node_id).unwrap();
        let mut state = node.state.clone();
        let mut depth = node.depth;
        let mut actions: Vec<TradeAction> = self.action_gen.generate(&state);

        while !self.evaluator.is_terminal(&state, depth, self.config.max_depth) && !actions.is_empty() {
            if let Some(action) = actions.choose(rng) {
                if let Some(new_state) = self.action_gen.apply_action(&state, action) {
                    state = new_state;
                    depth += 1;
                    actions = self.action_gen.generate(&state);
                } else {
                    break;
                }
            } else {
                break;
            }
        }

        self.evaluator.evaluate(&state)
    }

    fn backpropagate(&self, tree: &mut GameTree, node_id: NodeId, value: f64) {
        let mut current = node_id;
        while !current.is_null() {
            if let Some(node) = tree.get_mut(current) {
                node.stats.update(value);
                current = node.parent;
            } else {
                break;
            }
        }
    }

    fn build_result(&self, tree: &GameTree, root: NodeId) -> SearchResult {
        let root_node = tree.get(root).unwrap();
        let mut best_action = TradeAction::Hold;
        let mut best_visits = 0u64;
        let mut action_values = Vec::new();
        let mut best_line = Vec::new();

        let mut child = root_node.first_child;
        while !child.is_null() {
            if let Some(node) = tree.get(child) {
                action_values.push((node.action.unwrap_or(TradeAction::Hold), node.stats.mean_value));
                if node.stats.visits > best_visits {
                    best_visits = node.stats.visits;
                    best_action = node.action.unwrap_or(TradeAction::Hold);
                    // Build principal variation by following most visited child
                    let mut pv = vec![best_action];
                    let mut pv_node = child;
                    while let Some(pvn) = tree.get(pv_node) {
                        if pvn.first_child.is_null() { break; }
                        let mut next = pvn.first_child;
                        let mut next_visits = 0u64;
                        let mut next_action = TradeAction::Hold;
                        let mut next_node = NodeId::NULL;
                        while !next.is_null() {
                            if let Some(nc) = tree.get(next) {
                                if nc.stats.visits > next_visits {
                                    next_visits = nc.stats.visits;
                                    next_action = nc.action.unwrap_or(TradeAction::Hold);
                                    next_node = next;
                                }
                                next = nc.next_sibling;
                            } else { break; }
                        }
                        if !next_node.is_null() {
                            pv.push(next_action);
                            pv_node = next_node;
                        } else { break; }
                    }
                    best_line = pv;
                }
                child = node.next_sibling;
            } else {
                break;
            }
        }

        SearchResult {
            best_action,
            action_values,
            total_visits: root_node.stats.visits,
            best_line,
            estimated_value: root_node.stats.mean_value,
        }
    }
}
