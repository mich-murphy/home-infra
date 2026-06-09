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
  in {
    packages = forAllSystems ({pkgs, ...}: {
      actionlint = pkgs.actionlint;
      docker-compose = pkgs.docker-compose;
      kubectl = pkgs.kubectl;
      kubeconform = pkgs.kubeconform;
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
          # ansible-core supplies the ansible-playbook CLI (the ansible bundle
          # alone doesn't expose it through withPackages).
          (pkgs.python3.withPackages (ps: [ps.ansible ps.ansible-core ps.librouteros]))
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
