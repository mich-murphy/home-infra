{
  description = "Homelab development environment";

  inputs = {
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.2511.903775";
  };

  outputs = {
    self,
    nixpkgs,
  }: let
    allSystems = [
      "x86_64-linux"
      "aarch64-darwin"
    ];

    # Helper to provide system-specific attributes
    forAllSystems = f:
      nixpkgs.lib.genAttrs allSystems (system:
        f {
          pkgs = import nixpkgs {
            inherit system;
            config = {allowUnfree = true;};
          };
        });

    # Wrap terraform in an FHS environment on Linux so third-party provider
    # plugins (e.g. 1password/onepassword) that hard-code
    # /lib64/ld-linux-x86-64.so.2 as their ELF interpreter can execute on
    # NixOS — where that path does not exist. The FHS sandbox stitches in a
    # standard glibc layout for the wrapped process tree.
    terraformFor = pkgs:
      if pkgs.stdenv.isLinux
      then
        pkgs.buildFHSEnv {
          name = "terraform";
          targetPkgs = ps: [ps.terraform];
          runScript = "terraform";
        }
      else pkgs.terraform;
  in {
    devShells = forAllSystems ({pkgs}: {
      default = pkgs.mkShell {
        packages = [
          (terraformFor pkgs)
          pkgs.ansible
          pkgs.just
          pkgs.talosctl
          pkgs.kubectl
          pkgs.k9s
          pkgs.fluxcd
          pkgs.kubernetes-helm
          pkgs.alejandra
        ];
        # Source terraform/.envrc (gitignored — holds OP_SERVICE_ACCOUNT_TOKEN
        # for the 1password Terraform provider) on shell entry. Resolved via
        # git toplevel so we never accidentally source the repo-root .envrc
        # (which contains `use flake` and would recurse under direnv).
        shellHook = ''
          root="$(${pkgs.git}/bin/git rev-parse --show-toplevel 2>/dev/null)"
          if [ -n "$root" ] && [ -f "$root/terraform/.envrc" ]; then
            . "$root/terraform/.envrc"
          fi
        '';
      };
    });
  };
}
