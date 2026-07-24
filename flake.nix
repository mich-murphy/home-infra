{
  description = "Homelab development environment";

  inputs = {
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.2605.1005841";
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
          inherit system;
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

    # GitHub-hosted Ubuntu runners do not allow the user namespace setup that
    # buildFHSEnv uses, but CI only needs Terraform init/validate on glibc Linux.
    terraformCiFor = pkgs:
      pkgs.writeShellScriptBin "terraform-ci" ''
        exec ${pkgs.terraform}/bin/terraform "$@"
      '';

    # Keep ansible-core and ansible-lint on one Python interpreter so their
    # module paths cannot shadow one another. Collections are installed from
    # ansible/requirements.yaml; including the full `ansible` distribution
    # here would add a second, unrelated collection tree. pathspec 1.x renamed
    # its gitwildmatch API, so patch the two pinned lint dependencies that
    # still use the deprecated spelling.
    ansibleToolingFor = pkgs: let
      python = pkgs.python3.override {
        packageOverrides = _pythonFinal: pythonPrev: {
          black = pythonPrev.black.overridePythonAttrs (old: {
            postPatch =
              (old.postPatch or "")
              + ''
                substituteInPlace src/black/__init__.py src/black/files.py \
                  --replace-fail "pathspec.patterns.gitwildmatch" "pathspec.patterns.gitignore" \
                  --replace-fail "GitWildMatchPatternError" "GitIgnorePatternError"
                substituteInPlace src/black/files.py \
                  --replace-fail '"gitwildmatch"' '"gitignore"'
              '';
          });
          yamllint = pythonPrev.yamllint.overridePythonAttrs (old: {
            postPatch =
              (old.postPatch or "")
              + ''
                substituteInPlace yamllint/config.py \
                  --replace-fail "'gitwildmatch'" "'gitignore'"
              '';
          });
        };
      };
      ansiblePython = python.withPackages (ps: [
        ps.ansible-core
        ps.librouteros
      ]);
      ansibleLint =
        (pkgs.ansible-lint.override {
          python3Packages = python.pkgs;
          ansible = python.pkgs.ansible-core;
        }).overridePythonAttrs (old: {
          postPatch =
            (old.postPatch or "")
            + ''
              substituteInPlace src/ansiblelint/utils.py \
                --replace-fail \
                  "from ansible.module_utils._text import to_bytes" \
                  "from ansible.module_utils.common.text.converters import to_bytes"
            '';
        });
    in
      pkgs.buildEnv {
        name = "ansible-tooling";
        paths = [
          ansiblePython
          ansibleLint
        ];
      };
  in {
    packages = forAllSystems ({pkgs, ...}: {
      actionlint = pkgs.actionlint;
      ansible-lint = ansibleToolingFor pkgs;
      docker-compose = pkgs.docker-compose;
      kubectl = pkgs.kubectl;
      kubeconform = pkgs.kubeconform;
      talosctl = pkgs.talosctl;
      terraform-ci = terraformCiFor pkgs;
      yq-go = pkgs.yq-go;
    });

    devShells = forAllSystems ({
      pkgs,
      system,
    }: {
      default = pkgs.mkShell {
        packages = [
          (terraformFor pkgs)
          self.packages.${system}.terraform-ci
          # Ansible + librouteros on one interpreter: the community.routeros API
          # modules import librouteros from the controller's python (this shell).
          # The same environment carries ansible-lint to avoid duplicate
          # collection paths and their associated warnings.
          self.packages.${system}.ansible-lint
          pkgs.just
          pkgs.talosctl
          pkgs.kubectl
          pkgs.k9s
          pkgs.fluxcd
          pkgs.kubernetes-helm
          pkgs.alejandra
          self.packages.${system}.actionlint
          self.packages.${system}.docker-compose
          self.packages.${system}.kubeconform
          self.packages.${system}.yq-go
        ];
      };
    });
  };
}
