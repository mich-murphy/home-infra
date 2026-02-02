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
  in {
    devShells = forAllSystems ({pkgs}: {
      default = pkgs.mkShell {
        packages = [
          pkgs.terraform
          pkgs.ansible
          pkgs.just
          pkgs._1password-cli
          pkgs.talosctl
          pkgs.kubectl
          pkgs.k9s
          pkgs.kubernetes-helm
          pkgs.alejandra
        ];
      };
    });
  };
}
