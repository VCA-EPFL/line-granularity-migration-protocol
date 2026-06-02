# Live Migration FSM Model (LLM Context)

## Overview
This directory (`noclock`) contains an state machine model of the VM migration protocol without any notion of time.

## Architecture
Here we have a Storer, which is a simplified representation of the CPU. The storer can write to address X of memory. Writing to X simply increments the value of the memory at address X. The DMA engine can read from address X and send it to the network. The mirror buffer will also duplicate all writes to memory (from the storer) and send it to the network. This version is bugged, because the DMA engine might read the value of X after the CPU has updated it, but before the mirror buffer has had a chance to update the destination memory. This can lead to stale overwrites.


## The Global State (`GlobalState`)
The state of the system is defined by:
1. `source_mem` & `dest_mem`: The values of the memory at address `X`. The source is a monotonically increasing counter. The destination is written to by the mirror or DMA. If the destination ever decrements, we have a bug.
2. `mirror_buffer`: A FIFO queue (`[]`) intercepting host CPU writes.
3. `network_bag`: An unordered set (`[]`) of all packets currently in flight across the fabric.
4. `dma_state`: The DMA engine's state machine (`WAITING`, `TRANSMITTING`, `DONE`).
5. `dma_internal_buffer`: A single register (`None` or `int`) holding the chunk the DMA just read.

## The Transitions (`Transitions`)
Each Action has:
*   **Guard**: A condition checking if the action is valid in the current state.
*   **Effect**: A function that mutates the `GlobalState`.

The defined actions are:
*   `storer_writes`: CPU increments memory and pushes to `mirror_buffer`.
*   `mirror_sends`: Moves an item from `mirror_buffer` to `network_bag`.
*   `dma_reads`: DMA reads from `source_mem` to its internal buffer.
*   `dma_sends`: DMA moves its internal buffer to the `network_bag`.
*   `network_delivers`: Randomly pops a packet from the `network_bag` and applies it to `dest_mem`.

## The Execution Engine
`fsm.py` runs a random walk. At every step, it evaluates all Guards, finds all currently valid Actions, and randomly executes exactly one. 