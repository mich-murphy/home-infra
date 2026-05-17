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
        # for the 1password Terraform provider) on shell entry so the env var
        # is present regardless of how the shell was launched (direnv, raw
        # `nix develop`, CI, etc.). Looked up relative to $PWD so it works
        # whether entered from the repo root or terraform/.
        shellHook = ''
          for candidate in "$PWD/terraform/.envrc" "$PWD/.envrc" "$PWD/../terraform/.envrc"; do
            if [ -f "$candidate" ]; then
              . "$candidate"
              break
            fi
          done
        '';
      };
    });
  };
}
