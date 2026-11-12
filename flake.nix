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

    # Keep ansible-core and librouteros on one Python interpreter so RouterOS
    # API modules can import their controller-side dependency. Collections are
    # installed from ansible/requirements.yaml.
    ansibleToolingFor = pkgs: let
      python = pkgs.python3;
      ansiblePython = python.withPackages (ps: [
        ps.ansible-core
        ps.librouteros
      ]);
      ansibleLint = pkgs.ansible-lint.override {
        python3Packages = python.pkgs;
        ansible = python.pkgs.ansible-core;
      };
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
      # Reproducible offline validation and proof-cluster tooling. Cluster/chart
      # versions are pinned separately in talos/ and kubernetes/platform/.
      kubectl = pkgs.kubectl;
      kubernetes-helm = pkgs.kubernetes-helm;
      kubeconform = pkgs.kubeconform;
      kubernetes-proof-tools = pkgs.python3.withPackages (ps: [ps.pyyaml]);
      nodejs = pkgs.nodejs;
      # Locked workstation/CI loopback regression tools, not the proof image's
      # runtime. Selecting explicit prefixes prevents silently skipped RPC tests.
      talos-proof-rpc-tools = let
        beam = pkgs.beam.packages.erlang_27;
      in
        pkgs.writeShellScriptBin "talos-proof-rpc-env" ''
          case "$1" in
            otp) printf '%s\n' '${beam.erlang}/lib/erlang' ;;
            elixir) printf '%s\n' '${beam.elixir}/lib/elixir' ;;
            *) exit 2 ;;
          esac
        '';
      # Real PHP filesystem/projection regressions; not proof-image execution.
      talos-proof-php-tools = pkgs.writeShellScriptBin "talos-proof-php-env" ''
        printf '%s\n' '${pkgs.php85}/bin/php'
      '';
      portainer-drift-tools = pkgs.yq-go;
      shellcheck = pkgs.shellcheck;
      terraform-ci = terraformCiFor pkgs;
      # Static Terraform configuration checks read HCL as JSON.
      terraform-config-tools = pkgs.buildEnv {
        name = "terraform-config-tools";
        paths = [
          pkgs.hcl2json
          pkgs.jq
        ];
      };
    });

    devShells = forAllSystems ({
      pkgs,
      system,
    }: {
      default = pkgs.mkShell {
        packages = [
          (terraformFor pkgs)
          self.packages.${system}.terraform-ci
          self.packages.${system}.terraform-config-tools
          # Ansible + librouteros on one interpreter: the community.routeros API
          # modules import librouteros from the controller's python (this shell).
          # The same environment carries ansible-lint to avoid duplicate
          # collection paths and their associated warnings.
          self.packages.${system}.ansible-lint
          self.packages.${system}.portainer-drift-tools
          pkgs.alejandra
          self.packages.${system}.actionlint
          self.packages.${system}.docker-compose
          self.packages.${system}.kubectl
          self.packages.${system}.kubernetes-helm
          self.packages.${system}.kubeconform
          self.packages.${system}.kubernetes-proof-tools
          self.packages.${system}.nodejs
          self.packages.${system}.talos-proof-rpc-tools
          self.packages.${system}.talos-proof-php-tools
          self.packages.${system}.shellcheck
        ];
      };
    });
  };
}
