opaque N : Nat
axiom hN : 0 < N

def test (x : Fin N) : Fin N :=
  x + ⟨1 % N, Nat.mod_lt 1 hN⟩
