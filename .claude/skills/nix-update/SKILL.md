---
name: nix-update
description: Update the Nix flake or add new packages to the dev shell. Use when modifying flake.nix or updating dependencies.
---

# Nix Flake Update

Modify the Nix development environment.

## Steps

1. Read `flake.nix` to understand the current configuration
2. Make the requested changes (add packages, update inputs, etc.)
3. Format with alejandra:
   ```
   nix fmt
   ```
4. Verify the flake evaluates:
   ```
   nix flake check
   ```
5. If updating inputs:
   ```
   nix flake update
   ```
6. Verify the dev shell builds:
   ```
   nix develop --command echo "shell OK"
   ```
