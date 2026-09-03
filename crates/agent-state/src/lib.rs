use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum State {
    Idle,
    Intake,
    Analyzing,
    Planning,
    Executing,
    Observing,
    Validating,
    Reflecting,
    Completed,
    Failed,
}

#[derive(Debug, Clone)]
pub struct StateMachine {
    current: State,
    iteration: u32,
    max_iterations: u32,
}

impl StateMachine {
    pub fn new(max_iterations: u32) -> Self {
        Self {
            current: State::Idle,
            iteration: 0,
            max_iterations,
        }
    }

    pub fn current(&self) -> State {
        self.current
    }

    pub fn iteration(&self) -> u32 {
        self.iteration
    }

    pub fn transition(&mut self, next: State) {
        if next == State::Executing {
            self.iteration += 1;
        }
        self.current = next;
    }

    pub fn is_exhausted(&self) -> bool {
        self.iteration >= self.max_iterations
    }
}
