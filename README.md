# Analyzing-Hallucinations-and-Partial-proofs-Support-in-LLM-Based-Reasoning

## Overview
This repository contains a neuro-symbolic reasoning pipeline that bridges the gap between Large Language Models(LLMs) and formal symbolic solvers. It tests the deductive reasoning capabilities of LLMs on the PrOntoQA dataset by translating natural language logic puzzles into strict Python Z3 constraints. 

Beyond simple verification, this system introduces **Approximate Reasoning** and **Graceful Degradation**. By extracting the minimal Unsatisfiable Core (UNSAT core) from Z3, the system identifies the exact premises required for a proof. If a logical contradiction is found or a premise is removed, the system performs "belief revision" to output a partial valid derivation rather than failing completely.

## Key Features
* **Pure LLM Baseline Generation:** Captures the LLM's raw chain-of-thought reasoning before formal verification.
* **Automated Z3 Translation:** Prompts the Gemini model to map English logic to formal Boolean constraints using the `z3-solver` library.
* **Minimal Proof Extraction:** Leverages Z3's `unsat_core` functionality to isolate the absolute minimum number of premises needed to solve the puzzle, pruning LLM redundancies.
* **Belief Revision (Graceful Degradation):** Artificially relaxes (removes) a core premise and prompts the LLM to generate the maximum partial valid prefix that remains logically sound.
* **Robust Error Handling:** Includes an API Key Rotation Pool and exponential backoff to handle 429 and 503 rate limits, as well as a custom Regex auto-repair function to fix LLM CamelCase/snake_case variable hallucinations.

## System Architecture
1.  **Input:** A logic theory and query from the PrOntoQA dataset (e.g., 1-hop to 4-hop deductions).
2.  **Baseline Generation:** The LLM attempts to solve the puzzle using pure natural language generation.
3.  **Translation:** The LLM translates the text into formal Z3 assertions (using `Implies`, `And`, `Or`).
4.  **Verification:** A Python `exec()` sandbox runs the Z3 code to mathematically prove the query via contradiction (asserting the negated query).
5.  **Diagnostic Generation:** The extracted UNSAT core is fed back to the LLM to generate a human-readable Comparative Analysis and Belief Revision case study.

## Installation & Setup

### Prerequisites
* Python 3.8+
* Google Gemini API Key(s)

### Requirements
Install the required libraries:
```bash
pip install google-genai z3-solver
