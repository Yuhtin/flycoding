# Neural provenance

This directory adapts the neural implementation from
[`nftechie/stonkfly` revision `78ef3e05ab0fa086032098558d893667068944a0`](https://github.com/nftechie/stonkfly/tree/78ef3e05ab0fa086032098558d893667068944a0), under its MIT licence.

| Upstream file | SHA-256 | Flycodex adaptation |
| --- | --- | --- |
| `neural/kernel.cpp` | `e2d4d584f4633613277bb1bf6ea7ba20855c01a332ae2e9344ed7782604c8509` | Vendored integrator; comments identify its source. |
| `neural/rule.py` | `3c80680450c3b73042e332bd7ce8289d7d74d8695c60e7ac19eefd9759d95c44` | Candidate rule retains the upstream two-state update, adding an explicit early frozen return so passive efficacy decay is frozen too. |
| `neural/brain.py` | `895d0bcab7e03e859547e516905edc39fd2af4bb7ff7a7bf67d819bc15ac8c4d` | Reworked as `runtime.py`; all cache, graph, annotation and checkpoint paths derive from the constructor's `data_dir`. |
| `neural/connectome.py` | `cd9ceb396ca9b408eb7beafe8abd0894d5c5e13aa63c9ec23ffbc55526f11d18` | Its loss-accounted retention and Arrow import logic is incorporated in `policy.py`. |
| `neural/prepare.py` | `38a2821a8ee26fed74d88146931f77331038d6c2a69c4be8f885705630d130f3` | Its complete-graph CSR compilation and visual projection are incorporated in `policy.py`. |
| `neural/circuit.py` | `e9ed5d237c7c01fbaf80f75cec75f5f9f2e33965461e3480813ade78597f6c45` | Its annotated readouts and KC/DAN/MBON candidate circuit are incorporated in `runtime.py`. |
| `neural/visual.py` | `65c9639ab7fb6c5d77f83f297c4d82cf8b7a068957bd78e1da957b3f9aeae952` | Its RGB sampling and stated visual limitations are incorporated in `runtime.py` and `policy.py`. |

`sources.lock.json`, `arrays.lock.json`, and `neurons.lock.json` preserve the relevant pinned upstream data identities. No trading controller, market data, broker, or AgentKit dependency is included. The resulting model remains an experimental simulation, not validated fly vision or learning.
