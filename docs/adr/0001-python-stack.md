# ADR 0001: Use Python as the implementation stack

## Status

Accepted

## Context

The project needs a stack that can move quickly, integrate with broker APIs, and support deterministic trading logic, replay, and operational tooling.

## Decision

Python is the implementation language for the autonomous trading system.

## Consequences

- The codebase will use a Python project layout and Python-native dependency management.
- Strategy, risk, execution, and replay tooling will be implemented in Python.
- The language choice does not lock the project into a specific framework yet.
- Future implementation details such as packaging, async model, and test stack remain separate decisions.
