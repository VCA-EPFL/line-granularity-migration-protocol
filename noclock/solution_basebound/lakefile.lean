import Lake
open Lake DSL

package «solution_basebound» where

@[default_target]
lean_lib «Fsm» where
  srcDir := "."
  roots := #[`fsm]
