use crate::types::{GameState, NodeStats, TradeAction};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub struct NodeId(u32);

impl NodeId {
    pub const NULL: Self = Self(u32::MAX);
    pub const ROOT: Self = Self(0);

    pub fn is_null(&self) -> bool { self.0 == u32::MAX }
    pub fn index(&self) -> usize { self.0 as usize }
    pub fn from_index(idx: usize) -> Self { Self(idx as u32) }
}

#[derive(Debug)]
pub struct GameNode {
    pub state: GameState,
    pub action: Option<TradeAction>,
    pub parent: NodeId,
    pub first_child: NodeId,
    pub next_sibling: NodeId,
    pub depth: u32,
    pub is_terminal: bool,
    pub stats: NodeStats,
}

impl GameNode {
    pub fn is_leaf(&self) -> bool { self.first_child.is_null() }
    pub fn is_expanded(&self) -> bool { !self.first_child.is_null() }

    pub fn ucb1_score(&self, parent_visits: u64, c: f64) -> f64 {
        if self.stats.visits == 0 {
            return f64::INFINITY;
        }
        let exploitation = self.stats.mean_value;
        let exploration = c * ((parent_visits as f64).ln() / (self.stats.visits as f64)).sqrt();
        exploitation + exploration
    }
}

pub struct GameTree {
    nodes: Vec<GameNode>,
    capacity: usize,
}

impl GameTree {
    pub fn with_capacity(capacity: usize) -> Self {
        Self { nodes: Vec::with_capacity(capacity), capacity }
    }

    pub fn create_root(&mut self, state: GameState) -> NodeId {
        let id = NodeId(self.nodes.len() as u32);
        self.nodes.push(GameNode {
            state,
            action: None,
            parent: NodeId::NULL,
            first_child: NodeId::NULL,
            next_sibling: NodeId::NULL,
            depth: 0,
            is_terminal: false,
            stats: NodeStats::default(),
        });
        id
    }

    pub fn allocate(&mut self, parent: NodeId, action: Option<TradeAction>, state: GameState) -> Option<NodeId> {
        if self.nodes.len() >= self.capacity {
            return None;
        }
        let id = NodeId(self.nodes.len() as u32);
        let depth = if parent.is_null() { 0 } else { self.get(parent)?.depth + 1 };

        // Link as sibling of parent's first child
        if !parent.is_null() {
            let parent_node = self.nodes.get_mut(parent.index())?;
            if parent_node.first_child.is_null() {
                parent_node.first_child = id;
            } else {
                // Find last sibling
                let mut sibling = parent_node.first_child;
                while let Some(node) = self.nodes.get(sibling.index()) {
                    if node.next_sibling.is_null() { break; }
                    sibling = node.next_sibling;
                }
                if let Some(node) = self.nodes.get_mut(sibling.index()) {
                    node.next_sibling = id;
                }
            }
        }

        self.nodes.push(GameNode {
            state,
            action,
            parent,
            first_child: NodeId::NULL,
            next_sibling: NodeId::NULL,
            depth,
            is_terminal: false,
            stats: NodeStats::default(),
        });
        Some(id)
    }

    pub fn get(&self, id: NodeId) -> Option<&GameNode> {
        self.nodes.get(id.index())
    }

    pub fn get_mut(&mut self, id: NodeId) -> Option<&mut GameNode> {
        self.nodes.get_mut(id.index())
    }

    pub fn len(&self) -> usize { self.nodes.len() }
    pub fn is_empty(&self) -> bool { self.nodes.is_empty() }
}
